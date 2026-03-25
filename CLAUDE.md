# AutoForge

Autonomous metric-driven agentic coding framework. Generalizes the pattern:
**measure -> agent acts -> re-measure -> iterate until target met**.

## Project Structure

```
src/autoforge/
├── __init__.py         # Package version
├── __main__.py         # CLI entry point (run, health, list commands)
├── models.py           # Core data models (MetricResult, WorkflowConfig, RunReport)
├── runner.py           # Workflow runner (measure-act-validate loop)
├── budget.py           # Budget manager (iteration/token/time limits, stall detection)
├── git_manager.py      # Git operations (branch, commit, rollback per iteration)
├── regression.py       # Regression guard (test runner, constraint checking)
├── reporting.py        # Report generation (JSON, markdown, health dashboard)
├── registry.py         # Workflow & adapter registry
├── adapters/
│   ├── base.py         # BaseMetricAdapter ABC
│   └── complexity.py   # complexity-accounting adapter (NCS)
└── workflows/
    └── complexity_refactor.yaml  # First workflow config
```

## Key Commands

```bash
autoforge run complexity_refactor --path ./src --target 3.0
autoforge health --path ./src
autoforge list
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Architecture

- **MetricAdapter**: Protocol for plugging in measurement tools
- **WorkflowConfig**: YAML-defined workflow with metrics, budget, constraints
- **WorkflowRunner**: Executes the iteration loop with budget/regression guards
- **BudgetManager**: Enforces hard limits, detects improvement stalls
- **GitManager**: Creates branches, commits per iteration, supports rollback
- **RegressionGuard**: Runs tests between iterations, checks constraints

## Adding a New Adapter

1. Subclass `BaseMetricAdapter` in `src/autoforge/adapters/`
2. Implement `check_prerequisites()`, `measure()`, `identify_targets()`
3. Register in `src/autoforge/registry.py`
4. Create a workflow YAML in `src/autoforge/workflows/`
