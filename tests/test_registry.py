"""Tests for autoforge.registry — adapter/workflow registration and loading."""

import tempfile
from pathlib import Path

import pytest

from autoforge.adapters.base import BaseMetricAdapter
from autoforge.adapters.complexity import ComplexityAdapter
from autoforge.models import Direction, MetricResult
from autoforge.registry import (
    _ADAPTER_REGISTRY,
    find_workflow_config,
    get_adapter,
    list_adapters,
    list_workflows,
    load_workflow_config,
    register_adapter,
)


class TestAdapterRegistry:
    def test_list_includes_builtin(self):
        adapters = list_adapters()
        assert "complexity" in adapters

    def test_get_complexity(self):
        adapter = get_adapter("complexity")
        assert isinstance(adapter, ComplexityAdapter)
        assert adapter.name == "complexity"

    def test_get_with_kwargs(self):
        adapter = get_adapter("complexity", no_churn=False, ncs_model="additive")
        assert isinstance(adapter, ComplexityAdapter)
        assert adapter.ncs_model == "additive"
        assert adapter.no_churn is False

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown adapter 'nonexistent'"):
            get_adapter("nonexistent")

    def test_error_message_lists_available(self):
        with pytest.raises(ValueError, match="complexity"):
            get_adapter("bad_name")

    def test_register_custom_adapter(self):
        class DummyAdapter(BaseMetricAdapter):
            name = "dummy"
            supported_languages = ["python"]

            def check_prerequisites(self, repo_path):
                return True

            def measure(self, repo_path, target_path):
                return MetricResult(metric_name="dummy", value=0, unit="x", direction=Direction.MINIMIZE)

            def identify_targets(self, result, n):
                return []

        register_adapter("dummy", DummyAdapter)
        try:
            assert "dummy" in list_adapters()
            adapter = get_adapter("dummy")
            assert adapter.name == "dummy"
        finally:
            # Clean up to not affect other tests
            _ADAPTER_REGISTRY.pop("dummy", None)


class TestLoadWorkflowConfig:
    def test_load_builtin_complexity(self):
        workflows_dir = Path(__file__).parent.parent / "src" / "autoforge" / "workflows"
        cfg = load_workflow_config(str(workflows_dir / "complexity_refactor.yaml"))
        assert cfg.name == "complexity_refactor"
        assert cfg.primary_metric.name == "net_complexity_score"
        assert cfg.primary_metric.direction is Direction.MINIMIZE
        assert cfg.primary_metric.default_target == 3.0
        assert cfg.budget.max_iterations == 10
        assert cfg.budget.stall_patience == 3
        assert cfg.budget.min_improvement_percent == 1.0
        assert cfg.agent.skill == "refactor-complexity"
        assert "python" in cfg.language_support
        assert "typescript" in cfg.language_support

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_workflow_config("/nonexistent/workflow.yaml")

    def test_load_custom_yaml(self):
        with tempfile.TemporaryDirectory() as d:
            cfg_path = Path(d) / "custom.yaml"
            cfg_path.write_text(
                "name: custom_wf\n"
                "primary_metric:\n"
                "  name: test_score\n"
                "  direction: maximize\n"
                "  default_target: 80.0\n"
                "budget:\n"
                "  max_iterations: 5\n"
            )
            cfg = load_workflow_config(str(cfg_path))
            assert cfg.name == "custom_wf"
            assert cfg.primary_metric.direction is Direction.MAXIMIZE
            assert cfg.budget.max_iterations == 5


class TestFindWorkflowConfig:
    def test_find_builtin(self):
        cfg = find_workflow_config("complexity_refactor")
        assert cfg.name == "complexity_refactor"

    def test_find_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            find_workflow_config("nonexistent_workflow_xyz")

    def test_find_in_custom_dir(self):
        with tempfile.TemporaryDirectory() as d:
            cfg_path = Path(d) / "my_wf.yaml"
            cfg_path.write_text("name: my_wf\n")
            cfg = find_workflow_config("my_wf", search_dirs=[d])
            assert cfg.name == "my_wf"

    def test_find_yml_extension(self):
        with tempfile.TemporaryDirectory() as d:
            cfg_path = Path(d) / "test_wf.yml"
            cfg_path.write_text("name: test_wf\n")
            cfg = find_workflow_config("test_wf", search_dirs=[d])
            assert cfg.name == "test_wf"

    def test_search_dir_takes_precedence(self):
        """Custom search dir should be checked before builtins."""
        with tempfile.TemporaryDirectory() as d:
            cfg_path = Path(d) / "complexity_refactor.yaml"
            cfg_path.write_text("name: custom_override\n")
            cfg = find_workflow_config("complexity_refactor", search_dirs=[d])
            assert cfg.name == "custom_override"


class TestListWorkflows:
    def test_includes_builtin(self):
        workflows = list_workflows()
        assert "complexity_refactor" in workflows

    def test_custom_dir(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "wf_a.yaml").write_text("name: a\n")
            (Path(d) / "wf_b.yml").write_text("name: b\n")
            (Path(d) / "not_yaml.txt").write_text("ignore\n")
            workflows = list_workflows(search_dirs=[d])
            assert "wf_a" in workflows
            assert "wf_b" in workflows
            assert "not_yaml" not in workflows

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            workflows = list_workflows(search_dirs=[d])
            # Should still include builtins
            assert "complexity_refactor" in workflows

    def test_sorted_output(self):
        workflows = list_workflows()
        assert workflows == sorted(workflows)
