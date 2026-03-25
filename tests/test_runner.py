"""Tests for autoforge.runner."""

import tempfile
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from autoforge.adapters.complexity import ComplexityAdapter
from autoforge.models import (
    BudgetConfig,
    MetricResult,
    PrimaryMetricConfig,
    RunOutcome,
    WorkflowConfig,
)
from autoforge.runner import WorkflowRunner


def _make_config(**overrides):
    defaults = dict(
        name="test_workflow",
        primary_metric=PrimaryMetricConfig(
            name="net_complexity_score",
            direction="minimize",
            default_target=3.0,
        ),
        budget=BudgetConfig(
            max_iterations=3,
            max_tokens=100000,
            max_wall_clock_minutes=5,
            stall_patience=2,
            min_improvement_percent=0.5,
        ),
    )
    defaults.update(overrides)
    return WorkflowConfig(**defaults)


def _make_metric(value):
    return MetricResult(
        metric_name="net_complexity_score",
        value=value,
        unit="score",
        direction="minimize",
    )


class TestWorkflowRunner:
    def test_target_already_met(self):
        """When baseline already meets target, no iterations should run."""
        adapter = MagicMock()
        adapter.measure.return_value = _make_metric(2.0)

        config = _make_config()
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = WorkflowRunner(
                config=config,
                adapter=adapter,
                repo_path=tmpdir,
                target_path=tmpdir,
                target_value=3.0,
                skip_git=True,
                skip_tests=True,
                dry_run=True,
            )
            report = runner.run()

        assert report.outcome == RunOutcome.TARGET_MET
        assert report.initial_metric == 2.0
        assert len(report.iterations) == 0

    def test_dry_run_stall(self):
        """Dry run should detect stall when improvement is negligible."""
        call_count = 0

        def mock_measure(repo_path, target_path):
            nonlocal call_count
            call_count += 1
            # Barely improving: stall_patience=2 triggers after 2 weak iterations
            values = [8.0, 7.99, 7.98, 7.97, 7.96]
            idx = min(call_count - 1, len(values) - 1)
            return _make_metric(values[idx])

        adapter = MagicMock()
        adapter.measure.side_effect = mock_measure

        config = _make_config(
            budget=BudgetConfig(
                max_iterations=10,
                stall_patience=2,
                min_improvement_percent=0.5,
            ),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = WorkflowRunner(
                config=config,
                adapter=adapter,
                repo_path=tmpdir,
                target_path=tmpdir,
                target_value=3.0,
                skip_git=True,
                skip_tests=True,
                dry_run=True,
            )
            report = runner.run()

        assert report.outcome == RunOutcome.STALLED
        assert report.initial_metric == 8.0
        assert len(report.iterations) >= 2

    def test_budget_exhausted(self):
        """Should stop when max iterations reached."""
        call_count = 0

        def mock_measure(repo_path, target_path):
            nonlocal call_count
            call_count += 1
            # Always improving so no stall, but never reaching target
            return _make_metric(max(10.0 - call_count * 2.0, 4.0))

        adapter = MagicMock()
        adapter.measure.side_effect = mock_measure
        adapter.identify_targets.return_value = []

        config = _make_config(
            budget=BudgetConfig(max_iterations=2, stall_patience=10),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = WorkflowRunner(
                config=config,
                adapter=adapter,
                repo_path=tmpdir,
                target_path=tmpdir,
                target_value=1.0,
                skip_git=True,
                skip_tests=True,
                dry_run=True,
            )
            report = runner.run()

        assert report.outcome == RunOutcome.BUDGET_EXHAUSTED
        assert len(report.iterations) == 2


class TestCLIDryRun:
    def test_cli_health_json(self):
        """Smoke test: autoforge health --format json on a Python file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple Python file
            (Path(tmpdir) / "example.py").write_text(
                "def hello():\n    return 'world'\n"
            )
            result = subprocess.run(
                ["autoforge", "health", "--path", tmpdir, "--repo", tmpdir, "--format", "json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0
            import json
            data = json.loads(result.stdout)
            assert "complexity" in data
