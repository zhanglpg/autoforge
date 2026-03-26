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

### `autoforge health`

Run all (or specified) metric adapters and produce a health dashboard.

| Flag | Description |
|---|---|
| `--path, -p` | Target path to analyze |
| `--adapters` | Comma-separated adapter names |
| `--format, -f` | Output format: `text` or `json` |
| `--output, -o` | Save output to file |

### `autoforge list`

List all registered workflows and adapters.

## Architecture

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

- **WorkflowRunner** &mdash; orchestrates the iteration loop: measure baseline, invoke agent, re-measure, validate, commit or rollback.
- **Agent (Claude Code)** &mdash; the external coding agent invoked as a subprocess each iteration. The runner constructs a prompt with the current metric value, target, and priority files, then calls `claude --print --output-format json`. Use `--agent-command` to substitute a different agent.
- **BudgetManager** &mdash; enforces iteration/token/time limits and detects improvement stalls. Token usage is parsed best-effort from the agent's JSON output or stderr.
- **GitManager** &mdash; creates feature branches, commits per iteration, rolls back failed iterations.
- **RegressionGuard** &mdash; runs tests and checks constraint metrics between iterations.
- **MetricAdapter** &mdash; protocol for plugging in any measurement tool. Adapters normalize tool output into a standard `MetricResult` and identify priority files for the agent to focus on.

## Agent Integration

AutoForge follows a **subprocess-based agent model**: the framework handles everything except the actual code changes, which are delegated to a local coding agent.

### Default: Claude Code

Each iteration, the `WorkflowRunner`:

1. Calls `adapter.identify_targets()` to find priority files needing improvement.
2. Builds a structured prompt containing: iteration number, current metric value, target, direction (minimize/maximize), priority file list, and any `system_prompt_addendum` from the workflow YAML.
3. Writes the prompt to a temp file and invokes:
   ```
   claude --print --output-format json -p "$(cat <prompt_file>)"
   ```
4. Parses token usage from the agent's JSON output (or stderr) for budget tracking.

The agent runs inside the repository working directory and directly modifies files on disk. After the agent returns, AutoForge re-measures, validates (tests + constraints), and commits or rolls back.

### Custom Agents

Use `--agent-command` to substitute any command that accepts a prompt on stdin or as an argument:

```bash
# Use a custom script
autoforge run complexity_refactor --path ./src --target 3.0 \
  --agent-command "python my_agent.py"

# Use a different CLI tool
autoforge run complexity_refactor --path ./src --target 3.0 \
  --agent-command "aider --message"
```

### Workflow YAML Agent Config

Each workflow YAML can include an `agent` section to configure the agent binary and provide domain-specific instructions:

```yaml
agent:
  command: "claude"  # Agent binary (default: claude). Change to use a different agent.
  skill: "refactor-complexity"
  system_prompt_addendum: |
    You are performing complexity-driven iterative refactoring.
    Prioritize extracting helper functions and reducing nesting depth.
```

### Fail-Fast Validation

AutoForge verifies the agent binary exists on `PATH` before starting any iterations. If the agent is not found, the run fails immediately with a clear error message suggesting either installing the agent or using `--agent-command`.

## Built-in Workflows

### `complexity_refactor`

Reduces code complexity using [complexity-accounting](https://pypi.org/project/complexity-accounting/) to measure Net Complexity Score (NCS). The agent iteratively refactors mega-functions, dispatch chains, deep nesting, and duplicated logic.

### `test_quality`

Improves test suite quality by combining coverage measurement, function gap analysis, and assertion quality scoring. The agent generates missing tests and strengthens existing ones.

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
