"""Tests for autoforge.models — MetricResult, WorkflowConfig, RunReport."""

import pytest

from autoforge.models import (
    BudgetConfig,
    Direction,
    IterationRecord,
    MetricResult,
    PrimaryMetricConfig,
    RunOutcome,
    RunReport,
    WorkflowConfig,
)


# ---------------------------------------------------------------------------
# MetricResult
# ---------------------------------------------------------------------------

class TestMetricResultImprovement:
    """Test the improved_over method for both metric directions."""

    def test_minimize_improved(self):
        before = MetricResult(metric_name="ncs", value=10.0, unit="score", direction=Direction.MINIMIZE)
        after = MetricResult(metric_name="ncs", value=7.0, unit="score", direction=Direction.MINIMIZE)
        assert after.improved_over(before)

    def test_minimize_not_improved(self):
        before = MetricResult(metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE)
        after = MetricResult(metric_name="ncs", value=5.5, unit="score", direction=Direction.MINIMIZE)
        assert not after.improved_over(before)

    def test_minimize_unchanged(self):
        before = MetricResult(metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE)
        after = MetricResult(metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE)
        assert not after.improved_over(before)

    def test_maximize_improved(self):
        before = MetricResult(metric_name="cov", value=60.0, unit="percent", direction=Direction.MAXIMIZE)
        after = MetricResult(metric_name="cov", value=75.0, unit="percent", direction=Direction.MAXIMIZE)
        assert after.improved_over(before)

    def test_maximize_not_improved(self):
        before = MetricResult(metric_name="cov", value=80.0, unit="percent", direction=Direction.MAXIMIZE)
        after = MetricResult(metric_name="cov", value=70.0, unit="percent", direction=Direction.MAXIMIZE)
        assert not after.improved_over(before)

    def test_threshold_filters_small_improvements(self):
        before = MetricResult(metric_name="ncs", value=10.0, unit="score", direction=Direction.MINIMIZE)
        after = MetricResult(metric_name="ncs", value=9.8, unit="score", direction=Direction.MINIMIZE)
        assert after.improved_over(before, threshold=0.0)
        assert not after.improved_over(before, threshold=0.5)

    def test_threshold_maximize(self):
        before = MetricResult(metric_name="cov", value=70.0, unit="percent", direction=Direction.MAXIMIZE)
        after = MetricResult(metric_name="cov", value=70.3, unit="percent", direction=Direction.MAXIMIZE)
        assert not after.improved_over(before, threshold=0.5)

    def test_zero_values(self):
        before = MetricResult(metric_name="errors", value=0.0, unit="count", direction=Direction.MINIMIZE)
        after = MetricResult(metric_name="errors", value=0.0, unit="count", direction=Direction.MINIMIZE)
        assert not after.improved_over(before)


