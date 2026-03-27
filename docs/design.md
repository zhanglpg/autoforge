# AutoForge: Metric-Driven Coding Tools for AI Agents

## Architecture & Plan

**Vision:** An extensible measurement toolkit that AI coding agents use to iteratively improve codebases against quantifiable metrics &mdash; generalizing the pattern proven by code-complexity-measure + agentic-coding-skills to any code quality dimension.

**Key insight:** AutoForge is not an agent. It's a set of tools (`measure`, `targets`, `skill-info`) that agents call during their workflows. The agent drives the iteration loop; AutoForge provides structured metric data and workflow configuration.

## 1. The Core Pattern

The existing system demonstrates a powerful pattern:

```
Agent measures → Agent refactors → Agent re-measures → Agent iterates until target met
```

AutoForge provides the **measurement infrastructure** for this pattern. Wherever there is:

1. A **measurable signal** (numeric, comparable, automatable)
2. An **action space** the agent can operate in (code edits, config changes, test authoring)
3. A **termination condition** (target met, budget exhausted, no further improvement)

...AutoForge can provide the `measure` and `targets` commands that the agent calls as tools.

## 2. Design Principles

| Principle | Rationale |
|-----------|-----------|
| **Tool, not agent** | AutoForge provides measurement commands; the AI agent provides intelligence. Clean separation of concerns. |
| **Metric-first** | Every workflow starts from a measurable signal. No metric, no workflow. |
| **Regression-guarded** | Skill descriptions instruct agents to run tests between iterations. Autonomous mode enforces this mechanically. |
| **Budget-bounded** | Workflow configs define iteration/token/time limits. Skill descriptions communicate these to agents; autonomous mode enforces them. |
| **Composable** | Workflows can chain (refactor → test → benchmark) or run in parallel with cross-constraints. |
| **Language-agnostic core, language-specific adapters** | CLI and orchestration logic is universal; metric collection is per-ecosystem. |
| **Agent-native** | Designed around AI agents' strengths (tool use, file editing, bash, context retention). Measurement output is structured JSON for easy agent consumption. |

## 3. Architecture

### 3.1 Tool Architecture (Primary)

```
┌─────────────────────────────────────────────────┐
│            AI Agent (Claude Code, etc.)           │
│     Drives iteration loop with full context       │
│                                                   │
│  1. autoforge measure complexity → JSON result    │
│  2. autoforge targets complexity → worst files    │
│  3. Agent edits code, runs tests                  │
│  4. autoforge measure complexity → re-measure     │
│  5. Agent commits, repeats until done             │
├─────────────────────────────────────────────────┤
│              AutoForge CLI Tools                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ measure  │  │ targets  │  │  skill-info  │   │
│  └────┬─────┘  └────┬─────┘  └──────────────┘   │
│       │              │                            │
│  ┌────▼──────────────▼────┐                      │
│  │   MetricAdapter Layer  │                      │
│  │  complexity · test_quality · your own ...     │
│  └────────────────────────┘                      │
└─────────────────────────────────────────────────┘
```

The agent calls AutoForge commands as CLI tools. AutoForge returns structured JSON. The agent interprets results, decides what to change, and drives the iteration. This gives the agent:

- Full context across iterations (no stateless subprocess limitation)
- Native tool access (git, file editing, testing) without reimplementation
- Ability to reason about what's working and adapt strategy
- Better error recovery and diagnosis

### 3.2 Autonomous Runner (Legacy)

For fully unattended runs, AutoForge can also own the iteration loop:

