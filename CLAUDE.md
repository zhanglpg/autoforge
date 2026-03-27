# AutoForge

Autonomous metric-driven agentic coding framework. Generalizes the pattern:
**measure -> agent acts -> re-measure -> iterate until target met**.

## Project Structure

```
src/autoforge/
├── __init__.py         # Package version
├── __main__.py         # CLI entry point (run, measure, targets, skill-info, health, list)
├── models.py           # Core data models (MetricResult, WorkflowConfig, RunReport)
├── runner.py           # Workflow runner (measure-act-validate loop, autonomous mode)
├── skill.py            # Skill description generator (skill mode)
├── budget.py           # Budget manager (iteration/token/time limits, stall detection)
├── git_manager.py      # Git operations (branch, commit, rollback per iteration)
├── regression.py       # Regression guard (test runner, constraint checking)
├── reporting.py        # Report generation (JSON, markdown, health dashboard)
├── registry.py         # Workflow & adapter registry
├── adapters/
│   ├── base.py         # BaseMetricAdapter ABC
│   ├── complexity.py   # Complexity adapter (NCS)
│   └── test_quality.py # Test quality adapter (TQS)
└── workflows/
    ├── complexity_refactor.yaml
    └── test_quality.yaml
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

1. Subclass `BaseMetricAdapter` in `src/autoforge/adapters/`
2. Implement `check_prerequisites()`, `measure()`, `identify_targets()`
3. Register in `src/autoforge/registry.py`
4. Create a workflow YAML in `src/autoforge/workflows/`

## Documentation Maintenance

Always update the following files to keep them in sync with the current state of the system:

- **README.md** — Update whenever features, CLI options, architecture, project structure, or workflows change. The README is the public-facing documentation and must accurately reflect the current capabilities.
- **progress.md** — Update to reflect the current development progress, completed milestones, and next steps. This file tracks what has been built and what remains.
