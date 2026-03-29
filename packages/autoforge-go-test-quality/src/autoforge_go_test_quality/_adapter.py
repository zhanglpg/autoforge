"""
Go Test Quality Score (TQS) metric adapter.

Combines coverage, function gap analysis, assertion quality, and optional
mutation testing into a single 0-100 composite score for Go codebases.
All intermediate data models are adapter-internal — the framework sees
only MetricResult.
"""

from __future__ import annotations

import enum
import logging
import os
import re
import subprocess
from collections import defaultdict
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
    """Coverage measurements for a single Go source file."""

    file_path: str
    statement_coverage_pct: float
    covered_statements: int
    total_statements: int

    @property
    def combined_score(self) -> float:
        """Go has statement-level coverage only (no branch), so score = statement coverage."""
        return self.statement_coverage_pct


@dataclass(frozen=True)
class FunctionInfo:
    """An exported Go function extracted from go tool cover -func output."""

    name: str
    file_path: str
    coverage_pct: float


@dataclass(frozen=True)
class FunctionCoverageResult:
    """Function-level coverage gap analysis for one source file."""

    file_path: str
    total_exported_functions: int
    tested_functions: tuple[str, ...]
    untested_functions: tuple[str, ...]

    @property
    def score(self) -> float:
        if self.total_exported_functions == 0:
            return 100.0
        return (len(self.tested_functions) / self.total_exported_functions) * 100.0


@dataclass(frozen=True)
class AssertionInfo:
    """A single assertion found in a Go test file."""

    test_function: str
    line_number: int
    assertion_text: str
    strength: AssertionStrength


@dataclass(frozen=True)
class GoTestQualityIndicators:
    """Go-specific test quality signals."""

    has_table_driven_tests: bool
    table_test_count: int
    has_subtests: bool
    subtest_count: int
    uses_testify: bool


@dataclass(frozen=True)
class FileAssertionReport:
    """Assertion analysis for one Go test file."""

    test_file_path: str
    test_function_count: int
    assertions: tuple[AssertionInfo, ...]
    strong_count: int
    structural_count: int
    weak_count: int
    quality_indicators: GoTestQualityIndicators

    @property
    def weighted_score(self) -> float:
        """Assertion quality score 0-100 for this file.

        Per-function score = best assertion strength weight in that function
        (STRONG=1.0, STRUCTURAL=0.5, WEAK=0.2, none=0.0).
        Base = mean of per-function scores * 100.
        Bonus for Go-specific quality patterns (table tests, subtests, testify).
        """
        if self.test_function_count == 0:
            return 0.0

        by_func: dict[str, list[AssertionInfo]] = defaultdict(list)
        for a in self.assertions:
            by_func[a.test_function].append(a)

        func_scores: list[float] = []
        for _i in range(self.test_function_count):
            func_scores.append(0.0)  # placeholder for functions with no key

        # Rebuild: compute per-function best-strength score
        # We need to account for all test functions, not just those with assertions.
        # Use _extract_test_function_ranges ordering isn't available here,
        # so count: functions with assertions get their best weight, others get 0.
        func_best: dict[str, float] = {}
        for func_name, asserts in by_func.items():
            func_best[func_name] = max(a.strength.weight for a in asserts)

        total_score = sum(func_best.values())  # sum of best weights for funcs with assertions
        # Functions without any assertion contribute 0
        base = (total_score / self.test_function_count) * 100.0

        # Go-specific quality bonuses
        bonus = 0.0
        if self.quality_indicators.has_table_driven_tests:
            bonus += 5.0
        if self.quality_indicators.has_subtests:
            bonus += 3.0
        if self.quality_indicators.uses_testify:
            bonus += 2.0

        return max(0.0, min(100.0, base + bonus))

    @property
    def total_count(self) -> int:
        return self.strong_count + self.structural_count + self.weak_count


@dataclass(frozen=True)
class MutationResult:
    """Mutation testing results for one source file."""

    file_path: str
    total_mutants: int
    killed_mutants: int
    survived_mutants: int

    @property
    def score(self) -> float:
        if self.total_mutants == 0:
            return 0.0
        return (self.killed_mutants / self.total_mutants) * 100.0


