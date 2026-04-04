# AutoForge Development Progress

## Implemented

### Core Framework
- Core data models (`MetricResult`, `WorkflowConfig`, `RunReport`)
- CLI tools: `measure`, `targets`, `skill-info`, `health`, `list` commands
- `WorkflowRunner` with measure-act-validate iteration loop (autonomous mode)
- `BudgetManager` with iteration/token/time limits and stall detection
- `GitManager` with branch creation, per-iteration commits, rollback
- `RegressionGuard` with test running and constraint checking
- YAML workflow configuration system
- Registry for adapters and workflows (entry-point discovery)
- JSON and Markdown reporting with health dashboard
- Tool architecture: agents call `autoforge measure` / `autoforge targets` as CLI tools
- `SkillGenerator` for producing tool-contract descriptions from workflow configs (metrics, commands, budget, constraints)
- CI: `tests.yml` (Python 3.10-3.13 matrix), `autoforge.yml` (health + dry-run)

### Plugin Architecture
- Metric adapters extracted into separate installable packages
- Entry-point based plugin discovery (`autoforge.adapters` group)
- Core framework is dependency-lean (only `pyyaml`)
- `pip install autoforge[all]` for convenience install of all adapters
- Third-party adapters can register via entry points without touching core

### Metric Adapters
- **autoforge-complexity** — NCS measurement via complexity-accounting (Python, Go, Java, JS/TS, Rust, C++)
- **autoforge-test-quality** — Composite TQS for Python (coverage + assertion quality + mutation testing)
- **autoforge-go-test-quality** — Composite TQS for Go (coverage + assertion quality + mutation testing)
  - Go-specific quality indicators: table-driven tests, subtests, testify detection
  - Optional mutation testing via `go-mutesting`
- **autoforge-type-safety** — Type error count via pyright (default) or mypy
  - Per-file error count breakdown with worst-first targeting
  - Supports pyright (native JSON output) and mypy (--output=json) backends

### Workflows
- `complexity_refactor` — reduce NCS via complexity measurement
- `test_quality` — improve Python test quality via TQS
- `go_test_quality` — improve Go test quality via TQS
- `type_safety` — reduce type errors via pyright/mypy

### Claude Code Integration
- `.claude/commands/` with slash commands: `refactor-complexity`, `improve-test-quality`, `improve-go-tests`, `improve-type-safety`
- Commands call `autoforge skill-info` for tool contract and provide behavioral guidance (iteration protocol, coding guidelines) directly

## Current State

AutoForge is a **measurement toolkit for AI agents**. It provides CLI commands (`measure`, `targets`, `skill-info`) that AI coding agents call as tools during iterative code improvement workflows. Legacy autonomous mode (`autoforge run`) is still available.

282 tests across 11 test files. All core modules have dedicated test suites, plus an integration test suite covering end-to-end CLI workflows.

## Known Gaps

- Lint/type error validation not in regression guard (agents can run lint natively in tool mode)
- Max files per iteration not enforced at runtime (communicated via skill descriptions and `targets -n`)
- Health dashboard thresholds are hardcoded
- No Orchestrator layer (agent serves as orchestrator in tool mode)
- No multi-agent parallel execution (agent's responsibility in tool mode)

## Roadmap

- [x] **Type Safety** — `autoforge-type-safety` adapter (pyright/mypy type error count), workflow YAML, slash command
- [ ] **Security** — Security vulnerability scanning (SAST finding count by severity)
- [ ] **LLM-as-Judge** — Metric audit step in workflow configs (periodic LLM cross-check of metric outputs)
- [ ] **More language adapters** — Test quality adapters for JS/TS, Java, Rust
- [x] **CLI test coverage** — Tests for `skill.py`, `measure`, and `targets` commands
- [x] **Integration testing** — End-to-end CLI integration tests (measure, targets, skill-info, health, list, dry-run, agent workflow simulation)
- [ ] **MCP server integration** — Richer agent-tool communication
- [ ] **Scale & Ecosystem** — Multi-agent parallel execution, configurable health thresholds
- [ ] **Deprecation path for autonomous `run` mode**

## Deviations from Design Doc

1. **No Orchestrator layer** — CLI directly instantiates WorkflowRunner. In tool mode, the AI agent serves as the orchestrator.
2. **No multi-agent parallel execution** — Single sequential execution. Parallel execution is the agent's responsibility in tool mode. Phase 4 scope.
3. **Lint/type error validation missing** — Deferred to Type Safety phase. Agents run lint/type checks natively in tool mode.
4. **Max files per iteration not enforced** — `BudgetConfig.max_files_per_iteration` is communicated via skill descriptions and `targets -n`, but not enforced post-hoc.
5. **Health dashboard thresholds hardcoded** — Should become configurable when more adapters are added.
