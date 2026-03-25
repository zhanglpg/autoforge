"""
Complexity-accounting metric adapter.

Wraps the complexity-accounting tool (code-complexity-measure) to provide
Net Complexity Score (NCS) measurements through the standard MetricAdapter
interface.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime

from autoforge.adapters.base import BaseMetricAdapter
from autoforge.models import Direction, MetricResult

logger = logging.getLogger(__name__)


class ComplexityAdapter(BaseMetricAdapter):
    """Metric adapter for complexity-accounting (NCS measurement)."""

    name = "complexity"
    supported_languages = ["python", "go", "java", "javascript", "typescript", "rust", "cpp"]

    def __init__(
        self,
        *,
        no_churn: bool = True,
        no_coupling: bool = False,
        no_duplication: bool = False,
        ncs_model: str = "multiplicative",
        threshold: int | None = None,
        include_tests: bool = False,
    ):
        self.no_churn = no_churn
        self.no_coupling = no_coupling
        self.no_duplication = no_duplication
        self.ncs_model = ncs_model
        self.threshold = threshold
        self.include_tests = include_tests

    def check_prerequisites(self, repo_path: str) -> bool:
        """Check that complexity-accounting is importable."""
        try:
            import complexity_accounting  # noqa: F401
            return True
        except ImportError:
            logger.warning(
                "complexity-accounting not installed. "
                "Install with: pip install complexity-accounting"
            )
            return False

    def _build_command(self, target_path: str) -> list[str]:
        """Build the complexity-accounting scan command."""
        cmd = [
            sys.executable, "-m", "complexity_accounting",
            "scan", target_path,
            "--format", "json",
            "--ncs-model", self.ncs_model,
        ]
        if self.no_churn:
            cmd.append("--no-churn")
        if self.no_coupling:
            cmd.append("--no-coupling")
        if self.no_duplication:
            cmd.append("--no-duplication")
        if self.threshold is not None:
            cmd.extend(["--threshold", str(self.threshold)])
        if self.include_tests:
            cmd.append("--include-tests")
        return cmd

    def measure(self, repo_path: str, target_path: str) -> MetricResult:
        """Run complexity-accounting scan and return NCS as MetricResult."""
        cmd = self._build_command(target_path)
        logger.info("Running: %s", " ".join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"complexity-accounting scan failed (exit {result.returncode}):\n"
                f"{result.stderr}"
            )

        data = json.loads(result.stdout)
        summary = data.get("summary", {})
        ncs = summary.get("net_complexity_score", 0.0)

        breakdown: dict[str, float] = {}
        for file_info in data.get("files", []):
            path = file_info.get("path", "")
            avg_cog = file_info.get("avg_cognitive", 0.0)
            breakdown[path] = avg_cog

        return MetricResult(
            metric_name="net_complexity_score",
            value=ncs,
            unit="score",
            direction=Direction.MINIMIZE,
            breakdown=breakdown,
            tool="complexity-accounting",
            timestamp=datetime.utcnow().isoformat(),
        )

    def identify_targets(self, result: MetricResult, n: int) -> list[str]:
        """Return top-n files with highest average cognitive complexity."""
        sorted_files = sorted(
            result.breakdown.items(),
            key=lambda kv: kv[1],
            reverse=True,
        )
        return [path for path, _ in sorted_files[:n]]