@dataclass(frozen=True)
class FileTestQuality:
    """Complete TQS breakdown for a single Go source file."""

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

    coverage: float = 0.35
    function_coverage: float = 0.25
    assertion_quality: float = 0.30
    mutation: float = 0.10

    def effective_weights(self) -> dict[str, float]:
        return compute_effective_weights(self)


# ---------------------------------------------------------------------------
# Coverage Profile Parsing
# ---------------------------------------------------------------------------

def parse_go_coverage_profile(profile_text: str) -> dict[str, FileCoverageData]:
    """Parse a Go coverage profile into per-file coverage data.

    Format: ``file:startLine.startCol,endLine.endCol numStatements hitCount``
    """
    file_stats: dict[str, list[tuple[int, bool]]] = defaultdict(list)

    for line in profile_text.splitlines():
        line = line.strip()
        if not line or line.startswith("mode:"):
            continue

        # file.go:10.2,12.0 1 1
        match = re.match(r'^(.+):(\d+)\.\d+,(\d+)\.\d+\s+(\d+)\s+(\d+)$', line)
        if not match:
            continue

        file_path = match.group(1)
        num_statements = int(match.group(4))
        hit_count = int(match.group(5))
        file_stats[file_path].append((num_statements, hit_count > 0))

    results: dict[str, FileCoverageData] = {}
    for file_path, entries in file_stats.items():
        total = sum(stmts for stmts, _ in entries)
        covered = sum(stmts for stmts, hit in entries if hit)
        pct = (covered / total * 100.0) if total > 0 else 0.0

        results[file_path] = FileCoverageData(
            file_path=file_path,
            statement_coverage_pct=pct,
            covered_statements=covered,
            total_statements=total,
        )

    return results


def parse_go_cover_func(output: str) -> dict[str, list[tuple[str, float]]]:
    """Parse ``go tool cover -func`` output into per-file function coverage.

    Output format: ``file.go:line:	FuncName	85.7%``
    Returns ``{file_path: [(func_name, coverage_pct), ...]}``.
    """
    results: dict[str, list[tuple[str, float]]] = defaultdict(list)

    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("total:"):
            continue

        # github.com/user/pkg/foo.go:10:	ProcessOrder	85.7%
        match = re.match(r'^(.+?):\d+:\s+(\S+)\s+([\d.]+)%$', line)
        if not match:
            continue

        file_path = match.group(1)
        func_name = match.group(2)
        pct = float(match.group(3))
        results[file_path].append((func_name, pct))

    return results


def _read_go_module_path(repo_path: str) -> str:
    """Read the module path from go.mod."""
    go_mod = os.path.join(repo_path, "go.mod")
    try:
        with open(go_mod) as f:
            for line in f:
                line = line.strip()
                if line.startswith("module "):
                    return line[7:].strip()
    except OSError:
        pass
    return ""


def _resolve_go_path(module_path: str, go_file: str, repo_path: str) -> str:
    """Convert a Go module-qualified path to a filesystem path relative to repo_path.

    E.g. ``github.com/user/pkg/foo.go`` with module ``github.com/user/pkg``
    becomes ``foo.go`` (relative to repo_path).
    """
    if module_path and go_file.startswith(module_path + "/"):
        return go_file[len(module_path) + 1:]
    if module_path and go_file == module_path:
        return ""
    # If no module prefix match, return as-is (may already be relative)
    return go_file


# ---------------------------------------------------------------------------
# File Discovery
# ---------------------------------------------------------------------------

_EXCLUDED_DIRS = {"vendor", "testdata", ".git", "node_modules"}


def discover_go_source_files(target_path: str) -> list[str]:
    """Find all .go source files, excluding test files and vendor/."""
    results: list[str] = []
    for root, dirs, files in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIRS]
        for f in files:
            if f.endswith(".go") and not f.endswith("_test.go"):
                results.append(os.path.join(root, f))
    return sorted(results)


