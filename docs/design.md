# AutoForge: Autonomous Metric-Driven Agentic Coding System

## Architecture & Plan

**Vision:** An extensible framework where AI coding agents autonomously improve codebases by iterating against measurable feedback signals — generalizing the pattern proven by code-complexity-measure + agentic-coding-skills to any quantifiable code quality dimension.

## 1. The Core Insight

The existing system demonstrates a powerful pattern:

```
Measure complexity → Agent refactors → Re-measure → Iterate until target met
```

This is a specific instance of a general **Metric-Guided Autonomous Loop** (the core pattern behind AutoForge). The same pattern applies wherever we have:

1. A **measurable signal** (numeric, comparable, automatable)
2. An **action space** the agent can operate in (code edits, config changes, test authoring)
3. A **termination condition** (target met, budget exhausted, no further improvement)

Karpathy's autoresearch validates this at the research level — LLMs + quantitative feedback + iteration budget = surprisingly capable autonomous work. We're applying this to software engineering.

## 2. Design Principles

| Principle | Rationale |
|-----------|-----------|
| **Metric-first** | Every workflow starts from a measurable signal. No metric, no workflow. |
| **Regression-guarded** | Every iteration must pass existing tests + preserve other metrics. An agent improving coverage must not degrade complexity. |
| **Budget-bounded** | Hard caps on iterations, tokens, and wall-clock time. Runaway loops are the #1 risk. |
| **Composable** | Workflows can chain (refactor → test → benchmark) or run in parallel with cross-constraints. |
| **Language-agnostic core, language-specific adapters** | Orchestration logic is universal; metric collection and tooling is per-ecosystem. |
| **Agent-native** | Claude Code is the agent runtime. The system is designed around its strengths (tool use, file editing, bash, subagents). |

## 3. Architecture

### 3.1 High-Level Components

```
┌──────────────────────────────────────────────────────┐
│                   Orchestrator                        │
│  ┌────────────┐  ┌────────────┐  ┌────────────────┐ │
│  │  Workflow   │  │  Budget    │  │  Regression    │ │
│  │  Registry   │  │  Manager   │  │  Guard         │ │
│  └─────┬──────┘  └─────┬──────┘  └───────┬────────┘ │
└────────┼───────────────┼─────────────────┼───────────┘
         │               │                 │
    ┌────▼───────────────▼─────────────────▼────┐
    │              Workflow Runner                │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
    │  │ Measure  │→│  Agent   │→│ Validate │ │
    │  │ (before) │  │  Action  │  │ (after)  │ │
    │  └──────────┘  └──────────┘  └──────────┘ │
    │       ▲                           │        │
    │       └───── iterate ─────────────┘        │
    └────────────────────────────────────────────┘
                    │
              ┌─────▼──────┐
              │   Metric   │
              │  Adapters  │
              │ (per-lang  │
              │  per-type) │
              └────────────┘
```

### 3.2 Component Responsibilities

**Orchestrator** — The top-level controller. Receives a goal (e.g., "improve test coverage to 80%"), selects the appropriate workflow, allocates budget, and manages cross-workflow constraints.

**Workflow Registry** — Declarative catalog of available workflows. Each entry defines: metric type, tool dependencies, language support, default targets, and budget guidelines.

**Budget Manager** — Enforces hard limits:
- Max iterations per workflow run
- Max total token spend (LLM cost control)
- Max wall-clock time
- Max number of files modified per iteration
- "Improvement stall" detection (abort if N consecutive iterations show < threshold improvement)

**Regression Guard** — Before accepting any iteration's changes:
- Runs existing test suite
- Checks that other tracked metrics haven't degraded beyond tolerance
- Validates no new lint/type errors introduced
- Acts as the "do no harm" gate

**Workflow Runner** — Executes the measure → act → validate loop for a specific workflow. Stateless per-iteration; all state lives in the filesystem (git working tree).

