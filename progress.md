# AutoForge Development Progress

## Completed Milestones

### v0.1.0 — Core Framework
- Core data models (`MetricResult`, `WorkflowConfig`, `RunReport`)
- CLI tools: `measure`, `targets`, `skill-info`, `health`, `list` commands
- `WorkflowRunner` with measure-act-validate iteration loop (autonomous mode)
- `BudgetManager` with iteration/token/time limits and stall detection
- `GitManager` with branch creation, per-iteration commits, rollback
- `RegressionGuard` with test running and constraint checking
- YAML workflow configuration system
- Registry for adapters and workflows
- JSON and Markdown reporting with health dashboard

### v0.1.1 — Metric Adapters
- `ComplexityAdapter` wrapping complexity-accounting for NCS measurement
- `TestQualityAdapter` with coverage, function gap, assertion quality, mutation testing
- `complexity_refactor` workflow (minimize NCS)
- `test_quality` workflow (maximize TQS)

### v0.1.2 — Tool & Skill Architecture
- **Tool architecture**: AutoForge provides measurement CLI tools that AI agents call during their workflows
- `autoforge measure <adapter>` — structured metric measurement with JSON output
- `autoforge targets <adapter>` — identify worst files for targeting
- `autoforge skill-info <workflow>` — generate skill descriptions from workflow configs
- `SkillModeConfig` model for workflow YAML `skill_mode` section
- `skill.py` module with `generate_skill_description()` and `generate_skill_json()`
- Workflow YAMLs updated with `skill_mode` configuration
- Architecture reframed: AutoForge as measurement tools for agents, not a standalone agent

### v0.2.0 — Plugin Architecture (Adapter Extraction)
- Extracted metric adapters into separate installable packages
- `autoforge-complexity`: Code complexity adapter (NCS via complexity-accounting)
- `autoforge-test-quality`: Test quality adapter (coverage, assertions, mutation)
- Entry-point based plugin discovery (`autoforge.adapters` group)
- Core framework is now dependency-lean (only `pyyaml`)
- `pip install autoforge[all]` for convenience install of all adapters
- Clear install hints when adapter is not found
- Third-party adapters can register via entry points without touching core

### v0.3.0 — Multi-Language Support (Go)
- `autoforge-go-test-quality`: Go test quality adapter package
  - Statement coverage via `go test -coverprofile` with coverage profile parsing
  - Exported function coverage via `go tool cover -func`
  - Regex-based assertion analysis of `_test.go` files (strong/structural/weak classification)
  - Go-specific quality indicators: table-driven tests, subtests (`t.Run`), testify detection
  - Quality bonuses for idiomatic Go testing patterns
  - Optional mutation testing via `go-mutesting`
  - Composite Go TQS score (0-100) with configurable weights
- `go_test_quality` workflow YAML for AI agent-driven Go test improvement
- Registry updated with install hint for `go_test_quality` adapter
- Architecture proven for multi-language support — each language gets its own test quality adapter

### v0.3.1 — Metric Verification & Assertion Quality Fixes
- Fixed context-aware assertion classification for Go adapter
  - Multi-line `if got != want { t.Errorf(...) }` now correctly classified as STRONG
  - Error-guard patterns (`if err != nil { t.Fatal }`) excluded from promotion, remain WEAK
- Assertion strength weights now affect scoring (STRONG=1.0, STRUCTURAL=0.5, WEAK=0.2)
  - Previously only binary "has any assertion?" was used, ignoring quality tiers
- Added Go sample project (`testdata/go-sample-project/`) for metric validation
- Documented metric auditing best practices: metrics drive the loop, LLM judgment audits the results

### v0.3.2 — Claude Code Slash Commands (Layer 3 Wrappers)
- Added `.claude/commands/` with reference slash commands for Claude Code
  - `/project:refactor-complexity` — reduce code complexity via NCS measurement
  - `/project:improve-test-quality` — improve Python test quality via TQS measurement
  - `/project:improve-go-tests` — improve Go test quality via TQS measurement
- Commands are thin wrappers that call `autoforge skill-info` and let the agent drive
- Documented three-layer architecture: CLI tool (Layer 1), skill description (Layer 2), agent-framework skill (Layer 3)
- Layer 3 kept outside core — framework-specific wrappers are examples, not features

## Current State

AutoForge is a **measurement toolkit for AI agents**, not a standalone agent. It provides CLI commands (`measure`, `targets`, `skill-info`) that AI coding agents call as tools during iterative code improvement workflows.

Primary usage: AI agent (e.g., Claude Code) calls AutoForge measurement commands as tools:
- `autoforge measure complexity --path ./src --format json` — get structured metric data
- `autoforge targets complexity --path ./src -n 5` — identify worst files to fix
- `autoforge skill-info complexity_refactor` — get workflow instructions as a skill description

Legacy usage: `autoforge run` for autonomous mode where AutoForge owns the iteration loop.

Metric adapters are separate packages discovered via Python entry points:
- `autoforge-complexity` — NCS measurement via complexity-accounting (supports Python, Go, Java, JS/TS, Rust, C++)
- `autoforge-test-quality` — Composite TQS for Python (coverage + assertion quality + mutation testing)
- `autoforge-go-test-quality` — Composite TQS for Go (coverage + assertion quality + mutation testing)

The tool architecture is recommended because:
- Agent maintains context across iterations (no stateless subprocess limitation)
- Agent can reason about what's working and adapt strategy
- Native tool access (git, file editing, testing) without reimplementation
- Better error recovery and diagnosis

## Next Steps

- [ ] Add test quality adapters for more languages (JS/TS, Java, Rust)
- [ ] Add tests for `skill.py` module
- [ ] Add tests for `measure` and `targets` CLI commands
- [ ] Integration testing: end-to-end tool-mode workflow with Claude Code
- [ ] Explore MCP server integration for richer agent-tool communication
- [ ] Consider deprecation path for autonomous `run` mode
- [ ] Build metric audit step into workflow configs (periodic LLM cross-check of metric outputs)
