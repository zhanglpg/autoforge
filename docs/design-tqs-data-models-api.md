# Detailed Design: Test Quality Score (TQS) — Data Models & API

**Status:** Draft
**Parent:** [Design Doc: Test Quality Metrics](design-test-quality-metrics.md)
**Scope:** Precise data models and API signatures for the TQS adapter. Implementation details are a separate document.

## Context

AutoForge's iteration loop currently only supports complexity reduction. The [design doc](design-test-quality-metrics.md) specifies a **Test Quality Score (TQS)** adapter — a 0-100 composite metric combining coverage, function gaps, assertion quality, and optional mutation testing. This document fleshes out the precise data models and API signatures before implementation begins.

All new code goes in `src/autoforge/adapters/test_quality.py` (adapter-internal models + class + helpers). The framework-level models in `models.py` are unchanged.

---

## 1. Enums & Classification

```python
class AssertionStrength(enum.Enum):
    """Classification tier for a single assertion."""
    STRONG = "strong"         # weight 1.0 — assertEqual, assert x == y, pytest.raises
    STRUCTURAL = "structural" # weight 0.5 — assertIsInstance, assert len(x) > 0, assertIn
    WEAK = "weak"             # weight 0.2 — assert True, assertIsNotNone, bare assert x

    @property
    def weight(self) -> float:
        """Numeric weight for score computation."""
        ...
```

The three-tier classification is derived from the design doc's debate on assertion counting vs. quality (Section "Debate 2"). Strong assertions verify specific behavior, structural assertions verify shape, and weak assertions prove only existence.

---

## 2. Internal Data Models

All intermediate models are `frozen=True` dataclasses — these are measurement snapshots, never mutated after creation.

### 2.1 Coverage

```python
@dataclass(frozen=True)
class FileCoverageData:
    """Coverage measurements for a single source file."""
    file_path: str
    line_coverage_pct: float           # 0-100
    branch_coverage_pct: float         # 0-100, 0.0 if branch data unavailable
    covered_lines: frozenset[int]      # line numbers executed during tests
    missing_lines: frozenset[int]      # line numbers not executed
    covered_branches: int              # count of branches hit
    total_branches: int                # total branches in file

    @property
    def combined_score(self) -> float:
        """Weighted coverage score: 0.6 * line + 0.4 * branch."""
        ...
```

**Why `frozenset[int]`:** Coverage line sets can be large. `frozenset` supports the frozen dataclass pattern and enables hashing/caching. The performance cost is negligible since these sets are created once and read many times.

**Why both `covered_lines` and `missing_lines`:** `covered_lines` is needed by `find_uncovered_functions()` to cross-reference function line ranges. `missing_lines` is retained from the coverage JSON for potential reporting use.

### 2.2 Function Extraction (AST)

```python
@dataclass(frozen=True)
class FunctionInfo:
    """A public function/method extracted from source AST."""
    name: str            # qualified: "MyClass.my_method"
    file_path: str
    start_line: int
    end_line: int
    is_method: bool      # True if defined inside a class
    is_property: bool    # True if decorated with @property
```

**Why qualified names:** `"MyClass.my_method"` distinguishes methods from free functions and avoids collisions (e.g., two classes with a `reset()` method). The agent prompt can reference these names directly.

### 2.3 Function Coverage Gaps

```python
@dataclass(frozen=True)
class FunctionCoverageResult:
    """Function-level coverage gap analysis for one source file."""
    file_path: str
    total_public_functions: int
    tested_functions: tuple[str, ...]    # names of functions with >0% line coverage
    untested_functions: tuple[str, ...]  # names of functions with 0% line coverage

    @property
    def score(self) -> float:
        """(tested / total) * 100, or 100.0 if no public functions."""
        ...
```

### 2.4 Assertion Analysis

```python
@dataclass(frozen=True)
class AssertionInfo:
    """A single assertion found in a test file."""
    test_function: str       # enclosing test function name
    line_number: int
    assertion_text: str      # short repr, e.g. "assertEqual(result, 42)"
    strength: AssertionStrength

@dataclass(frozen=True)
class FileAssertionReport:
    """Assertion analysis for one test file."""
    test_file_path: str
    test_function_count: int
    assertions: tuple[AssertionInfo, ...]  # tuple for frozen compat
    strong_count: int
    structural_count: int
    weak_count: int

    @property
    def weighted_score(self) -> float:
        """Assertion quality score 0-100 for this file."""
        ...

    @property
    def total_count(self) -> int:
        """Total assertion count across all tiers."""
        ...
```

