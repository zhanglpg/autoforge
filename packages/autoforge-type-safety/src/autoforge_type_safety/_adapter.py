"""
Type Safety metric adapter for AutoForge.

Wraps pyright or mypy to measure type error count per file through the
standard MetricAdapter interface.

Architecture:
- Frozen dataclasses for intermediate results
- Module-level pure functions for parsing tool output
- TypeSafetyAdapter class as thin orchestrator
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from autoforge.adapters.base import BaseMetricAdapter
from autoforge.models import Direction, MetricResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TypeDiagnostic:
    """A single type error diagnostic from pyright or mypy."""

    file_path: str
    line: int
    column: int
    severity: str  # "error", "warning", "information"
    message: str
    rule: str  # e.g. "reportAssignmentType", "reportMissingImports"


@dataclass(frozen=True)
class FileTypeResult:
    """Type checking results for a single file."""

    file_path: str
    error_count: int
    warning_count: int
    info_count: int
    diagnostics: tuple[TypeDiagnostic, ...]


@dataclass(frozen=True)
class TypeCheckSummary:
    """Aggregate type check results across all files."""

    total_errors: int
    total_warnings: int
    total_files_checked: int
    files_with_errors: int
    file_results: dict[str, FileTypeResult]
    tool: str


# ---------------------------------------------------------------------------
# Pure parsing functions
# ---------------------------------------------------------------------------


def parse_pyright_json(raw: dict) -> TypeCheckSummary:
    """Parse the JSON output of ``pyright --outputjson``.

    Pyright JSON schema (v1.1+):
      - generalDiagnostics: list of {file, severity, message, range, rule}
      - summary: {filesAnalyzed, errorCount, warningCount, informationCount}
      - severity is a string: "error", "warning", or "information"
    """
    diagnostics_by_file: dict[str, list[TypeDiagnostic]] = {}

    for diag in raw.get("generalDiagnostics", []):
        file_path = diag.get("file", "")
        severity = diag.get("severity", "error")
        rng = diag.get("range", {})
        start = rng.get("start", {})

        td = TypeDiagnostic(
            file_path=file_path,
            line=start.get("line", 0),
            column=start.get("character", 0),
            severity=severity,
            message=diag.get("message", ""),
            rule=diag.get("rule", ""),
        )
        diagnostics_by_file.setdefault(file_path, []).append(td)

    summary = raw.get("summary", {})
    total_files = summary.get("filesAnalyzed", 0)

    file_results: dict[str, FileTypeResult] = {}
    total_errors = 0
    total_warnings = 0

    for fpath, diags in diagnostics_by_file.items():
        errors = sum(1 for d in diags if d.severity == "error")
        warnings = sum(1 for d in diags if d.severity == "warning")
        infos = sum(1 for d in diags if d.severity == "information")
        total_errors += errors
        total_warnings += warnings
        file_results[fpath] = FileTypeResult(
            file_path=fpath,
            error_count=errors,
            warning_count=warnings,
            info_count=infos,
            diagnostics=tuple(diags),
        )

    return TypeCheckSummary(
        total_errors=total_errors,
        total_warnings=total_warnings,
        total_files_checked=total_files,
        files_with_errors=len([f for f in file_results.values() if f.error_count > 0]),
        file_results=file_results,
        tool="pyright",
    )


def parse_mypy_json(output: str) -> TypeCheckSummary:
    """Parse mypy ``--output=json`` output (one JSON object per line).

    Each line: {"file", "line", "column", "severity", "message", "code"}
    Requires mypy >= 1.7.
    """
    diagnostics_by_file: dict[str, list[TypeDiagnostic]] = {}

    for line in output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            diag = json.loads(line)
        except json.JSONDecodeError:
            continue

        file_path = diag.get("file", "")
        severity = diag.get("severity", "error")

        td = TypeDiagnostic(
            file_path=file_path,
            line=diag.get("line", 0),
            column=diag.get("column", 0),
            severity=severity,
            message=diag.get("message", ""),
            rule=diag.get("code", ""),
        )
        diagnostics_by_file.setdefault(file_path, []).append(td)

    file_results: dict[str, FileTypeResult] = {}
    total_errors = 0
    total_warnings = 0

    for fpath, diags in diagnostics_by_file.items():
        errors = sum(1 for d in diags if d.severity == "error")
        warnings = sum(1 for d in diags if d.severity in ("warning", "note"))
        infos = sum(1 for d in diags if d.severity not in ("error", "warning", "note"))
        total_errors += errors
        total_warnings += warnings
        file_results[fpath] = FileTypeResult(
            file_path=fpath,
            error_count=errors,
            warning_count=warnings,
            info_count=infos,
            diagnostics=tuple(diags),
        )

    return TypeCheckSummary(
        total_errors=total_errors,
        total_warnings=total_warnings,
        total_files_checked=len(file_results),
        files_with_errors=len([f for f in file_results.values() if f.error_count > 0]),
        file_results=file_results,
        tool="mypy",
    )


def build_metric_result(summary: TypeCheckSummary) -> MetricResult:
    """Convert a TypeCheckSummary into the standard MetricResult."""
    breakdown: dict[str, float] = {}
    for fpath, fr in summary.file_results.items():
        if fr.error_count > 0:
            breakdown[fpath] = float(fr.error_count)

    return MetricResult(
        metric_name="type_error_count",
        value=float(summary.total_errors),
        unit="count",
        direction=Direction.MINIMIZE,
        breakdown=breakdown,
        tool=summary.tool,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def normalize_paths(summary: TypeCheckSummary, base_path: str) -> TypeCheckSummary:
    """Normalize absolute file paths in summary to be relative to base_path."""
    base = Path(base_path).resolve()
    new_results: dict[str, FileTypeResult] = {}

    for fpath, fr in summary.file_results.items():
        try:
            rel = str(Path(fpath).resolve().relative_to(base))
        except ValueError:
            rel = fpath

        new_diags = tuple(
            TypeDiagnostic(
                file_path=rel,
                line=d.line,
                column=d.column,
                severity=d.severity,
                message=d.message,
                rule=d.rule,
            )
            for d in fr.diagnostics
        )
        new_results[rel] = FileTypeResult(
            file_path=rel,
            error_count=fr.error_count,
            warning_count=fr.warning_count,
            info_count=fr.info_count,
            diagnostics=new_diags,
        )

    return TypeCheckSummary(
        total_errors=summary.total_errors,
        total_warnings=summary.total_warnings,
        total_files_checked=summary.total_files_checked,
        files_with_errors=summary.files_with_errors,
        file_results=new_results,
        tool=summary.tool,
    )


# ---------------------------------------------------------------------------
# Adapter class
# ---------------------------------------------------------------------------


class TypeSafetyAdapter(BaseMetricAdapter):
    """Measures type error count using pyright or mypy."""

    name = "type_safety"
    supported_languages = ["python"]

    def __init__(
        self,
        *,
        tool: str = "pyright",
        typechecking_mode: str = "basic",
        extra_args: list[str] | None = None,
        timeout: int = 300,
    ) -> None:
        self.tool = tool
        self.typechecking_mode = typechecking_mode
        self.extra_args = extra_args or []
        self.timeout = timeout
        self._detailed_results: TypeCheckSummary | None = None

    def check_prerequisites(self, repo_path: str) -> bool:
        """Verify that pyright or mypy is available on PATH."""
        if not self.check_tool_available(self.tool):
            logger.warning(
                "%s not found on PATH. Install with: %s",
                self.tool,
                "npm install -g pyright" if self.tool == "pyright" else "pip install mypy",
            )
            return False
        return True

    def _build_command(self, target_path: str) -> list[str]:
        """Build the subprocess command for the configured tool."""
        if self.tool == "pyright":
            cmd = [
                "pyright",
                "--outputjson",
                "--pythonpath",
                sys.executable,
            ]
            cmd.extend(self.extra_args)
            cmd.append(target_path)
            return cmd

        # mypy
        cmd = [
            "mypy",
            "--output=json",
            "--no-error-summary",
        ]
        cmd.extend(self.extra_args)
        cmd.append(target_path)
        return cmd

    def measure(self, repo_path: str, target_path: str) -> MetricResult:
        """Run type checker and return error count as MetricResult."""
        cmd = self._build_command(target_path)
        logger.info("Running: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"{self.tool} timed out after {self.timeout}s on {target_path}"
            )

        # pyright: exit 0 = no errors, exit 1 = errors found (normal), exit >= 2 = crash
        # mypy: exit 0 = no errors, exit 1 = errors found (normal), exit 2 = fatal
        if self.tool == "pyright":
            if result.returncode >= 2:
                raise RuntimeError(
                    f"pyright crashed (exit {result.returncode}): {result.stderr}"
                )
            if not result.stdout.strip():
                raise RuntimeError(
                    f"pyright produced no output (exit {result.returncode}): {result.stderr}"
                )
            try:
                raw = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Failed to parse pyright JSON output: {e}")
            summary = parse_pyright_json(raw)
        else:
            if result.returncode >= 2:
                raise RuntimeError(
                    f"mypy fatal error (exit {result.returncode}): {result.stderr}"
                )
            summary = parse_mypy_json(result.stdout)

        # Normalize paths relative to target_path
        summary = normalize_paths(summary, target_path)
        self._detailed_results = summary

        return build_metric_result(summary)

    def identify_targets(self, result: MetricResult, n: int) -> list[str]:
        """Return top-n files with most type errors (worst first)."""
        sorted_files = sorted(
            result.breakdown.items(),
            key=lambda kv: kv[1],
            reverse=True,  # Most errors first (MINIMIZE direction)
        )
        return [path for path, _ in sorted_files[:n]]