**Metric Adapters** — Each adapter encapsulates both the tool invocation and output normalization for a specific metric type. An adapter handles prerequisite checks, runs the underlying tool (pytest-cov, istanbul, semgrep, etc.), parses the output, and returns a standard schema:

```json
{
  "metric_name": "branch_coverage",
  "value": 72.3,
  "unit": "percent",
  "breakdown": { "file_a.py": 45.0, "file_b.py": 91.2 },
  "tool": "pytest-cov",
  "timestamp": "..."
}
```

### 3.3 Orchestration Layer Decision: Claude Code as Agent Runtime

**Hybrid approach:** Use Claude Code as the agent that does the actual work (code analysis, editing, tool invocation), but wrap it with a lightweight CLI driver that handles:
- Budget enforcement (iteration count, token tracking)
- Structured logging (metric values per iteration, diffs applied)
- Git branch/commit management per iteration (for rollback)
- Cross-workflow coordination

The driver is deliberately thin — it doesn't make code decisions, it just manages the loop lifecycle. This keeps the "intelligence" in Claude Code where it belongs, while adding the mechanical guarantees that an LLM shouldn't be trusted with (budget limits, git safety).

**Multi-agent execution model:** Each workflow gets its own Claude Code instance, operating on its own git branch.

```
┌──────────────────────────────────┐
│      CLI Driver (Python)         │  ← budget, logging, git, coordination
│      ~500 lines                  │
└──┬──────────┬──────────┬────────┘
   │ spawn    │ spawn    │ spawn     (parallel on separate branches)
┌──▼───────┐┌─▼────────┐┌▼────────┐
│ Claude   ││ Claude   ││ Claude  │
│ Code #1  ││ Code #2  ││ Code #3 │
│ coverage ││ types    ││ security│
│ branch A ││ branch B ││ branch C│
└──────────┘└──────────┘└─────────┘
   │            │           │
   └────────────┴───────────┘
         merge on completion
```

## 4. Workflow Catalog

### 4.1 Proven (Exists Today)

| Workflow | Metric | Tools | Status |
|----------|--------|-------|--------|
| Complexity Refactoring | Cyclomatic/cognitive complexity score | code-complexity-measure | ✅ Production |

### 4.2 High-ROI Next Candidates

#### 4.2.1 Test Quality & Test-Driven Implementation

**Key insight:** The highest value isn't in improving line coverage on existing code — it's in using test quality as a specification signal that drives implementation.

**Two modes of operation:**

- **Mode A — Improve test quality on existing code (retrofit)**
- **Mode B — Test-as-Spec Implementation Loop (greenfield / feature development)**

Test quality metrics:

| Metric | What it measures | Tool |
|--------|-----------------|------|
| Mutation score | Do tests actually catch bugs when code is mutated? | mutmut, Stryker |
| Use-case coverage | Are real user scenarios tested? | LLM-as-judge |
| Edge case coverage | Boundary conditions, empty inputs, error paths | LLM-as-judge + mutation |
| Assertion density | Meaningful assertions per test | AST analysis |
| Contract verification | API contracts, invariants, pre/post conditions | LLM-as-judge |
| Branch coverage | Traditional code path coverage | pytest-cov, c8 |

Composite score:
```
0.35 * mutation_score +
0.25 * usecase_coverage +
0.20 * edge_case_coverage +
0.10 * assertion_density_score +
0.10 * branch_coverage
```

#### 4.2.2 Type Safety & Static Analysis

Metric: Type error count (pyright/mypy strict mode), type coverage %

#### 4.2.3 Security Vulnerability Remediation

Metric: SAST finding count by severity (critical/high/medium/low)

#### 4.2.4 Performance Optimization

Metric: Benchmark execution time, memory allocation counts, p50/p99 latency

#### 4.2.5 Documentation & API Completeness

Metric: % public APIs with docstrings, doc coverage score

#### 4.2.6 LLM-as-Judge Workflows (Subjective Quality)

