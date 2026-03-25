"""Tests for autoforge.models."""

import json

from autoforge.models import (
    BudgetConfig,
    IterationRecord,
    MetricConstraint,
    MetricResult,
    PrimaryMetricConfig,
    RunOutcome,
    RunReport,
    WorkflowConfig,
)


class TestMetricResult:
    def test_improved_over_minimize(self):
        before = MetricResult(metric_name="ncs", value=10.0, unit="score", direction="minimize")
        after = MetricResult(metric_name="ncs", value=7.0, unit="score", direction="minimize")
        assert after.improved_over(before)

    def test_improved_over_maximize(self):
        before = MetricResult(metric_name="coverage", value=60.0, unit="percent", direction="maximize")
        after = MetricResult(metric_name="coverage", value=75.0, unit="percent", direction="maximize")
        assert after.improved_over(before)

    def test_not_improved_minimize(self):
        before = MetricResult(metric_name="ncs", value=5.0, unit="score", direction="minimize")
        after = MetricResult(metric_name="ncs", value=5.5, unit="score", direction="minimize")
        assert not after.improved_over(before)

    def test_improved_over_with_threshold(self):
        before = MetricResult(metric_name="ncs", value=10.0, unit="score", direction="minimize")
        after = MetricResult(metric_name="ncs", value=9.8, unit="score", direction="minimize")
        # Improved, but not by more than threshold of 0.5
        assert not after.improved_over(before, threshold=0.5)

    def test_degraded_beyond_tolerance(self):
        baseline = MetricResult(metric_name="ncs", value=5.0, unit="score", direction="minimize")
        current = MetricResult(metric_name="ncs", value=6.0, unit="score", direction="minimize")
        # 20% degradation, 10% tolerance -> violated
        assert current.degraded_beyond(baseline, tolerance_percent=10.0)

    def test_not_degraded_within_tolerance(self):
        baseline = MetricResult(metric_name="ncs", value=5.0, unit="score", direction="minimize")
        current = MetricResult(metric_name="ncs", value=5.2, unit="score", direction="minimize")
        # 4% degradation, 10% tolerance -> ok
        assert not current.degraded_beyond(baseline, tolerance_percent=10.0)

    def test_degraded_maximize(self):
        baseline = MetricResult(metric_name="cov", value=80.0, unit="percent", direction="maximize")
        current = MetricResult(metric_name="cov", value=70.0, unit="percent", direction="maximize")
        # 12.5% drop, 5% tolerance -> violated
        assert current.degraded_beyond(baseline, tolerance_percent=5.0)


class TestWorkflowConfig:
    def test_from_dict_minimal(self):
        data = {"name": "test_wf"}
        cfg = WorkflowConfig.from_dict(data)
        assert cfg.name == "test_wf"
        assert cfg.budget.max_iterations == 15

    def test_from_dict_full(self):
        data = {
            "name": "complexity_refactor",
            "version": "1.0",
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
        }
        cfg = WorkflowConfig.from_dict(data)
        assert cfg.name == "complexity_refactor"
        assert cfg.primary_metric.default_target == 3.0
        assert cfg.budget.max_iterations == 10
        assert cfg.budget.max_tokens == 300000
        assert len(cfg.constraint_metrics) == 1
        assert cfg.agent.skill == "refactor-complexity"
        assert cfg.scope_priority == "worst_first"


class TestRunReport:
    def test_to_dict(self):
        report = RunReport(
            workflow="test",
            target={"ncs": 3.0},
            outcome=RunOutcome.TARGET_MET,
            initial_metric=8.0,
            final_metric=2.5,
        )
        report.iterations.append(
            IterationRecord(n=1, metric_before=8.0, metric_after=5.0)
        )
        d = report.to_dict()
        assert d["workflow"] == "test"
        assert d["outcome"] == "target_met"
        assert d["initial_metric"] == 8.0
        assert d["final_metric"] == 2.5
        assert len(d["iterations"]) == 1
        # Should be valid JSON
        json.dumps(d)

    def test_to_markdown(self):
        report = RunReport(
            workflow="complexity_refactor",
            target={"ncs": 3.0},
            outcome=RunOutcome.STALLED,
            initial_metric=7.0,
            final_metric=4.5,
            branch="autoforge/complexity_refactor/20260325",
        )
        report.iterations.append(
            IterationRecord(n=1, metric_before=7.0, metric_after=5.5, files_modified=["a.py"])
        )
        report.iterations.append(
            IterationRecord(n=2, metric_before=5.5, metric_after=4.5, files_modified=["b.py"])
        )
        md = report.to_markdown()
        assert "complexity_refactor" in md
        assert "stalled" in md
        assert "7.0" in md
        assert "4.5" in md
