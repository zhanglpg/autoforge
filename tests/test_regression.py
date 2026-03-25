"""Tests for autoforge.regression — RegressionGuard."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from autoforge.models import Direction, MetricResult
from autoforge.regression import RegressionGuard, RegressionViolation


class TestTestCommandDetection:
    """Test auto-detection of test commands for various ecosystems."""

    def test_python_pyproject(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "pyproject.toml").write_text("[project]\nname = 'x'\n")
            guard = RegressionGuard(d)
            cmd = guard._detect_test_command()
            assert "pytest" in cmd

    def test_python_setup_py(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "setup.py").write_text("from setuptools import setup\nsetup()\n")
            guard = RegressionGuard(d)
            cmd = guard._detect_test_command()
            assert "pytest" in cmd

    def test_node_package_json(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "package.json").write_text('{"name": "x"}')
            guard = RegressionGuard(d)
            assert guard._detect_test_command() == "npm test"

    def test_go_module(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "go.mod").write_text("module x\n")
            guard = RegressionGuard(d)
            assert guard._detect_test_command() == "go test ./..."

    def test_rust_cargo(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Cargo.toml").write_text('[package]\nname = "x"\n')
            guard = RegressionGuard(d)
            assert guard._detect_test_command() == "cargo test"

    def test_no_recognized_project(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d)
            assert guard._detect_test_command() is None

    def test_python_takes_precedence_over_node(self):
        """If both pyproject.toml and package.json exist, Python wins."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "pyproject.toml").write_text("[project]\nname = 'x'\n")
            (Path(d) / "package.json").write_text('{"name": "x"}')
            guard = RegressionGuard(d)
            cmd = guard._detect_test_command()
            assert "pytest" in cmd


class TestRunTests:
    def test_no_test_command_detected(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d)
            passed, output = guard.run_tests()
            assert passed is True
            assert "No tests configured" in output

    def test_explicit_command_passes(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d, test_command="true")
            passed, output = guard.run_tests()
            assert passed is True

    def test_explicit_command_fails(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d, test_command="false")
            passed, output = guard.run_tests()
            assert passed is False

    def test_command_output_captured(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d, test_command="echo hello_test")
            passed, output = guard.run_tests()
            assert passed is True
            assert "hello_test" in output

    def test_stderr_captured_on_failure(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d, test_command="echo error_msg >&2; false")
            passed, output = guard.run_tests()
            assert not passed
            assert "error_msg" in output


class TestValidateIteration:
    def test_passes_when_tests_pass(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d, test_command="true")
            passed, issues = guard.validate_iteration(run_tests=True)
            assert passed
            assert issues == []

    def test_fails_when_tests_fail(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d, test_command="echo BOOM; false")
            passed, issues = guard.validate_iteration(run_tests=True)
            assert not passed
            assert len(issues) == 1
            assert "Tests failed" in issues[0]

    def test_skip_tests(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d, test_command="false")  # would fail
            passed, issues = guard.validate_iteration(run_tests=False)
            assert passed
            assert issues == []


class TestConstraintBaselines:
    def test_set_and_check_constraint(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d)

            baseline = MetricResult(
                metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE
            )
            guard.set_constraint_baseline("ncs", baseline)

            # Mock adapter that returns a worse value
            adapter = MagicMock()
            adapter.measure.return_value = MetricResult(
                metric_name="ncs", value=6.0, unit="score", direction=Direction.MINIMIZE
            )

            violations = guard.check_constraints(
                adapter, d, d, tolerance_map={"ncs": 10.0}
            )
            assert len(violations) == 1
            assert "ncs" in violations[0]

    def test_constraint_within_tolerance(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d)

            baseline = MetricResult(
                metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE
            )
            guard.set_constraint_baseline("ncs", baseline)

            adapter = MagicMock()
            adapter.measure.return_value = MetricResult(
                metric_name="ncs", value=5.2, unit="score", direction=Direction.MINIMIZE
            )

            violations = guard.check_constraints(
                adapter, d, d, tolerance_map={"ncs": 10.0}
            )
            assert violations == []

    def test_no_constraints_set(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d)
            adapter = MagicMock()
            violations = guard.check_constraints(adapter, d, d, tolerance_map={})
            assert violations == []

    def test_constraint_check_handles_adapter_error(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d)
            baseline = MetricResult(
                metric_name="x", value=5.0, unit="u", direction=Direction.MINIMIZE
            )
            guard.set_constraint_baseline("x", baseline)

            adapter = MagicMock()
            adapter.measure.side_effect = RuntimeError("tool broken")

            violations = guard.check_constraints(
                adapter, d, d, tolerance_map={"x": 10.0}
            )
            assert violations == []  # errors are logged, not raised

    def test_default_tolerance_used(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d)

            baseline = MetricResult(
                metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE
            )
            guard.set_constraint_baseline("ncs", baseline)

            adapter = MagicMock()
            adapter.measure.return_value = MetricResult(
                metric_name="ncs", value=6.0, unit="score", direction=Direction.MINIMIZE
            )

            # Not in tolerance_map -> default 10.0 used
            violations = guard.check_constraints(
                adapter, d, d, tolerance_map={}
            )
            assert len(violations) == 1  # 20% > default 10%


class TestValidateIterationWithConstraints:
    """Test that validate_iteration checks constraints when provided."""

    def test_constraints_checked_when_adapter_provided(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d, test_command="true")

            baseline = MetricResult(
                metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE
            )
            guard.set_constraint_baseline("ncs", baseline)

            # Adapter returns degraded value (20% worse, exceeds 10% tolerance)
            adapter = MagicMock()
            adapter.measure.return_value = MetricResult(
                metric_name="ncs", value=6.0, unit="score", direction=Direction.MINIMIZE
            )

            passed, issues = guard.validate_iteration(
                run_tests=True,
                adapter=adapter,
                repo_path=d,
                target_path=d,
                tolerance_map={"ncs": 10.0},
            )
            assert not passed
            assert any("ncs" in issue for issue in issues)

    def test_constraints_skipped_when_no_adapter(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d, test_command="true")

            baseline = MetricResult(
                metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE
            )
            guard.set_constraint_baseline("ncs", baseline)

            # No adapter passed — constraints not checked
            passed, issues = guard.validate_iteration(run_tests=True)
            assert passed
            assert issues == []

    def test_constraints_skipped_when_no_baselines(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d, test_command="true")
            adapter = MagicMock()

            # No baselines set — constraints not checked
            passed, issues = guard.validate_iteration(
                run_tests=True,
                adapter=adapter,
                repo_path=d,
                target_path=d,
                tolerance_map={},
            )
            assert passed
            assert issues == []

    def test_both_tests_and_constraints_can_fail(self):
        with tempfile.TemporaryDirectory() as d:
            guard = RegressionGuard(d, test_command="false")

            baseline = MetricResult(
                metric_name="ncs", value=5.0, unit="score", direction=Direction.MINIMIZE
            )
            guard.set_constraint_baseline("ncs", baseline)

            adapter = MagicMock()
            adapter.measure.return_value = MetricResult(
                metric_name="ncs", value=6.0, unit="score", direction=Direction.MINIMIZE
            )

            passed, issues = guard.validate_iteration(
                run_tests=True,
                adapter=adapter,
                repo_path=d,
                target_path=d,
                tolerance_map={"ncs": 10.0},
            )
            assert not passed
            assert len(issues) == 2  # test failure + constraint violation


class TestRegressionViolation:
    def test_exception_has_reason(self):
        exc = RegressionViolation("tests broke")
        assert exc.reason == "tests broke"
        assert str(exc) == "tests broke"
