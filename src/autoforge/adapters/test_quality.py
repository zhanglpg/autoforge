"""
Test Quality Score (TQS) metric adapter.

Combines coverage, function gap analysis, assertion quality, and optional
mutation testing into a single 0-100 composite score. All intermediate
data models are adapter-internal — the framework sees only MetricResult.
"""

from __future__ import annotations

import ast
import enum
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from autoforge.adapters.base import BaseMetricAdapter
from autoforge.models import Direction, MetricResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Classification
# ---------------------------------------------------------------------------

class AssertionStrength(enum.Enum):
    """Classification tier for a single assertion."""

    STRONG = "strong"
    STRUCTURAL = "structural"
    WEAK = "weak"

    @property
    def weight(self) -> float:
        """Numeric weight for score computation."""
        _weights = {
            AssertionStrength.STRONG: 1.0,
            AssertionStrength.STRUCTURAL: 0.5,
            AssertionStrength.WEAK: 0.2,
        }
        return _weights[self]


# ---------------------------------------------------------------------------
# Internal Data Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FileCoverageData:
    """Coverage measurements for a single source file."""

    file_path: str
    line_coverage_pct: float
    branch_coverage_pct: float
    covered_lines: frozenset[int]
    missing_lines: frozenset[int]
    covered_branches: int
    total_branches: int

    @property
    def combined_score(self) -> float:
        """Weighted coverage score: 0.6 * line + 0.4 * branch."""
        return 0.6 * self.line_coverage_pct + 0.4 * self.branch_coverage_pct


@dataclass(frozen=True)
class FunctionInfo:
    """A public function/method extracted from source AST."""

    name: str
    file_path: str
    start_line: int
    end_line: int
    is_method: bool
    is_property: bool


@dataclass(frozen=True)
class FunctionCoverageResult:
    """Function-level coverage gap analysis for one source file."""

    file_path: str
    total_public_functions: int
    tested_functions: tuple[str, ...]
    untested_functions: tuple[str, ...]

    @property
    def score(self) -> float:
        """(tested / total) * 100, or 100.0 if no public functions."""
        if self.total_public_functions == 0:
            return 100.0
        return (len(self.tested_functions) / self.total_public_functions) * 100.0


@dataclass(frozen=True)
class AssertionInfo:
    """A single assertion found in a test file."""

    test_function: str
    line_number: int
    assertion_text: str
    strength: AssertionStrength


@dataclass(frozen=True)
class FileAssertionReport:
    """Assertion analysis for one test file."""

    test_file_path: str
    test_function_count: int
    assertions: tuple[AssertionInfo, ...]
    strong_count: int
    structural_count: int
    weak_count: int

    @property
    def weighted_score(self) -> float:
        """Assertion quality score 0-100 for this file.

        Formula: min(100, weighted_density * 33.3)
        where weighted_density = sum(weights) / test_function_count
        """
        if self.test_function_count == 0:
            return 0.0
        total_weight = sum(a.strength.weight for a in self.assertions)
        weighted_density = total_weight / self.test_function_count
        return min(100.0, weighted_density * 33.3)

    @property
    def total_count(self) -> int:
        """Total assertion count across all tiers."""
        return self.strong_count + self.structural_count + self.weak_count


@dataclass(frozen=True)
class MutationResult:
    """Mutation testing results for one source file."""

    file_path: str
    total_mutants: int
    killed_mutants: int
    survived_mutants: int
    timeout_mutants: int
    error_mutants: int

    @property
    def score(self) -> float:
        """(killed / total) * 100, or 0.0 if no mutants."""
        if self.total_mutants == 0:
            return 0.0
        return (self.killed_mutants / self.total_mutants) * 100.0


@dataclass(frozen=True)
class FileTestQuality:
    """Complete TQS breakdown for a single source file."""

    file_path: str
    coverage: FileCoverageData | None
    function_coverage: FunctionCoverageResult | None
    assertion_quality: FileAssertionReport | None
    mutation: MutationResult | None
    coverage_score: float
    function_coverage_score: float
    assertion_quality_score: float
    mutation_score: float
    composite_tqs: float
    mapped_test_files: tuple[str, ...]


