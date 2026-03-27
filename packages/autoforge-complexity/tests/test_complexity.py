"""Tests for autoforge.adapters.complexity — ComplexityAdapter."""

import tempfile
from pathlib import Path

import pytest

from autoforge_complexity import ComplexityAdapter
from autoforge.models import Direction, MetricResult


class TestComplexityAdapterAttributes:
    def test_name(self):
        adapter = ComplexityAdapter()
        assert adapter.name == "complexity"

    def test_supported_languages(self):
        adapter = ComplexityAdapter()
        assert "python" in adapter.supported_languages
        assert "go" in adapter.supported_languages
        assert "typescript" in adapter.supported_languages
        assert "rust" in adapter.supported_languages
        assert len(adapter.supported_languages) == 7

    def test_default_options(self):
        adapter = ComplexityAdapter()
        assert adapter.no_churn is True
        assert adapter.no_coupling is False
        assert adapter.no_duplication is False
        assert adapter.ncs_model == "multiplicative"
        assert adapter.threshold is None
        assert adapter.include_tests is False


class TestBuildCommand:
    def test_default_flags(self):
        adapter = ComplexityAdapter()
        cmd = adapter._build_command("/some/path")
        assert "--format" in cmd
        assert "json" in cmd
        assert "--no-churn" in cmd
        assert "--no-coupling" not in cmd
        assert "--no-duplication" not in cmd
        assert "/some/path" in cmd

    def test_all_flags_enabled(self):
        adapter = ComplexityAdapter(
            no_churn=True, no_coupling=True, no_duplication=True,
            ncs_model="additive", threshold=15, include_tests=True,
        )
        cmd = adapter._build_command("/path")
        assert "--no-churn" in cmd
        assert "--no-coupling" in cmd
        assert "--no-duplication" in cmd
        assert "additive" in cmd
        assert "--threshold" in cmd
        assert "15" in cmd
        assert "--include-tests" in cmd

    def test_no_churn_disabled(self):
        adapter = ComplexityAdapter(no_churn=False)
        cmd = adapter._build_command("/path")
        assert "--no-churn" not in cmd


class TestIdentifyTargets:
    def test_returns_worst_files_first(self):
        adapter = ComplexityAdapter()
        result = MetricResult(
            metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE,
            breakdown={"a.py": 15.0, "b.py": 3.0, "c.py": 25.0, "d.py": 8.0},
        )
        targets = adapter.identify_targets(result, n=2)
        assert targets == ["c.py", "a.py"]

    def test_returns_all_when_n_exceeds(self):
        adapter = ComplexityAdapter()
        result = MetricResult(
            metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE,
            breakdown={"a.py": 10.0, "b.py": 5.0},
        )
        targets = adapter.identify_targets(result, n=100)
        assert len(targets) == 2

    def test_empty_breakdown(self):
        adapter = ComplexityAdapter()
        result = MetricResult(
            metric_name="ncs", value=0.0, unit="score", direction=Direction.MINIMIZE,
        )
        assert adapter.identify_targets(result, n=5) == []


class TestPrerequisites:
    def test_prerequisites_met_when_installed(self):
        adapter = ComplexityAdapter()
        assert adapter.check_prerequisites("/any/path") is True


class TestMeasure:
    def test_measure_real_file(self):
        adapter = ComplexityAdapter()
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "sample.py").write_text(
                "def simple():\n"
                "    return 1\n"
                "\n"
                "def complex_func(x, y):\n"
                "    if x > 0:\n"
                "        for i in range(y):\n"
                "            if i % 2 == 0:\n"
                "                if x > i:\n"
                "                    print(x + i)\n"
            )
            result = adapter.measure(d, d)
            assert result.metric_name == "net_complexity_score"
            assert result.unit == "score"
            assert result.direction is Direction.MINIMIZE
            assert result.tool == "complexity-accounting"
            assert isinstance(result.value, float)
            assert result.value >= 0
            assert result.timestamp != ""
            assert len(result.breakdown) >= 1

    def test_measure_empty_directory(self):
        adapter = ComplexityAdapter()
        with tempfile.TemporaryDirectory() as d:
            result = adapter.measure(d, d)
            assert result.value == 0.0

    def test_measure_nonexistent_path_raises(self):
        adapter = ComplexityAdapter()
        with pytest.raises(RuntimeError, match="failed"):
            adapter.measure("/tmp", "/nonexistent/path/xyz")
