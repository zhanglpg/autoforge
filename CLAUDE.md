# AutoForge

Metric-driven coding tools for AI agents. AutoForge provides measurement CLI commands (`measure`, `targets`, `skill-info`) that AI coding agents call as tools to drive iterative code improvement.

**AutoForge is not an agent** — it's a toolkit. The agent drives the workflow; AutoForge provides the measurement infrastructure.

## Project Structure

```
src/autoforge/                          # Core framework
├── __init__.py                         # Package version
├── __main__.py                         # CLI entry point
├── models.py                           # Core data models
├── runner.py                           # Workflow runner (legacy autonomous mode)
├── skill.py                            # Skill description generator
├── budget.py                           # Budget manager
├── git_manager.py                      # Git operations
├── regression.py                       # Regression guard
├── reporting.py                        # Report generation
├── registry.py                         # Workflow & adapter registry (entry-point discovery)
├── adapters/
│   └── base.py                         # BaseMetricAdapter ABC
└── workflows/
    ├── complexity_refactor.yaml
    ├── test_quality.yaml
    └── go_test_quality.yaml

packages/                               # Adapter packages (separate install)
├── autoforge-complexity/               # pip install autoforge-complexity
│   └── src/autoforge_complexity/
├── autoforge-test-quality/             # pip install autoforge-test-quality
│   └── src/autoforge_test_quality/
└── autoforge-go-test-quality/          # pip install autoforge-go-test-quality
    └── src/autoforge_go_test_quality/
```

## Key Commands

```bash
# Tool mode (recommended — agent calls these as tools)
autoforge measure complexity --path ./src --format json
autoforge targets complexity --path ./src -n 5
autoforge skill-info complexity_refactor --path ./src --target 3.0

# Health & discovery
autoforge health --path ./src
autoforge list

# Autonomous mode (legacy — AutoForge drives the loop)
autoforge run complexity_refactor --path ./src --target 3.0
```

## Development

```bash
pip install -e ".[dev]"
pip install -e packages/autoforge-complexity
pip install -e packages/autoforge-test-quality
pytest
```

## Architecture

AutoForge provides measurement tools that AI agents call during their workflows:
- **`autoforge measure`** — runs a metric adapter, returns structured JSON
- **`autoforge targets`** — identifies worst files for a metric
- **`autoforge skill-info`** — generates skill descriptions from workflow configs

The agent maintains full context across iterations, manages git, runs tests, and reasons about strategy. AutoForge handles metric collection and normalization.

Legacy autonomous mode (`autoforge run`) spawns the agent as a subprocess each iteration, with mechanical budget/git/regression enforcement.

Core components:
- **MetricAdapter**: Protocol for plugging in measurement tools
- **WorkflowConfig**: YAML-defined workflow with metrics, budget, constraints
- **SkillGenerator**: Produces skill descriptions from workflow configs
- **WorkflowRunner**: Executes the iteration loop (legacy autonomous mode)
- **BudgetManager**: Enforces hard limits, detects improvement stalls (autonomous mode; communicated to agents via skill descriptions)
- **GitManager**: Creates branches, commits per iteration, supports rollback (autonomous mode)
- **RegressionGuard**: Runs tests between iterations, checks constraints (autonomous mode)

## Metric Auditing Principle

Metrics drive the improvement loop; LLM judgment audits the results. When using AutoForge metrics to drive test-quality or code-quality improvement:

- **Don't trust the metric blindly.** Sample metric outputs and verify classifications match reality.
- **Watch for gaming.** Metrics reward structure, not semantics — tests can satisfy the metric without testing meaningful behavior.
- **Investigate suspicious scores.** A sudden jump to 100% or a high score on obviously weak code suggests a metric bug or miscalibration.

See the "Metric Auditing" section in README.md for detailed rationale and examples from the Go adapter verification.

## Adding a New Adapter

1. Create a new package (see `packages/autoforge-complexity/` as reference)
2. Subclass `BaseMetricAdapter` from `autoforge.adapters.base`
3. Implement `check_prerequisites()`, `measure()`, `identify_targets()`
4. Register via entry point: `[project.entry-points."autoforge.adapters"]`
5. Create a workflow YAML in `src/autoforge/workflows/`

Once registered, agents can immediately use `autoforge measure <name>` and `autoforge targets <name>` as tools.

## Documentation Maintenance

Always update the following files to keep them in sync with the current state of the system:

- **README.md** — Update whenever features, CLI options, architecture, project structure, or workflows change. The README is the public-facing documentation and must accurately reflect the current capabilities.
- **progress.md** — Update to reflect the current development progress, completed milestones, and next steps. This file tracks what has been built and what remains.
