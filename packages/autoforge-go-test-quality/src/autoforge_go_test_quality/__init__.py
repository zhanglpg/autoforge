"""
AutoForge Go Test Quality Adapter.

Combines coverage, function gap analysis, assertion quality, and optional
mutation testing into a single 0-100 composite score (TQS) for Go codebases.
"""

from autoforge_go_test_quality._adapter import (
    AssertionInfo,
    AssertionStrength,
    FileAssertionReport,
    FileCoverageData,
    FileTestQuality,
    FunctionCoverageResult,
    FunctionInfo,
    GoTestQualityAdapter,
    GoTestQualityIndicators,
    MutationResult,
    TQSWeights,
    analyze_go_test_file_assertions,
    classify_go_assertion,
    compute_assertion_quality_score,
    compute_effective_weights,
    compute_file_tqs,
    discover_go_source_files,
    discover_go_test_files,
    map_go_tests_to_sources,
    parse_go_cover_func,
    parse_go_coverage_profile,
)

__all__ = [
    "AssertionInfo",
    "AssertionStrength",
    "FileAssertionReport",
    "FileCoverageData",
    "FileTestQuality",
    "FunctionCoverageResult",
    "FunctionInfo",
    "GoTestQualityAdapter",
    "GoTestQualityIndicators",
    "MutationResult",
    "TQSWeights",
    "analyze_go_test_file_assertions",
    "classify_go_assertion",
    "compute_assertion_quality_score",
    "compute_effective_weights",
    "compute_file_tqs",
    "discover_go_source_files",
    "discover_go_test_files",
    "map_go_tests_to_sources",
    "parse_go_cover_func",
    "parse_go_coverage_profile",
]
__version__ = "0.1.0"
