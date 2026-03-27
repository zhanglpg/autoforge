# AutoForge

Metric-driven coding tools for AI agents. AutoForge provides **measurement infrastructure** that AI coding agents (like Claude Code) use as tools to drive iterative code improvement.

**AutoForge is not an agent** &mdash; it's a toolkit that gives agents the ability to measure, target, and track code quality metrics. The agent drives the workflow; AutoForge provides the measurement commands and workflow configuration.

```
Agent (Claude Code, etc.) drives the loop
  ├── autoforge measure complexity --path ./src    → JSON metric result
  ├── autoforge targets complexity --path ./src    → worst files to fix
  ├── (agent edits code, runs tests, commits)
  └── autoforge measure complexity --path ./src    → re-measure to confirm
```

## Features

- **CLI measurement tools** &mdash; `measure` and `targets` commands that agents call as tools to get structured metric data.
- **Pluggable metric adapters** &mdash; bring your own measurement tool. Built-in adapters for code complexity (NCS via `complexity-accounting`) and test quality (coverage + assertion analysis).
- **Skill descriptions** &mdash; generate workflow instructions from YAML configs that agents can follow as structured skills.
- **YAML workflow configs** &mdash; declarative definitions specifying metrics, budgets, constraints, and agent guidance.
- **Health dashboards** &mdash; run all adapters to produce a codebase health snapshot.
- **Autonomous mode** (legacy) &mdash; a subprocess runner that owns the iteration loop, for fully unattended runs.

## How It Works

AutoForge is designed to be used **by** an AI agent, not **as** one. The agent (e.g., Claude Code) calls AutoForge's CLI commands as tools during its workflow:

1. **`autoforge measure`** &mdash; runs a metric adapter and returns structured JSON results
2. **`autoforge targets`** &mdash; identifies the worst files for a given metric
3. **`autoforge skill-info`** &mdash; generates a complete skill description from a workflow config

The agent maintains full context across iterations &mdash; it remembers what it tried, adapts strategy, and uses its native capabilities for git, file editing, and test running. AutoForge provides the measurement infrastructure; the agent provides the intelligence.

### Why This Architecture?

In the subprocess/autonomous model, each agent invocation is stateless &mdash; iteration 5 might retry exactly what iteration 2 already failed at. By making AutoForge a **tool** rather than a driver, the agent:

- Maintains conversational context across iterations
- Reasons about what's working and what isn't
- Uses native tool access (git, file editing, testing) without reimplementation
- Recovers from errors with full diagnostic context

## Installation

```bash
# Core framework only
pip install autoforge

# With specific metric adapters
pip install autoforge-complexity      # Code complexity (NCS)
pip install autoforge-test-quality    # Test quality (TQS)

# Or install everything
pip install autoforge[all]
```

For development:

```bash
git clone https://github.com/zhanglpg/autoforge.git
cd autoforge
pip install -e ".[dev]"

# Install adapter packages in dev mode
pip install -e packages/autoforge-complexity
pip install -e packages/autoforge-test-quality
```

Requires Python 3.10+.

## Quick Start

### Using with an AI Agent (Recommended)

1. Generate a skill description for the agent:
   ```bash
   autoforge skill-info complexity_refactor --path ./src --target 3.0
   ```
2. Provide the skill description as context to your agent (paste into conversation, add to CLAUDE.md, etc.)
3. The agent follows the skill protocol: measure, identify targets, make changes, test, re-measure, commit

Or have the agent call the measurement commands directly as tools:

```bash
# Agent calls these as CLI tools during its workflow
autoforge measure complexity --path ./src --format json
autoforge targets complexity --path ./src -n 5
```

### Standalone Measurement

```bash
# Measure a metric (returns JSON by default)
autoforge measure complexity --path ./src
autoforge measure test_quality --path ./src --format text

# Identify worst files to target
autoforge targets complexity --path ./src -n 5
autoforge targets test_quality --path ./src -n 10 --format text
```

### Check Project Health

```bash
# Run all metric adapters and show a health dashboard
autoforge health --path ./src

# Output as JSON
autoforge health --path ./src --format json
```

### List Available Workflows and Adapters

```bash
autoforge list
```

### Autonomous Mode (Legacy)

For fully unattended runs where AutoForge owns the iteration loop and spawns the agent as a subprocess:

```bash
autoforge run complexity_refactor --path ./src --target 3.0
autoforge run test_quality --path ./src --target 80.0
```

This mode requires a local AI coding agent binary (defaults to Claude Code) on your `PATH`. AutoForge invokes `claude --print --output-format json -p "<prompt>"` as a subprocess each iteration.

## CLI Reference

### `autoforge measure <adapter>`

Run a metric adapter and output results. This is the primary command agents use to measure metrics.

| Flag | Description |
|---|---|
| `--path, -p` | Target path to measure (default: repo root) |
| `--repo, -r` | Repository root (default: `.`) |
| `--format, -f` | Output format: `text` or `json` (default: `json`) |

### `autoforge targets <adapter>`

Identify the worst files for a metric. Agents use this to know where to focus.

| Flag | Description |
|---|---|
| `--path, -p` | Target path to analyze (default: repo root) |
| `--repo, -r` | Repository root (default: `.`) |
| `-n` | Number of target files to return (default: 5) |
| `--format, -f` | Output format: `text` or `json` (default: `json`) |

### `autoforge skill-info <workflow>`

Generate a skill description from a workflow config for AI agent consumption.

| Flag | Description |
|---|---|
| `--path, -p` | Target path for skill context (default: repo root) |
| `--repo, -r` | Repository root (default: `.`) |
| `--target, -t` | Target metric value |
| `--config, -c` | Path to workflow YAML config file |
| `--test-command` | Test command for skill description |
| `--format, -f` | Output format: `text` (markdown) or `json` |
| `--output, -o` | Save output to file |

