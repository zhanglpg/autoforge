"""Tests for autoforge.adapters.base — BaseMetricAdapter ABC."""

from autoforge.adapters.base import BaseMetricAdapter
from autoforge.models import Direction, MetricResult


class _DummyAdapter(BaseMetricAdapter):
    name = "dummy"

    def check_prerequisites(self, repo_path):
        return True

    def measure(self, repo_path, target_path):
        return MetricResult(metric_name="x", value=0, unit="u", direction=Direction.MINIMIZE)

    def identify_targets(self, result, n):
        return []


class TestCheckToolAvailable:
    def test_existing_tool_found(self):
        adapter = _DummyAdapter()
        assert adapter.check_tool_available("python3") is True

    def test_missing_tool_not_found(self):
        adapter = _DummyAdapter()
        assert adapter.check_tool_available("nonexistent_tool_xyz_12345") is False


class TestBaseMetricAdapterInterface:
    def test_name_attribute(self):
        adapter = _DummyAdapter()
        assert adapter.name == "dummy"

    def test_check_prerequisites_callable(self):
        adapter = _DummyAdapter()
        result = adapter.check_prerequisites("/any/path")
        assert result is True

    def test_measure_returns_metric_result(self):
        adapter = _DummyAdapter()
        result = adapter.measure("/repo", "/target")
        assert isinstance(result, MetricResult)
        assert result.metric_name == "x"
        assert result.value == 0
        assert result.direction == Direction.MINIMIZE

    def test_identify_targets_returns_list(self):
        adapter = _DummyAdapter()
        mr = MetricResult(metric_name="x", value=1, unit="u", direction=Direction.MINIMIZE)
        targets = adapter.identify_targets(mr, 5)
        assert isinstance(targets, list)
        assert targets == []
