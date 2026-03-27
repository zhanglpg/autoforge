# AutoForge Implementation Progress

*Last updated: 2026-03-27*

Tracks implementation status against the [design doc](design.md) roadmap.

## Phase 0: Foundation — Status: Complete

**Goal:** Extract the proven pattern into reusable measurement tools for AI agents.

| Deliverable | Status | Notes |
|------------|--------|-------|
| Standard metric adapter interface | Done | `models.py` MetricAdapter protocol + `adapters/base.py` ABC |
| Workflow configuration schema (YAML) | Done | `models.py` WorkflowConfig with full parsing/validation |
| CLI measurement tools | Done | `__main__.py` — `measure`, `targets`, `skill-info`, `health`, `list` commands |
| Autonomous runner (legacy) | Done | `runner.py` — measure -> act -> validate loop via subprocess |
| Budget enforcement | Done | `budget.py` — iterations, tokens, wall-clock, stall detection |
| Git management | Done | `git_manager.py` — branch, commit, rollback per iteration |
| Wrap complexity-accounting as first adapter | Done | `adapters/complexity.py` — NCS measurement |
| Basic regression guard | Done | `regression.py` — test runner with auto-detection |
| Structured logging | Done | Standard `logging` throughout all modules |
| Per-run report output (JSON + markdown) | Done | `reporting.py` — JSON, markdown, health dashboard |
| GitHub Actions integration | Done | `tests.yml` (CI) + `autoforge.yml` (health/run) |
| Constraint metric checking at iteration time | Done | Runner sets baselines at startup, passes through to `validate_iteration()` |
| **Lint/type error validation** | **Gap** | Design specifies it; not yet in regression guard |
| Token tracking from agent | Done | Best-effort parsing of Claude Code output (JSON + stderr); falls back to 0 |
| **Max files per iteration enforcement** | **Gap** | In BudgetConfig but not enforced at runtime |

### Phase 0 Verdict

Phase 0 is complete. The CLI tools work end-to-end — agents can call `autoforge measure` and `autoforge targets` as tools. The autonomous runner provides backward compatibility. Two minor gaps remain (lint validation, max files enforcement) which are deferred to Phase 2.

## Phase 1: Test Quality & Test-as-Spec — Status: Complete

**Goal:** Add a test quality metric adapter with composite TQS scoring, usable via `autoforge measure test_quality`.

| Deliverable | Status | Notes |
|------------|--------|-------|
| TestQualityAdapter implementation | Done | `adapters/test_quality.py` — 4 sub-metrics, weight redistribution |
| Coverage score (line + branch) | Done | `pytest-cov` JSON parsing, 0.6*line + 0.4*branch weighting |
| Function coverage gaps | Done | AST-based public function extraction, cross-ref with coverage |
| Assertion quality score | Done | Strong/structural/weak classification, weighted density formula |
| Mutation score (optional, sampled) | Done | `mutmut` integration, configurable sample size, disabled by default |
| Per-file TQS breakdown | Done | Composite score per source file via `MetricResult.breakdown` |
| Test-to-source mapping | Done | Convention-based (`test_foo.py` → `foo.py`, `foo_test.py` → `foo.py`) |
| Weight redistribution | Done | Disabled metrics (weight=0) redistribute proportionally |
| Workflow YAML | Done | `workflows/test_quality.yaml` — target 80, budget 15 iters / 500k tokens |
| Registry integration | Done | `test_quality` registered alongside `complexity` |
| Unit tests (pure helpers) | Done | Data models, classification, scoring, file discovery |
| Orchestration tests (mocked) | Done | `measure()`, `_collect_coverage()`, `_analyze_all_files()`, `check_prerequisites()`, mutation methods |
| Edge case tests (verification plan) | Done | No tests→low TQS, coverage without assertions penalized, weight redistribution, unmapped files excluded |
| Workflow YAML integration tests | Done | Config loading, budget, constraints verified |
| `datetime.utcnow()` deprecation fix | Done | All modules migrated to `datetime.now(timezone.utc)` |

### Phase 1 Verdict

Phase 1 is complete. Agents can call `autoforge measure test_quality` and `autoforge targets test_quality` as tools. The TQS adapter faithfully implements the design in `docs/design-test-quality-metrics.md`:
- 4 sub-metrics with configurable weights and automatic redistribution
- Full pipeline: coverage collection → AST analysis → assertion quality → optional mutation → aggregation
- Assertion quality metric measures fraction of test functions with ≥1 meaningful assertion
- 316 tests (37 new orchestration/edge-case tests added), all passing
- Spec coverage (LLM-as-judge) intentionally deferred per design doc — belongs in Phase 3

