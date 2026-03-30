"""
Skill description generator for AutoForge.

Generates tool-contract descriptions that tell AI coding agents what metrics
are available, how to invoke measurement commands, and what budget/constraint
rules apply. The agent owns its own iteration strategy, git workflow, and
coding approach — this module only surfaces the measurement interface.
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
) -> str:
    """Generate a tool-contract skill description for an AI coding agent.

    The description tells the agent what metric to optimize, how to measure it,
    and what budget/constraint rules to follow. It does NOT prescribe iteration
    strategy, git workflow, or coding approach — those are the agent's domain.

    Args:
        config: The workflow configuration to generate a skill for.
        repo_path: Repository root path.
        target_path: Target path to improve (defaults to repo_path).
        target_value: Override target metric value.

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
            "## Constraints (do not violate)\n\n" + "\n".join(constraints)
        )

    # Custom instructions from workflow
    custom_instructions = ""
    if config.agent.system_prompt_addendum:
        custom_instructions = (
            "## Domain-Specific Instructions\n\n"
            f"{config.agent.system_prompt_addendum.strip()}"
        )

    # Iteration protocol from workflow YAML (if present)
    iteration_protocol = ""
    if config.skill_mode.iteration_protocol:
        iteration_protocol = (
            "## Iteration Protocol\n\n"
            f"{config.skill_mode.iteration_protocol.strip()}"
        )

    # Skill description from workflow YAML (if present)
    workflow_skill_desc = ""
    if config.description:
        workflow_skill_desc = f"**Goal**: {config.description}"

    skill = f"""\
# AutoForge Skill: {config.name}

{workflow_skill_desc}

Your objective is to {direction_verb} the **{config.primary_metric.name}** metric to \
{direction_cmp} **{target}**.

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
- **Stall detection**: If improvement is less than {config.budget.min_improvement_percent}% \
for {config.budget.stall_patience} consecutive iterations, stop early
- **Max files per iteration**: {config.budget.max_files_per_iteration}

{constraints_section}

{custom_instructions}

{iteration_protocol}"""

    # Clean up excessive blank lines from empty optional sections
    import re
    skill = re.sub(r'\n{3,}', '\n\n', skill)

    return skill.strip()


def generate_skill_json(
    config: WorkflowConfig,
    *,
    repo_path: str = ".",
    target_path: str | None = None,
    target_value: float | None = None,
) -> str:
    """Generate skill description as a structured JSON document.

    Returns pure structured data for programmatic consumption — no embedded
    text blob. Agents and frameworks can use this to build their own prompts.
    """
    target_path = target_path or repo_path
    target = target_value or config.primary_metric.default_target

    data = {
        "skill_name": config.name,
        "version": config.version,
        "description": config.description,
        "adapter": config.adapter,
        "primary_metric": {
            "name": config.primary_metric.name,
            "direction": config.primary_metric.direction.value,
            "target": target,
        },
        "budget": {
            "max_iterations": config.budget.max_iterations,
            "max_wall_clock_minutes": config.budget.max_wall_clock_minutes,
            "stall_patience": config.budget.stall_patience,
            "min_improvement_percent": config.budget.min_improvement_percent,
            "max_files_per_iteration": config.budget.max_files_per_iteration,
        },
        "commands": {
            "measure": (
                f"autoforge measure {config.adapter} "
                f"--path {target_path} --repo {repo_path} --format json"
            ),
            "targets": (
                f"autoforge targets {config.adapter} "
                f"--path {target_path} --repo {repo_path} "
                f"-n {config.budget.max_files_per_iteration}"
            ),
        },
        "output_schema": {
            "metric_name": "<string>",
            "value": "<float>",
            "unit": "<string>",
            "direction": "minimize|maximize",
            "breakdown": {"<file_path>": "<float>"},
        },
        "constraints": [
            {
                "name": c.name,
                "tolerance_percent": c.tolerance_percent,
                "direction": c.direction.value,
            }
            for c in config.constraint_metrics
        ],
    }

    if config.agent.system_prompt_addendum:
        data["domain_instructions"] = config.agent.system_prompt_addendum.strip()

    if config.skill_mode.iteration_protocol:
        data["iteration_protocol"] = config.skill_mode.iteration_protocol.strip()

    return json.dumps(data, indent=2)