**Why `tuple` over `list`:** Lists are mutable and incompatible with `frozen=True`. `tuple[AssertionInfo, ...]` is the idiomatic Python workaround.

**Score formula:** `min(100, weighted_density * 33.3)` where `weighted_density = sum(assertion.strength.weight for assertion) / test_function_count`. This means: 0 assertions → 0, 1 strong per test → 33, 3+ strong per test → 100.

### 2.5 Mutation Testing

```python
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
        ...
```

### 2.6 Per-File Composite

```python
@dataclass(frozen=True)
class FileTestQuality:
    """Complete TQS breakdown for a single source file."""
    file_path: str

    # Raw analysis results (None when data unavailable)
    coverage: FileCoverageData | None
    function_coverage: FunctionCoverageResult | None
    assertion_quality: FileAssertionReport | None   # None if no mapped test file
    mutation: MutationResult | None                  # None if disabled/not sampled

    # Pre-computed sub-scores (0-100 each)
    coverage_score: float
    function_coverage_score: float
    assertion_quality_score: float
    mutation_score: float              # 0.0 if not computed

    composite_tqs: float               # weighted composite 0-100
    mapped_test_files: tuple[str, ...]  # test files associated with this source
```

**Why store both raw results and pre-computed scores:** The raw results (`coverage`, `function_coverage`, etc.) carry structural detail for debugging and future reporting. The pre-computed scores are the values that feed into `compute_file_tqs()`. Keeping both avoids recomputation while preserving full provenance.

### 2.7 Weight Configuration

```python
@dataclass
class TQSWeights:
    """Weight configuration with redistribution support."""
    coverage: float = 0.30
    function_coverage: float = 0.20
    assertion_quality: float = 0.30
    mutation: float = 0.20

    def effective_weights(self) -> dict[str, float]:
        """Normalize weights, redistributing disabled (0.0) metrics proportionally.

        Example: mutation=0.0 → {coverage: 0.375, function_coverage: 0.25,
                                  assertion_quality: 0.375}
        """
        ...
```

**Not frozen:** `TQSWeights` is a configuration object, not a measurement snapshot. It may be constructed from YAML config and doesn't benefit from immutability guarantees.

---

## 3. TestQualityAdapter Class

```python
class TestQualityAdapter(BaseMetricAdapter):
    """Metric adapter for Test Quality Score (TQS) measurement.

    Combines coverage, function gap analysis, assertion quality, and optional
    mutation testing into a single 0-100 composite score.
    """

    name: str = "test_quality"
    supported_languages: list[str] = ["python"]

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
        """Initialize TQS adapter with sub-metric weights and tool configuration."""
        ...

    # --- BaseMetricAdapter interface ---

    def check_prerequisites(self, repo_path: str) -> bool:
        """Verify pytest, coverage.py, and optionally mutmut are available."""
        ...

    def measure(self, repo_path: str, target_path: str) -> MetricResult:
        """Run all TQS sub-metrics and return composite score as MetricResult.

        Returns MetricResult with:
          metric_name="test_quality_score"
          value=aggregate TQS (0-100)
          direction=Direction.MAXIMIZE
          breakdown={source_file_path: composite_tqs, ...}

        Side effect: stores _detailed_results for identify_targets().
        """
        ...

    def identify_targets(self, result: MetricResult, n: int) -> list[str]:
        """Return top-n source files with lowest TQS (worst-tested first).

        Sorts by composite TQS ascending, consistent with ComplexityAdapter pattern.
        """
        ...

    # --- Internal orchestration ---

    def _collect_coverage(
        self, repo_path: str, target_path: str,
    ) -> dict[str, FileCoverageData]:
        """Run pytest-cov and parse JSON output into per-file coverage data."""
        ...

    def _build_coverage_command(self, target_path: str) -> list[str]:
        """Build the pytest --cov command with appropriate flags."""
        ...

    def _analyze_all_files(
        self,
        repo_path: str,
        target_path: str,
        coverage_data: dict[str, FileCoverageData],
    ) -> dict[str, FileTestQuality]:
        """Compute per-file TQS for all source files in target_path."""
        ...

    def _run_sampled_mutation(
        self, repo_path: str, sample_files: list[str],
    ) -> dict[str, MutationResult]:
        """Run mutmut on a sample of source files and return results."""
        ...

    def _build_mutation_command(self, source_file: str) -> list[str]:
        """Build the mutmut run command for a single source file."""
        ...

    def _select_mutation_sample(
        self, file_scores: dict[str, FileTestQuality], n: int,
    ) -> list[str]:
        """Select n files for mutation testing, prioritizing high-coverage low-assertion files."""
        ...

    def _compute_aggregate_tqs(
        self, file_results: dict[str, FileTestQuality],
    ) -> float:
        """Compute the repo-wide TQS as a weighted average across files."""
        ...
```

