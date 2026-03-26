"""
Reporting module for AutoForge.

All serialization and presentation logic lives here — models.py contains
only pure data. This module generates JSON reports, markdown summaries,
and health-check dashboards.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from autoforge.models import Direction, MetricResult, RunReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RunReport serialization
# ---------------------------------------------------------------------------

def report_to_dict(report: RunReport) -> dict:
    """Serialize a RunReport to a JSON-compatible dictionary."""
    return {
        "workflow": report.workflow,
        "target": report.target,
        "iterations": [
            {
                "n": it.n,
                "metric_before": it.metric_before,
                "metric_after": it.metric_after,
                "files_modified": it.files_modified,
                "constraint_violations": it.constraint_violations,
                "tokens_used": it.tokens_used,
                "duration_seconds": round(it.duration_seconds, 2),
                "commit_sha": it.commit_sha,
                "error": it.error,
            }
            for it in report.iterations
        ],
        "outcome": report.outcome.value,
        "initial_metric": report.initial_metric,
        "final_metric": report.final_metric,
        "total_tokens": report.total_tokens,
        "total_duration_seconds": round(report.total_duration_seconds, 2),
        "branch": report.branch,
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "error": report.error,
    }


def report_to_markdown(report: RunReport) -> str:
    """Generate a human-readable markdown summary of a RunReport."""
    lines = [
        f"# AutoForge Run Report: {report.workflow}",
        "",
        f"**Outcome:** {report.outcome.value}",
        f"**Branch:** `{report.branch}`",
        f"**Started:** {report.started_at}",
        f"**Finished:** {report.finished_at}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Initial | {report.initial_metric} |",
        f"| Final | {report.final_metric} |",
        f"| Target | {report.target} |",
        f"| Improvement | {abs(report.initial_metric - report.final_metric):.2f} |",
        "",
        "## Iterations",
        "",
        "| # | Before | After | Files | Tokens | Duration |",
        "|---|--------|-------|-------|--------|----------|",
    ]
    for it in report.iterations:
        files_str = ", ".join(it.files_modified[:3])
        if len(it.files_modified) > 3:
            files_str += f" (+{len(it.files_modified) - 3})"
        lines.append(
            f"| {it.n} | {it.metric_before} | {it.metric_after} "
            f"| {files_str} | {it.tokens_used} | {it.duration_seconds:.1f}s |"
        )

    lines.extend([
        "",
        "## Summary",
        "",
        f"- **Total iterations:** {len(report.iterations)}",
        f"- **Total tokens:** {report.total_tokens}",
        f"- **Total duration:** {report.total_duration_seconds:.1f}s",
    ])

    if report.error:
        lines.extend(["", f"**Error:** {report.error}"])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def save_run_report(report: RunReport, output_dir: str) -> tuple[str, str]:
    """
    Save a run report as both JSON and Markdown files.
    Returns (json_path, markdown_path).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base_name = f"autoforge-{report.workflow}-{timestamp}"

    json_path = out / f"{base_name}.json"
    md_path = out / f"{base_name}.md"

    json_path.write_text(json.dumps(report_to_dict(report), indent=2) + "\n")
    logger.info("Saved JSON report: %s", json_path)

    md_path.write_text(report_to_markdown(report) + "\n")
    logger.info("Saved Markdown report: %s", md_path)

    return str(json_path), str(md_path)


# ---------------------------------------------------------------------------
# Health dashboard
# ---------------------------------------------------------------------------

def format_health_dashboard(metrics: dict[str, MetricResult]) -> str:
    """
    Generate a health dashboard from multiple metric results.
    Returns a formatted string suitable for console or PR comment.
    """
    lines = [
        "# AutoForge Codebase Health Report",
        "",
        f"*Generated: {datetime.now(timezone.utc).isoformat()}*",
        "",
        "| Metric | Value | Unit | Status |",
        "|--------|-------|------|--------|",
    ]

    for name, result in sorted(metrics.items()):
        status = _health_status(name, result)
        lines.append(
            f"| {name} | {result.value:.2f} | {result.unit} | {status} |"
        )

    lines.extend(["", "## Per-File Breakdown", ""])

    for name, result in sorted(metrics.items()):
        if result.breakdown:
            lines.append(f"### {name}")
            lines.append("")
            lines.append("| File | Value |")
            lines.append("|------|-------|")
            sorted_files = sorted(
                result.breakdown.items(),
                key=lambda kv: kv[1],
                reverse=(result.direction is Direction.MINIMIZE),
            )
            for path, value in sorted_files[:10]:
                lines.append(f"| `{path}` | {value:.2f} |")
            if len(result.breakdown) > 10:
                lines.append(f"| ... | ({len(result.breakdown) - 10} more files) |")
            lines.append("")

    return "\n".join(lines)


def _health_status(name: str, result: MetricResult) -> str:
    """Determine health status indicator for a metric."""
    if result.metric_name == "net_complexity_score":
        if result.value <= 3:
            return "Healthy"
        elif result.value <= 6:
            return "Moderate"
        elif result.value <= 10:
            return "Concerning"
        else:
            return "Critical"

    if result.direction is Direction.MAXIMIZE:
        if result.value >= 80:
            return "Healthy"
        elif result.value >= 60:
            return "Moderate"
        elif result.value >= 40:
            return "Concerning"
        else:
            return "Critical"

    if result.direction is Direction.MINIMIZE:
        if result.value <= 0:
            return "Healthy"
        elif result.value <= 5:
            return "Moderate"
        elif result.value <= 20:
            return "Concerning"
        else:
            return "Critical"

    return "Unknown"
