# AutoForge

Autonomous metric-driven agentic coding framework. Generalizes the pattern:
**measure -> agent acts -> re-measure -> iterate until target met**.

## Project Structure

```
src/autoforge/                          # Core framework
├── __init__.py                         # Package version
├── __main__.py                         # CLI entry point
├── models.py                           # Core data models
├── runner.py                           # Workflow runner (measure-act-validate loop)
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
    └── test_quality.yaml

packages/                               # Adapter packages (separate install)
├── autoforge-complexity/               # pip install autoforge-complexity
│   └── src/autoforge_complexity/
└── autoforge-test-quality/             # pip install autoforge-test-quality
    └── src/autoforge_test_quality/
```

## Key Commands

```bash
# Autonomous mode (AutoForge drives the loop)
autoforge run complexity_refactor --path ./src --target 3.0

# Skill mode (agent-driven — measurement tools for AI agents)
autoforge measure complexity --path ./src --format json
autoforge targets complexity --path ./src -n 5
autoforge skill-info complexity_refactor --path ./src --target 3.0

# Health & discovery
autoforge health --path ./src
autoforge list
```

## Development

```bash
pip install -e ".[dev]"
pip install -e packages/autoforge-complexity
pip install -e packages/autoforge-test-quality
pytest
```

## Architecture

Two execution modes:
- **Autonomous Mode**: `WorkflowRunner` owns the loop, spawns agent as subprocess
- **Skill Mode** (recommended): AI agent drives the workflow, calls `autoforge measure`/`targets` as tools

Core components:
- **MetricAdapter**: Protocol for plugging in measurement tools
- **WorkflowConfig**: YAML-defined workflow with metrics, budget, constraints
- **WorkflowRunner**: Executes the iteration loop with budget/regression guards (autonomous mode)
- **SkillGenerator**: Produces skill descriptions from workflow configs (skill mode)
- **BudgetManager**: Enforces hard limits, detects improvement stalls
- **GitManager**: Creates branches, commits per iteration, supports rollback
- **RegressionGuard**: Runs tests between iterations, checks constraints

## Adding a New Adapter

1. Create a new package (see `packages/autoforge-complexity/` as reference)
2. Subclass `BaseMetricAdapter` from `autoforge.adapters.base`
3. Implement `check_prerequisites()`, `measure()`, `identify_targets()`
4. Register via entry point: `[project.entry-points."autoforge.adapters"]`
5. Create a workflow YAML in `src/autoforge/workflows/`

## Documentation Maintenance

Always update the following files to keep them in sync with the current state of the system:

- **README.md** — Update whenever features, CLI options, architecture, project structure, or workflows change. The README is the public-facing documentation and must accurately reflect the current capabilities.
- **progress.md** — Update to reflect the current development progress, completed milestones, and next steps. This file tracks what has been built and what remains.
