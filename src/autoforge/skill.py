"""
Skill description generator for AutoForge.

Generates structured skill descriptions that allow AI coding agents (e.g.,
Claude Code) to drive AutoForge workflows directly. The agent reads the skill
description, calls `autoforge measure` and `autoforge targets` as CLI tools,
reasons about results, makes changes, and re-measures — all within its native
capabilities.

This is the hybrid architecture: AutoForge owns measurement and budget rules,
the agent owns coding strategy and reasoning.
"""

from __future__ import annotations

import json
from pathlib import Path

from autoforge.models import Direction, WorkflowConfig


def generate_skill_description(
    config: WorkflowConfig,
    *,
    repo_path: str = ".",
    target_path: str | None = None,
    target_value: float | None = None,
    test_command: str | None = None,
) -> str:
    """Generate a complete skill description for an AI coding agent.

    The description instructs the agent on how to execute the workflow
    using `autoforge measure` and `autoforge targets` CLI commands,
    while following the workflow's budget and constraint rules.

    Args:
        config: The workflow configuration to generate a skill for.
        repo_path: Repository root path.
        target_path: Target path to improve (defaults to repo_path).
        target_value: Override target metric value.
        test_command: Override test command for regression guard.

    Returns:
        A multi-line skill description string.
    """
    target_path = target_path or repo_path
    target = target_value or config.primary_metric.default_target
    direction = config.primary_metric.direction
    direction_verb = "reduce" if direction is Direction.MINIMIZE else "increase"
    direction_cmp = "below" if direction is Direction.MINIMIZE else "above"

    # Build measurement commands
    measure_cmd = (
        f"autoforge measure {config.adapter} "
        f"--path {target_path} --repo {repo_path} --format json"
    )
    targets_cmd = (
        f"autoforge targets {config.adapter} "
        f"--path {target_path} --repo {repo_path} -n {config.budget.max_files_per_iteration}"
    )

    # Build test command section
    test_section = ""
    if test_command:
        test_section = f"Test command: `{test_command}`"
    else:
        test_section = (
            "Auto-detect test command (pytest, npm test, go test, cargo test), "
            "or run the project's standard test suite."
        )

    # Constraint metrics section
    constraints_section = ""
    if config.constraint_metrics:
        constraints = []
        for c in config.constraint_metrics:
            constraints.append(
                f"  - **{c.name}**: must not degrade more than {c.tolerance_percent}% "
                f"from baseline ({c.direction.value})"
            )
        constraints_section = (
            "## Constraints (do not violate)\n" + "\n".join(constraints)
        )

    # Custom instructions from workflow
    custom_instructions = ""
    if config.agent.system_prompt_addendum:
        custom_instructions = (
            "## Domain-Specific Instructions\n"
            f"{config.agent.system_prompt_addendum.strip()}"
        )

    # Skill description from workflow YAML (if present)
    workflow_skill_desc = ""
    if config.description:
        workflow_skill_desc = f"**Goal**: {config.description}"

    skill = f"""\
# AutoForge Skill: {config.name}

{workflow_skill_desc}

You are executing the **{config.name}** workflow. Your objective is to
{direction_verb} the **{config.primary_metric.name}** metric to {direction_cmp}
**{target}** through iterative code changes.

## How This Works

You drive the iteration loop. Each iteration:
1. **Measure** the current metric by running the measurement command
2. **Identify targets** — find the worst files to focus on
3. **Make changes** — edit code to improve the metric (2-4 focused changes)
4. **Run tests** — verify no regressions
5. **Re-measure** — confirm improvement
6. **Commit** — commit the iteration with a descriptive message
7. **Repeat** until the target is met or budget is exhausted

## Measurement Commands

Use these CLI commands to measure and identify targets:

```bash
# Measure the current metric value (returns JSON)
{measure_cmd}

# Identify worst files to target (returns file list)
{targets_cmd}
```

The measure command returns JSON with this structure:
```json
{{
  "metric_name": "{config.primary_metric.name}",
  "value": <float>,
  "unit": "<unit>",
  "direction": "{direction.value}",
  "breakdown": {{"<file_path>": <per_file_value>, ...}}
}}
```

## Budget Limits

Stop after any of these limits are reached:
- **Max iterations**: {config.budget.max_iterations}
- **Max wall-clock time**: {config.budget.max_wall_clock_minutes} minutes
- **Stall detection**: If improvement is less than {config.budget.min_improvement_percent}%
  for {config.budget.stall_patience} consecutive iterations, stop early
- **Max files per iteration**: {config.budget.max_files_per_iteration}

## Regression Guard

After each change, before committing:
- {test_section}
- If tests fail, **revert your changes** for this iteration and try a different approach
- Never commit code that breaks tests

{constraints_section}

{custom_instructions}

## Git Convention

- Create a branch: `autoforge/{config.name}/<timestamp>` (if not already on one)
- Commit message format: `autoforge({config.name}): iteration N — metric before -> after`
- If an iteration fails validation, revert and try again with a different approach

## Important Rules

- Make **focused, minimal changes** per iteration (2-4 related refactorings)
- Preserve existing behavior — no feature additions unless the workflow requires it
- Always measure before and after to confirm improvement
- If you get stuck or the metric isn't improving, try a fundamentally different approach
- Track your iteration count and stop when budget is exhausted

## Getting Started

1. Run the measure command to get the baseline
2. Run the targets command to see which files need the most work
3. Start your first iteration
"""

    return skill.strip()


def generate_skill_json(
    config: WorkflowConfig,
    **kwargs,
) -> str:
    """Generate skill description as a structured JSON document.

    Useful for programmatic consumption or integration with agent frameworks.
    """
    description = generate_skill_description(config, **kwargs)

    data = {
        "skill_name": config.name,
        "version": config.version,
        "description": config.description,
        "workflow": config.name,
        "adapter": config.adapter,
        "primary_metric": {
            "name": config.primary_metric.name,
            "direction": config.primary_metric.direction.value,
            "target": kwargs.get("target_value") or config.primary_metric.default_target,
        },
        "budget": {
            "max_iterations": config.budget.max_iterations,
            "max_wall_clock_minutes": config.budget.max_wall_clock_minutes,
            "stall_patience": config.budget.stall_patience,
            "min_improvement_percent": config.budget.min_improvement_percent,
            "max_files_per_iteration": config.budget.max_files_per_iteration,
        },
        "commands": {
            "measure": f"autoforge measure {config.adapter} --path {{target_path}} --repo {{repo_path}} --format json",
            "targets": f"autoforge targets {config.adapter} --path {{target_path}} --repo {{repo_path}} -n {config.budget.max_files_per_iteration}",
        },
        "constraints": [
            {
                "name": c.name,
                "tolerance_percent": c.tolerance_percent,
                "direction": c.direction.value,
            }
            for c in config.constraint_metrics
        ],
        "skill_description": description,
    }

    return json.dumps(data, indent=2)