class TestMetricResultDegradation:
    """Test the degraded_beyond method for constraint checking."""

    def test_minimize_degraded(self):
        baseline = MetricResult(metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE)
        current = MetricResult(metric_name="ncs", value=6.0, unit="score", direction=Direction.MINIMIZE)
        assert current.degraded_beyond(baseline, tolerance_percent=10.0)  # 20% > 10%

    def test_minimize_within_tolerance(self):
        baseline = MetricResult(metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE)
        current = MetricResult(metric_name="ncs", value=5.2, unit="score", direction=Direction.MINIMIZE)
        assert not current.degraded_beyond(baseline, tolerance_percent=10.0)  # 4% < 10%

    def test_minimize_improved_not_degraded(self):
        baseline = MetricResult(metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE)
        current = MetricResult(metric_name="ncs", value=3.0, unit="score", direction=Direction.MINIMIZE)
        assert not current.degraded_beyond(baseline, tolerance_percent=5.0)

    def test_maximize_degraded(self):
        baseline = MetricResult(metric_name="cov", value=80.0, unit="percent", direction=Direction.MAXIMIZE)
        current = MetricResult(metric_name="cov", value=70.0, unit="percent", direction=Direction.MAXIMIZE)
        assert current.degraded_beyond(baseline, tolerance_percent=5.0)  # 12.5% > 5%

    def test_maximize_within_tolerance(self):
        baseline = MetricResult(metric_name="cov", value=80.0, unit="percent", direction=Direction.MAXIMIZE)
        current = MetricResult(metric_name="cov", value=78.0, unit="percent", direction=Direction.MAXIMIZE)
        assert not current.degraded_beyond(baseline, tolerance_percent=5.0)  # 2.5% < 5%

    def test_zero_tolerance_never_degrades(self):
        baseline = MetricResult(metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE)
        current = MetricResult(metric_name="ncs", value=100.0, unit="score", direction=Direction.MINIMIZE)
        assert not current.degraded_beyond(baseline, tolerance_percent=0.0)

    def test_zero_baseline_value(self):
        baseline = MetricResult(metric_name="errors", value=0.0, unit="count", direction=Direction.MINIMIZE)
        current = MetricResult(metric_name="errors", value=1.0, unit="count", direction=Direction.MINIMIZE)
        assert current.degraded_beyond(baseline, tolerance_percent=5.0)

    def test_zero_baseline_no_change(self):
        baseline = MetricResult(metric_name="errors", value=0.0, unit="count", direction=Direction.MINIMIZE)
        current = MetricResult(metric_name="errors", value=0.0, unit="count", direction=Direction.MINIMIZE)
        assert not current.degraded_beyond(baseline, tolerance_percent=5.0)

    def test_negative_tolerance(self):
        baseline = MetricResult(metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE)
        current = MetricResult(metric_name="ncs", value=100.0, unit="score", direction=Direction.MINIMIZE)
        assert not current.degraded_beyond(baseline, tolerance_percent=-1.0)


class TestMetricResultFields:
    """Test MetricResult default values and field population."""

    def test_defaults(self):
        r = MetricResult(metric_name="x", value=1.0, unit="u", direction=Direction.MINIMIZE)
        assert r.breakdown == {}
        assert r.tool == ""
        assert r.timestamp  # auto-generated

    def test_full_fields(self):
        r = MetricResult(
            metric_name="ncs",
            value=5.5,
            unit="score",
            direction=Direction.MINIMIZE,
            breakdown={"a.py": 3.0, "b.py": 8.0},
            tool="complexity-accounting",
            timestamp="2026-01-01T00:00:00",
        )
        assert r.breakdown["b.py"] == 8.0
        assert r.tool == "complexity-accounting"
        assert r.timestamp == "2026-01-01T00:00:00"


# ---------------------------------------------------------------------------
# WorkflowConfig
# ---------------------------------------------------------------------------

