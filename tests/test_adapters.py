"""Tests for autoforge.adapters."""

from autoforge.adapters.complexity import ComplexityAdapter
from autoforge.models import MetricResult


class TestComplexityAdapter:
    def test_attributes(self):
        adapter = ComplexityAdapter()
        assert adapter.name == "complexity"
        assert "python" in adapter.supported_languages
        assert "go" in adapter.supported_languages

    def test_build_command_default(self):
        adapter = ComplexityAdapter()
        cmd = adapter._build_command("/some/path")
        assert "--format" in cmd
        assert "json" in cmd
        assert "--no-churn" in cmd
        assert "--no-coupling" not in cmd

    def test_build_command_all_flags(self):
        adapter = ComplexityAdapter(
            no_churn=True,
            no_coupling=True,
            no_duplication=True,
            ncs_model="additive",
            threshold=15,
            include_tests=True,
        )
        cmd = adapter._build_command("/some/path")
        assert "--no-churn" in cmd
        assert "--no-coupling" in cmd
        assert "--no-duplication" in cmd
        assert "--ncs-model" in cmd
        assert "additive" in cmd
        assert "--threshold" in cmd
        assert "15" in cmd
        assert "--include-tests" in cmd

    def test_identify_targets(self):
        adapter = ComplexityAdapter()
        result = MetricResult(
            metric_name="ncs",
            value=5.0,
            unit="score",
            direction="minimize",
            breakdown={
                "a.py": 15.0,
                "b.py": 3.0,
                "c.py": 25.0,
                "d.py": 8.0,
            },
        )
        targets = adapter.identify_targets(result, n=2)
        assert targets == ["c.py", "a.py"]

    def test_identify_targets_empty(self):
        adapter = ComplexityAdapter()
        result = MetricResult(
            metric_name="ncs", value=0.0, unit="score", direction="minimize"
        )
        targets = adapter.identify_targets(result, n=5)
        assert targets == []