### Stateful cache: `_detailed_results`

After `measure()`, the adapter stores `_detailed_results: dict[str, FileTestQuality]` on `self`. This allows `identify_targets()` to sort using the rich sub-score data, while `MetricResult.breakdown` stays a flat `dict[str, float]` per the framework contract.

This is a pragmatic design choice. The alternative — encoding sub-scores into breakdown keys like `"src/foo.py:coverage": 85.0` — would break the existing convention where breakdown keys are file paths. Storing rich data on the instance keeps the public API clean.

---

## 4. Module-Level Pure Helper Functions

All helpers are pure functions (no `self`, no side effects) for testability. 80%+ of logic can be unit tested with synthetic data and no subprocess mocking.

### 4.1 Coverage

```python
def parse_coverage_json(coverage_json: dict) -> dict[str, FileCoverageData]:
    """Parse pytest-cov JSON report into per-file FileCoverageData."""
    ...

def compute_coverage_score(line_pct: float, branch_pct: float) -> float:
    """Compute combined coverage score: 0.6 * line + 0.4 * branch."""
    ...
```

### 4.2 AST / Function Extraction

```python
def extract_public_functions(source_code: str, file_path: str) -> list[FunctionInfo]:
    """AST-parse Python source and return all public functions and methods.

    "Public" means: name does not start with underscore, excluding dunder methods.
    Includes class methods and standalone functions.
    """
    ...

def find_uncovered_functions(
    functions: list[FunctionInfo],
    covered_lines: frozenset[int],
) -> FunctionCoverageResult:
    """Cross-reference function line ranges with coverage to find untested functions.

    A function is "tested" if any line in its range [start_line, end_line] is covered.
    """
    ...
```

### 4.3 Assertion Analysis

```python
def classify_assertion(node: ast.AST) -> AssertionStrength:
    """Classify a single AST assertion node by strength tier.

    Takes a raw AST node rather than a string — the caller walks the AST once
    and hands individual nodes to the classifier, avoiding re-parsing.
    """
    ...

def analyze_test_file_assertions(
    source_code: str, file_path: str,
) -> FileAssertionReport:
    """AST-parse a test file and classify all assertions found.

    Finds test functions (def test_* or methods in TestCase subclasses),
    walks AST for: assert stmts, self.assert* calls, pytest.raises.
    """
    ...

def compute_assertion_quality_score(report: FileAssertionReport) -> float:
    """Compute 0-100 assertion quality score from an assertion report.

    Formula: min(100, weighted_density * 33.3)
    where weighted_density = sum(weights) / test_function_count
    """
    ...
```

### 4.4 Test-to-Source Mapping

```python
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
    Phase 2 (deferred): Coverage-based fallback for unmatched files.
    """
    ...
```

### 4.5 Weight Computation

```python
def compute_effective_weights(weights: TQSWeights) -> dict[str, float]:
    """Normalize weights, redistributing disabled (0.0) metrics proportionally.

    Returns dict with keys: "coverage", "function_coverage",
    "assertion_quality", "mutation". All values sum to 1.0.
    """
    ...

def compute_file_tqs(
    coverage_score: float,
    function_coverage_score: float,
    assertion_quality_score: float,
    mutation_score: float,
    weights: dict[str, float],
) -> float:
    """Compute composite TQS for a single file given sub-scores and effective weights.

    Returns weighted sum, clamped to [0, 100].
    """
    ...
```

