"""Tests for autoforge.registry."""

import pytest
from pathlib import Path

from autoforge.registry import (
    get_adapter,
    list_adapters,
    load_workflow_config,
    list_workflows,
)
from autoforge.adapters.complexity import ComplexityAdapter


class TestAdapterRegistry:
    def test_list_adapters(self):
        adapters = list_adapters()
        assert "complexity" in adapters

    def test_get_complexity_adapter(self):
        adapter = get_adapter("complexity")
        assert isinstance(adapter, ComplexityAdapter)
        assert adapter.name == "complexity"

    def test_get_unknown_adapter(self):
        with pytest.raises(ValueError, match="Unknown adapter"):
            get_adapter("nonexistent")


class TestWorkflowConfig:
    def test_load_builtin_complexity(self):
        workflows_dir = Path(__file__).parent.parent / "src" / "autoforge" / "workflows"
        cfg = load_workflow_config(str(workflows_dir / "complexity_refactor.yaml"))
        assert cfg.name == "complexity_refactor"
        assert cfg.primary_metric.name == "net_complexity_score"
        assert cfg.primary_metric.direction == "minimize"
        assert cfg.primary_metric.default_target == 3.0
        assert cfg.budget.max_iterations == 10
        assert cfg.budget.stall_patience == 3
        assert cfg.agent.skill == "refactor-complexity"

    def test_load_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            load_workflow_config("/nonexistent/workflow.yaml")

    def test_list_workflows(self):
        workflows_dir = str(
            Path(__file__).parent.parent / "src" / "autoforge" / "workflows"
        )
        workflows = list_workflows(search_dirs=[workflows_dir])
        assert "complexity_refactor" in workflows
