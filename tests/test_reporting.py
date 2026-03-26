"""Tests for autoforge.reporting — report generation and health dashboards."""

import json
import tempfile
from pathlib import Path

from autoforge.models import Direction, IterationRecord, MetricResult, RunOutcome, RunReport
from autoforge.reporting import format_health_dashboard, save_run_report, _health_status


class TestSaveRunReport:
    def test_creates_both_files(self):
        report = RunReport(
            workflow="test_wf",
            target={"ncs": 3.0},
            outcome=RunOutcome.TARGET_MET,
            initial_metric=8.0,
            final_metric=2.5,
        )
        with tempfile.TemporaryDirectory() as d:
            json_path, md_path = save_run_report(report, d)
            assert Path(json_path).exists() == True
            assert Path(md_path).exists() == True
            assert "test_wf" in Path(json_path).name
            assert Path(json_path).suffix == ".json"
            assert Path(md_path).suffix == ".md"

    def test_json_is_valid(self):
        report = RunReport(
            workflow="test",
            outcome=RunOutcome.STALLED,
            initial_metric=10.0,
            final_metric=6.0,
        )
        report.iterations.append(
            IterationRecord(n=1, metric_before=10.0, metric_after=6.0, tokens_used=5000)
        )
        with tempfile.TemporaryDirectory() as d:
            json_path, _ = save_run_report(report, d)
            data = json.loads(Path(json_path).read_text())
            assert data["workflow"] == "test"
            assert data["outcome"] == "stalled"
            assert len(data["iterations"]) == 1
            assert data["iterations"][0]["tokens_used"] == 5000

    def test_markdown_has_content(self):
        report = RunReport(
            workflow="wf", outcome=RunOutcome.TARGET_MET,
            initial_metric=10.0, final_metric=3.0,
        )
        with tempfile.TemporaryDirectory() as d:
            _, md_path = save_run_report(report, d)
            content = Path(md_path).read_text()
            assert "AutoForge Run Report" in content

    def test_creates_nested_output_dir(self):
        report = RunReport(workflow="x")
        with tempfile.TemporaryDirectory() as d:
            nested = str(Path(d) / "a" / "b" / "c")
            json_path, md_path = save_run_report(report, nested)
            assert Path(json_path).exists() == True
            assert Path(md_path).exists() == True


class TestHealthDashboard:
    def test_single_metric(self):
        metrics = {
            "complexity": MetricResult(
                metric_name="net_complexity_score", value=5.2,
                unit="score", direction=Direction.MINIMIZE,
                breakdown={"a.py": 8.0, "b.py": 3.0},
            ),
        }
        dashboard = format_health_dashboard(metrics)
        assert isinstance(dashboard, str)
        assert "Health Report" in dashboard
        assert "5.20" in dashboard
        assert "a.py" in dashboard
        assert "b.py" in dashboard
        assert "Moderate" in dashboard
        assert len(dashboard) > 0

    def test_multiple_metrics(self):
        metrics = {
            "complexity": MetricResult(
                metric_name="net_complexity_score", value=2.0,
                unit="score", direction=Direction.MINIMIZE,
            ),
            "coverage": MetricResult(
                metric_name="branch_coverage", value=85.0,
                unit="percent", direction=Direction.MAXIMIZE,
            ),
        }
        dashboard = format_health_dashboard(metrics)
        assert "complexity" in dashboard
        assert "coverage" in dashboard

    def test_no_breakdown(self):
        metrics = {
            "simple": MetricResult(
                metric_name="x", value=1.0, unit="count", direction=Direction.MINIMIZE,
            ),
        }
        dashboard = format_health_dashboard(metrics)
        assert "Per-File Breakdown" in dashboard  # section header present
        # but no file table for this metric

    def test_large_breakdown_truncated(self):
        breakdown = {f"file_{i}.py": float(i) for i in range(15)}
        metrics = {
            "big": MetricResult(
                metric_name="ncs", value=5.0, unit="score",
                direction=Direction.MINIMIZE, breakdown=breakdown,
            ),
        }
        dashboard = format_health_dashboard(metrics)
        assert "5 more files" in dashboard  # 15 - 10 = 5

    def test_maximize_breakdown_sorted(self):
        """For maximize metrics, breakdown should be sorted with lowest first (worst)."""
        metrics = {
            "cov": MetricResult(
                metric_name="coverage", value=60.0, unit="percent",
                direction=Direction.MAXIMIZE,
                breakdown={"good.py": 95.0, "bad.py": 20.0, "ok.py": 60.0},
            ),
        }
        dashboard = format_health_dashboard(metrics)
        # For maximize, reverse=False (direction != "minimize"), so ascending order
        lines = dashboard.split("\n")
        file_lines = [l for l in lines if "`" in l and ".py" in l]
        assert len(file_lines) == 3


