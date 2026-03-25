"""
Workflow and Adapter Registry for AutoForge.

Manages the catalog of available workflows and their corresponding
metric adapters. Loads workflow configs from YAML files.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from autoforge.adapters.base import BaseMetricAdapter
from autoforge.adapters.complexity import ComplexityAdapter
from autoforge.models import WorkflowConfig

logger = logging.getLogger(__name__)

# Built-in adapter registry
_ADAPTER_REGISTRY: dict[str, type[BaseMetricAdapter]] = {
    "complexity": ComplexityAdapter,
}

# Built-in workflow directory
_BUILTIN_WORKFLOWS_DIR = Path(__file__).parent / "workflows"


def register_adapter(name: str, adapter_cls: type[BaseMetricAdapter]) -> None:
    """Register a new metric adapter type."""
    _ADAPTER_REGISTRY[name] = adapter_cls
    logger.info("Registered adapter: %s", name)


def get_adapter(name: str, **kwargs) -> BaseMetricAdapter:
    """Instantiate a registered adapter by name."""
    cls = _ADAPTER_REGISTRY.get(name)
    if cls is None:
        available = ", ".join(sorted(_ADAPTER_REGISTRY.keys()))
        raise ValueError(f"Unknown adapter '{name}'. Available: {available}")
    return cls(**kwargs)


def list_adapters() -> list[str]:
    """List all registered adapter names."""
    return sorted(_ADAPTER_REGISTRY.keys())


def load_workflow_config(path: str) -> WorkflowConfig:
    """Load a workflow configuration from a YAML file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Workflow config not found: {path}")
    with open(p) as f:
        data = yaml.safe_load(f)
    return WorkflowConfig.from_dict(data)


def find_workflow_config(name: str, search_dirs: list[str] | None = None) -> WorkflowConfig:
    """
    Find and load a workflow config by name.

    Searches:
    1. Provided search directories
    2. Current directory's .autoforge/ folder
    3. Built-in workflows directory
    """
    search_paths = []

    if search_dirs:
        for d in search_dirs:
            search_paths.append(Path(d))

    # Current directory
    search_paths.append(Path.cwd() / ".autoforge")

    # Built-in
    search_paths.append(_BUILTIN_WORKFLOWS_DIR)

    for base in search_paths:
        for ext in (".yaml", ".yml"):
            candidate = base / f"{name}{ext}"
            if candidate.exists():
                logger.info("Found workflow config: %s", candidate)
                return load_workflow_config(str(candidate))

    available = list_workflows(search_dirs)
    raise FileNotFoundError(
        f"Workflow '{name}' not found. Available: {', '.join(available) or 'none'}"
    )


def list_workflows(search_dirs: list[str] | None = None) -> list[str]:
    """List all available workflow names."""
    workflows = set()

    search_paths = []
    if search_dirs:
        for d in search_dirs:
            search_paths.append(Path(d))
    search_paths.append(Path.cwd() / ".autoforge")
    search_paths.append(_BUILTIN_WORKFLOWS_DIR)

    for base in search_paths:
        if base.is_dir():
            for f in base.iterdir():
                if f.suffix in (".yaml", ".yml"):
                    workflows.add(f.stem)

    return sorted(workflows)