@dataclass
class TQSWeights:
    """Weight configuration with redistribution support."""

    coverage: float = 0.30
    function_coverage: float = 0.20
    assertion_quality: float = 0.30
    mutation: float = 0.20

    def effective_weights(self) -> dict[str, float]:
        """Normalize weights, redistributing disabled (0.0) metrics proportionally."""
        return compute_effective_weights(self)


# ---------------------------------------------------------------------------
# Module-Level Pure Helper Functions — Coverage
# ---------------------------------------------------------------------------

def parse_coverage_json(coverage_json: dict) -> dict[str, FileCoverageData]:
    """Parse pytest-cov JSON report into per-file FileCoverageData."""
    results: dict[str, FileCoverageData] = {}
    files = coverage_json.get("files", {})

    for file_path, file_data in files.items():
        summary = file_data.get("summary", {})
        covered_lines = frozenset(file_data.get("executed_lines", []))
        missing_lines = frozenset(file_data.get("missing_lines", []))

        line_pct = summary.get("percent_covered", 0.0)
        branch_pct = summary.get("percent_covered_branches", 0.0)
        covered_branches = summary.get("covered_branches", 0)
        total_branches = summary.get("num_branches", 0)

        results[file_path] = FileCoverageData(
            file_path=file_path,
            line_coverage_pct=line_pct,
            branch_coverage_pct=branch_pct,
            covered_lines=covered_lines,
            missing_lines=missing_lines,
            covered_branches=covered_branches,
            total_branches=total_branches,
        )

    return results


def compute_coverage_score(line_pct: float, branch_pct: float) -> float:
    """Compute combined coverage score: 0.6 * line + 0.4 * branch."""
    return 0.6 * line_pct + 0.4 * branch_pct


# ---------------------------------------------------------------------------
# Module-Level Pure Helper Functions — AST / Function Extraction
# ---------------------------------------------------------------------------

def extract_public_functions(source_code: str, file_path: str) -> list[FunctionInfo]:
    """AST-parse Python source and return all public functions and methods.

    "Public" means: name does not start with underscore.
    Includes class methods and standalone functions.
    """
    try:
        tree = ast.parse(source_code, filename=file_path)
    except SyntaxError:
        logger.warning("Failed to parse %s, skipping function extraction", file_path)
        return []

    functions: list[FunctionInfo] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("_"):
                        continue
                    is_prop = any(
                        isinstance(d, ast.Name) and d.id == "property"
                        or isinstance(d, ast.Attribute) and d.attr == "property"
                        for d in item.decorator_list
                    )
                    functions.append(FunctionInfo(
                        name=f"{node.name}.{item.name}",
                        file_path=file_path,
                        start_line=item.lineno,
                        end_line=item.end_lineno or item.lineno,
                        is_method=True,
                        is_property=is_prop,
                    ))

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            functions.append(FunctionInfo(
                name=node.name,
                file_path=file_path,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                is_method=False,
                is_property=False,
            ))

    return functions


def find_uncovered_functions(
    functions: list[FunctionInfo],
    covered_lines: frozenset[int],
) -> FunctionCoverageResult:
    """Cross-reference function line ranges with coverage to find untested functions.

    A function is "tested" if any line in its range [start_line, end_line] is covered.
    """
    if not functions:
        return FunctionCoverageResult(
            file_path="",
            total_public_functions=0,
            tested_functions=(),
            untested_functions=(),
        )

    tested: list[str] = []
    untested: list[str] = []

    for func in functions:
        func_lines = set(range(func.start_line, func.end_line + 1))
        if func_lines & covered_lines:
            tested.append(func.name)
        else:
            untested.append(func.name)

    return FunctionCoverageResult(
        file_path=functions[0].file_path,
        total_public_functions=len(functions),
        tested_functions=tuple(tested),
        untested_functions=tuple(untested),
    )


# ---------------------------------------------------------------------------
# Module-Level Pure Helper Functions — Assertion Analysis
# ---------------------------------------------------------------------------