## Phase 2: Type Safety + Security — Status: Not Started

## Phase 3: Health Dashboard + LLM-as-Judge — Status: Not Started

Health dashboard reporting exists (`reporting.py`), but LLM-as-Judge and sandbox are not started.

## Phase 4: Scale & Ecosystem — Status: Not Started

## Test Coverage

370 tests across 13 files. All core modules have dedicated test suites.

| Module | Test File | Tests |
|--------|-----------|-------|
| models | test_models.py | 31 |
| CLI (main) | test___main__.py | 21 |
| CLI (e2e) | test_cli.py | 24 |
| runner | test_runner.py | 22 |
| budget | test_budget.py | 20 |
| git_manager | test_git_manager.py | 20 |
| regression | test_regression.py | 25 |
| reporting | test_reporting.py | 25 |
| adapters | test_adapters.py | 17 |
| base adapter | test_base.py | 6 |
| complexity | test_complexity.py | 13 |
| registry | test_registry.py | 18 |
| test_quality | test_test_quality_adapter.py | 128 |

## CI/CD

| Workflow | Trigger | Status |
|----------|---------|--------|
| `tests.yml` | PR + push to main | Done — Python 3.10-3.13 matrix |
| `autoforge.yml` | PR (health), weekly schedule, manual dispatch | Done — health + dry-run modes |

---

## Deviations from Design Doc

### 1. No Orchestrator layer

**Design (Section 3.1):** Top-level Orchestrator that selects workflows, allocates budgets, and manages cross-workflow constraints.

**Implementation:** CLI directly instantiates WorkflowRunner. No orchestrator.

**Verdict:** Fine for now. With the tool architecture, the AI agent effectively serves as the orchestrator — it selects workflows, manages iterations, and can chain multiple `autoforge measure` calls. A programmatic orchestrator may be needed for CI pipelines running autonomous mode.

### 2. No multi-agent parallel execution

**Design (Section 3.2 legacy):** Multiple Claude Code instances on separate branches running in parallel, with merge on completion.

**Implementation:** Single sequential workflow execution.

**Verdict:** With the tool architecture, parallel execution is the agent's responsibility. An agent can naturally run multiple measurement commands. This is Phase 4 scope.

### ~~3. Tool Adapters merged into Metric Adapters~~ (Fixed)

**Design (Section 3.1):** Originally specified separate "Metric Adapters" and "Tool Adapters" as distinct components.

**Status:** Fixed. Design doc updated to show a single "Metric Adapters" component.

### 4. ~~Constraint metrics not checked during iteration~~ (Fixed)

**Status:** Fixed. Runner now measures constraint baselines at startup and checks them during validation.

### 5. Lint/type error validation missing

**Design (Section 3.3):** Regression guard "validates no new lint/type errors introduced."

**Implementation:** Not implemented.

**Verdict:** Defer to Phase 2 (Type Safety). In tool mode, agents can run lint/type checks natively. Only needed for autonomous mode enforcement.

### ~~6. Token tracking is a no-op~~ (Fixed — best-effort)

**Status:** Fixed. Runner parses Claude Code output for token counts. Best-effort — falls back to 0 if unavailable.

### 7. Max files per iteration not enforced

**Design (Section 5.5):** "Max files per iteration (default: 5)."

**Implementation:** `BudgetConfig.max_files_per_iteration` limits scope hints via `identify_targets()` and is communicated in skill descriptions. No post-hoc enforcement.

**Verdict:** Acceptable. In tool mode, the agent receives scoped targets via `autoforge targets -n 5`. In autonomous mode, hard enforcement would require rejecting iterations that touch too many files.

### 8. Health dashboard thresholds are hardcoded

**Implementation:** `_health_status()` uses hardcoded thresholds.

**Verdict:** Fine for now. Should become configurable when more adapters are added.

## Recommended Next Actions

1. ~~**Wire up constraint checking in runner**~~ Done.
2. ~~**Add token usage logging (best-effort)**~~ Done.
3. ~~**Update design doc Section 3.1**~~ Done.
4. ~~**Close Phase 0**~~ Done.
5. ~~**Begin Phase 1 (Test Quality & Test-as-Spec)**~~ Done.
6. ~~**Remove TQS data model design doc**~~ Done.
7. ~~**Document tool architecture in README**~~ Done. README reframed around tool/skill model.
8. **Begin Phase 2 (Type Safety + Security)** — Next milestone.
