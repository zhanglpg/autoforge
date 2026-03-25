"""
Reporting module for AutoForge.

Generates JSON reports and markdown summaries from workflow runs.
Also supports health-check dashboards across multiple metrics.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from autoforge.models import MetricResult, RunReport

logger = logging.getLogger(__name__)


def save_run_report(report: RunReport, output_dir: str) -> tuple[str, str]:
    """
    Save a run report as both JSON and Markdown files.
    Returns (json_path, markdown_path).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    base_name = f"autoforge-{report.workflow}-{timestamp}"

    json_path = out / f"{base_name}.json"
    md_path = out / f"{base_name}.md"

    # JSON report
    json_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n")
    logger.info("Saved JSON report: %s", json_path)

    # Markdown report
    md_path.write_text(report.to_markdown() + "\n")
    logger.info("Saved Markdown report: %s", md_path)

    return str(json_path), str(md_path)


def format_health_dashboard(metrics: dict[str, MetricResult]) -> str:
    """
    Generate a health dashboard from multiple metric results.

    Returns a formatted string suitable for console or PR comment.
    """
    lines = [
        "# AutoForge Codebase Health Report",
        "",
        f"*Generated: {datetime.utcnow().isoformat()}*",
        "",
        "| Metric | Value | Unit | Status |",
        "|--------|-------|------|--------|",
    ]

    for name, result in sorted(metrics.items()):
        status = _health_status(name, result)
        lines.append(
            f"| {name} | {result.value:.2f} | {result.unit} | {status} |"
        )

    lines.extend([
        "",
        "## Per-File Breakdown",
        "",
    ])

    for name, result in sorted(metrics.items()):
        if result.breakdown:
            lines.append(f"### {name}")
            lines.append("")
            lines.append("| File | Value |")
            lines.append("|------|-------|")
            sorted_files = sorted(
                result.breakdown.items(),
                key=lambda kv: kv[1],
                reverse=(result.direction == "minimize"),
            )
            for path, value in sorted_files[:10]:
                lines.append(f"| `{path}` | {value:.2f} |")
            if len(result.breakdown) > 10:
                lines.append(f"| ... | ({len(result.breakdown) - 10} more files) |")
            lines.append("")

    return "\n".join(lines)


def _health_status(name: str, result: MetricResult) -> str:
    """Determine health status indicator for a metric."""
    # NCS-specific thresholds
    if result.metric_name == "net_complexity_score":
        if result.value <= 3:
            return "Healthy"
        elif result.value <= 6:
            return "Moderate"
        elif result.value <= 10:
            return "Concerning"
        else:
            return "Critical"

    # Coverage-like metrics (higher is better)
    if result.direction == "maximize":
        if result.value >= 80:
            return "Healthy"
        elif result.value >= 60:
            return "Moderate"
        elif result.value >= 40:
            return "Concerning"
        else:
            return "Critical"

    # Count-like metrics (lower is better)
    if result.direction == "minimize":
        if result.value <= 0:
            return "Healthy"
        elif result.value <= 5:
            return "Moderate"
        elif result.value <= 20:
            return "Concerning"
        else:
            return "Critical"

    return "Unknown"
