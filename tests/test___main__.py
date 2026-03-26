"""Tests for autoforge.__main__ — maps to __main__.py for TQS scoring."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autoforge.__main__ import build_parser, cmd_health, cmd_list, cmd_run, _setup_logging


class TestBuildParser:
    def test_version_flag_exits_zero(self):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0

    def test_no_command_returns_none(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None

    def test_run_command_all_args(self):
        parser = build_parser()
        args = parser.parse_args([
            "run", "complexity_refactor",
            "--path", "/src",
            "--repo", "/repo",
            "--target", "3.5",
            "--adapter", "complexity",
            "--max-iterations", "5",
            "--max-tokens", "100000",
            "--max-time", "20",
            "--test-command", "pytest",
            "--skip-tests",
            "--skip-git",
            "--dry-run",
            "--output", "/out",
        ])
        assert args.command == "run"
        assert args.workflow == "complexity_refactor"
        assert args.path == "/src"
        assert args.repo == "/repo"
        assert args.target == 3.5
        assert args.adapter == "complexity"
        assert args.max_iterations == 5
        assert args.max_tokens == 100000
        assert args.max_time == 20
        assert args.test_command == "pytest"
        assert args.skip_tests is True
        assert args.skip_git is True
        assert args.dry_run is True
        assert args.output == "/out"

    def test_run_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["run", "my_workflow"])
        assert args.workflow == "my_workflow"
        assert args.path is None
        assert args.repo == "."
        assert args.target is None
        assert args.adapter is None
        assert args.max_iterations is None
        assert args.skip_tests is False
        assert args.skip_git is False
        assert args.dry_run is False

    def test_health_command_all_args(self):
        parser = build_parser()
        args = parser.parse_args([
            "health", "--path", "/src", "--repo", "/repo",
            "--adapters", "complexity,coverage",
            "--format", "json", "--output", "/out/report.md",
        ])
        assert args.command == "health"
        assert args.path == "/src"
        assert args.adapters == "complexity,coverage"
        assert args.format == "json"
        assert args.output == "/out/report.md"

    def test_health_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["health"])
        assert args.path is None
        assert args.repo == "."
        assert args.adapters is None
        assert args.format == "text"
        assert args.output is None

    def test_list_command(self):
        parser = build_parser()
        args = parser.parse_args(["list"])
        assert args.command == "list"

    def test_verbose_flag(self):
        parser = build_parser()
        args = parser.parse_args(["-v", "list"])
        assert args.verbose is True

    def test_parser_prog_name(self):
        parser = build_parser()
        assert parser.prog == "autoforge"


class TestSetupLogging:
    def test_info_level(self):
        import logging
        root = logging.getLogger()
        root.handlers.clear()
        _setup_logging(verbose=False)
        assert root.level == logging.INFO

    def test_debug_level(self):
        import logging
        root = logging.getLogger()
        root.handlers.clear()
        _setup_logging(verbose=True)
        assert root.level == logging.DEBUG


class TestCmdList:
    def test_lists_adapters_and_workflows(self, capsys):
        parser = build_parser()
        args = parser.parse_args(["list"])
        ret = cmd_list(args)
        assert ret == 0
        captured = capsys.readouterr()
        assert "complexity" in captured.out
        assert "complexity_refactor" in captured.out
        assert "Available Adapters" in captured.out
        assert "Available Workflows" in captured.out


class TestCmdHealth:
    def test_health_json_output(self, capsys):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "example.py").write_text("def f():\n    return 1\n")
            parser = build_parser()
            args = parser.parse_args(["health", "--path", d, "--repo", d, "--format", "json"])
            ret = cmd_health(args)
            assert ret == 0
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert "complexity" in data
            assert "metric_name" in data["complexity"]
            assert "value" in data["complexity"]

    def test_health_text_output(self, capsys):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "example.py").write_text("x = 1\n")
            parser = build_parser()
            args = parser.parse_args(["health", "--path", d, "--repo", d])
            ret = cmd_health(args)
            assert ret == 0
            captured = capsys.readouterr()
            assert "Health Report" in captured.out

    def test_health_save_to_file(self, capsys):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "example.py").write_text("x = 1\n")
            output_file = str(Path(d) / "report.md")
            parser = build_parser()
            args = parser.parse_args(["health", "--path", d, "--repo", d, "--output", output_file])
            ret = cmd_health(args)
            assert ret == 0
            assert Path(output_file).exists()
            content = Path(output_file).read_text()
            assert "Health Report" in content

    def test_health_no_metrics_returns_error(self, capsys):
        with tempfile.TemporaryDirectory() as d:
            parser = build_parser()
            args = parser.parse_args(["health", "--path", d, "--repo", d, "--adapters", "nonexistent"])
            ret = cmd_health(args)
            assert ret == 1
            captured = capsys.readouterr()
            assert "No metrics collected" in captured.out


class TestCmdRun:
    def test_dry_run_produces_report(self, capsys):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "example.py").write_text(
                "def f(x):\n"
                "    if x > 0:\n"
                "        for i in range(x):\n"
                "            if i > 5:\n"
                "                print(i)\n"
            )
            output_dir = str(Path(d) / "reports")
            parser = build_parser()
            args = parser.parse_args([
                "run", "complexity_refactor",
                "--path", d, "--repo", d,
                "--skip-git", "--skip-tests", "--dry-run",
                "--max-iterations", "1",
                "--output", output_dir,
            ])
            ret = cmd_run(args)
            assert ret in (0, 1)
            captured = capsys.readouterr()
            assert "AutoForge Run Report" in captured.out
            report_files = list(Path(output_dir).glob("*.json"))
            assert len(report_files) >= 1

    def test_run_with_config_file(self, capsys):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "example.py").write_text("def f(): return 1\n")
            cfg_file = Path(d) / "wf.yaml"
            cfg_file.write_text(
                "name: test_wf\n"
                "adapter: complexity\n"
                "primary_metric:\n"
                "  name: ncs\n"
                "  direction: minimize\n"
                "  default_target: 100.0\n"
                "budget:\n"
                "  max_iterations: 1\n"
            )
            output_dir = str(Path(d) / "reports")
            parser = build_parser()
            args = parser.parse_args([
                "run", "test_wf",
                "--config", str(cfg_file),
                "--path", d, "--repo", d,
                "--skip-git", "--skip-tests", "--dry-run",
                "--output", output_dir,
            ])
            ret = cmd_run(args)
            captured = capsys.readouterr()
            assert "AutoForge Run Report" in captured.out


class TestMainEntrypoint:
    def test_no_args_exits_1(self):
        result = subprocess.run(
            [sys.executable, "-m", "autoforge"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 1

    def test_version_output(self):
        result = subprocess.run(
            [sys.executable, "-m", "autoforge", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "autoforge" in result.stdout

    def test_list_output(self):
        result = subprocess.run(
            [sys.executable, "-m", "autoforge", "list"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "complexity" in result.stdout
        assert "Available Adapters" in result.stdout