# Strong assertions: verify specific behavior
_STRONG_ASSERT_METHODS = frozenset({
    "assertEqual", "assertNotEqual",
    "assertAlmostEqual", "assertNotAlmostEqual",
    "assertRaises", "assertRaisesRegex",
    "assertWarns", "assertWarnsRegex",
    "assertLogs", "assertNoLogs",
    "assertCountEqual",
    "assertMultiLineEqual",
    "assertSequenceEqual", "assertListEqual", "assertTupleEqual",
    "assertSetEqual", "assertDictEqual",
    "assertRegex", "assertNotRegex",
})

# Structural assertions: verify shape, not specific values
_STRUCTURAL_ASSERT_METHODS = frozenset({
    "assertIsInstance", "assertNotIsInstance",
    "assertIn", "assertNotIn",
    "assertGreater", "assertGreaterEqual",
    "assertLess", "assertLessEqual",
})

# Weak assertions: prove existence, not correctness
_WEAK_ASSERT_METHODS = frozenset({
    "assertTrue", "assertFalse",
    "assertIsNone", "assertIsNotNone",
    "assertIs", "assertIsNot",
})


def classify_assertion(node: ast.AST) -> AssertionStrength:
    """Classify a single AST assertion node by strength tier."""
    # bare assert statement: check comparisons
    if isinstance(node, ast.Assert):
        test = node.test
        # assert x == y, assert x != y → strong
        if isinstance(test, ast.Compare):
            for op in test.ops:
                if isinstance(op, (ast.Eq, ast.NotEq)):
                    return AssertionStrength.STRONG
                if isinstance(op, (ast.In, ast.NotIn, ast.Is, ast.IsNot)):
                    return AssertionStrength.STRUCTURAL
                if isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                    return AssertionStrength.STRUCTURAL
        # assert func_call(...) — weak by default
        if isinstance(test, ast.Call):
            return AssertionStrength.WEAK
        # bare assert x — weak
        return AssertionStrength.WEAK

    # self.assertXxx(...) or unittest method calls
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        method = node.func.attr
        if method in _STRONG_ASSERT_METHODS:
            return AssertionStrength.STRONG
        if method in _STRUCTURAL_ASSERT_METHODS:
            return AssertionStrength.STRUCTURAL
        if method in _WEAK_ASSERT_METHODS:
            return AssertionStrength.WEAK

    # pytest.raises(...) — strong
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "raises":
            return AssertionStrength.STRONG

    return AssertionStrength.WEAK


def _get_assertion_text(node: ast.AST) -> str:
    """Extract a short text representation of an assertion node."""
    try:
        return ast.unparse(node)[:80]
    except Exception:
        return "<assertion>"


def analyze_test_file_assertions(
    source_code: str,
    file_path: str,
) -> FileAssertionReport:
    """AST-parse a test file and classify all assertions found."""
    try:
        tree = ast.parse(source_code, filename=file_path)
    except SyntaxError:
        logger.warning("Failed to parse test file %s", file_path)
        return FileAssertionReport(
            test_file_path=file_path,
            test_function_count=0,
            assertions=(),
            strong_count=0,
            structural_count=0,
            weak_count=0,
        )

    assertions: list[AssertionInfo] = []
    test_function_count = 0

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test"):
            continue

        test_function_count += 1

        for child in ast.walk(node):
            strength: AssertionStrength | None = None

            if isinstance(child, ast.Assert):
                strength = classify_assertion(child)
            elif isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                method = child.func.attr
                if method in _STRONG_ASSERT_METHODS | _STRUCTURAL_ASSERT_METHODS | _WEAK_ASSERT_METHODS:
                    strength = classify_assertion(child)
                elif method == "raises":
                    strength = classify_assertion(child)

            if strength is not None:
                assertions.append(AssertionInfo(
                    test_function=node.name,
                    line_number=child.lineno,
                    assertion_text=_get_assertion_text(child),
                    strength=strength,
                ))

    strong = sum(1 for a in assertions if a.strength is AssertionStrength.STRONG)
    structural = sum(1 for a in assertions if a.strength is AssertionStrength.STRUCTURAL)
    weak = sum(1 for a in assertions if a.strength is AssertionStrength.WEAK)

    return FileAssertionReport(
        test_file_path=file_path,
        test_function_count=test_function_count,
        assertions=tuple(assertions),
        strong_count=strong,
        structural_count=structural,
        weak_count=weak,
    )


