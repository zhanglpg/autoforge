"""Tests for the skill description generator."""

import json

from autoforge.models import (
    AgentConfig,
    BudgetConfig,
    Direction,
    MetricConstraint,
    PrimaryMetricConfig,
    SkillModeConfig,
    WorkflowConfig,
)
from autoforge.skill import generate_skill_description, generate_skill_json


def _make_config(**overrides):
    """Build a WorkflowConfig with sensible defaults, accepting overrides."""
    defaults = dict(
        name="test_workflow",
        version="1.0",
        description="Test workflow description",
        adapter="test_adapter",
        primary_metric=PrimaryMetricConfig(
            name="test_score",
            direction=Direction.MINIMIZE,
            default_target=5.0,
        ),
        budget=BudgetConfig(
            max_iterations=10,
            max_wall_clock_minutes=30,
            stall_patience=3,
            min_improvement_percent=1.0,
            max_files_per_iteration=5,
        ),
        agent=AgentConfig(),
        constraint_metrics=[],
        skill_mode=SkillModeConfig(),
    )
    defaults.update(overrides)
    return WorkflowConfig(**defaults)


class TestGenerateSkillDescription:
    def test_contains_metric_info(self):
        config = _make_config()
        output = generate_skill_description(config)
        assert "test_score" in output
        assert "minimize" in output
        assert "5.0" in output

    def test_contains_measurement_commands(self):
        config = _make_config()
        output = generate_skill_description(config, target_path="/src")
        assert "autoforge measure test_adapter" in output
        assert "autoforge targets test_adapter" in output
        assert "--path /src" in output

    def test_contains_json_schema(self):
        config = _make_config()
        output = generate_skill_description(config)
        assert '"metric_name"' in output
        assert '"breakdown"' in output
        assert '"direction"' in output

    def test_contains_budget_limits(self):
        config = _make_config()
        output = generate_skill_description(config)
        assert "10" in output  # max_iterations
        assert "30 minutes" in output
        assert "1.0%" in output  # min_improvement_percent

    def test_contains_constraints_when_present(self):
        config = _make_config(
            constraint_metrics=[
                MetricConstraint(
                    name="test_suite_pass",
                    tolerance_percent=0,
                    direction=Direction.MAXIMIZE,
                )
            ]
        )
        output = generate_skill_description(config)
        assert "test_suite_pass" in output
        assert "Constraints" in output

    def test_omits_constraints_when_empty(self):
        config = _make_config(constraint_metrics=[])
        output = generate_skill_description(config)
        assert "Constraints" not in output

    def test_contains_domain_instructions(self):
        config = _make_config(
            agent=AgentConfig(system_prompt_addendum="Focus on mega-functions first")
        )
        output = generate_skill_description(config)
        assert "Focus on mega-functions first" in output
        assert "Domain-Specific Instructions" in output

    def test_omits_domain_instructions_when_empty(self):
        config = _make_config(agent=AgentConfig(system_prompt_addendum=""))
        output = generate_skill_description(config)
        assert "Domain-Specific Instructions" not in output

    def test_contains_iteration_protocol_from_yaml(self):
        config = _make_config(
            skill_mode=SkillModeConfig(
                enabled=True,
                iteration_protocol="1. Measure\n2. Fix\n3. Re-measure",
            )
        )
        output = generate_skill_description(config)
        assert "Iteration Protocol" in output
        assert "1. Measure" in output

    def test_omits_iteration_protocol_when_empty(self):
        config = _make_config(skill_mode=SkillModeConfig())
        output = generate_skill_description(config)
        assert "Iteration Protocol" not in output

    def test_does_not_contain_git_conventions(self):
        config = _make_config()
        output = generate_skill_description(config)
        assert "Git Convention" not in output
        assert "autoforge/" not in output or "autoforge/measure" in output or "autoforge measure" in output

    def test_does_not_contain_important_rules(self):
        config = _make_config()
        output = generate_skill_description(config)
        assert "Important Rules" not in output

    def test_does_not_contain_getting_started(self):
        config = _make_config()
        output = generate_skill_description(config)
        assert "Getting Started" not in output

    def test_does_not_contain_how_this_works(self):
        config = _make_config()
        output = generate_skill_description(config)
        assert "How This Works" not in output

    def test_target_value_override(self):
        config = _make_config()
        output = generate_skill_description(config, target_value=2.0)
        assert "2.0" in output

    def test_maximize_direction(self):
        config = _make_config(
            primary_metric=PrimaryMetricConfig(
                name="coverage",
                direction=Direction.MAXIMIZE,
                default_target=90.0,
            )
        )
        output = generate_skill_description(config)
        assert "increase" in output
        assert "above" in output


class TestGenerateSkillJson:
    def test_valid_json(self):
        config = _make_config()
        output = generate_skill_json(config)
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_required_keys(self):
        config = _make_config()
        data = json.loads(generate_skill_json(config))
        assert data["skill_name"] == "test_workflow"
        assert data["adapter"] == "test_adapter"
        assert "primary_metric" in data
        assert "budget" in data
        assert "commands" in data
        assert "output_schema" in data
        assert "constraints" in data

    def test_no_embedded_skill_description(self):
        config = _make_config()
        data = json.loads(generate_skill_json(config))
        assert "skill_description" not in data

    def test_output_schema_present(self):
        config = _make_config()
        data = json.loads(generate_skill_json(config))
        schema = data["output_schema"]
        assert "metric_name" in schema
        assert "value" in schema
        assert "breakdown" in schema

    def test_commands_have_concrete_paths(self):
        config = _make_config()
        data = json.loads(
            generate_skill_json(config, target_path="/my/path", repo_path="/repo")
        )
        assert "/my/path" in data["commands"]["measure"]
        assert "/repo" in data["commands"]["measure"]

    def test_includes_domain_instructions_when_set(self):
        config = _make_config(
            agent=AgentConfig(system_prompt_addendum="Custom instructions here")
        )
        data = json.loads(generate_skill_json(config))
        assert data["domain_instructions"] == "Custom instructions here"

    def test_omits_domain_instructions_when_empty(self):
        config = _make_config(agent=AgentConfig(system_prompt_addendum=""))
        data = json.loads(generate_skill_json(config))
        assert "domain_instructions" not in data

    def test_includes_iteration_protocol_when_present(self):
        config = _make_config(
            skill_mode=SkillModeConfig(
                enabled=True,
                iteration_protocol="Step 1\nStep 2",
            )
        )
        data = json.loads(generate_skill_json(config))
        assert "Step 1" in data["iteration_protocol"]

    def test_omits_iteration_protocol_when_empty(self):
        config = _make_config(skill_mode=SkillModeConfig())
        data = json.loads(generate_skill_json(config))
        assert "iteration_protocol" not in data

    def test_primary_metric_structure(self):
        config = _make_config()
        data = json.loads(generate_skill_json(config))
        pm = data["primary_metric"]
        assert pm["name"] == "test_score"
        assert pm["direction"] == "minimize"
        assert pm["target"] == 5.0

    def test_target_value_override(self):
        config = _make_config()
        data = json.loads(generate_skill_json(config, target_value=2.0))
        assert data["primary_metric"]["target"] == 2.0
