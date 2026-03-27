# AutoForge Development Progress

## Completed Milestones

### v0.1.0 — Core Framework
- Core data models (`MetricResult`, `WorkflowConfig`, `RunReport`)
- `WorkflowRunner` with measure-act-validate iteration loop
- `BudgetManager` with iteration/token/time limits and stall detection
- `GitManager` with branch creation, per-iteration commits, rollback
- `RegressionGuard` with test running and constraint checking
- YAML workflow configuration system
- Registry for adapters and workflows
- JSON and Markdown reporting with health dashboard
- CLI: `run`, `health`, `list` commands

### v0.1.1 — Metric Adapters
- `ComplexityAdapter` wrapping complexity-accounting for NCS measurement
- `TestQualityAdapter` with coverage, function gap, assertion quality, mutation testing
- `complexity_refactor` workflow (minimize NCS)
- `test_quality` workflow (maximize TQS)

### v0.1.2 — Hybrid Skill Architecture
- **Skill mode**: AI agents drive workflows directly using measurement CLI tools
- `autoforge measure <adapter>` — standalone metric measurement with JSON output
- `autoforge targets <adapter>` — identify worst files for targeting
- `autoforge skill-info <workflow>` — generate skill descriptions from workflow configs
- `SkillModeConfig` model for workflow YAML `skill_mode` section
- `skill.py` module with `generate_skill_description()` and `generate_skill_json()`
- Workflow YAMLs updated with `skill_mode` configuration
- Architecture documentation updated for dual-mode operation

### v0.2.0 — Plugin Architecture (Adapter Extraction)
- Extracted metric adapters into separate installable packages
- `autoforge-complexity`: Code complexity adapter (NCS via complexity-accounting)
- `autoforge-test-quality`: Test quality adapter (coverage, assertions, mutation)
- Entry-point based plugin discovery (`autoforge.adapters` group)
- Core framework is now dependency-lean (only `pyyaml`)
- `pip install autoforge[all]` for convenience install of all adapters
- Clear install hints when adapter is not found
- Third-party adapters can register via entry points without touching core

## Current State

AutoForge supports two execution modes:
1. **Autonomous mode** (`autoforge run`): AutoForge owns the iteration loop, spawns agent as subprocess
2. **Skill mode** (`autoforge measure`/`targets`/`skill-info`): AI agent drives the workflow with full context

Metric adapters are separate packages discovered via Python entry points:
- `autoforge-complexity` — NCS measurement via complexity-accounting
- `autoforge-test-quality` — Composite TQS (coverage + assertion quality + mutation testing)

Skill mode is recommended because:
- Agent maintains context across iterations (no stateless subprocess limitation)
- Agent can reason about what's working and adapt strategy
- Native tool access (git, file editing, testing) without reimplementation
- Better error recovery and diagnosis

## Next Steps

- [ ] Add tests for `skill.py` module
- [ ] Add tests for `measure` and `targets` CLI commands
- [ ] Integration testing: end-to-end skill-mode workflow with Claude Code
- [ ] Consider a `autoforge run --skill-mode` flag that generates and prints skill description instead of running the loop
- [ ] Explore MCP server integration for richer agent-tool communication
