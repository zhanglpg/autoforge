# AutoForge Implementation Progress

*Last updated: 2026-03-25 (Phase 0 closed)*

Tracks implementation status against the [design doc](design.md) roadmap.

## Phase 0: Foundation — Status: Complete

**Goal:** Extract the proven pattern into a reusable framework.

| Deliverable | Status | Notes |
|------------|--------|-------|
| Standard metric adapter interface | Done | `models.py` MetricAdapter protocol + `adapters/base.py` ABC |
| Workflow configuration schema (YAML) | Done | `models.py` WorkflowConfig with full parsing/validation |
| CLI driver skeleton | Done | `__main__.py` — `run`, `health`, `list` commands |
| Iteration loop | Done | `runner.py` — measure -> act -> validate loop |
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

Phase 0 is complete. The core loop works end-to-end with budget enforcement, regression guards, constraint checking, and best-effort token tracking. Two minor gaps remain (lint validation, max files enforcement) which are deferred to Phase 2 and are documented in the deviations section below.

## Phase 1: Test Quality & Test-as-Spec — Status: Not Started

## Phase 2: Type Safety + Security — Status: Not Started

## Phase 3: Health Dashboard + LLM-as-Judge — Status: Not Started

Health dashboard reporting exists (`reporting.py`), but LLM-as-Judge and sandbox are not started.

## Phase 4: Scale & Ecosystem — Status: Not Started

## Test Coverage

202 tests across 9 files. All core modules have dedicated test suites.

| Module | Test File | Tests |
|--------|-----------|-------|
| models | test_models.py | 31 |
| CLI | test_cli.py | 24 |
| runner | test_runner.py | 22 |
| budget | test_budget.py | 20 |
| git_manager | test_git_manager.py | 20 |
| regression | test_regression.py | 25 |
| reporting | test_reporting.py | 25 |
| adapters | test_adapters.py | 17 |
| registry | test_registry.py | 18 |

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

**Verdict:** Fine for now. The Orchestrator is needed for composite workflows (Phase 3+). No correction needed yet, but should be introduced before multi-workflow support.

### 2. No multi-agent parallel execution

**Design (Section 3.3):** Multiple Claude Code instances on separate branches running in parallel, with merge on completion.

**Implementation:** Single sequential workflow execution.

**Verdict:** Correct sequencing. This is Phase 4 scope. Design is aspirational here and doesn't need correction.

### ~~3. Tool Adapters merged into Metric Adapters~~ (Fixed)

**Design (Section 3.1):** Originally specified separate "Metric Adapters" and "Tool Adapters" as distinct components.

**Status:** Fixed. Design doc Section 3.1 updated to show a single "Metric Adapters" component that handles both tool invocation and output normalization, matching the implementation.

### 4. ~~Constraint metrics not checked during iteration~~ (Fixed)

**Design (Section 5.2):** Regression guard checks that constraint metrics haven't degraded beyond tolerance.

**Status:** Fixed. Runner now measures constraint baselines at startup via `_set_constraint_baselines()` and passes adapter/tolerance info to `validate_iteration()`, which calls `check_constraints()` when baselines are present.

### 5. Lint/type error validation missing

**Design (Section 3.2):** Regression guard "validates no new lint/type errors introduced."

**Implementation:** Not implemented.

**Verdict:** Defer to Phase 2 (Type Safety). Not critical for Phase 0 since the complexity workflow doesn't need it. But should be noted as a gap.

### ~~6. Token tracking is a no-op~~ (Fixed — best-effort)

**Design (Sections 3.2, 3.3):** Budget manager tracks token spend for cost control.

**Status:** Fixed. Runner now uses `--output-format json` and parses Claude Code output for token counts via `_parse_token_usage()`. Tries JSON `usage` field first, then regex on stderr. Falls back to 0 if unavailable. Token counts are passed to `budget.record_iteration(tokens=...)` and stored on `IterationRecord.tokens_used`.

**Limitation:** Token tracking is best-effort. Claude Code does not guarantee structured token reporting in all modes. The budget enforcement for tokens will only trigger if the agent output includes parseable token counts.

### 7. Max files per iteration not enforced

**Design (Section 5.4):** "Max files per iteration (default: 5)."

**Implementation:** `BudgetConfig.max_files_per_iteration` exists and is passed to `identify_targets()` to limit scope hints to the agent, but there's no post-hoc enforcement (the agent could still modify more files).

**Verdict: Acceptable.** The agent is given scoped targets; hard enforcement would require rejecting iterations that touch too many files, which may cause more harm than good. Consider adding a warning rather than a hard block.

### 8. Health dashboard thresholds are hardcoded

**Design:** Doesn't specify.

**Implementation:** `_health_status()` in `reporting.py` uses hardcoded thresholds (e.g., NCS <= 3 = Healthy).

**Verdict:** Fine for now. Should become configurable when more adapters are added, but not urgent.

## Recommended Next Actions

1. ~~**Wire up constraint checking in runner**~~ Done.
2. ~~**Add token usage logging (best-effort)**~~ Done. Runner parses Claude Code JSON/stderr output for tokens.
3. ~~**Update design doc Section 3.1**~~ Done. Merged "Tool Adapters" into "Metric Adapters."
4. ~~**Close Phase 0**~~ Done. Phase 0 is complete.
5. **Begin Phase 1 (Test Quality & Test-as-Spec)** — Next milestone.