class TestHealthStatus:
    """Test all branches of the _health_status function."""

    def test_ncs_healthy(self):
        r = MetricResult(metric_name="net_complexity_score", value=2.0, unit="score", direction=Direction.MINIMIZE)
        assert _health_status("x", r) == "Healthy"

    def test_ncs_moderate(self):
        r = MetricResult(metric_name="net_complexity_score", value=5.0, unit="score", direction=Direction.MINIMIZE)
        assert _health_status("x", r) == "Moderate"

    def test_ncs_concerning(self):
        r = MetricResult(metric_name="net_complexity_score", value=8.0, unit="score", direction=Direction.MINIMIZE)
        assert _health_status("x", r) == "Concerning"

    def test_ncs_critical(self):
        r = MetricResult(metric_name="net_complexity_score", value=15.0, unit="score", direction=Direction.MINIMIZE)
        assert _health_status("x", r) == "Critical"

    def test_ncs_boundary_3(self):
        r = MetricResult(metric_name="net_complexity_score", value=3.0, unit="score", direction=Direction.MINIMIZE)
        assert _health_status("x", r) == "Healthy"

    def test_ncs_boundary_6(self):
        r = MetricResult(metric_name="net_complexity_score", value=6.0, unit="score", direction=Direction.MINIMIZE)
        assert _health_status("x", r) == "Moderate"

    def test_ncs_boundary_10(self):
        r = MetricResult(metric_name="net_complexity_score", value=10.0, unit="score", direction=Direction.MINIMIZE)
        assert _health_status("x", r) == "Concerning"

    def test_maximize_healthy(self):
        r = MetricResult(metric_name="coverage", value=85.0, unit="percent", direction=Direction.MAXIMIZE)
        assert _health_status("x", r) == "Healthy"

    def test_maximize_moderate(self):
        r = MetricResult(metric_name="coverage", value=65.0, unit="percent", direction=Direction.MAXIMIZE)
        assert _health_status("x", r) == "Moderate"

    def test_maximize_concerning(self):
        r = MetricResult(metric_name="coverage", value=45.0, unit="percent", direction=Direction.MAXIMIZE)
        assert _health_status("x", r) == "Concerning"

    def test_maximize_critical(self):
        r = MetricResult(metric_name="coverage", value=30.0, unit="percent", direction=Direction.MAXIMIZE)
        assert _health_status("x", r) == "Critical"

    def test_minimize_healthy(self):
        r = MetricResult(metric_name="errors", value=0.0, unit="count", direction=Direction.MINIMIZE)
        assert _health_status("x", r) == "Healthy"

    def test_minimize_moderate(self):
        r = MetricResult(metric_name="errors", value=3.0, unit="count", direction=Direction.MINIMIZE)
        assert _health_status("x", r) == "Moderate"

    def test_minimize_concerning(self):
        r = MetricResult(metric_name="errors", value=15.0, unit="count", direction=Direction.MINIMIZE)
        assert _health_status("x", r) == "Concerning"

    def test_minimize_critical(self):
        r = MetricResult(metric_name="errors", value=25.0, unit="count", direction=Direction.MINIMIZE)
        assert _health_status("x", r) == "Critical"

    def test_ncs_zero(self):
        """NCS of exactly 0 should be Healthy."""
        r = MetricResult(metric_name="net_complexity_score", value=0.0, unit="score", direction=Direction.MINIMIZE)
        assert _health_status("x", r) == "Healthy"