def compute_assertion_quality_score(report: FileAssertionReport) -> float:
    """Compute 0-100 assertion quality score from an assertion report.

    Formula: min(100, weighted_density * 33.3)
    where weighted_density = sum(weights) / test_function_count
    """
    return report.weighted_score


# ---------------------------------------------------------------------------
# Module-Level Pure Helper Functions — Test-to-Source Mapping
# ---------------------------------------------------------------------------

def map_tests_to_sources(
    source_files: list[str],
    test_files: list[str],
    test_dir_pattern: str = "tests/",
) -> dict[str, list[str]]:
    """Map source files to their test files using naming conventions.

    Convention: test_foo.py → foo.py, tests/test_bar.py → bar.py
    Returns {source_file_path: [test_file_paths]}.
    Source files with no matching test files map to empty lists.

    Phase 1: Convention-based only.
    """
    # Build lookup: base_name → list of test file paths
    test_lookup: dict[str, list[str]] = {}
    for tf in test_files:
        base = os.path.basename(tf)
        # test_foo.py → foo.py
        if base.startswith("test_"):
            source_name = base[5:]  # strip "test_"
        # foo_test.py → foo.py
        elif base.endswith("_test.py"):
            source_name = base[:-8] + ".py"
        else:
            continue
        test_lookup.setdefault(source_name, []).append(tf)

    result: dict[str, list[str]] = {}
    for sf in source_files:
        base = os.path.basename(sf)
        result[sf] = test_lookup.get(base, [])

    return result


# ---------------------------------------------------------------------------
# Module-Level Pure Helper Functions — Weight Computation
# ---------------------------------------------------------------------------

def compute_effective_weights(weights: TQSWeights) -> dict[str, float]:
    """Normalize weights, redistributing disabled (0.0) metrics proportionally."""
    raw = {
        "coverage": weights.coverage,
        "function_coverage": weights.function_coverage,
        "assertion_quality": weights.assertion_quality,
        "mutation": weights.mutation,
    }
    active = {k: v for k, v in raw.items() if v > 0}
    total = sum(active.values())
    if total == 0:
        # All disabled — equal weight fallback
        n = len(raw)
        return {k: 1.0 / n for k in raw}
    return {k: (v / total if k in active else 0.0) for k, v in raw.items()}


def compute_file_tqs(
    coverage_score: float,
    function_coverage_score: float,
    assertion_quality_score: float,
    mutation_score: float,
    weights: dict[str, float],
) -> float:
    """Compute composite TQS for a single file given sub-scores and effective weights."""
    tqs = (
        weights.get("coverage", 0) * coverage_score
        + weights.get("function_coverage", 0) * function_coverage_score
        + weights.get("assertion_quality", 0) * assertion_quality_score
        + weights.get("mutation", 0) * mutation_score
    )
    return max(0.0, min(100.0, tqs))


# ---------------------------------------------------------------------------
# Module-Level Pure Helper Functions — File Discovery
# ---------------------------------------------------------------------------

_TEST_FILE_PATTERNS = {"test_", "conftest"}
_TEST_DIR_NAMES = {"tests", "test"}


def discover_python_source_files(
    target_path: str,
    exclude_tests: bool = True,
) -> list[str]:
    """Find all Python source files under target_path, excluding test files."""
    results: list[str] = []
    for root, dirs, files in os.walk(target_path):
        if exclude_tests:
            dirs[:] = [d for d in dirs if d not in _TEST_DIR_NAMES]
        for f in files:
            if not f.endswith(".py"):
                continue
            if exclude_tests:
                if f.startswith("test_") or f.endswith("_test.py") or f == "conftest.py":
                    continue
            results.append(os.path.join(root, f))
    return sorted(results)


