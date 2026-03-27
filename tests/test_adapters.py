"""Tests for autoforge.adapters.base — BaseMetricAdapter."""

import pytest

from autoforge.adapters.base import BaseMetricAdapter
from autoforge.models import Direction, MetricResult


class TestBaseMetricAdapter:
    def test_check_tool_available_existing(self):
        """'python' should be available on PATH."""

        class Dummy(BaseMetricAdapter):
            name = "dummy"

            def check_prerequisites(self, repo_path):
                return True

            def measure(self, repo_path, target_path):
                return MetricResult(metric_name="x", value=0, unit="u", direction=Direction.MINIMIZE)

            def identify_targets(self, result, n):
                return []

        adapter = Dummy()
        assert adapter.check_tool_available("python3") or adapter.check_tool_available("python")

    def test_check_tool_available_missing(self):
        class Dummy(BaseMetricAdapter):
            name = "dummy"

            def check_prerequisites(self, repo_path):
                return True

            def measure(self, repo_path, target_path):
                return MetricResult(metric_name="x", value=0, unit="u", direction=Direction.MINIMIZE)

            def identify_targets(self, result, n):
                return []

        adapter = Dummy()
        assert not adapter.check_tool_available("nonexistent_tool_xyz_12345")
