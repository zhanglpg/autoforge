"""
Base metric adapter interface.

All metric adapters implement the MetricAdapter protocol defined in models.py.
This module provides a concrete base class with shared utilities.
"""

from __future__ import annotations

import logging
import shutil
from abc import ABC, abstractmethod

from autoforge.models import MetricResult

logger = logging.getLogger(__name__)


class BaseMetricAdapter(ABC):
    """Abstract base class for metric adapters with shared utilities."""

    name: str = ""
    supported_languages: list[str] = []

    def check_tool_available(self, tool_cmd: str) -> bool:
        """Check if a CLI tool is available on PATH."""
        return shutil.which(tool_cmd) is not None

    @abstractmethod
    def check_prerequisites(self, repo_path: str) -> bool:
        """Verify tool is installed and repo is compatible."""
        ...

    @abstractmethod
    def measure(self, repo_path: str, target_path: str) -> MetricResult:
        """Run the metric tool and return normalized result."""
        ...

    @abstractmethod
    def identify_targets(self, result: MetricResult, n: int) -> list[str]:
        """Return top-n files to target for improvement (worst first)."""
        ...