class TestWorkflowConfigFromDict:
    """Test WorkflowConfig.from_dict with various inputs."""

    def test_minimal_config(self):
        cfg = WorkflowConfig.from_dict({"name": "test_wf"})
        assert cfg.name == "test_wf"
        assert cfg.version == "1.0"
        assert cfg.budget.max_iterations == 15
        assert cfg.constraint_metrics == []
        assert cfg.scope_priority == "worst_first"

    def test_full_config(self):
        data = {
            "name": "complexity_refactor",
            "version": "2.0",
            "description": "Reduce complexity",
            "primary_metric": {
                "name": "net_complexity_score",
                "direction": "minimize",
                "default_target": 3.0,
            },
            "constraint_metrics": [
                {
                    "name": "test_pass",
                    "tolerance_percent": 0,
                    "direction": "maximize",
                },
            ],
            "budget": {
                "max_iterations": 10,
                "max_tokens": 300000,
                "max_wall_clock_minutes": 20,
                "stall_patience": 3,
                "min_improvement_percent": 1.0,
                "max_files_per_iteration": 5,
            },
            "scope": {"priority": "worst_first"},
            "agent": {
                "skill": "refactor-complexity",
                "system_prompt_addendum": "Be careful",
            },
            "language_support": {
                "python": {
                    "metric_tool": "complexity-accounting",
                    "metric_command": "scan {path}",
                    "metric_parser": "complexity_json",
                },
            },
        }
        cfg = WorkflowConfig.from_dict(data)
        assert cfg.name == "complexity_refactor"
        assert cfg.version == "2.0"
        assert cfg.primary_metric.default_target == 3.0
        assert cfg.primary_metric.direction is Direction.MINIMIZE
        assert cfg.budget.max_iterations == 10
        assert cfg.budget.max_tokens == 300000
        assert len(cfg.constraint_metrics) == 1
        assert cfg.agent.skill == "refactor-complexity"
        assert cfg.scope_priority == "worst_first"
        assert "python" in cfg.language_support
        assert cfg.language_support["python"].metric_tool == "complexity-accounting"

    def test_empty_dict(self):
        cfg = WorkflowConfig.from_dict({})
        assert cfg.name == ""
        assert cfg.primary_metric.name == ""
        assert cfg.budget.max_iterations == 15

    def test_missing_optional_sections(self):
        cfg = WorkflowConfig.from_dict({"name": "x", "primary_metric": {"name": "m"}})
        assert cfg.primary_metric.name == "m"
        assert cfg.primary_metric.direction is Direction.MINIMIZE  # default
        assert cfg.agent.skill == ""

    def test_multiple_constraints(self):
        data = {
            "name": "x",
            "constraint_metrics": [
                {"name": "a", "tolerance_percent": 5, "direction": "minimize"},
                {"name": "b", "tolerance_percent": 10, "direction": "maximize"},
                {"name": "c", "tolerance_percent": 20, "direction": "minimize"},
            ],
        }
        cfg = WorkflowConfig.from_dict(data)
        assert len(cfg.constraint_metrics) == 3
        assert cfg.constraint_metrics[1].tolerance_percent == 10

    def test_multiple_languages(self):
        data = {
            "name": "x",
            "language_support": {
                "python": {"metric_tool": "pytest-cov"},
                "typescript": {"metric_tool": "c8"},
                "go": {"metric_tool": "go-cover"},
            },
        }
        cfg = WorkflowConfig.from_dict(data)
        assert len(cfg.language_support) == 3


# ---------------------------------------------------------------------------
# RunReport
# ---------------------------------------------------------------------------

class TestRunReport:
    def test_defaults(self):
        report = RunReport(workflow="test")
        assert report.outcome == RunOutcome.ERROR
        assert report.iterations == []
        assert report.initial_metric == 0.0
        assert report.started_at  # auto-generated

    def test_fields_populated(self):
        report = RunReport(
            workflow="test",
            target={"ncs": 3.0},
            outcome=RunOutcome.TARGET_MET,
            initial_metric=8.0,
            final_metric=2.5,
            branch="autoforge/test/20260325",
        )
        assert report.workflow == "test"
        assert report.target == {"ncs": 3.0}
        assert report.outcome == RunOutcome.TARGET_MET

    def test_invalid_direction_in_from_dict(self):
        with pytest.raises(ValueError, match="Invalid direction"):
            WorkflowConfig.from_dict({
                "name": "x",
                "primary_metric": {"name": "m", "direction": "invalid"},
            })

    def test_invalid_constraint_direction(self):
        with pytest.raises(ValueError, match="Invalid direction"):
            WorkflowConfig.from_dict({
                "name": "x",
                "constraint_metrics": [{"name": "a", "direction": "bad"}],
            })


class TestRunOutcome:
    def test_all_values(self):
        assert RunOutcome.TARGET_MET.value == "target_met"
        assert RunOutcome.BUDGET_EXHAUSTED.value == "budget_exhausted"
        assert RunOutcome.STALLED.value == "stalled"
        assert RunOutcome.CONSTRAINT_VIOLATED.value == "constraint_violated"
        assert RunOutcome.ERROR.value == "error"
        assert RunOutcome.ABORTED.value == "aborted"


class TestIterationRecord:
    def test_defaults(self):
        r = IterationRecord(n=1, metric_before=10.0, metric_after=8.0)
        assert r.files_modified == []
        assert r.constraint_violations == []
        assert r.tokens_used == 0
        assert r.commit_sha == ""
        assert r.error == ""
