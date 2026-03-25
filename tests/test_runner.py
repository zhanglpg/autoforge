"""Tests for autoforge.runner — WorkflowRunner iteration loop."""

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autoforge.models import (
    AgentConfig,
    BudgetConfig,
    Direction,
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
            direction=Direction.MINIMIZE,
            default_target=3.0,
        ),
        budget=BudgetConfig(
            max_iterations=5,
            max_tokens=100000,
            max_wall_clock_minutes=10,
            stall_patience=3,
            min_improvement_percent=0.5,
        ),
        agent=AgentConfig(skill="test-skill", system_prompt_addendum="Be careful."),
    )
    defaults.update(overrides)
    return WorkflowConfig(**defaults)


def _make_metric(value, direction=Direction.MINIMIZE):
    return MetricResult(
        metric_name="net_complexity_score",
        value=value,
        unit="score",
        direction=direction,
        breakdown={"a.py": value * 0.6, "b.py": value * 0.4},
    )


class TestTargetAlreadyMet:
    def test_minimize_already_below_target(self):
        adapter = MagicMock()
        adapter.measure.return_value = _make_metric(2.0)

        with tempfile.TemporaryDirectory() as d:
            runner = WorkflowRunner(
                config=_make_config(),
                adapter=adapter,
                repo_path=d, target_path=d,
                target_value=3.0,
                skip_git=True, skip_tests=True, dry_run=True,
            )
            report = runner.run()

        assert report.outcome == RunOutcome.TARGET_MET
        assert report.initial_metric == 2.0
        assert report.final_metric == 2.0
        assert len(report.iterations) == 0
        adapter.measure.assert_called_once()

    def test_maximize_already_above_target(self):
        adapter = MagicMock()
        adapter.measure.return_value = MetricResult(
            metric_name="coverage", value=90.0, unit="percent", direction=Direction.MAXIMIZE,
        )
        config = _make_config(
            primary_metric=PrimaryMetricConfig(name="coverage", direction=Direction.MAXIMIZE, default_target=80.0),
        )
        with tempfile.TemporaryDirectory() as d:
            runner = WorkflowRunner(
                config=config, adapter=adapter,
                repo_path=d, target_path=d,
                target_value=80.0,
                skip_git=True, skip_tests=True, dry_run=True,
            )
            report = runner.run()
        assert report.outcome == RunOutcome.TARGET_MET


class TestStallDetection:
    def test_stall_after_negligible_improvement(self):
        call_count = 0

        def mock_measure(repo_path, target_path):
            nonlocal call_count
            call_count += 1
            # Barely improving: stall should trigger
            values = [8.0, 7.99, 7.98, 7.97, 7.96, 7.95]
            idx = min(call_count - 1, len(values) - 1)
            return _make_metric(values[idx])

        adapter = MagicMock()
        adapter.measure.side_effect = mock_measure

        config = _make_config(
            budget=BudgetConfig(
                max_iterations=10, stall_patience=3, min_improvement_percent=0.5,
            ),
        )
        with tempfile.TemporaryDirectory() as d:
            runner = WorkflowRunner(
                config=config, adapter=adapter,
                repo_path=d, target_path=d,
                target_value=3.0,
                skip_git=True, skip_tests=True, dry_run=True,
            )
            report = runner.run()

        assert report.outcome == RunOutcome.STALLED
        assert report.initial_metric == 8.0
        assert len(report.iterations) >= 3


class TestBudgetExhaustion:
    def test_stops_at_max_iterations(self):
        call_count = 0

        def mock_measure(repo_path, target_path):
            nonlocal call_count
            call_count += 1
            return _make_metric(max(10.0 - call_count * 1.5, 4.0))

        adapter = MagicMock()
        adapter.measure.side_effect = mock_measure
        adapter.identify_targets.return_value = []

        config = _make_config(
            budget=BudgetConfig(max_iterations=3, stall_patience=100),
        )
        with tempfile.TemporaryDirectory() as d:
            runner = WorkflowRunner(
                config=config, adapter=adapter,
                repo_path=d, target_path=d,
                target_value=1.0,
                skip_git=True, skip_tests=True, dry_run=True,
            )
            report = runner.run()

        assert report.outcome == RunOutcome.BUDGET_EXHAUSTED
        assert len(report.iterations) == 3


class TestTargetReached:
    def test_reaches_target_during_iterations(self):
        call_count = 0

        def mock_measure(repo_path, target_path):
            nonlocal call_count
            call_count += 1
            values = [10.0, 6.0, 2.5]
            idx = min(call_count - 1, len(values) - 1)
            return _make_metric(values[idx])

        adapter = MagicMock()
        adapter.measure.side_effect = mock_measure

        config = _make_config(budget=BudgetConfig(max_iterations=10, stall_patience=10))
        with tempfile.TemporaryDirectory() as d:
            runner = WorkflowRunner(
                config=config, adapter=adapter,
                repo_path=d, target_path=d,
                target_value=3.0,
                skip_git=True, skip_tests=True, dry_run=True,
            )
            report = runner.run()

        assert report.outcome == RunOutcome.TARGET_MET
        assert report.final_metric == 2.5
        assert len(report.iterations) == 2