def discover_go_test_files(target_path: str) -> list[str]:
    """Find all _test.go files."""
    results: list[str] = []
    for root, dirs, files in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIRS]
        for f in files:
            if f.endswith("_test.go"):
                results.append(os.path.join(root, f))
    return sorted(results)


def map_go_tests_to_sources(
    source_files: list[str],
    test_files: list[str],
) -> dict[str, list[str]]:
    """Map Go source files to their test files.

    Convention: foo.go <-> foo_test.go in same directory.
    """
    test_lookup: dict[str, list[str]] = {}
    for tf in test_files:
        dir_path = os.path.dirname(tf)
        base = os.path.basename(tf)
        if base.endswith("_test.go"):
            source_name = base[:-8] + ".go"  # strip "_test"
            key = os.path.join(dir_path, source_name)
            test_lookup.setdefault(key, []).append(tf)

    result: dict[str, list[str]] = {}
    for sf in source_files:
        result[sf] = test_lookup.get(sf, [])
    return result


# ---------------------------------------------------------------------------
# Regex-Based Assertion Analysis for Go Test Files
# ---------------------------------------------------------------------------

# Test function pattern
_GO_TEST_FUNC_RE = re.compile(r'^func\s+(Test\w+)\s*\(', re.MULTILINE)

# --- STRONG assertions: verify specific values/behavior ---
_STRONG_PATTERNS = [
    # testify equality
    re.compile(r'(?:assert|require)\.Equal\b'),
    re.compile(r'(?:assert|require)\.EqualValues\b'),
    re.compile(r'(?:assert|require)\.EqualError\b'),
    re.compile(r'(?:assert|require)\.Exactly\b'),
    re.compile(r'(?:assert|require)\.JSONEq\b'),
    re.compile(r'(?:assert|require)\.YAMLEq\b'),
    re.compile(r'(?:assert|require)\.Contains\b'),
    re.compile(r'(?:assert|require)\.NotContains\b'),
    re.compile(r'(?:assert|require)\.Regexp\b'),
    re.compile(r'(?:assert|require)\.NotRegexp\b'),
    # cmp.Diff
    re.compile(r'cmp\.Diff\b'),
    # reflect.DeepEqual
    re.compile(r'reflect\.DeepEqual\b'),
    # Explicit comparison + error on same line (rare but possible)
    re.compile(r'if\s+\w+\s*!=\s*\w+\s*\{[^}]*t\.(?:Error|Fatal|Errorf|Fatalf)'),
    re.compile(r'if\s+\w+\s*==\s*\w+\s*\{[^}]*t\.(?:Error|Fatal|Errorf|Fatalf)'),
]

# Patterns that indicate the surrounding `if` is a value comparison (for
# promoting multi-line t.Errorf inside an if-block from WEAK to STRONG).
_COMPARISON_IF_RE = re.compile(
    r'^\s*if\s+.*(?:!=|==|<|>|<=|>=)\s*'
)

# --- STRUCTURAL assertions: verify shape/type/presence ---
_STRUCTURAL_PATTERNS = [
    re.compile(r'(?:assert|require)\.IsType\b'),
    re.compile(r'(?:assert|require)\.Implements\b'),
    re.compile(r'(?:assert|require)\.Len\b'),
    re.compile(r'(?:assert|require)\.Greater\b'),
    re.compile(r'(?:assert|require)\.GreaterOrEqual\b'),
    re.compile(r'(?:assert|require)\.Less\b'),
    re.compile(r'(?:assert|require)\.LessOrEqual\b'),
    re.compile(r'(?:assert|require)\.Subset\b'),
    re.compile(r'(?:assert|require)\.ElementsMatch\b'),
    re.compile(r'errors\.Is\b'),
    re.compile(r'errors\.As\b'),
]

