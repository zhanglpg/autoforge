# AutoForge

Autonomous metric-driven agentic coding framework. Generalizes the pattern:

**measure &rarr; agent acts &rarr; re-measure &rarr; iterate until target met**

AutoForge wraps any code-quality metric into an iterative improvement loop driven by an AI coding agent (e.g., Claude Code). Define a target metric, set budget limits, and let the framework orchestrate measurement, agent action, regression testing, and git management automatically.

## Features

- **Metric-driven iteration loop** &mdash; measure, act, validate, repeat until the target is reached or budget is exhausted.
- **Pluggable metric adapters** &mdash; bring your own measurement tool. Built-in adapters for code complexity (NCS via `complexity-accounting`) and test quality (coverage + assertion analysis).
- **Budget management** &mdash; hard limits on iterations, tokens, and wall-clock time, plus automatic stall detection when improvements plateau.
- **Regression guard** &mdash; runs your test suite between iterations and enforces constraint metrics so improvements never break existing behavior.
- **Git integration** &mdash; automatic branch creation, per-iteration commits, and rollback on failed iterations.
- **YAML workflow configs** &mdash; declarative workflow definitions that specify metrics, budgets, constraints, agent prompts, and language-specific tooling.
- **Reporting** &mdash; JSON and Markdown run reports with health dashboards.

## Prerequisites

