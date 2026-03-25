"""Tests for autoforge.reporting."""

import tempfile
from pathlib import Path

from autoforge.models import IterationRecord, MetricResult, RunOutcome, RunReport
from autoforge.reporting import format_health_dashboard, save_run_report


class TestSaveRunReport:
    def test_save_creates_files(self):
        report = RunReport(
            workflow="test_wf",
            target={"ncs": 3.0},
            outcome=RunOutcome.TARGET_MET,
            initial_metric=8.0,
            final_metric=2.5,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path, md_path = save_run_report(report, tmpdir)
            assert Path(json_path).exists()
            assert Path(md_path).exists()
            assert "test_wf" in Path(json_path).name
            assert Path(json_path).suffix == ".json"
            assert Path(md_path).suffix == ".md"

    def test_json_report_valid(self):
        import json

        report = RunReport(
            workflow="test_wf",
            outcome=RunOutcome.STALLED,
            initial_metric=10.0,
            final_metric=6.0,
        )
        report.iterations.append(
            IterationRecord(n=1, metric_before=10.0, metric_after=6.0)
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path, _ = save_run_report(report, tmpdir)
            data = json.loads(Path(json_path).read_text())
            assert data["workflow"] == "test_wf"
            assert data["outcome"] == "stalled"
            assert len(data["iterations"]) == 1


class TestHealthDashboard:
    def test_format_dashboard(self):
        metrics = {
            "complexity": MetricResult(
                metric_name="net_complexity_score",
                value=5.2,
                unit="score",
                direction="minimize",
                breakdown={"a.py": 8.0, "b.py": 3.0},
            ),
        }
        dashboard = format_health_dashboard(metrics)
        assert "Health Report" in dashboard
        assert "5.20" in dashboard
        assert "a.py" in dashboard
        assert "Moderate" in dashboard

    def test_healthy_ncs(self):
        metrics = {
            "complexity": MetricResult(
                metric_name="net_complexity_score",
                value=2.0,
                unit="score",
                direction="minimize",
            ),
        }
        dashboard = format_health_dashboard(metrics)
        assert "Healthy" in dashboard

    def test_critical_ncs(self):
        metrics = {
            "complexity": MetricResult(
                metric_name="net_complexity_score",
                value=15.0,
                unit="score",
                direction="minimize",
            ),
        }
        dashboard = format_health_dashboard(metrics)
        assert "Critical" in dashboard
