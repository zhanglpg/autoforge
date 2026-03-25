# Design Doc: Test Quality Metrics for AutoForge (Phase 1)

## Context

AutoForge's iteration loop currently supports **complexity reduction** as its only metric adapter. We want to add a **test quality** adapter designed for **test-driven implementation**: the agent writes tests that fully specify a design spec, then the framework measures how well the tests cover that spec and how robust the tests are.

The core challenge: **what does "test quality" actually mean, and how do we quantify it as a single actionable number?**

---

## Brainstorm: What Can Be Measured?

### Candidate Signals

| Signal | What it tells you | Pros | Cons |
|---|---|---|---|
| **Line coverage** | Which lines execute during tests | Well-understood, fast, universal tooling | Doesn't prove tests *verify* anything |
| **Branch coverage** | Which decision branches are exercised | Catches edge cases line coverage misses | Same "no assertion" problem |
| **Mutation score** | Would tests catch injected bugs? | Gold standard for fault-detection ability | Very slow (10-100x test runtime) |
| **Assertion density** | Assertions per test function | Cheap to compute, correlates with thoroughness | Gameable (`assert True` x100) |
| **Assertion quality** | Types of assertions used | Distinguishes meaningful checks from trivial ones | Requires AST analysis, language-specific |
| **Function coverage** | % of functions with any test | Quick gap analysis | Binary per-function, no depth |
| **Spec coverage** | % of design requirements with corresponding tests | Directly measures TDD intent | Requires structured spec input |
| **Test-to-code ratio** | Lines of test vs production code | Simple proxy for investment | Quantity != quality |
| **Test isolation** | Independence between tests | Important for reliability | Hard to measure without running permutations |
| **Flakiness rate** | Consistency across repeated runs | Critical reliability signal | Requires multiple runs, slow |

### Debate 1: Coverage vs. Mutation Testing

**Coverage** is the obvious starting point -- fast, well-tooled, universally understood. But it has a fatal flaw:

```python
def add(a, b):
    return a + b

def test_add():
    add(1, 2)  # 100% coverage, ZERO verification
```

Coverage answers "did the code run?" not "did we check the result?"

**Mutation testing** solves this by injecting small bugs (mutants) and checking if tests catch them. But it's 10-100x slower -- running it every iteration would be prohibitively expensive.

**Resolution:** Use coverage as the foundation. Use assertion analysis to catch the "empty test" problem cheaply. Offer mutation testing as **sampled** -- run on a configurable subset of files per iteration to keep cost manageable.

### Debate 2: Assertion Counting vs. Assertion Quality

Raw assertion count is gameable. But classifying assertions is more meaningful:

- **Strong**: `assertEqual`, `assertRaises`, `assert x == y` -- verify specific behavior
- **Weak**: `assert True`, `assertIsNotNone(result)` -- prove existence, not correctness
- **Structural**: `assertIsInstance`, `assert len(x) > 0` -- verify shape, not values

Weighted scoring (strong=1.0, structural=0.5, weak=0.2) gives a more meaningful signal.

### Debate 3: Spec Coverage -- The TDD Dimension

For test-driven implementation, the most important question is: **do the tests fully specify the design?** None of the traditional metrics answer this. We need a new signal.

**The problem:** Given a design spec document and a test suite, measure what fraction of the spec's requirements are covered by tests.

**Approaches considered:**

| Approach | How it works | Pros | Cons |
|---|---|---|---|
| **Keyword matching** | Extract key terms from spec, check if they appear in test names/docstrings | Fast, deterministic | Shallow -- matching words != matching intent |
| **LLM-as-judge** | Have Claude evaluate spec-vs-test alignment | Understands intent, handles natural language | Expensive (tokens per measurement), non-deterministic |
| **Structured requirements** | Require spec to use tagged requirements (`REQ-001`), tests to reference them | Precise, fast, auditable | Requires spec format discipline |
| **Hybrid: extract then match** | Use LLM once to extract requirements from spec into structured format, then do deterministic matching each iteration | Intent-aware extraction, fast iteration measurement | One-time LLM cost, simpler matching |

**Resolution: Hybrid approach.**

