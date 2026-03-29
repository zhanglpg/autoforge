"""
Workflow and Adapter Registry for AutoForge.

Manages the catalog of available workflows and their corresponding
metric adapters. Loads workflow configs from YAML files.

Adapters are discovered via the ``autoforge.adapters`` entry-point group.
Third-party packages register adapters by declaring an entry point, e.g.::

    [project.entry-points."autoforge.adapters"]
    complexity = "autoforge_complexity:ComplexityAdapter"
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from pathlib import Path

import yaml

from autoforge.adapters.base import BaseMetricAdapter
from autoforge.models import WorkflowConfig

logger = logging.getLogger(__name__)

# Manually registered adapters (via register_adapter())
_ADAPTER_REGISTRY: dict[str, type[BaseMetricAdapter]] = {}

# Built-in workflow directory
_BUILTIN_WORKFLOWS_DIR = Path(__file__).parent / "workflows"

# Cache for discovered entry-point adapters
_EP_CACHE: dict[str, type[BaseMetricAdapter]] | None = None


def _discover_entry_point_adapters() -> dict[str, type[BaseMetricAdapter]]:
    """Discover adapters from installed entry points (cached)."""
    global _EP_CACHE
    if _EP_CACHE is not None:
        return _EP_CACHE

    _EP_CACHE = {}
    eps = entry_points(group="autoforge.adapters")
    for ep in eps:
        try:
            cls = ep.load()
            _EP_CACHE[ep.name] = cls
            logger.debug("Discovered adapter via entry point: %s", ep.name)
        except Exception as e:
            logger.warning("Failed to load adapter entry point '%s': %s", ep.name, e)

    return _EP_CACHE


def register_adapter(name: str, adapter_cls: type[BaseMetricAdapter]) -> None:
    """Register a new metric adapter type (programmatic registration)."""
    _ADAPTER_REGISTRY[name] = adapter_cls
    logger.info("Registered adapter: %s", name)


def get_adapter(name: str, **kwargs) -> BaseMetricAdapter:
    """Instantiate a registered adapter by name.

    Looks up in order: manually registered adapters, then entry-point adapters.
    """
    # Check manual registry first
    cls = _ADAPTER_REGISTRY.get(name)
    if cls is None:
        # Fall back to entry-point discovery
        ep_adapters = _discover_entry_point_adapters()
        cls = ep_adapters.get(name)

    if cls is None:
        available = ", ".join(sorted(list_adapters())) or "none"
        install_hint = _get_install_hint(name)
        msg = f"Unknown adapter '{name}'. Available: {available}"
        if install_hint:
            msg += f"\n\nTo install: {install_hint}"
        raise ValueError(msg)
    return cls(**kwargs)


def _get_install_hint(name: str) -> str:
    """Return a pip install hint for known adapter names."""
    hints = {
        "complexity": "pip install autoforge-complexity",
        "test_quality": "pip install autoforge-test-quality",
        "go_test_quality": "pip install autoforge-go-test-quality",
    }
    return hints.get(name, "")


def list_adapters() -> list[str]:
    """List all registered adapter names (manual + entry-point)."""
    ep_adapters = _discover_entry_point_adapters()
    all_names = set(_ADAPTER_REGISTRY.keys()) | set(ep_adapters.keys())
    return sorted(all_names)


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