```
┌──────────────────────────────────────────────────┐
│              AutoForge CLI Driver                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐ │
│  │ BudgetMgr  │  │  GitMgr    │  │ Regression │ │
│  │ (limits,   │  │  (branch,  │  │ Guard      │ │
│  │  stall     │  │   commit,  │  │ (tests,    │ │
│  │  detect)   │  │   rollback)│  │  checks)   │ │
│  └────────────┘  └────────────┘  └────────────┘ │
│          ↓ spawn subprocess each iteration       │
│  ┌───────────────────────────────────────────┐   │
│  │  Agent (claude --print -p "<prompt>")     │   │
│  └───────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

AutoForge spawns the agent as a subprocess each iteration, managing budget, git, and regression testing mechanically. Each agent invocation is stateless. This mode is useful for fully automated pipelines but loses the context-retention benefits of the tool architecture.

### 3.3 Component Responsibilities

**MetricAdapter** — Protocol for plugging in any measurement tool. Each adapter encapsulates tool invocation, output normalization into a standard `MetricResult`, and priority file identification. An adapter handles:
- Prerequisite checks (are required tools installed?)
- Running the underlying tool (pytest-cov, complexity-accounting, etc.)
- Parsing output into a standard schema
- Identifying worst files for agent targeting

Standard output schema:
```json
{
  "metric_name": "branch_coverage",
  "value": 72.3,
  "unit": "percent",
  "direction": "maximize",
  "breakdown": { "file_a.py": 45.0, "file_b.py": 91.2 },
  "tool": "pytest-cov",
  "timestamp": "..."
}
```

**Skill Generator** — Produces structured skill descriptions from workflow configs. These descriptions give agents complete instructions for executing a workflow: what commands to call, budget limits, constraints, and domain-specific guidance.

**WorkflowConfig** — YAML-defined workflow with metrics, budgets, constraints, and agent guidance. The single source of truth for workflow behavior.

**Workflow Registry** — Discovers adapters via Python entry points and workflows via YAML files. Third-party adapters register themselves without touching core code.

**BudgetManager** — Enforces hard limits (iterations, tokens, wall-clock time) and detects improvement stalls. In tool mode, budget rules are communicated to agents via skill descriptions. In autonomous mode, they are enforced mechanically.

**GitManager** — Creates branches, commits per iteration, supports rollback. Used by autonomous mode; in tool mode, the agent manages git natively.

**RegressionGuard** — Runs tests between iterations and checks constraint metrics. Used by autonomous mode; in tool mode, skill descriptions instruct agents to run tests.

## 4. Workflow Catalog

### 4.1 Proven (Exists Today)

| Workflow | Metric | Tools | Status |
|----------|--------|-------|--------|
| Complexity Refactoring | Net Complexity Score (NCS) | complexity-accounting | ✅ Production |
| Test Quality | Composite TQS (coverage + assertions) | pytest-cov, AST analysis | ✅ Production |

### 4.2 High-ROI Next Candidates

#### 4.2.1 Test Quality & Test-Driven Implementation

**Key insight:** The highest value isn't in improving line coverage on existing code — it's in using test quality as a specification signal that drives implementation.

**Two layers of measurement:**

- **Script-based TQS (Test Quality Score):** Deterministic, fast, runs every iteration via `autoforge measure test_quality`
- **LLM-as-judge spec coverage:** Semantic evaluation of whether tests fully specify a design doc (separate workflow, see Section 4.2.6)

Script-based TQS metrics (deterministic, run every iteration):

| Metric | What it measures | Tool |
|--------|-----------------|------|
| Line + branch coverage | Traditional code path coverage | pytest-cov, c8 |
| Function coverage gaps | % of public functions with any test | AST analysis + coverage |
| Assertion quality | Meaningful assertions per test (strong/structural/weak classification) | AST analysis |
| Mutation score (optional) | Do tests actually catch bugs when code is mutated? | mutmut, Stryker |

TQS composite score (default weights, redistribute when mutation disabled):
```
0.30 * coverage_score +
0.20 * function_coverage_gaps +
0.30 * assertion_quality_score +
0.20 * mutation_score
```

LLM-as-judge metrics (semantic, separate evaluation pass):

| Metric | What it measures | Tool |
|--------|-----------------|------|
| Spec coverage | Do tests fully specify the design document? | LLM-as-judge |
| Use-case coverage | Are real user scenarios tested? | LLM-as-judge |
| Edge case coverage | Boundary conditions, empty inputs, error paths | LLM-as-judge |
| Contract verification | API contracts, invariants, pre/post conditions | LLM-as-judge |

Spec coverage is fundamentally a semantic judgment (does `test_user_creation` actually verify the "users can register with email" requirement?) and cannot be reliably measured by keyword matching or script-based heuristics. See `docs/design-test-quality-metrics.md` for full analysis.

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

### 5.1 Tool Architecture over Standalone Agent

The most important architectural decision: AutoForge provides **measurement tools**, not an autonomous agent.

**Rationale:**
- AI agents (Claude Code, etc.) are already excellent at code analysis, editing, git, and testing
- Wrapping an agent in a subprocess loop loses context between iterations
- The agent should call measurement tools, not be called by an orchestrator
- Clean separation: AutoForge owns metrics, the agent owns strategy

The autonomous `run` mode is preserved for backward compatibility and fully unattended CI pipelines, but the tool architecture is the recommended approach.

### 5.2 Git-Based Iteration State

Each iteration operates on a git branch. In autonomous mode, the driver manages this. In tool mode, the agent manages git natively using the branch convention from the skill description:
- Branch: `autoforge/{workflow}/{timestamp}`
- Commit message: `autoforge({workflow}): iteration N — metric before -> after`

### 5.3 Multi-Metric Constraints

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

In tool mode, skill descriptions communicate constraints to the agent. In autonomous mode, the regression guard enforces them.

### 5.4 Improvement Stall Detection

If the metric doesn't improve by at least `min_improvement_threshold` for `stall_patience` consecutive iterations, stop.

Default: `stall_patience = 3`, `min_improvement_threshold = 0.5%`

In tool mode, skill descriptions instruct agents to track this. In autonomous mode, the budget manager enforces it.

### 5.5 Scope Control

- File-level targeting via `autoforge targets`
- Priority ordering (worst metric values first)
- Max files per iteration (default: 5)
- Agents receive focused target lists to keep changes scoped

### 5.6 Observability & Reporting

- `autoforge measure` returns structured JSON for agent consumption
- `autoforge health` produces dashboards for human review
- Autonomous mode produces per-run JSON reports with iteration-level metrics

## 6. Composite Workflows

### 6.1 Sequential Pipeline

```
Complexity Refactor → Test Coverage → Type Safety → Security Scan
```

With the tool architecture, an agent can naturally chain workflows by calling different `autoforge measure` commands in sequence.

### 6.2 Parallel with Merge

Run coverage and type-safety improvements in parallel on separate branches, then merge.

### 6.3 Health Check Mode

Run all metric adapters without agent action — produce a codebase health dashboard via `autoforge health`.

## 7. Phased Roadmap

### Phase 0: Foundation (Weeks 1-2)

**Goal:** Extract the proven pattern into reusable measurement tools.

- Standard metric adapter interface (input/output schema)
- Workflow configuration schema (YAML)
- CLI tools: `measure`, `targets`, `skill-info`, `health`, `list`
- Autonomous runner for backward compatibility
- Wrap complexity-accounting as first metric adapter
- Structured logging and run report generation
- Basic regression guard (for autonomous mode)

**Deliverable:** Agents can call `autoforge measure complexity` and `autoforge targets complexity` as tools.

### Phase 1: Test Quality & Test-as-Spec Workflow (Weeks 3-6)

### Phase 2: Type Safety + Security (Weeks 6-8)

### Phase 3: Health Dashboard + LLM-as-Judge + Sandbox (Weeks 9-11)

### Phase 4: Scale & Ecosystem (Weeks 12+)

## 8. Success Metrics

| Metric | Target |
|--------|--------|
| Workflow generalization | 5+ distinct metric adapters sharing the same CLI interface |
| Cross-language support | Python + JS/TS for all Phase 1-2 adapters |
| Agent success rate | >70% of agent-driven runs reach target |
| Cost efficiency | <$5 average token cost per workflow run |
| Regression rate | <5% of runs introduce test failures |
| Time to add new adapter | <1 day |

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Semantically wrong changes | High | Mutation testing as constraint; human review |
| Metric gaming | Medium | Constraint metrics; quality gates |
| Runaway token costs | Medium | Skill descriptions communicate budget caps; autonomous mode enforces them |
| Noisy metrics | Medium | Statistical significance checks |
| Tool installation differences | Low | Docker-based metric runner |
| Context window limits | Medium | File-level scoping via `autoforge targets`; priority ordering |

## Appendix A: Workflow Configuration Schema

See `src/autoforge/workflows/complexity_refactor.yaml` for the reference implementation.

## Appendix B: Standard Metric Adapter Interface

See `src/autoforge/models.py` for `MetricResult` and `MetricAdapter` protocol, and `src/autoforge/adapters/base.py` for `BaseMetricAdapter` ABC.