1. **Spec parsing step** (once per run): Parse the design spec to extract a structured list of requirements/behaviors. Support two modes:
   - **Structured spec**: Spec already has numbered requirements, bullet points, or section headers -- extract directly via parsing
   - **Freeform spec**: Use regex/heuristics to extract requirement-like sentences (LLM extraction as future enhancement)
2. **Test matching step** (each iteration): For each extracted requirement, check if a corresponding test exists by:
   - Test function name contains requirement keywords
   - Test docstring references the requirement ID or description
   - Coverage data shows the relevant code path is exercised
3. **Score**: `spec_coverage = matched_requirements / total_requirements x 100`

This gives us the TDD signal -- "what % of the design spec has tests?" -- without per-iteration LLM cost.

### Per-File Decomposition

AutoForge requires `MetricResult.breakdown: dict[str, float]` mapping files to scores. For test quality, the natural unit is **per-source-file** -- "how well is `src/foo.py` tested?"

Test-to-source mapping uses **convention-based matching with coverage-based fallback**:
1. Try convention: `test_foo.py` -> `foo.py`
2. Fallback: run coverage per test file to discover which source files it exercises

---

## Proposed Design: Test Quality Score (TQS)

### Composite Metric

TQS is a **0-100 score** combining five sub-metrics:

| Sub-metric | Default Weight | Source | Speed |
|---|---|---|---|
| **Coverage score** | 25% | `coverage.py` / `pytest-cov` (line + branch) | Fast |
| **Function coverage gaps** | 15% | AST analysis + coverage data | Fast |
| **Assertion quality score** | 20% | AST analysis of test files | Very fast |
| **Spec coverage score** | 25% | Spec parsing + test matching | Fast (after initial parse) |
| **Mutation score** | 15% | `mutmut` (sampled) | Slow |

When a sub-metric is disabled (mutation testing off, or no spec file provided), its weight redistributes proportionally among the remaining active sub-metrics.

```
TQS = w_cov x coverage + w_func x func_coverage + w_assert x assertion_quality
    + w_spec x spec_coverage + w_mut x mutation_score
```

**Weight redistribution example:** If both mutation and spec are disabled, only coverage (25%), function gaps (15%), and assertion quality (20%) remain. Normalized: coverage=41.7%, function gaps=25%, assertion quality=33.3%.

### Sub-metric Definitions

**1. Coverage Score (0-100):**
- Combined: `0.6 x line_coverage + 0.4 x branch_coverage`
- Source: `pytest --cov={target} --cov-report=json --cov-branch`
- Per-file breakdown directly from coverage JSON report
- Rationale: Line coverage is the baseline; branch coverage catches conditional logic gaps

**2. Function Coverage Gaps (0-100):**
- AST-parse source files to list all public functions/methods
- Cross-reference with coverage data to identify untested functions
- Score = `(tested_functions / total_functions) x 100`
- Highly actionable: the agent can see exactly which functions need tests
- Rationale: Even with high line coverage, entire functions can be missed; this catches that

**3. Assertion Quality Score (0-100):**
- For each source file's test file(s), AST-parse to find assertions
- Classify each assertion:
  - **Strong** (weight 1.0): `assertEqual`, `assertRaises`, `assert x == y`, `pytest.raises`, value comparisons
  - **Structural** (weight 0.5): `assertIsInstance`, `assert len(x) > 0`, `assertIn`
  - **Weak** (weight 0.2): `assert True`, `assertIsNotNone(result)`, bare `assert x`
- Compute weighted assertion density per test function
- Score = `min(100, weighted_density x 33.3)` (0 assertions -> 0, 1 strong -> 33, 3+ strong -> 100)
- Files with no test file -> score 0
- Rationale: Catches the "coverage without verification" problem without mutation testing overhead

**4. Spec Coverage Score (0-100):**
- **Input**: Design spec file path passed via `spec_file` adapter parameter (markdown, text, or structured YAML)
- **Extraction** (once per run): Parse spec into list of requirements
  - Structured: extract bullet points, numbered items, section headers
  - Each requirement gets: `{id, description, keywords[]}`