# --- WEAK assertions: prove existence, not correctness ---
_WEAK_PATTERNS = [
    re.compile(r'(?:assert|require)\.NotNil\b'),
    re.compile(r'(?:assert|require)\.Nil\b'),
    re.compile(r'(?:assert|require)\.True\b'),
    re.compile(r'(?:assert|require)\.False\b'),
    re.compile(r'(?:assert|require)\.NoError\b'),
    re.compile(r'(?:assert|require)\.Error\b'),
    re.compile(r't\.Error\b'),
    re.compile(r't\.Errorf\b'),
    re.compile(r't\.Fatal\b'),
    re.compile(r't\.Fatalf\b'),
]

# Go-specific quality indicators
_TABLE_TEST_RE = re.compile(
    r'(?:tests?|cases?|tt|tc|testCases?)\s*(?::=|=)\s*'
    r'(?:\[\]struct\b|map\[string\]struct\b|map\[string\])',
    re.MULTILINE,
)
_SUBTEST_RE = re.compile(r't\.Run\(')
_TESTIFY_IMPORT_RE = re.compile(
    r'"github\.com/stretchr/testify/(?:assert|require)"',
)


def classify_go_assertion(line: str) -> AssertionStrength | None:
    """Classify a single line of Go test code by assertion strength."""
    for pattern in _STRONG_PATTERNS:
        if pattern.search(line):
            return AssertionStrength.STRONG
    for pattern in _STRUCTURAL_PATTERNS:
        if pattern.search(line):
            return AssertionStrength.STRUCTURAL
    for pattern in _WEAK_PATTERNS:
        if pattern.search(line):
            return AssertionStrength.WEAK
    return None


_ERROR_GUARD_RE = re.compile(
    r'^\s*if\s+\w*[Ee]rr\w*\s*!=\s*nil\s*\{'
)


def _classify_with_context(
    line: str,
    line_idx: int,
    lines: list[str],
) -> AssertionStrength | None:
    """Classify a line with surrounding context awareness.

    Promotes t.Error/t.Errorf/t.Fatal/t.Fatalf from WEAK to STRONG when
    they appear inside a value-comparison ``if`` block — the most common
    Go assertion idiom (``if got != want { t.Errorf(...) }``).

    Does NOT promote when the ``if`` is a common guard pattern:
    - ``if err != nil`` (error guard — just checking success, not verifying a value)
    """
    strength = classify_go_assertion(line)
    if strength is not AssertionStrength.WEAK:
        return strength

    # Only consider t.Error/t.Errorf/t.Fatal/t.Fatalf for promotion.
    # Testify patterns like assert.Nil, assert.True etc. stay WEAK.
    stripped = line.strip()
    is_t_error = bool(re.match(r't\.(?:Error|Errorf|Fatal|Fatalf)\b', stripped))
    if not is_t_error:
        return strength

    for back in range(1, min(4, line_idx + 1)):
        prev = lines[line_idx - back]
        if _COMPARISON_IF_RE.match(prev):
            # Don't promote error-guard patterns
            if _ERROR_GUARD_RE.match(prev):
                return strength
            return AssertionStrength.STRONG
        # Stop scanning if we hit another statement (non-blank, non-brace)
        prev_stripped = prev.strip()
        if prev_stripped and prev_stripped not in ('{', '}'):
            break

    return strength


def _detect_quality_indicators(source_code: str) -> GoTestQualityIndicators:
    """Detect Go-specific test quality indicators in a test file."""
    table_matches = _TABLE_TEST_RE.findall(source_code)
    subtest_matches = _SUBTEST_RE.findall(source_code)
    testify_matches = _TESTIFY_IMPORT_RE.findall(source_code)

    return GoTestQualityIndicators(
        has_table_driven_tests=len(table_matches) > 0,
        table_test_count=len(table_matches),
        has_subtests=len(subtest_matches) > 0,
        subtest_count=len(subtest_matches),
        uses_testify=len(testify_matches) > 0,
    )