AutoForge requires a **local AI coding agent** to perform the actual code modifications. The agent is configurable &mdash; it defaults to [Claude Code](https://docs.anthropic.com/en/docs/claude-code) but can be changed per workflow or at the command line.

- The configured agent binary must be installed and available on your `PATH`. AutoForge checks this at startup and **fails fast** with a clear error if the agent cannot be found.
- By default, AutoForge invokes `claude --print --output-format json -p "<prompt>"` as a subprocess each iteration.
- To use a different agent, set `agent.command` in your workflow YAML or use the `--agent-command` CLI flag (see [Agent Integration](#agent-integration)).

AutoForge itself does **not** call the Claude API directly &mdash; it orchestrates the iteration loop (measure, budget, git, regression) and delegates code changes to the local agent process.

## Installation

```bash
pip install autoforge
```

For development:

```bash
git clone https://github.com/zhanglpg/autoforge.git
cd autoforge
pip install -e ".[dev]"
```

Requires Python 3.10+.

## Quick Start

### Run a workflow

```bash
# Reduce code complexity in ./src to a target NCS of 3.0
autoforge run complexity_refactor --path ./src --target 3.0

# Improve test quality to 80% score
autoforge run test_quality --path ./src --target 80.0
```

### Check project health

```bash
# Run all metric adapters and show a health dashboard
autoforge health --path ./src

# Output as JSON
autoforge health --path ./src --format json
```

### List available workflows and adapters

```bash
autoforge list
```

## CLI Reference

### `autoforge run <workflow>`

Execute a metric-driven improvement workflow.

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

### `autoforge measure <adapter>`

Run a metric adapter and output results. Designed for skill mode &mdash; agents call this to measure metrics.

| Flag | Description |
|---|---|
| `--path, -p` | Target path to measure (default: repo root) |
| `--repo, -r` | Repository root (default: `.`) |
| `--format, -f` | Output format: `text` or `json` (default: `json`) |

### `autoforge targets <adapter>`

Identify the worst files for a metric. Agents call this to know where to focus.

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

## Architecture

AutoForge supports two execution modes:

### Mode 1: Autonomous Runner (subprocess)

```
┌─────────────────────────────────────────────────┐
│                  WorkflowRunner                  │
│         (measure → act → validate loop)          │
├────────────┬────────────┬───────────┬────────────┤
│ BudgetMgr  │  GitMgr    │ Regression│  Reporting │
│ (limits,   │  (branch,  │ Guard     │  (JSON,    │
│  stall     │   commit,  │ (tests,   │   markdown,│
│  detect)   │   rollback)│  checks)  │   health)  │
├────────────┴────────────┴───────────┴────────────┤
│              MetricAdapter (pluggable)            │
│     complexity · test_quality · your own ...      │
└─────────────────────────────────────────────────-┘
```

AutoForge owns the loop and spawns the agent as a subprocess each iteration. Best for fully unattended runs.

### Mode 2: Skill Mode (agent-driven) &mdash; Recommended

```
┌─────────────────────────────────────────────────┐
│            AI Agent (Claude Code, etc.)           │
│     Drives iteration loop with full context       │
├─────────────────────────────────────────────────┤
│  autoforge measure  │  autoforge targets         │
│  (metric adapters)  │  (worst-file targeting)    │
├─────────────────────────────────────────────────┤
│         autoforge skill-info <workflow>           │
│    (generates skill description from config)      │
└─────────────────────────────────────────────────┘
```

The AI agent drives the workflow directly, calling `autoforge measure` and `autoforge targets` as CLI tools. The agent maintains full context across iterations &mdash; it remembers what it tried, can adapt strategy, and uses its native git/edit/test capabilities. AutoForge provides the measurement infrastructure and workflow configuration.

### Core Components

- **MetricAdapter** &mdash; protocol for plugging in any measurement tool. Adapters normalize tool output into a standard `MetricResult` and identify priority files for the agent to focus on.
- **WorkflowRunner** &mdash; orchestrates the autonomous iteration loop (Mode 1).
- **Skill Generator** &mdash; produces structured skill descriptions from workflow configs (Mode 2).
- **BudgetManager** &mdash; enforces iteration/token/time limits and detects improvement stalls.
- **GitManager** &mdash; creates feature branches, commits per iteration, rolls back failed iterations.
- **RegressionGuard** &mdash; runs tests and checks constraint metrics between iterations.

## Skill Mode (Agent-Driven)

The recommended way to use AutoForge is **skill mode**, where an AI coding agent (like Claude Code) drives the workflow using AutoForge's measurement tools. This approach gives the agent full context across iterations &mdash; it remembers what it tried, can adapt strategy, and uses its native capabilities for git, file editing, and test running.

### Why Skill Mode?

In autonomous mode, each agent invocation is stateless &mdash; iteration 5 might retry exactly what iteration 2 already failed at. In skill mode, the agent maintains conversational context and can reason about what's working and what isn't.

### Generate a Skill Description

```bash
# Generate skill instructions for Claude Code
autoforge skill-info complexity_refactor --path ./src --target 3.0

# Output as structured JSON
autoforge skill-info complexity_refactor --format json

# Save to a file
autoforge skill-info test_quality --output ./skill.md
```

### Standalone Measurement Commands

These commands let any agent (or human) measure metrics and identify targets:

```bash
# Measure a metric (returns JSON by default)
autoforge measure complexity --path ./src
autoforge measure test_quality --path ./src --format text

# Identify worst files to target
autoforge targets complexity --path ./src -n 5
autoforge targets test_quality --path ./src -n 10 --format text
```

### Using with Claude Code

1. Generate the skill description: `autoforge skill-info complexity_refactor --path ./src`
2. Provide it as context to Claude Code (paste into conversation, or add to CLAUDE.md)
3. Claude Code will follow the skill protocol: measure, identify targets, make changes, test, re-measure, commit

The agent handles git management, test running, and error recovery natively &mdash; no subprocess overhead or stateless limitations.

## Autonomous Mode (Subprocess)

The original execution mode where AutoForge owns the iteration loop and invokes the agent as a subprocess.

### Default: Claude Code

Each iteration, the `WorkflowRunner`:

1. Calls `adapter.identify_targets()` to find priority files needing improvement.
2. Builds a structured prompt with current metric value, target, direction, priority files, and `system_prompt_addendum`.
3. Invokes the agent as a subprocess: `claude --print --output-format json -p "<prompt>"`
4. Parses token usage from the agent's output for budget tracking.

### Custom Agents

Use `--agent-command` to substitute any command:

```bash
autoforge run complexity_refactor --path ./src --target 3.0 \
  --agent-command "python my_agent.py"
```

### Workflow YAML Agent Config

```yaml
agent:
  command: "claude"
  skill: "refactor-complexity"
  system_prompt_addendum: |
    You are performing complexity-driven iterative refactoring.
    Prioritize extracting helper functions and reducing nesting depth.
```

### Fail-Fast Validation

AutoForge verifies the agent binary exists on `PATH` before starting. If not found, the run fails immediately with a clear error.

## Built-in Workflows

### `complexity_refactor`

Reduces code complexity using [complexity-accounting](https://pypi.org/project/complexity-accounting/) to measure Net Complexity Score (NCS). The agent iteratively refactors mega-functions, dispatch chains, deep nesting, and duplicated logic.

### `test_quality`

Improves test suite quality by combining coverage measurement, function gap analysis, and assertion quality scoring. The assertion quality metric measures what fraction of test functions have at least one meaningful assertion on the output — code-path coverage is handled by the coverage sub-metrics, so the assertion score purely answers "do the tests verify anything?" Assertion count is deliberately ignored, making it impossible to game by spamming assertions.

## Adding a New Adapter

1. Subclass `BaseMetricAdapter` in `src/autoforge/adapters/`
2. Implement `check_prerequisites()`, `measure()`, `identify_targets()`
3. Register in `src/autoforge/registry.py`
4. Create a workflow YAML in `src/autoforge/workflows/`

See `src/autoforge/adapters/complexity.py` for a reference implementation.

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

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
