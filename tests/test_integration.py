"""
Integration tests for AutoForge CLI commands.

These tests run the actual CLI via subprocess, exercising the full pipeline:
adapter discovery -> measurement -> output formatting. They use real adapters
(complexity is always available) and temporary directories with sample code.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

AUTOFORGE = [sys.executable, "-m", "autoforge"]
TIMEOUT = 30


def _run(*args: str, **kwargs) -> subprocess.CompletedProcess:
    """Run an autoforge CLI command and return the result."""
    return subprocess.run(
        [*AUTOFORGE, *args],
        capture_output=True,
        text=True,
        timeout=kwargs.pop("timeout", TIMEOUT),
        **kwargs,
    )


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Create a temporary project with Python files of varying complexity."""
    # Simple file — low complexity
    (tmp_path / "simple.py").write_text(
        "def greet(name):\n"
        "    return f'Hello, {name}'\n"
        "\n"
        "def add(a, b):\n"
        "    return a + b\n"
    )
    # Complex file — nested control flow
    (tmp_path / "complex.py").write_text(
        "def process(items, threshold, mode):\n"
        "    results = []\n"
        "    for item in items:\n"
        "        if item.value > threshold:\n"
        "            if mode == 'strict':\n"
        "                for sub in item.children:\n"
        "                    if sub.active:\n"
        "                        results.append(sub)\n"
        "            elif mode == 'lenient':\n"
        "                results.append(item)\n"
        "            else:\n"
        "                raise ValueError(f'Unknown mode: {mode}')\n"
        "        else:\n"
        "            if item.fallback:\n"
        "                results.append(item.fallback)\n"
        "    return results\n"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# autoforge list
# ---------------------------------------------------------------------------

class TestListIntegration:
    def test_list_returns_adapters_and_workflows(self):
        result = _run("list")
        assert result.returncode == 0
        assert "complexity" in result.stdout
        assert "Available Adapters" in result.stdout
        assert "Available Workflows" in result.stdout

    def test_list_includes_all_installed_adapters(self):
        result = _run("list")
        assert result.returncode == 0
        # These are installed in dev mode
        assert "complexity" in result.stdout
        assert "test_quality" in result.stdout
        assert "go_test_quality" in result.stdout

    def test_list_includes_all_workflows(self):
        result = _run("list")
        assert result.returncode == 0
        assert "complexity_refactor" in result.stdout
        assert "test_quality" in result.stdout
        assert "go_test_quality" in result.stdout


# ---------------------------------------------------------------------------
# autoforge measure
# ---------------------------------------------------------------------------

class TestMeasureIntegration:
    def test_measure_json_output(self, sample_project):
        result = _run("measure", "complexity", "--path", str(sample_project), "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["metric_name"] == "net_complexity_score"
        assert isinstance(data["value"], (int, float))
        assert data["direction"] == "minimize"
        assert data["unit"] == "score"
        assert "breakdown" in data
        assert isinstance(data["breakdown"], dict)
        assert "tool" in data
        assert "timestamp" in data

    def test_measure_text_output(self, sample_project):
        result = _run("measure", "complexity", "--path", str(sample_project), "--format", "text")
        assert result.returncode == 0
        assert "net_complexity_score" in result.stdout
        assert "minimize" in result.stdout

    def test_measure_breakdown_contains_files(self, sample_project):
        result = _run("measure", "complexity", "--path", str(sample_project), "--format", "json")
        data = json.loads(result.stdout)
        breakdown = data["breakdown"]
        # Both files should appear in breakdown
        file_names = {Path(k).name for k in breakdown}
        assert "simple.py" in file_names
        assert "complex.py" in file_names

    def test_measure_complex_file_scores_higher(self, sample_project):
        result = _run("measure", "complexity", "--path", str(sample_project), "--format", "json")
        data = json.loads(result.stdout)
        breakdown = data["breakdown"]
        # Find scores by filename
        scores = {}
        for path, score in breakdown.items():
            scores[Path(path).name] = score
        assert scores["complex.py"] > scores["simple.py"]

    def test_measure_unknown_adapter(self, sample_project):
        result = _run("measure", "nonexistent_adapter", "--path", str(sample_project), "--format", "json")
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert "error" in data
        assert "nonexistent_adapter" in data["error"]

    def test_measure_unknown_adapter_text(self, sample_project):
        result = _run("measure", "nonexistent_adapter", "--path", str(sample_project), "--format", "text")
        assert result.returncode == 1
        assert "Error" in result.stdout

    def test_measure_empty_directory(self, tmp_path):
        result = _run("measure", "complexity", "--path", str(tmp_path), "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["value"] == 0.0 or isinstance(data["value"], (int, float))

    def test_measure_json_is_valid(self, sample_project):
        """Ensure JSON output is parseable and has all expected fields."""
        result = _run("measure", "complexity", "--path", str(sample_project), "--format", "json")
        data = json.loads(result.stdout)
        required_fields = {"metric_name", "value", "unit", "direction", "breakdown", "tool", "timestamp"}
        assert required_fields.issubset(data.keys())

    def test_measure_text_shows_breakdown(self, sample_project):
        result = _run("measure", "complexity", "--path", str(sample_project), "--format", "text")
        assert result.returncode == 0
        assert "Breakdown" in result.stdout
        assert "complex.py" in result.stdout


# ---------------------------------------------------------------------------
# autoforge targets
# ---------------------------------------------------------------------------

class TestTargetsIntegration:
    def test_targets_json_output(self, sample_project):
        result = _run("targets", "complexity", "--path", str(sample_project), "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "targets" in data
        assert "target_scores" in data
        assert "current_value" in data
        assert "metric_name" in data
        assert isinstance(data["targets"], list)

    def test_targets_text_output(self, sample_project):
        result = _run("targets", "complexity", "--path", str(sample_project), "--format", "text")
        assert result.returncode == 0
        assert "targets for" in result.stdout

    def test_targets_worst_first(self, sample_project):
        """The most complex file should be the first target."""
        result = _run("targets", "complexity", "--path", str(sample_project), "-n", "2", "--format", "json")
        data = json.loads(result.stdout)
        targets = data["targets"]
        assert len(targets) >= 1
        # complex.py should be the worst (highest NCS for minimize direction)
        assert "complex.py" in targets[0]

    def test_targets_respects_n_flag(self, sample_project):
        result = _run("targets", "complexity", "--path", str(sample_project), "-n", "1", "--format", "json")
        data = json.loads(result.stdout)
        assert len(data["targets"]) == 1

    def test_targets_scores_match_breakdown(self, sample_project):
        """Target scores should correspond to actual metric values."""
        result = _run("targets", "complexity", "--path", str(sample_project), "--format", "json")
        data = json.loads(result.stdout)
        for target in data["targets"]:
            assert target in data["target_scores"]
            assert isinstance(data["target_scores"][target], (int, float))

    def test_targets_unknown_adapter(self, sample_project):
        result = _run("targets", "nonexistent_adapter", "--path", str(sample_project))
        assert result.returncode == 1
        assert "Error" in result.stdout


# ---------------------------------------------------------------------------
# autoforge skill-info
# ---------------------------------------------------------------------------

class TestSkillInfoIntegration:
    def test_skill_info_text_output(self):
        result = _run("skill-info", "complexity_refactor")
        assert result.returncode == 0
        # Should contain measurement commands and metric info
        assert "autoforge measure" in result.stdout or "measure" in result.stdout
        assert "complexity" in result.stdout.lower()

    def test_skill_info_json_output(self):
        result = _run("skill-info", "complexity_refactor", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_skill_info_with_target(self):
        result = _run("skill-info", "complexity_refactor", "--target", "3.0")
        assert result.returncode == 0
        assert "3.0" in result.stdout

    def test_skill_info_with_path(self, sample_project):
        result = _run("skill-info", "complexity_refactor", "--path", str(sample_project))
        assert result.returncode == 0
        assert len(result.stdout) > 0

    def test_skill_info_save_to_file(self, tmp_path):
        output_file = str(tmp_path / "skill.md")
        result = _run("skill-info", "complexity_refactor", "--output", output_file)
        assert result.returncode == 0
        assert Path(output_file).exists()
        content = Path(output_file).read_text()
        assert "complexity" in content.lower()

    def test_skill_info_unknown_workflow(self):
        result = _run("skill-info", "nonexistent_workflow")
        assert result.returncode != 0

    def test_skill_info_test_quality_workflow(self):
        result = _run("skill-info", "test_quality")
        assert result.returncode == 0
        assert "test" in result.stdout.lower()

    def test_skill_info_with_custom_config(self, tmp_path):
        cfg = tmp_path / "custom.yaml"
        cfg.write_text(
            "name: custom_wf\n"
            "adapter: complexity\n"
            "description: A custom workflow\n"
            "primary_metric:\n"
            "  name: ncs\n"
            "  direction: minimize\n"
            "  default_target: 5.0\n"
            "budget:\n"
            "  max_iterations: 10\n"
        )
        result = _run("skill-info", "custom_wf", "--config", str(cfg))
        assert result.returncode == 0
        assert "custom" in result.stdout.lower() or "ncs" in result.stdout.lower()


# ---------------------------------------------------------------------------
# autoforge health
# ---------------------------------------------------------------------------

class TestHealthIntegration:
    def test_health_text_output(self, sample_project):
        result = _run("health", "--path", str(sample_project), "--repo", str(sample_project))
        assert result.returncode == 0
        assert "Health Report" in result.stdout

    def test_health_json_output(self, sample_project):
        result = _run("health", "--path", str(sample_project), "--repo", str(sample_project), "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "complexity" in data
        assert "value" in data["complexity"]
        assert "metric_name" in data["complexity"]

    def test_health_specific_adapter(self, sample_project):
        result = _run(
            "health", "--path", str(sample_project), "--repo", str(sample_project),
            "--adapters", "complexity", "--format", "json",
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "complexity" in data
        assert len(data) == 1

    def test_health_save_to_file(self, sample_project):
        output_file = str(sample_project / "health_report.md")
        result = _run(
            "health", "--path", str(sample_project), "--repo", str(sample_project),
            "--output", output_file,
        )
        assert result.returncode == 0
        assert Path(output_file).exists()
        content = Path(output_file).read_text()
        assert "Health Report" in content

    def test_health_nonexistent_adapter(self, sample_project):
        result = _run(
            "health", "--path", str(sample_project), "--repo", str(sample_project),
            "--adapters", "nonexistent",
        )
        assert result.returncode == 1
        assert "No metrics collected" in result.stdout


# ---------------------------------------------------------------------------
# autoforge run (dry-run only)
# ---------------------------------------------------------------------------

class TestRunDryRunIntegration:
    def test_dry_run_measures_and_reports(self, sample_project):
        output_dir = str(sample_project / "reports")
        result = _run(
            "run", "complexity_refactor",
            "--path", str(sample_project), "--repo", str(sample_project),
            "--skip-git", "--skip-tests", "--dry-run",
            "--max-iterations", "1",
            "--output", output_dir,
        )
        assert result.returncode in (0, 1)
        assert "AutoForge Run Report" in result.stdout
        # Reports should be saved
        report_files = list(Path(output_dir).glob("*.json"))
        assert len(report_files) >= 1

    def test_dry_run_json_report_valid(self, sample_project):
        output_dir = str(sample_project / "reports")
        _run(
            "run", "complexity_refactor",
            "--path", str(sample_project), "--repo", str(sample_project),
            "--skip-git", "--skip-tests", "--dry-run",
            "--max-iterations", "1",
            "--output", output_dir,
        )
        report_files = list(Path(output_dir).glob("*.json"))
        assert len(report_files) >= 1
        data = json.loads(report_files[0].read_text())
        assert "workflow" in data
        assert "outcome" in data

    def test_dry_run_with_target(self, sample_project):
        output_dir = str(sample_project / "reports")
        result = _run(
            "run", "complexity_refactor",
            "--path", str(sample_project), "--repo", str(sample_project),
            "--skip-git", "--skip-tests", "--dry-run",
            "--target", "0.5",
            "--max-iterations", "1",
            "--output", output_dir,
        )
        assert result.returncode in (0, 1)


# ---------------------------------------------------------------------------
# End-to-end: measure -> targets -> measure cycle
# ---------------------------------------------------------------------------

class TestMeasureTargetsCycle:
    """Simulate the tool-mode workflow an AI agent would follow."""

    def test_measure_then_targets_consistent(self, sample_project):
        """Measure and targets should report consistent metric values."""
        measure_result = _run(
            "measure", "complexity",
            "--path", str(sample_project), "--format", "json",
        )
        targets_result = _run(
            "targets", "complexity",
            "--path", str(sample_project), "--format", "json",
        )
        assert measure_result.returncode == 0
        assert targets_result.returncode == 0

        measure_data = json.loads(measure_result.stdout)
        targets_data = json.loads(targets_result.stdout)

        # Overall metric values should match
        assert measure_data["value"] == targets_data["current_value"]
        assert measure_data["metric_name"] == targets_data["metric_name"]

        # Target scores should be a subset of the breakdown
        for target, score in targets_data["target_scores"].items():
            assert target in measure_data["breakdown"]
            assert measure_data["breakdown"][target] == score

    def test_full_agent_workflow_simulation(self, sample_project):
        """Simulate: measure -> identify targets -> (agent edits) -> re-measure."""
        # Step 1: Initial measurement
        r1 = _run("measure", "complexity", "--path", str(sample_project), "--format", "json")
        assert r1.returncode == 0
        initial = json.loads(r1.stdout)

        # Step 2: Identify targets
        r2 = _run("targets", "complexity", "--path", str(sample_project), "-n", "1", "--format", "json")
        assert r2.returncode == 0
        targets = json.loads(r2.stdout)
        assert len(targets["targets"]) == 1
        worst_file = targets["targets"][0]

        # Step 3: Simulate agent edit — simplify the complex file
        worst_path = sample_project / Path(worst_file).name
        if worst_path.exists():
            worst_path.write_text(
                "def process(items, threshold, mode):\n"
                "    return [item for item in items if item.value > threshold]\n"
            )

        # Step 4: Re-measure — complexity should decrease
        r3 = _run("measure", "complexity", "--path", str(sample_project), "--format", "json")
        assert r3.returncode == 0
        after = json.loads(r3.stdout)

        # NCS is minimize — lower is better
        assert after["value"] <= initial["value"]


# ---------------------------------------------------------------------------
# CLI edge cases
# ---------------------------------------------------------------------------

class TestCLIEdgeCases:
    def test_no_command_exits_nonzero(self):
        result = _run()
        assert result.returncode == 1

    def test_version_flag(self):
        result = _run("--version")
        assert result.returncode == 0
        assert "autoforge" in result.stdout

    def test_verbose_flag_enables_debug(self, sample_project):
        result = _run("-v", "measure", "complexity", "--path", str(sample_project), "--format", "json")
        assert result.returncode == 0
        # Debug output goes to stderr
        # JSON output should still be valid on stdout
        json.loads(result.stdout)

    def test_measure_default_format_is_json(self, sample_project):
        result = _run("measure", "complexity", "--path", str(sample_project))
        assert result.returncode == 0
        json.loads(result.stdout)  # Should be valid JSON by default

    def test_targets_default_n_is_five(self, sample_project):
        # Create enough files to verify default n=5
        for i in range(7):
            (sample_project / f"mod_{i}.py").write_text(
                f"def func_{i}(x):\n"
                f"    if x > 0:\n"
                f"        for j in range({i + 1}):\n"
                f"            if j > 0:\n"
                f"                print(j)\n"
            )
        result = _run("targets", "complexity", "--path", str(sample_project), "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data["targets"]) == 5