def _extract_test_function_ranges(source_code: str) -> list[tuple[str, int, int]]:
    """Extract test function names and their line ranges from Go source.

    Returns list of (func_name, start_line, end_line).
    Uses brace counting to find function boundaries.
    """
    lines = source_code.splitlines()
    functions: list[tuple[str, int, int]] = []
    i = 0

    while i < len(lines):
        match = _GO_TEST_FUNC_RE.match(lines[i])
        if match:
            func_name = match.group(1)
            start_line = i + 1  # 1-indexed

            # Find the opening brace
            brace_depth = 0
            found_open = False
            j = i
            while j < len(lines):
                for ch in lines[j]:
                    if ch == '{':
                        brace_depth += 1
                        found_open = True
                    elif ch == '}':
                        brace_depth -= 1
                if found_open and brace_depth == 0:
                    functions.append((func_name, start_line, j + 1))
                    break
                j += 1
            i = j + 1
        else:
            i += 1

    return functions


def analyze_go_test_file_assertions(
    source_code: str,
    file_path: str,
) -> FileAssertionReport:
    """Analyze a Go test file for assertions using regex patterns."""
    func_ranges = _extract_test_function_ranges(source_code)
    lines = source_code.splitlines()

    assertions: list[AssertionInfo] = []

    for func_name, start, end in func_ranges:
        for line_num in range(start - 1, min(end, len(lines))):
            line = lines[line_num]
            strength = _classify_with_context(line, line_num, lines)
            if strength is not None:
                assertions.append(AssertionInfo(
                    test_function=func_name,
                    line_number=line_num + 1,
                    assertion_text=line.strip()[:80],
                    strength=strength,
                ))

    strong = sum(1 for a in assertions if a.strength is AssertionStrength.STRONG)
    structural = sum(1 for a in assertions if a.strength is AssertionStrength.STRUCTURAL)
    weak = sum(1 for a in assertions if a.strength is AssertionStrength.WEAK)

    quality_indicators = _detect_quality_indicators(source_code)

    return FileAssertionReport(
        test_file_path=file_path,
        test_function_count=len(func_ranges),
        assertions=tuple(assertions),
        strong_count=strong,
        structural_count=structural,
        weak_count=weak,
        quality_indicators=quality_indicators,
    )


def compute_assertion_quality_score(report: FileAssertionReport) -> float:
    """Compute 0-100 assertion quality score from an assertion report."""
    return report.weighted_score


# ---------------------------------------------------------------------------
# Weight Computation
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
# GoTestQualityAdapter
# ---------------------------------------------------------------------------

