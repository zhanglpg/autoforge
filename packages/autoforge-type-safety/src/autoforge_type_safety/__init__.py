"""
AutoForge Type Safety Adapter.

Wraps pyright or mypy to measure type error count through the standard
MetricAdapter interface.
"""

from autoforge_type_safety._adapter import (
    FileTypeResult,
    TypeCheckSummary,
    TypeDiagnostic,
    TypeSafetyAdapter,
    build_metric_result,
    normalize_paths,
    parse_mypy_json,
    parse_pyright_json,
)

__all__ = [
    "FileTypeResult",
    "TypeCheckSummary",
    "TypeDiagnostic",
    "TypeSafetyAdapter",
    "build_metric_result",
    "normalize_paths",
    "parse_mypy_json",
    "parse_pyright_json",
]
__version__ = "0.1.0"
