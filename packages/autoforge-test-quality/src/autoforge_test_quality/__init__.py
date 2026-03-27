"""
AutoForge Test Quality Adapter.

Combines coverage, function gap analysis, assertion quality, and optional
mutation testing into a single 0-100 composite score (TQS).
"""

from autoforge_test_quality._adapter import (
    AssertionInfo,
    AssertionStrength,
    FileAssertionReport,
    FileCoverageData,
    FileTestQuality,
    FunctionCoverageResult,
    FunctionInfo,
    MutationResult,
    TQSWeights,
    TestQualityAdapter,
    analyze_test_file_assertions,
    classify_assertion,
    compute_assertion_quality_score,
    compute_coverage_score,
    compute_effective_weights,
    compute_file_tqs,
    discover_python_source_files,
    discover_test_files,
    extract_public_functions,
    find_uncovered_functions,
    map_tests_to_sources,
    parse_coverage_json,
)

__all__ = [
    "AssertionInfo",
    "AssertionStrength",
    "FileAssertionReport",
    "FileCoverageData",
    "FileTestQuality",
    "FunctionCoverageResult",
    "FunctionInfo",
    "MutationResult",
    "TQSWeights",
    "TestQualityAdapter",
    "analyze_test_file_assertions",
    "classify_assertion",
    "compute_assertion_quality_score",
    "compute_coverage_score",
    "compute_effective_weights",
    "compute_file_tqs",
    "discover_python_source_files",
    "discover_test_files",
    "extract_public_functions",
    "find_uncovered_functions",
    "map_tests_to_sources",
    "parse_coverage_json",
]
__version__ = "0.1.0"