- **Matching** (each iteration): For each requirement, check if a test covers it:
  - Test function name contains requirement keywords
  - Test docstring references the requirement ID or description
  - Coverage data shows the relevant code path is exercised
- Score = `(matched_requirements / total_requirements) x 100`
- When no spec file is provided: sub-metric is excluded, weights redistribute
- Rationale: This is the TDD dimension -- "do tests specify the design?" -- which no traditional metric captures

**5. Mutation Score (0-100, optional):**
- Run `mutmut` on sampled files (configurable sample size, default top-5 by coverage gap)
- Score = `(killed_mutants / total_mutants) x 100`
- Default: disabled (`mutation_weight=0.0`) -- too slow for most iterative loops
- Recommended for: final validation pass, CI gates, or small codebases
- Rationale: Gold standard for test effectiveness, but cost must be managed

### Direction

`Direction.MAXIMIZE` -- higher TQS is better.

---

## Adapter Implementation Plan

### Language Scope

**Python-only** for Phase 1. The adapter pattern (BaseMetricAdapter subclass) makes it straightforward to add language variants later by swapping coverage tools (istanbul, go test -cover, JaCoCo) and assertion classification rules.

### New Files

| File | Action |
|---|---|
| `src/autoforge/adapters/test_quality.py` | **Create** -- adapter + helpers |
| `src/autoforge/workflows/test_quality.yaml` | **Create** -- workflow config |
| `src/autoforge/registry.py` | **Modify** -- register `test_quality` adapter |
| `tests/test_test_quality_adapter.py` | **Create** -- unit tests |

### TestQualityAdapter Class

```python
class TestQualityAdapter(BaseMetricAdapter):
    name = "test_quality"
    supported_languages = ["python"]

    # Constructor params:
    #   coverage_weight: float = 0.25
    #   func_coverage_weight: float = 0.15
    #   assertion_weight: float = 0.20
    #   spec_weight: float = 0.25
    #   mutation_weight: float = 0.15  (0.0 to disable)
    #   mutation_sample_size: int = 5
    #   test_command: str = "pytest"
    #   test_dir_pattern: str = "tests/"
    #   spec_file: str | None = None  (path to design spec)
    #   branch_coverage: bool = True

    def check_prerequisites(self, repo_path):
        # Verify pytest, coverage.py installed
        # Verify target has .py files
        # If mutation_weight > 0, verify mutmut installed
        # If spec_file set, verify file exists

    def measure(self, repo_path, target_path):
        # 1. Run pytest --cov -> parse coverage JSON
        # 2. AST-analyze source files for public function list
        # 3. Cross-ref functions with coverage for gap detection
        # 4. Map test files to source files (convention + fallback)
        # 5. AST-analyze test files for assertion quality
        # 6. If spec_file: parse spec -> match requirements to tests
        # 7. If mutation_weight > 0: run sampled mutmut
        # 8. Compute per-file TQS with active weight redistribution
        # 9. Aggregate into overall TQS
        # 10. Return MetricResult(
        #       metric_name="test_quality_score",
        #       value=aggregate_tqs,
        #       unit="score",
        #       direction=Direction.MAXIMIZE,
        #       breakdown={source_file: file_tqs, ...},
        #       tool="test_quality",
        #       timestamp=utc_now
        #     )

    def identify_targets(self, result, n):
        # Sort breakdown by TQS ascending (worst-tested first)
        # Return top-n source file paths
```

### Internal Helpers