class TestErrorHandling:
    def test_measurement_error_in_iteration(self):
        call_count = 0

        def mock_measure(repo_path, target_path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_metric(10.0)  # baseline ok
            elif call_count == 2:
                return _make_metric(8.0)  # iter 1 ok
            else:
                raise RuntimeError("tool crashed")

        adapter = MagicMock()
        adapter.measure.side_effect = mock_measure

        config = _make_config(budget=BudgetConfig(max_iterations=3, stall_patience=10))
        with tempfile.TemporaryDirectory() as d:
            runner = WorkflowRunner(
                config=config, adapter=adapter,
                repo_path=d, target_path=d,
                target_value=1.0,
                skip_git=True, skip_tests=True, dry_run=True,
            )
            report = runner.run()

        # Iteration 1 succeeds, iteration 2 errors, iteration 3 errors, then budget
        assert len(report.iterations) >= 2
        error_iters = [it for it in report.iterations if it.error]
        assert len(error_iters) >= 1
        assert "tool crashed" in error_iters[0].error

    def test_baseline_error(self):
        adapter = MagicMock()
        adapter.measure.side_effect = RuntimeError("cannot measure")

        with tempfile.TemporaryDirectory() as d:
            runner = WorkflowRunner(
                config=_make_config(),
                adapter=adapter,
                repo_path=d, target_path=d,
                skip_git=True, skip_tests=True, dry_run=True,
            )
            report = runner.run()

        assert report.outcome == RunOutcome.ERROR
        assert "cannot measure" in report.error


class TestImprovementCalculation:
    def test_zero_baseline_value(self):
        call_count = 0

        def mock_measure(repo_path, target_path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_metric(0.0)  # baseline = 0, target not met (direction=minimize, target=-1)
            return _make_metric(0.0)

        adapter = MagicMock()
        adapter.measure.side_effect = mock_measure

        config = _make_config(budget=BudgetConfig(max_iterations=1))
        with tempfile.TemporaryDirectory() as d:
            runner = WorkflowRunner(
                config=config, adapter=adapter,
                repo_path=d, target_path=d,
                target_value=-1.0,  # can't reach
                skip_git=True, skip_tests=True, dry_run=True,
            )
            report = runner.run()

        # Should handle 0/0 gracefully
        assert report.outcome == RunOutcome.BUDGET_EXHAUSTED
        assert len(report.iterations) == 1


class TestTestValidation:
    def test_failed_tests_rollback_iteration(self):
        call_count = 0

        def mock_measure(repo_path, target_path):
            nonlocal call_count
            call_count += 1
            return _make_metric(max(10.0 - call_count, 5.0))

        adapter = MagicMock()
        adapter.measure.side_effect = mock_measure

        config = _make_config(budget=BudgetConfig(max_iterations=2, stall_patience=10))
        with tempfile.TemporaryDirectory() as d:
            runner = WorkflowRunner(
                config=config, adapter=adapter,
                repo_path=d, target_path=d,
                target_value=1.0,
                test_command="false",  # always fail
                skip_git=True, skip_tests=False, dry_run=True,
            )
            report = runner.run()

        # All iterations should have constraint violations
        assert report.outcome == RunOutcome.BUDGET_EXHAUSTED
        for it in report.iterations:
            assert it.constraint_violations or it.error


class TestReportFinalization:
    def test_report_has_timing(self):
        adapter = MagicMock()
        adapter.measure.return_value = _make_metric(2.0)

        with tempfile.TemporaryDirectory() as d:
            runner = WorkflowRunner(
                config=_make_config(),
                adapter=adapter,
                repo_path=d, target_path=d,
                target_value=3.0,
                skip_git=True, skip_tests=True, dry_run=True,
            )
            report = runner.run()

        assert report.started_at
        assert report.finished_at
        assert report.total_duration_seconds >= 0

    def test_default_target_from_config(self):
        adapter = MagicMock()
        adapter.measure.return_value = _make_metric(2.0)

        config = _make_config()
        with tempfile.TemporaryDirectory() as d:
            runner = WorkflowRunner(
                config=config, adapter=adapter,
                repo_path=d, target_path=d,
                target_value=None,  # should use config default
                skip_git=True, skip_tests=True, dry_run=True,
            )
            assert runner.target_value == 3.0  # from config


class TestAgentInvocation:
    def test_run_agent_with_explicit_command(self):
        """When agent_command is set, it should be used directly."""
        call_count = 0

        def mock_measure(repo_path, target_path):
            nonlocal call_count
            call_count += 1
            # First call = baseline, second = after agent
            return _make_metric(10.0 if call_count == 1 else 5.0)

        adapter = MagicMock()
        adapter.measure.side_effect = mock_measure
        adapter.identify_targets.return_value = []

        config = _make_config(budget=BudgetConfig(max_iterations=1, stall_patience=10))
        with tempfile.TemporaryDirectory() as d:
            runner = WorkflowRunner(
                config=config, adapter=adapter,
                repo_path=d, target_path=d,
                target_value=3.0,
                skip_git=True, skip_tests=True,
                dry_run=False,
                agent_command="true",  # no-op command
            )
            report = runner.run()

        assert len(report.iterations) == 1
        assert report.iterations[0].metric_after == 5.0

    def test_run_agent_default_prompt(self):
        """When no agent_command, builds a prompt and runs claude."""
        call_count = 0

        def mock_measure(repo_path, target_path):
            nonlocal call_count
            call_count += 1
            return _make_metric(10.0 if call_count == 1 else 8.0)

        adapter = MagicMock()
        adapter.measure.side_effect = mock_measure
        adapter.identify_targets.return_value = ["a.py", "b.py"]

        config = _make_config(budget=BudgetConfig(max_iterations=1, stall_patience=10))
        with tempfile.TemporaryDirectory() as d:
            # Patch subprocess.run to avoid actually calling claude
            with patch("autoforge.runner.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                runner = WorkflowRunner(
                    config=config, adapter=adapter,
                    repo_path=d, target_path=d,
                    target_value=3.0,
                    skip_git=True, skip_tests=True,
                    dry_run=False,
                )
                report = runner.run()

            # Agent was called
            assert mock_run.called
            # Prompt file should be cleaned up
            assert not (Path(d) / ".autoforge-prompt.tmp").exists()

    def test_run_agent_without_addendum(self):
        """Agent prompt works when no system_prompt_addendum is set."""
        call_count = 0

        def mock_measure(repo_path, target_path):
            nonlocal call_count
            call_count += 1
            return _make_metric(10.0 if call_count == 1 else 8.0)

        adapter = MagicMock()
        adapter.measure.side_effect = mock_measure
        adapter.identify_targets.return_value = []

        config = _make_config(
            agent=AgentConfig(skill="", system_prompt_addendum=""),
            budget=BudgetConfig(max_iterations=1, stall_patience=10),
        )
        with tempfile.TemporaryDirectory() as d:
            with patch("autoforge.runner.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                runner = WorkflowRunner(
                    config=config, adapter=adapter,
                    repo_path=d, target_path=d,
                    target_value=3.0,
                    skip_git=True, skip_tests=True,
                )
                report = runner.run()
            assert mock_run.called

    def test_agent_nonzero_exit_is_not_fatal(self):
        """Agent returning non-zero should log warning but continue."""
        call_count = 0

        def mock_measure(repo_path, target_path):
            nonlocal call_count
            call_count += 1
            return _make_metric(10.0 if call_count <= 1 else 8.0)

        adapter = MagicMock()
        adapter.measure.side_effect = mock_measure
        adapter.identify_targets.return_value = []

        config = _make_config(budget=BudgetConfig(max_iterations=1, stall_patience=10))
        with tempfile.TemporaryDirectory() as d:
            runner = WorkflowRunner(
                config=config, adapter=adapter,
                repo_path=d, target_path=d,
                target_value=3.0,
                skip_git=True, skip_tests=True,
                agent_command="false",  # exits 1
            )
            report = runner.run()
        # Should still complete without error
        assert len(report.iterations) == 1


class TestTargetMetDirection:
    def test_maximize_target(self):
        call_count = 0

        def mock_measure(repo_path, target_path):
            nonlocal call_count
            call_count += 1
            return MetricResult(
                metric_name="coverage", value=50.0 + call_count * 20,
                unit="percent", direction=Direction.MAXIMIZE,
            )

        adapter = MagicMock()
        adapter.measure.side_effect = mock_measure

        config = _make_config(
            primary_metric=PrimaryMetricConfig(name="coverage", direction=Direction.MAXIMIZE, default_target=80.0),
            budget=BudgetConfig(max_iterations=5, stall_patience=10),
        )
        with tempfile.TemporaryDirectory() as d:
            runner = WorkflowRunner(
                config=config, adapter=adapter,
                repo_path=d, target_path=d,
                target_value=80.0,
                skip_git=True, skip_tests=True, dry_run=True,
            )
            report = runner.run()
        assert report.outcome == RunOutcome.TARGET_MET


class TestCLISmokeTest:
    def test_health_json_with_real_file(self):
        """End-to-end: autoforge health on a real Python file."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "example.py").write_text(
                "def hello():\n    return 'world'\n\n"
                "def complex_func(x):\n"
                "    if x > 0:\n"
                "        for i in range(x):\n"
                "            if i % 2 == 0:\n"
                "                print(i)\n"
            )
            result = subprocess.run(
                ["autoforge", "health", "--path", d, "--repo", d, "--format", "json"],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0
            data = json.loads(result.stdout)
            assert "complexity" in data
            assert data["complexity"]["metric_name"] == "net_complexity_score"
            assert data["complexity"]["value"] >= 0

    def test_health_text_format(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "simple.py").write_text("x = 1\n")
            result = subprocess.run(
                ["autoforge", "health", "--path", d, "--repo", d],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0
            assert "Health Report" in result.stdout
