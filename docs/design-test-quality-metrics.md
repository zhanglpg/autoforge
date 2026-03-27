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

**Resolution: Spec coverage is out of scope for the script-based TQS metric.**

Evaluating whether tests fully specify a design is fundamentally a **semantic judgment** -- it requires understanding intent, not just matching keywords. A test named `test_add` doesn't tell you whether it adequately specifies the addition behavior described in a design doc. Keyword matching produces false positives (name overlap without semantic coverage) and false negatives (tests that cover a requirement using different terminology).

**LLM-as-judge is the right tool for this.** It can read the design spec and the test suite, understand what each test actually verifies, and judge whether the spec's requirements are adequately covered. This belongs in a separate **LLM-as-judge evaluation step** (see Section 4.2.6 of the main design doc), not in the deterministic script-based metric adapter.

The script-based TQS focuses on what scripts can reliably measure: coverage, function gaps, assertion quality, and mutation testing. Spec-to-test traceability will be handled by a future LLM-as-judge workflow that can be composed with TQS as a constraint or run as a separate evaluation pass.

### Per-File Decomposition

AutoForge requires `MetricResult.breakdown: dict[str, float]` mapping files to scores. For test quality, the natural unit is **per-source-file** -- "how well is `src/foo.py` tested?"

Test-to-source mapping uses **convention-based matching with coverage-based fallback**:
1. Try convention: `test_foo.py` -> `foo.py`
2. Fallback: run coverage per test file to discover which source files it exercises

---

## Proposed Design: Test Quality Score (TQS)

### Composite Metric

TQS is a **0-100 score** combining four script-based sub-metrics:

| Sub-metric | Default Weight | Source | Speed |
|---|---|---|---|
| **Coverage score** | 30% | `coverage.py` / `pytest-cov` (line + branch) | Fast |
| **Function coverage gaps** | 20% | AST analysis + coverage data | Fast |
| **Assertion quality score** | 30% | AST analysis of test files | Very fast |
| **Mutation score** | 20% | `mutmut` (sampled) | Slow |

When mutation testing is disabled (default), its weight redistributes proportionally among the other three.

```
TQS = w_cov x coverage + w_func x func_coverage + w_assert x assertion_quality
    + w_mut x mutation_score
```

**Weight redistribution example:** With mutation disabled, the remaining weights normalize to: coverage=37.5%, function gaps=25%, assertion quality=37.5%.

**Note:** Spec-to-test coverage (whether tests fully specify a design doc) is intentionally excluded from TQS. It requires semantic judgment that scripts cannot reliably perform and will be handled by a separate LLM-as-judge evaluation (see "Out of Scope" section below).

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
- Per-function scoring with three components:
  - **Depth (60%)**: Diminishing-returns curve `(1 - e^(-effective/2)) x 100` — first 2-3 strong assertions provide most value
  - **Strength ratio (30%)**: `(strong + 0.5 x structural) / total x 100` — adding weak assertions dilutes this, penalising spam
  - **Presence (10%)**: Binary check that the function asserts anything
- File score = average of per-function scores (empty test functions contribute 0)
- Files with no test file -> score 0
- Typical scores: 3 strong -> ~87, 15 weak -> ~57, 3 strong + 10 weak spam -> ~72
- Rationale: Catches the "coverage without verification" problem while preventing assertion spam — adding junk assertions actively hurts the score via strength-ratio dilution

**4. Mutation Score (0-100, optional):**
- Run `mutmut` on sampled files (configurable sample size, default top-5 by coverage gap)
- Score = `(killed_mutants / total_mutants) x 100`
- Default: disabled (`mutation_weight=0.0`) -- too slow for most iterative loops
- Recommended for: final validation pass, CI gates, or small codebases
- Rationale: Gold standard for test effectiveness, but cost must be managed

### Direction

`Direction.MAXIMIZE` -- higher TQS is better.

---

## Out of Scope: Spec Coverage (LLM-as-Judge)

**Spec-to-test traceability** -- measuring whether tests fully specify a design document -- is explicitly out of scope for the script-based TQS metric.

**Why:** Evaluating whether a test adequately covers a design requirement is a semantic judgment. A test named `test_user_creation` might or might not verify the "users can register with email and password" requirement from a spec. Keyword matching produces unreliable results (false positives from name overlap, false negatives from different terminology). Only an LLM can read both the spec and the test and judge whether the intent is covered.

**Where it belongs:** This will be implemented as a separate **LLM-as-judge evaluation** workflow (see main design doc Section 4.2.6). It can be:
- Run as a standalone evaluation pass after TQS-driven test improvement
- Composed as a constraint metric alongside TQS in a multi-metric workflow
- Used in the test-as-spec implementation loop where the agent writes tests against a design doc

**Interaction with TQS:** The script-based TQS ensures tests are structurally sound (good coverage, meaningful assertions, mutation-resilient). The LLM-as-judge spec coverage ensures tests are semantically complete (all design requirements are verified). Together they form the full test quality picture, but they are measured by fundamentally different mechanisms.

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
    #   coverage_weight: float = 0.30
    #   func_coverage_weight: float = 0.20
    #   assertion_weight: float = 0.30
    #   mutation_weight: float = 0.20  (0.0 to disable)
    #   mutation_sample_size: int = 5
    #   test_command: str = "pytest"
    #   test_dir_pattern: str = "tests/"
    #   branch_coverage: bool = True

    def check_prerequisites(self, repo_path):
        # Verify pytest, coverage.py installed
        # Verify target has .py files
        # If mutation_weight > 0, verify mutmut installed

    def measure(self, repo_path, target_path):
        # 1. Run pytest --cov -> parse coverage JSON
        # 2. AST-analyze source files for public function list
        # 3. Cross-ref functions with coverage for gap detection
        # 4. Map test files to source files (convention + fallback)
        # 5. AST-analyze test files for assertion quality
        # 6. If mutation_weight > 0: run sampled mutmut
        # 7. Compute per-file TQS with active weight redistribution
        # 8. Aggregate into overall TQS
        # 9. Return MetricResult(
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

# --- Weight redistribution ---
_compute_active_weights(weights_dict, active_metrics) -> dict[str, float]:
    # Filter to active metrics, normalize so sum = 1.0
    # Return {metric_name: normalized_weight}
```

### Workflow YAML

```yaml
name: test_quality
version: "1.0"
description: "Improve test suite quality through iterative test generation and enhancement"
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
    You are improving test quality. For each target file:
    1. If no tests exist, write comprehensive tests covering all public functions
    2. If tests exist but lack assertions, add meaningful strong assertions
    3. Each test should have 2-3 strong assertions (assertEqual, specific value checks)
    4. Cover edge cases, error paths, and boundary values
    5. Prefer testing behavior over implementation details
    6. Name tests descriptively to reflect the behavior they verify
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
   - Score computation: verify weighted composite calculation, weight redistribution
   - File mapping: convention-based + fallback logic

2. **Integration test**:
   - Create a small test project with known gaps (missing tests, empty assertions)
   - Run adapter, verify TQS reflects the known quality level
   - Verify per-file breakdown ranks files correctly

3. **CLI smoke test**:
   - `autoforge run test_quality --path ./src --target 80`
   - `autoforge health --path ./src`

4. **Edge cases**:
   - No tests exist at all -> TQS near 0
   - 100% coverage but no assertions -> TQS penalized by assertion quality score
   - Mutation testing disabled -> weights redistribute across remaining three
   - Test files that don't map to any source file -> excluded from scoring