class GoTestQualityAdapter(BaseMetricAdapter):
    """Metric adapter for Go Test Quality Score (TQS) measurement.

    Combines coverage, function gap analysis, assertion quality, and optional
    mutation testing into a single 0-100 composite score for Go codebases.
    """

    __test__ = False  # Prevent pytest from collecting this as a test class

    name = "go_test_quality"
    supported_languages = ["go"]

    def __init__(
        self,
        *,
        coverage_weight: float = 0.35,
        func_coverage_weight: float = 0.25,
        assertion_weight: float = 0.30,
        mutation_weight: float = 0.10,
        mutation_sample_size: int = 3,
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
        self.coverage_timeout = coverage_timeout
        self.mutation_timeout = mutation_timeout
        self._detailed_results: dict[str, FileTestQuality] = {}

    # --- BaseMetricAdapter interface ---

    def check_prerequisites(self, repo_path: str) -> bool:
        """Verify the Go toolchain and go.mod are available."""
        if not self.check_tool_available("go"):
            logger.warning("go not found on PATH")
            return False

        go_mod = os.path.join(repo_path, "go.mod")
        if not os.path.exists(go_mod):
            logger.warning("go.mod not found in %s", repo_path)
            return False

        if self.weights.mutation > 0:
            if not self.check_tool_available("go-mutesting"):
                logger.warning(
                    "go-mutesting not found on PATH but mutation_weight > 0. "
                    "Install with: go install github.com/zimmski/go-mutesting/cmd/go-mutesting@latest"
                )
                return False

        return True

    def measure(self, repo_path: str, target_path: str) -> MetricResult:
        """Run all TQS sub-metrics and return composite score as MetricResult."""
        module_path = _read_go_module_path(repo_path)

        # Step 1: Collect coverage
        coverage_data, func_coverage_data = self._collect_coverage(
            repo_path, target_path, module_path,
        )

        # Step 2: Analyze all files
        file_results = self._analyze_all_files(
            repo_path, target_path, module_path, coverage_data, func_coverage_data,
        )

        # Step 3 (optional): Mutation testing
        if self.weights.mutation > 0:
            sample = self._select_mutation_sample(file_results, self.mutation_sample_size)
            if sample:
                mutation_data = self._run_mutation(repo_path, sample)
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

        # Step 4: Aggregate
        aggregate_tqs = self._compute_aggregate_tqs(file_results)
        self._detailed_results = file_results

        breakdown = {fp: ftq.composite_tqs for fp, ftq in file_results.items()}

        return MetricResult(
            metric_name="go_test_quality_score",
            value=aggregate_tqs,
            unit="score",
            direction=Direction.MAXIMIZE,
            breakdown=breakdown,
            tool="go_test_quality",
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
        module_path: str,
    ) -> tuple[dict[str, FileCoverageData], dict[str, list[tuple[str, float]]]]:
        """Run go test -cover and parse coverage data."""
        # Determine the Go package pattern for target_path
        rel_target = os.path.relpath(target_path, repo_path)
        if rel_target == ".":
            pkg_pattern = "./..."
        else:
            pkg_pattern = f"./{rel_target}/..."

        coverage_file = os.path.join(repo_path, "coverage.out")

        cmd = [
            "go", "test",
            f"-coverprofile={coverage_file}",
            pkg_pattern,
        ]
        logger.info("Running coverage: %s", " ".join(cmd))

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=self.coverage_timeout,
            )
        except subprocess.TimeoutExpired:
            logger.warning("go test coverage timed out after %ds", self.coverage_timeout)
            return {}, {}

        if not os.path.exists(coverage_file):
            logger.warning("Coverage profile not generated")
            return {}, {}

        # Parse coverage profile
        with open(coverage_file) as f:
            profile_text = f.read()
        raw_coverage = parse_go_coverage_profile(profile_text)

        # Parse go tool cover -func for per-function data
        func_data: dict[str, list[tuple[str, float]]] = {}
        try:
            func_proc = subprocess.run(
                ["go", "tool", "cover", f"-func={coverage_file}"],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=30,
            )
            if func_proc.returncode == 0:
                func_data = parse_go_cover_func(func_proc.stdout)
        except subprocess.TimeoutExpired:
            logger.warning("go tool cover -func timed out")

        # Clean up
        try:
            os.remove(coverage_file)
        except OSError:
            pass

        # Resolve module-qualified paths to relative filesystem paths
        coverage_data: dict[str, FileCoverageData] = {}
        for go_path, cov in raw_coverage.items():
            rel_path = _resolve_go_path(module_path, go_path, repo_path)
            abs_path = os.path.normpath(os.path.join(repo_path, rel_path))
            coverage_data[abs_path] = FileCoverageData(
                file_path=abs_path,
                statement_coverage_pct=cov.statement_coverage_pct,
                covered_statements=cov.covered_statements,
                total_statements=cov.total_statements,
            )

        resolved_func_data: dict[str, list[tuple[str, float]]] = {}
        for go_path, funcs in func_data.items():
            rel_path = _resolve_go_path(module_path, go_path, repo_path)
            abs_path = os.path.normpath(os.path.join(repo_path, rel_path))
            resolved_func_data[abs_path] = funcs

        return coverage_data, resolved_func_data

    def _analyze_all_files(
        self,
        repo_path: str,
        target_path: str,
        module_path: str,
        coverage_data: dict[str, FileCoverageData],
        func_coverage_data: dict[str, list[tuple[str, float]]],
    ) -> dict[str, FileTestQuality]:
        """Compute per-file TQS for all Go source files."""
        source_files = discover_go_source_files(target_path)
        test_files = discover_go_test_files(target_path)
        test_map = map_go_tests_to_sources(source_files, test_files)
        eff_weights = self.weights.effective_weights()

        file_results: dict[str, FileTestQuality] = {}

        for sf in source_files:
            norm_sf = os.path.normpath(sf)

            # Coverage
            cov = coverage_data.get(norm_sf)
            cov_score = cov.combined_score if cov else 0.0

            # Function coverage from go tool cover -func
            func_list = func_coverage_data.get(norm_sf, [])
            exported_funcs = [(name, pct) for name, pct in func_list
                             if name[0].isupper()]
            if exported_funcs:
                tested = tuple(name for name, pct in exported_funcs if pct > 0)
                untested = tuple(name for name, pct in exported_funcs if pct == 0)
                func_cov = FunctionCoverageResult(
                    file_path=sf,
                    total_exported_functions=len(exported_funcs),
                    tested_functions=tested,
                    untested_functions=untested,
                )
            else:
                func_cov = FunctionCoverageResult(
                    file_path=sf,
                    total_exported_functions=0,
                    tested_functions=(),
                    untested_functions=(),
                )
            func_score = func_cov.score

            # Assertion quality from test files
            mapped_tests = test_map.get(sf, [])
            assertion_report: FileAssertionReport | None = None
            assertion_score = 0.0

            if mapped_tests:
                all_assertions: list[AssertionInfo] = []
                total_test_funcs = 0
                combined_indicators = GoTestQualityIndicators(
                    has_table_driven_tests=False,
                    table_test_count=0,
                    has_subtests=False,
                    subtest_count=0,
                    uses_testify=False,
                )

                for tf in mapped_tests:
                    try:
                        with open(tf) as fh:
                            test_code = fh.read()
                        report = analyze_go_test_file_assertions(test_code, tf)
                        all_assertions.extend(report.assertions)
                        total_test_funcs += report.test_function_count
                        # Merge quality indicators
                        qi = report.quality_indicators
                        combined_indicators = GoTestQualityIndicators(
                            has_table_driven_tests=(
                                combined_indicators.has_table_driven_tests
                                or qi.has_table_driven_tests
                            ),
                            table_test_count=(
                                combined_indicators.table_test_count
                                + qi.table_test_count
                            ),
                            has_subtests=(
                                combined_indicators.has_subtests
                                or qi.has_subtests
                            ),
                            subtest_count=(
                                combined_indicators.subtest_count
                                + qi.subtest_count
                            ),
                            uses_testify=(
                                combined_indicators.uses_testify
                                or qi.uses_testify
                            ),
                        )
                    except (OSError, UnicodeDecodeError):
                        continue

                strong = sum(1 for a in all_assertions
                           if a.strength is AssertionStrength.STRONG)
                structural = sum(1 for a in all_assertions
                               if a.strength is AssertionStrength.STRUCTURAL)
                weak = sum(1 for a in all_assertions
                         if a.strength is AssertionStrength.WEAK)

                assertion_report = FileAssertionReport(
                    test_file_path=mapped_tests[0],
                    test_function_count=total_test_funcs,
                    assertions=tuple(all_assertions),
                    strong_count=strong,
                    structural_count=structural,
                    weak_count=weak,
                    quality_indicators=combined_indicators,
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

    def _run_mutation(
        self,
        repo_path: str,
        sample_files: list[str],
    ) -> dict[str, MutationResult]:
        """Run go-mutesting on sample files."""
        results: dict[str, MutationResult] = {}

        for source_file in sample_files:
            rel_path = os.path.relpath(source_file, repo_path)
            pkg_dir = os.path.dirname(rel_path)
            if not pkg_dir:
                pkg_dir = "."

            cmd = ["go-mutesting", f"./{pkg_dir}/..."]
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

            # Parse go-mutesting output: PASS/FAIL lines
            killed = 0
            survived = 0
            for line in proc.stdout.splitlines():
                if line.startswith("PASS:"):
                    killed += 1
                elif line.startswith("FAIL:"):
                    survived += 1

            total = killed + survived
            if total > 0:
                results[source_file] = MutationResult(
                    file_path=source_file,
                    total_mutants=total,
                    killed_mutants=killed,
                    survived_mutants=survived,
                )

        return results

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