def discover_test_files(
    repo_path: str,
    test_dir_pattern: str,
) -> list[str]:
    """Find all Python test files matching the test directory pattern."""
    results: list[str] = []
    test_dir = os.path.join(repo_path, test_dir_pattern)
    if os.path.isdir(test_dir):
        for root, _dirs, files in os.walk(test_dir):
            for f in files:
                if f.endswith(".py") and (f.startswith("test_") or f.endswith("_test.py")):
                    results.append(os.path.join(root, f))
    return sorted(results)


# ---------------------------------------------------------------------------
# TestQualityAdapter
# ---------------------------------------------------------------------------

class TestQualityAdapter(BaseMetricAdapter):
    """Metric adapter for Test Quality Score (TQS) measurement.

    Combines coverage, function gap analysis, assertion quality, and optional
    mutation testing into a single 0-100 composite score.
    """

    __test__ = False  # Prevent pytest from collecting this as a test class

    name = "test_quality"
    supported_languages = ["python"]

    def __init__(
        self,
        *,
        coverage_weight: float = 0.30,
        func_coverage_weight: float = 0.20,
        assertion_weight: float = 0.30,
        mutation_weight: float = 0.20,
        mutation_sample_size: int = 5,
        test_command: str = "pytest",
        test_dir_pattern: str = "tests/",
        branch_coverage: bool = True,
        coverage_timeout: int = 300,
        mutation_timeout: int = 600,
    ) -> None:
        self.weights = TQSWeights(
            coverage=coverage_weight,
            function_coverage=func_coverage_weight,
            assertion_quality=assertion_weight,
            mutation=mutation_weight,
        )
        self.mutation_sample_size = mutation_sample_size
        self.test_command = test_command
        self.test_dir_pattern = test_dir_pattern
        self.branch_coverage = branch_coverage
        self.coverage_timeout = coverage_timeout
        self.mutation_timeout = mutation_timeout
        self._detailed_results: dict[str, FileTestQuality] = {}

    # --- BaseMetricAdapter interface ---

    def check_prerequisites(self, repo_path: str) -> bool:
        """Verify pytest, coverage.py, and optionally mutmut are available."""
        if not self.check_tool_available("pytest"):
            logger.warning("pytest not found on PATH")
            return False

        try:
            import coverage as _cov  # noqa: F401
        except ImportError:
            logger.warning(
                "coverage not installed. Install with: pip install coverage"
            )
            return False

        if self.weights.mutation > 0:
            if not self.check_tool_available("mutmut"):
                logger.warning(
                    "mutmut not found on PATH but mutation_weight > 0. "
                    "Install with: pip install mutmut"
                )
                return False

        return True

    def measure(self, repo_path: str, target_path: str) -> MetricResult:
        """Run all TQS sub-metrics and return composite score as MetricResult."""
        # Step 1-2: Collect coverage data
        coverage_data = self._collect_coverage(repo_path, target_path)

        # Step 3-6: Analyze all files (function gaps, assertions, weights)
        file_results = self._analyze_all_files(repo_path, target_path, coverage_data)

        # Step 5 (optional): Mutation testing
        if self.weights.mutation > 0:
            sample = self._select_mutation_sample(file_results, self.mutation_sample_size)
            if sample:
                mutation_data = self._run_sampled_mutation(repo_path, sample)
                # Re-compute TQS for mutated files
                eff_weights = self.weights.effective_weights()
                for fp, mut_result in mutation_data.items():
                    if fp in file_results:
                        old = file_results[fp]
                        new_tqs = compute_file_tqs(
                            old.coverage_score,
                            old.function_coverage_score,
                            old.assertion_quality_score,
                            mut_result.score,
                            eff_weights,
                        )
                        file_results[fp] = FileTestQuality(
                            file_path=old.file_path,
                            coverage=old.coverage,
                            function_coverage=old.function_coverage,
                            assertion_quality=old.assertion_quality,
                            mutation=mut_result,
                            coverage_score=old.coverage_score,
                            function_coverage_score=old.function_coverage_score,
                            assertion_quality_score=old.assertion_quality_score,
                            mutation_score=mut_result.score,
                            composite_tqs=new_tqs,
                            mapped_test_files=old.mapped_test_files,
                        )

        # Step 7: Aggregate
        aggregate_tqs = self._compute_aggregate_tqs(file_results)

        # Step 9: Cache for identify_targets
        self._detailed_results = file_results

        # Step 8: Build MetricResult
        breakdown = {fp: ftq.composite_tqs for fp, ftq in file_results.items()}

        return MetricResult(
            metric_name="test_quality_score",
            value=aggregate_tqs,
            unit="score",
            direction=Direction.MAXIMIZE,
            breakdown=breakdown,
            tool="test_quality",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def identify_targets(self, result: MetricResult, n: int) -> list[str]:
        """Return top-n source files with lowest TQS (worst-tested first)."""
        sorted_files = sorted(
            result.breakdown.items(),
            key=lambda kv: kv[1],
        )
        return [path for path, _ in sorted_files[:n]]

    # --- Internal orchestration ---

    def _collect_coverage(
        self,
        repo_path: str,
        target_path: str,
    ) -> dict[str, FileCoverageData]:
        """Run pytest-cov and parse JSON output into per-file coverage data."""
        cmd = self._build_coverage_command(target_path)
        logger.info("Running coverage: %s", " ".join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=self.coverage_timeout,
        )

        # pytest may return non-zero if tests fail, but coverage JSON is still written
        cov_json_path = os.path.join(repo_path, "coverage.json")
        if not os.path.exists(cov_json_path):
            logger.warning(
                "Coverage JSON not generated (pytest exit %d). stderr: %s",
                result.returncode,
                result.stderr[:500],
            )
            return {}

        with open(cov_json_path) as f:
            coverage_json = json.load(f)

        # Clean up
        try:
            os.remove(cov_json_path)
        except OSError:
            pass

        return parse_coverage_json(coverage_json)

    def _build_coverage_command(self, target_path: str) -> list[str]:
        """Build the pytest --cov command with appropriate flags."""
        cmd = [
            sys.executable, "-m", "pytest",
            f"--cov={target_path}",
            "--cov-report=json",
            "-q", "--tb=no", "--no-header",
        ]
        if self.branch_coverage:
            cmd.append("--cov-branch")
        return cmd

    def _analyze_all_files(
        self,
        repo_path: str,
        target_path: str,
        coverage_data: dict[str, FileCoverageData],
    ) -> dict[str, FileTestQuality]:
        """Compute per-file TQS for all source files in target_path."""
        source_files = discover_python_source_files(target_path)
        test_files = discover_test_files(repo_path, self.test_dir_pattern)
        test_map = map_tests_to_sources(source_files, test_files, self.test_dir_pattern)
        eff_weights = self.weights.effective_weights()

        # Build normalized coverage lookup to handle path mismatches.
        # coverage.json reports paths relative to repo_path (cwd for pytest),
        # while discover_python_source_files returns absolute paths.
        # Resolve coverage paths to absolute before normalizing.
        norm_coverage: dict[str, FileCoverageData] = {}
        for cov_path, cov_data in coverage_data.items():
            abs_cov = os.path.join(repo_path, cov_path) if not os.path.isabs(cov_path) else cov_path
            norm_coverage[os.path.normpath(abs_cov)] = cov_data

        file_results: dict[str, FileTestQuality] = {}

        for sf in source_files:
            # Coverage data — use normalized path for lookup
            cov = norm_coverage.get(os.path.normpath(sf))
            cov_score = cov.combined_score if cov else 0.0

            # Function gap analysis
            try:
                with open(sf) as fh:
                    source_code = fh.read()
                functions = extract_public_functions(source_code, sf)
            except (OSError, UnicodeDecodeError):
                functions = []

            covered_lines = cov.covered_lines if cov else frozenset()
            func_cov = find_uncovered_functions(functions, covered_lines)
            func_score = func_cov.score

            # Assertion quality — merge reports if multiple test files
            mapped_tests = test_map.get(sf, [])
            assertion_report: FileAssertionReport | None = None
            assertion_score = 0.0

            if mapped_tests:
                all_assertions: list[AssertionInfo] = []
                total_test_funcs = 0
                for tf in mapped_tests:
                    try:
                        with open(tf) as fh:
                            test_code = fh.read()
                        report = analyze_test_file_assertions(test_code, tf)
                        all_assertions.extend(report.assertions)
                        total_test_funcs += report.test_function_count
                    except (OSError, UnicodeDecodeError):
                        continue

                strong = sum(1 for a in all_assertions if a.strength is AssertionStrength.STRONG)
                structural = sum(1 for a in all_assertions if a.strength is AssertionStrength.STRUCTURAL)
                weak = sum(1 for a in all_assertions if a.strength is AssertionStrength.WEAK)

                assertion_report = FileAssertionReport(
                    test_file_path=mapped_tests[0],
                    test_function_count=total_test_funcs,
                    assertions=tuple(all_assertions),
                    strong_count=strong,
                    structural_count=structural,
                    weak_count=weak,
                )
                assertion_score = compute_assertion_quality_score(assertion_report)

            composite = compute_file_tqs(
                cov_score, func_score, assertion_score, 0.0, eff_weights,
            )

            file_results[sf] = FileTestQuality(
                file_path=sf,
                coverage=cov,
                function_coverage=func_cov,
                assertion_quality=assertion_report,
                mutation=None,
                coverage_score=cov_score,
                function_coverage_score=func_score,
                assertion_quality_score=assertion_score,
                mutation_score=0.0,
                composite_tqs=composite,
                mapped_test_files=tuple(mapped_tests),
            )

        return file_results

    def _run_sampled_mutation(
        self,
        repo_path: str,
        sample_files: list[str],
    ) -> dict[str, MutationResult]:
        """Run mutmut on a sample of source files and return results."""
        results: dict[str, MutationResult] = {}

        for source_file in sample_files:
            cmd = self._build_mutation_command(source_file)
            logger.info("Running mutation: %s", " ".join(cmd))

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=repo_path,
                    timeout=self.mutation_timeout,
                )
            except subprocess.TimeoutExpired:
                logger.warning("Mutation testing timed out for %s", source_file)
                continue

            # Parse mutmut results JSON
            results_cmd = [
                sys.executable, "-m", "mutmut", "results", "--json",
            ]
            try:
                res_proc = subprocess.run(
                    results_cmd,
                    capture_output=True,
                    text=True,
                    cwd=repo_path,
                    timeout=30,
                )
                data = json.loads(res_proc.stdout)
                killed = data.get("killed", 0)
                survived = data.get("survived", 0)
                timeout = data.get("timeout", 0)
                errors = data.get("suspicious", 0)
                total = killed + survived + timeout + errors

                results[source_file] = MutationResult(
                    file_path=source_file,
                    total_mutants=total,
                    killed_mutants=killed,
                    survived_mutants=survived,
                    timeout_mutants=timeout,
                    error_mutants=errors,
                )
            except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to parse mutation results for %s: %s", source_file, e)

        return results

    def _build_mutation_command(self, source_file: str) -> list[str]:
        """Build the mutmut run command for a single source file."""
        return [
            sys.executable, "-m", "mutmut", "run",
            "--paths-to-mutate", source_file,
            "--no-progress",
        ]

    def _select_mutation_sample(
        self,
        file_scores: dict[str, FileTestQuality],
        n: int,
    ) -> list[str]:
        """Select n files for mutation testing, prioritizing high-coverage low-assertion files."""
        candidates = sorted(
            file_scores.values(),
            key=lambda ftq: (ftq.coverage_score - ftq.assertion_quality_score),
            reverse=True,
        )
        return [c.file_path for c in candidates[:n]]

    def _compute_aggregate_tqs(
        self,
        file_results: dict[str, FileTestQuality],
    ) -> float:
        """Compute the repo-wide TQS as a weighted average across files."""
        if not file_results:
            return 0.0
        total = sum(ftq.composite_tqs for ftq in file_results.values())
        return total / len(file_results)