```python
# --- Coverage ---
_run_coverage(target_path, test_command) -> dict[str, CoverageData]:
    # Run pytest --cov={target} --cov-report=json --cov-branch
    # Parse coverage.json
    # Return {source_file: {line_pct, branch_pct, covered_lines, missing_lines}}

# --- Function gap analysis ---
_extract_public_functions(source_path) -> list[FunctionInfo]:
    # AST-parse source file
    # Return list of {name, lineno, end_lineno} for public functions/methods

_find_uncovered_functions(functions, coverage_data) -> list[str]:
    # Cross-ref function line ranges with covered_lines
    # Return names of functions with 0% coverage

# --- Assertion analysis ---
_analyze_assertions(test_file_path) -> AssertionReport:
    # AST-parse test file
    # Find test functions (def test_* or methods in TestCase subclass)
    # Walk AST for: assert stmts, self.assert* calls, pytest.raises
    # Classify each as strong/structural/weak
    # Return {test_count, total_assertions, weighted_score, strong_ratio}

# --- Test-to-source mapping ---
_map_tests_to_sources(target_path, test_dir) -> dict[str, list[str]]:
    # Phase 1: Convention-based (test_foo.py -> foo.py)
    # Phase 2: Coverage-based fallback for unmatched files
    # Return {source_file: [test_files]}

# --- Spec parsing ---
@dataclass
class Requirement:
    id: str           # "REQ-001" or auto-generated "req_1"
    description: str  # the requirement text
    keywords: list[str]  # extracted keywords for matching

_parse_spec_requirements(spec_file) -> list[Requirement]:
    # Parse markdown: extract bullet points, numbered items, headers
    # For each, extract keywords (nouns, verbs, key phrases)
    # Return structured requirement list

# --- Spec-to-test matching ---
_match_requirements_to_tests(requirements, test_files, coverage_data) -> dict[str, bool]:
    # For each requirement:
    #   1. Check test function names for keyword matches
    #   2. Check test docstrings for requirement ID/description matches
    #   3. Optionally check coverage data for code path exercise
    # Return {requirement_id: is_covered}

# --- Weight redistribution ---
_compute_active_weights(weights_dict, active_metrics) -> dict[str, float]:
    # Filter to active metrics, normalize so sum = 1.0
    # Return {metric_name: normalized_weight}
```

### Workflow YAML

```yaml
name: test_quality
version: "1.0"
description: "Improve test quality through iterative test-driven implementation"
adapter: test_quality

primary_metric:
  name: test_quality_score
  direction: maximize
  default_target: 80.0

constraint_metrics:
  - name: test_suite_pass
    tolerance_percent: 0
    direction: maximize

budget:
  max_iterations: 15
  max_tokens: 500000
  max_wall_clock_minutes: 45
  stall_patience: 3
  min_improvement_percent: 2.0
  max_files_per_iteration: 5

scope:
  priority: worst_first

agent:
  skill: "improve-test-quality"
  system_prompt_addendum: |
    You are writing tests for a test-driven implementation. For each target file:
    1. Review the design spec requirements that lack test coverage
    2. Write tests that specify the required behavior BEFORE implementation
    3. Each test should have 2-3 strong assertions (assertEqual, specific value checks)
    4. Cover edge cases, error paths, and boundary values
    5. Name tests descriptively to reflect the spec requirement they verify
    6. Include docstrings referencing the spec requirement being tested
```

### Registry Update

```python
# In src/autoforge/registry.py
from autoforge.adapters.test_quality import TestQualityAdapter

_ADAPTER_REGISTRY = {
    "complexity": ComplexityAdapter,
    "test_quality": TestQualityAdapter,
}
```

---

## Verification Plan

1. **Unit tests** (mocked data):
   - Assertion analysis: test classification of strong/weak/structural
   - Function gap detection: verify uncovered functions found correctly
   - Spec parsing: test extraction from markdown with bullet points, numbered lists, headers
   - Spec matching: test keyword/docstring-based requirement matching
   - Score computation: verify weighted composite calculation, weight redistribution
   - File mapping: convention-based + fallback logic

2. **Integration test**:
   - Create a small test project with known gaps (missing tests, empty assertions, unmatched spec items)
   - Run adapter, verify TQS reflects the known quality level
   - Verify per-file breakdown ranks files correctly

3. **CLI smoke test**:
   - `autoforge run test_quality --path ./src --target 80`
   - `autoforge run test_quality --path ./src --target 80 --spec-file design.md`
   - `autoforge health --path ./src`

4. **Edge cases**:
   - No tests exist at all -> TQS near 0
   - 100% coverage but no assertions -> TQS penalized by assertion quality score
   - No spec file provided -> spec sub-metric excluded, weights redistribute
   - All spec requirements matched -> spec score = 100
   - Empty spec file -> spec sub-metric excluded gracefully
   - Test files that don't map to any source file -> excluded from scoring
