"""
Regression Guard for AutoForge.

The "do no harm" gate: runs tests and checks constraint metrics between
iterations to ensure changes don't break things or degrade other metrics.
"""

from __future__ import annotations

import logging
import subprocess
import sys

from autoforge.models import MetricAdapter, MetricResult

logger = logging.getLogger(__name__)


class RegressionViolation(Exception):
    """Raised when a regression is detected."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class RegressionGuard:
    """Validates that changes don't introduce regressions."""

    def __init__(
        self,
        repo_path: str,
        test_command: str | None = None,
    ):
        self.repo_path = repo_path
        self.test_command = test_command
        self._constraint_baselines: dict[str, MetricResult] = {}

    def set_constraint_baseline(self, name: str, result: MetricResult) -> None:
        """Record a baseline measurement for a constraint metric."""
        self._constraint_baselines[name] = result

    def run_tests(self) -> tuple[bool, str]:
        """Run the test suite. Returns (passed, output)."""
        if not self.test_command:
            # Auto-detect test command
            cmd = self._detect_test_command()
            if not cmd:
                logger.info("No test command found, skipping test validation")
                return True, "No tests configured"
        else:
            cmd = self.test_command

        logger.info("Running tests: %s", cmd)
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=self.repo_path,
            timeout=600,
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0

        if not passed:
            logger.warning("Tests failed (exit %d)", result.returncode)
        else:
            logger.info("Tests passed")

        return passed, output

    def _detect_test_command(self) -> str | None:
        """Auto-detect the test command for this repo."""
        from pathlib import Path

        repo = Path(self.repo_path)

        # Python: pytest
        if (repo / "pyproject.toml").exists() or (repo / "setup.py").exists():
            return f"{sys.executable} -m pytest -x -q"

        # Node.js: npm test
        if (repo / "package.json").exists():
            return "npm test"

        # Go
        if (repo / "go.mod").exists():
            return "go test ./..."

        # Rust
        if (repo / "Cargo.toml").exists():
            return "cargo test"

        return None

    def check_constraints(
        self,
        adapter: MetricAdapter,
        repo_path: str,
        target_path: str,
        tolerance_map: dict[str, float],
    ) -> list[str]:
        """
        Check constraint metrics against baselines.
        Returns list of violation descriptions (empty = all good).
        """
        violations = []

        for name, baseline in self._constraint_baselines.items():
            tolerance = tolerance_map.get(name, 10.0)
            try:
                current = adapter.measure(repo_path, target_path)
                if current.degraded_beyond(baseline, tolerance):
                    msg = (
                        f"Constraint '{name}' violated: "
                        f"{baseline.value} -> {current.value} "
                        f"(tolerance: {tolerance}%)"
                    )
                    violations.append(msg)
                    logger.warning(msg)
            except Exception as e:
                logger.warning("Failed to check constraint '%s': %s", name, e)

        return violations

    def validate_iteration(
        self,
        run_tests: bool = True,
    ) -> tuple[bool, list[str]]:
        """
        Full validation after an iteration.
        Returns (passed, list of issues).
        """
        issues = []

        if run_tests:
            passed, output = self.run_tests()
            if not passed:
                issues.append(f"Tests failed:\n{output[-500:]}")

        return len(issues) == 0, issues