Metric: Structured score from a reviewer LLM (1-10 on readability, architecture adherence)

## 5. Key Design Decisions

### 5.1 Git-Based Iteration State

Each iteration operates on a git branch. The driver:
1. Creates a branch: `autoforge/{workflow}/{timestamp}`
2. Agent makes changes, driver commits after each iteration
3. On success: squash-merge to source branch (or leave as PR)
4. On failure/abort: branch is preserved for inspection

### 5.2 Multi-Metric Constraints

Each workflow declares:
- **Primary metric:** the optimization target
- **Constraint metrics:** must not degrade beyond tolerance

```yaml
workflow: test_coverage
primary_metric:
  name: branch_coverage
  target: 80
  direction: maximize
constraint_metrics:
  - name: complexity_score
    tolerance: 5
    direction: minimize
  - name: test_suite_time
    tolerance: 20
    direction: minimize
```

### 5.3 Improvement Stall Detection

If the metric doesn't improve by at least `min_improvement_threshold` for `stall_patience` consecutive iterations, abort.

Default: `stall_patience = 3`, `min_improvement_threshold = 0.5%`

### 5.4 Scope Control

- File-level targeting
- Priority ordering (worst metric values first)
- Max files per iteration (default: 5)
- Incremental PRs with bounded scope

### 5.5 Observability & Reporting

Each workflow run produces a structured JSON report with per-iteration metrics, timing, and token usage.

## 6. Composite Workflows

### 6.1 Sequential Pipeline

```
Complexity Refactor → Test Coverage → Type Safety → Security Scan
```

### 6.2 Parallel with Merge

Run coverage and type-safety improvements in parallel on separate branches, then merge.

### 6.3 Health Check Mode

Run all metric adapters without agent action — produce a codebase health dashboard.

## 7. Phased Roadmap

### Phase 0: Foundation (Weeks 1-2)

**Goal:** Extract the proven pattern into a reusable framework.

- Standard metric adapter interface (input/output schema)
- Workflow configuration schema (YAML)
- CLI driver skeleton (iteration loop, budget enforcement, git management)
- Wrap code-complexity-measure as first metric adapter
- Structured logging and run report generation
- Basic regression guard (run tests between iterations)
- GitHub Actions integration
- Per-run report output (JSON + markdown summary)

**Deliverable:** The existing complexity refactoring workflow runs through the new framework with identical results.

### Phase 1: Test Quality & Test-as-Spec Workflow (Weeks 3-6)

### Phase 2: Type Safety + Security (Weeks 6-8)

### Phase 3: Health Dashboard + LLM-as-Judge + Sandbox (Weeks 9-11)

### Phase 4: Scale & Ecosystem (Weeks 12+)

## 8. Success Metrics

| Metric | Target |
|--------|--------|
| Workflow generalization | 5+ distinct workflows sharing the same core |
| Cross-language support | Python + JS/TS for all Phase 1-2 workflows |
| Autonomous success rate | >70% of runs reach target |
| Cost efficiency | <$5 average token cost per workflow run |
| Regression rate | <5% of runs introduce test failures |
| Time to add new workflow | <1 day |

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Semantically wrong changes | High | Mutation testing as constraint; human review |
| Metric gaming | Medium | Constraint metrics; quality gates |
| Runaway token costs | Medium | Hard budget caps; stall detection |
| Noisy metrics | Medium | Statistical significance checks |
| Tool installation differences | Low | Docker-based metric runner |
| Context window limits | Medium | File-level scoping; priority ordering |

## Appendix A: Workflow Configuration Schema

See `src/autoforge/workflows/complexity_refactor.yaml` for the reference implementation.

## Appendix B: Standard Metric Adapter Interface

See `src/autoforge/models.py` for `MetricResult` and `MetricAdapter` protocol, and `src/autoforge/adapters/base.py` for `BaseMetricAdapter` ABC.