### 4.6 File Discovery

```python
def discover_python_source_files(
    target_path: str, exclude_tests: bool = True,
) -> list[str]:
    """Find all Python source files under target_path, excluding test files.

    Excludes files matching: test_*.py, *_test.py, conftest.py, and
    files under directories named "tests/" or "test/".
    """
    ...

def discover_test_files(
    repo_path: str, test_dir_pattern: str,
) -> list[str]:
    """Find all Python test files matching the test directory pattern."""
    ...
```

---

## 5. Data Flow

The `measure()` call follows this sequence:

```
1. discover_python_source_files() + discover_test_files()
       → source_files: list[str], test_files: list[str]

2. _build_coverage_command() → subprocess → parse_coverage_json()
       → coverage_data: dict[str, FileCoverageData]

3. map_tests_to_sources(source_files, test_files)
       → test_map: dict[str, list[str]]    (convention-based only)

4. Per source file:
   a. extract_public_functions() → find_uncovered_functions()
          → FunctionCoverageResult
   b. analyze_test_file_assertions() on each mapped test file
          → FileAssertionReport (merged if multiple test files)
   c. compute_coverage_score(), compute_assertion_quality_score()
          → per-sub-metric scores (0-100)

5. If mutation enabled:
   _select_mutation_sample() → _run_sampled_mutation()
          → mutation_data: dict[str, MutationResult]

6. compute_effective_weights() → compute_file_tqs() per file
       → FileTestQuality per source file

7. _compute_aggregate_tqs(all FileTestQuality)
       → repo-wide TQS (0-100)

8. Return MetricResult(
       metric_name="test_quality_score",
       value=aggregate_tqs,
       unit="score",
       direction=Direction.MAXIMIZE,
       breakdown={path: composite_tqs for each source file},
       tool="test_quality",
   )

9. Store _detailed_results on self for identify_targets()
```

---

## 6. Design Decisions

| Decision | Rationale |
|---|---|
| Convention-only test mapping (Phase 1) | Coverage-based fallback deferred — too expensive (subprocess per test file). Unmapped files get score 0 for assertion quality |
| `identify_targets()` sorts by composite TQS only | Consistent with ComplexityAdapter pattern; weights already encode relative importance |
| `FileTestQuality` stays adapter-internal | No changes to `MetricResult` or framework contract; reports see flat `breakdown` only |
| All intermediate models in `test_quality.py` | Adapter-internal, not part of framework exchange format |
| `frozen=True` dataclasses | Measurement snapshots; immutability prevents bugs, enables caching |
| `frozenset[int]` for line sets | Supports frozen dataclass pattern; created once, read many times |
| `tuple` over `list` in frozen fields | Python requirement — lists are mutable, incompatible with `frozen=True` |
| `_detailed_results` instance cache | Keeps `MetricResult.breakdown` flat (`dict[str, float]`) per framework contract while enabling richer `identify_targets()` logic |
| Pure module-level helpers | 80%+ of logic unit-testable with synthetic data, no subprocess mocking needed |
| `classify_assertion(node: ast.AST)` takes AST node | Caller walks AST once, hands nodes to classifier — avoids re-parsing |
| `TQSWeights` is mutable (not frozen) | Configuration object, not a measurement snapshot |

---

## 7. Files to Create/Modify

| File | Action |
|---|---|
| `src/autoforge/adapters/test_quality.py` | **Create** — adapter class, all dataclasses, all helper functions |
| `src/autoforge/registry.py` | **Modify** — register `"test_quality"` adapter |
| `src/autoforge/workflows/test_quality.yaml` | **Create** — workflow config |
| `tests/test_test_quality_adapter.py` | **Create** — unit tests |

---

## 8. Verification Plan

- **Unit tests** (mocked/synthetic data): assertion classification, function gap detection, score computation, weight redistribution, convention-based file mapping
- **Integration test**: small test project with known gaps → verify TQS reflects quality level, per-file breakdown ranks files correctly
- **CLI smoke**: `autoforge run test_quality --path ./src --target 80`
- **Edge cases**: no tests exist (TQS ~0), 100% coverage but no assertions (penalized), mutation disabled (weights redistribute), test files with no source match (excluded)
