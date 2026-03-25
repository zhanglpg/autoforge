"""Tests for autoforge.regression."""

import tempfile
from pathlib import Path

from autoforge.regression import RegressionGuard


class TestRegressionGuard:
    def test_detect_python_test_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a pyproject.toml to trigger Python detection
            (Path(tmpdir) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
            guard = RegressionGuard(tmpdir)
            cmd = guard._detect_test_command()
            assert cmd is not None
            assert "pytest" in cmd

    def test_detect_node_test_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "package.json").write_text('{"name": "test"}')
            guard = RegressionGuard(tmpdir)
            cmd = guard._detect_test_command()
            assert cmd == "npm test"

    def test_detect_go_test_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "go.mod").write_text("module test\n")
            guard = RegressionGuard(tmpdir)
            cmd = guard._detect_test_command()
            assert cmd == "go test ./..."

    def test_detect_no_test_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guard = RegressionGuard(tmpdir)
            cmd = guard._detect_test_command()
            assert cmd is None

    def test_run_tests_no_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guard = RegressionGuard(tmpdir)
            passed, output = guard.run_tests()
            assert passed
            assert "No tests configured" in output

    def test_run_tests_with_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guard = RegressionGuard(tmpdir, test_command="true")
            passed, output = guard.run_tests()
            assert passed

    def test_run_tests_failing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guard = RegressionGuard(tmpdir, test_command="false")
            passed, output = guard.run_tests()
            assert not passed

    def test_validate_iteration_skip_tests(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guard = RegressionGuard(tmpdir)
            passed, issues = guard.validate_iteration(run_tests=False)
            assert passed
            assert len(issues) == 0