### `autoforge health`

Run all (or specified) metric adapters and produce a health dashboard.

| Flag | Description |
|---|---|
| `--path, -p` | Target path to analyze |
| `--repo, -r` | Repository root (default: `.`) |
| `--adapters` | Comma-separated adapter names |
| `--format, -f` | Output format: `text` or `json` |
| `--output, -o` | Save output to file |

### `autoforge list`

List all registered workflows and adapters.

### `autoforge run <workflow>` (Autonomous Mode)

Execute a metric-driven improvement workflow with AutoForge owning the iteration loop.

| Flag | Description |
|---|---|
| `--path, -p` | Target path to improve (default: repo root) |
| `--repo, -r` | Repository root (default: `.`) |
| `--target, -t` | Target metric value to achieve |
| `--adapter, -a` | Metric adapter override |
| `--config, -c` | Path to a custom workflow YAML |
| `--max-iterations` | Override max iteration count |
| `--max-tokens` | Override max token budget |
| `--max-time` | Override max wall-clock time (minutes) |
| `--test-command` | Custom test command for regression guard |
| `--skip-tests` | Skip test validation between iterations |
| `--skip-git` | Skip git branch/commit management |
| `--dry-run` | Measure only, don't run the agent |
| `--agent-command` | Custom agent command (overrides workflow `agent.command`; used as-is) |
| `--output, -o` | Output directory for reports |

## Architecture

```
┌─────────────────────────────────────────────────┐
│            AI Agent (Claude Code, etc.)           │
│     Drives the iteration loop with full context   │
├─────────────────────────────────────────────────┤
│  autoforge measure  │  autoforge targets         │
│  (metric adapters)  │  (worst-file targeting)    │
├─────────────────────────────────────────────────┤
│         autoforge skill-info <workflow>           │
│    (generates skill description from config)      │
└─────────────────────────────────────────────────┘
```

AutoForge provides the measurement layer. The AI agent provides the intelligence layer. This separation means:

- **AutoForge** handles: metric collection, adapter management, result normalization, workflow configuration, health dashboards
- **The agent** handles: code analysis, editing strategy, git management, test running, error recovery, iteration reasoning

### Core Components

- **MetricAdapter** &mdash; protocol for plugging in any measurement tool. Adapters normalize tool output into a standard `MetricResult` and identify priority files for the agent to focus on.
- **Skill Generator** &mdash; produces structured skill descriptions from workflow configs, giving agents complete instructions for executing a workflow.
- **WorkflowConfig** &mdash; YAML-defined workflow with metrics, budgets, constraints, and agent guidance.
- **WorkflowRunner** &mdash; orchestrates an autonomous iteration loop (legacy mode, for unattended runs).
- **BudgetManager** &mdash; enforces iteration/token/time limits and detects improvement stalls (used by autonomous mode; skill descriptions communicate budget rules to agents).
- **GitManager** &mdash; creates feature branches, commits per iteration, rolls back failed iterations (autonomous mode).
- **RegressionGuard** &mdash; runs tests and checks constraint metrics between iterations (autonomous mode).

## Built-in Workflows

### `complexity_refactor`

Reduces code complexity using [complexity-accounting](https://pypi.org/project/complexity-accounting/) to measure Net Complexity Score (NCS). The agent iteratively refactors mega-functions, dispatch chains, deep nesting, and duplicated logic.

### `test_quality`

Improves test suite quality by combining coverage measurement, function gap analysis, and assertion quality scoring. The assertion quality metric measures what fraction of test functions have at least one meaningful assertion on the output &mdash; code-path coverage is handled by the coverage sub-metrics, so the assertion score purely answers "do the tests verify anything?" Assertion count is deliberately ignored, making it impossible to game by spamming assertions.

## Adding a New Adapter

Adapters are discovered via Python entry points. Create a new package:

1. Create a package with a class that subclasses `BaseMetricAdapter` from `autoforge.adapters.base`
2. Implement `check_prerequisites()`, `measure()`, `identify_targets()`
3. Register via entry point in your package's `pyproject.toml`:
   ```toml
   [project.entry-points."autoforge.adapters"]
   my_metric = "my_package:MyAdapter"
   ```
4. Create a workflow YAML in `src/autoforge/workflows/` (or your project's `.autoforge/` directory)

See `packages/autoforge-complexity/` for a reference implementation.

Once registered, agents can immediately use `autoforge measure my_metric` and `autoforge targets my_metric` as tools.

## Project Structure

```
src/autoforge/                          # Core framework
├── __init__.py                         # Package version
├── __main__.py                         # CLI entry point
├── models.py                           # Core data models (MetricResult, WorkflowConfig, RunReport)
├── runner.py                           # Workflow runner (autonomous mode iteration loop)
├── skill.py                            # Skill description generator
├── budget.py                           # Budget manager (iteration/token/time limits, stall detection)
├── git_manager.py                      # Git operations (branch, commit, rollback)
├── regression.py                       # Regression guard (test runner, constraint checking)
├── reporting.py                        # Report generation (JSON, markdown, health dashboard)
├── registry.py                         # Workflow & adapter registry (entry-point discovery)
├── adapters/
│   └── base.py                         # BaseMetricAdapter ABC
└── workflows/
    ├── complexity_refactor.yaml
    └── test_quality.yaml

packages/
├── autoforge-complexity/               # Complexity adapter package
│   └── src/autoforge_complexity/
│       └── _adapter.py                 # ComplexityAdapter (NCS via complexity-accounting)
└── autoforge-test-quality/             # Test quality adapter package
    └── src/autoforge_test_quality/
        └── _adapter.py                 # TestQualityAdapter (coverage, assertions, mutation)
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
