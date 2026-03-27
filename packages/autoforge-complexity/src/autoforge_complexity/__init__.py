"""
AutoForge Complexity Adapter.

Wraps the complexity-accounting tool to provide Net Complexity Score (NCS)
measurements through the standard MetricAdapter interface.
"""

from autoforge_complexity._adapter import ComplexityAdapter

__all__ = ["ComplexityAdapter"]
__version__ = "0.1.0"
