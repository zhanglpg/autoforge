"""Tests for autoforge-type-safety — TypeSafetyAdapter."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from autoforge.models import Direction, MetricResult
from autoforge_type_safety import (
    FileTypeResult,
    TypeCheckSummary,
    TypeDiagnostic,
    TypeSafetyAdapter,
    build_metric_result,
    normalize_paths,
    parse_mypy_json,
    parse_pyright_json,
)


# ---------------------------------------------------------------------------
# Fixtures: representative pyright / mypy JSON output
# ---------------------------------------------------------------------------

PYRIGHT_EMPTY = {
    "version": "1.1.408",
    "time": "100",
    "generalDiagnostics": [],
    "summary": {
        "filesAnalyzed": 5,
        "errorCount": 0,
        "warningCount": 0,
        "informationCount": 0,
    },
}

PYRIGHT_SINGLE_ERROR = {
    "version": "1.1.408",
    "time": "100",
    "generalDiagnostics": [
        {
            "file": "/project/src/foo.py",
            "severity": "error",
            "message": 'Type "int" is not assignable to type "str"',
            "range": {
                "start": {"line": 10, "character": 4},
                "end": {"line": 10, "character": 15},
            },
            "rule": "reportAssignmentType",
        },
    ],
    "summary": {"filesAnalyzed": 3, "errorCount": 1, "warningCount": 0, "informationCount": 0},
}

PYRIGHT_MULTIPLE_FILES = {
    "version": "1.1.408",
    "time": "200",
    "generalDiagnostics": [
        {
            "file": "/project/src/a.py",
            "severity": "error",
            "message": "error 1",
            "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 5}},
            "rule": "reportGeneralClassIssue",
        },
        {
            "file": "/project/src/a.py",
            "severity": "error",
            "message": "error 2",
            "range": {"start": {"line": 5, "character": 0}, "end": {"line": 5, "character": 5}},
            "rule": "reportMissingImports",
        },
        {
            "file": "/project/src/b.py",
            "severity": "error",
            "message": "error 3",
            "range": {"start": {"line": 3, "character": 0}, "end": {"line": 3, "character": 5}},
            "rule": "reportArgumentType",
        },
    ],
    "summary": {"filesAnalyzed": 10, "errorCount": 3, "warningCount": 0, "informationCount": 0},
}

PYRIGHT_MIXED_SEVERITIES = {
    "version": "1.1.408",
    "time": "100",
    "generalDiagnostics": [
        {
            "file": "/project/src/c.py",
            "severity": "error",
            "message": "type error",
            "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 5}},
            "rule": "reportAssignmentType",
        },
        {
            "file": "/project/src/c.py",
            "severity": "warning",
            "message": "type warning",
            "range": {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 5}},
            "rule": "reportUnusedImport",
        },
        {
            "file": "/project/src/c.py",
            "severity": "information",
            "message": "type info",
            "range": {"start": {"line": 3, "character": 0}, "end": {"line": 3, "character": 5}},
            "rule": "reportUnusedVariable",
        },
    ],
    "summary": {"filesAnalyzed": 1, "errorCount": 1, "warningCount": 1, "informationCount": 1},
}

MYPY_SINGLE_ERROR = (
    '{"file": "src/foo.py", "line": 10, "column": 4, '
    '"severity": "error", "message": "Incompatible types", "code": "assignment"}\n'
)

MYPY_MULTIPLE_FILES = (
    '{"file": "src/a.py", "line": 1, "column": 0, "severity": "error", "message": "e1", "code": "attr-defined"}\n'
    '{"file": "src/a.py", "line": 5, "column": 0, "severity": "error", "message": "e2", "code": "call-overload"}\n'
    '{"file": "src/b.py", "line": 3, "column": 0, "severity": "error", "message": "e3", "code": "assignment"}\n'
    '{"file": "src/b.py", "line": 7, "column": 0, "severity": "note", "message": "note1", "code": "note"}\n'
)


# ---------------------------------------------------------------------------
# Adapter attribute tests
# ---------------------------------------------------------------------------


class TestAdapterAttributes:
    def test_name(self):
        adapter = TypeSafetyAdapter()
        assert adapter.name == "type_safety"

    def test_supported_languages(self):
        adapter = TypeSafetyAdapter()
        assert adapter.supported_languages == ["python"]

    def test_default_options(self):
        adapter = TypeSafetyAdapter()
        assert adapter.tool == "pyright"
        assert adapter.extra_args == []
        assert adapter.timeout == 300

    def test_custom_options(self):
        adapter = TypeSafetyAdapter(tool="mypy", extra_args=["--strict"], timeout=600)
        assert adapter.tool == "mypy"
        assert adapter.extra_args == ["--strict"]
        assert adapter.timeout == 600


# ---------------------------------------------------------------------------
# parse_pyright_json tests
# ---------------------------------------------------------------------------


class TestParsePyrightJson:
    def test_empty_output(self):
        summary = parse_pyright_json(PYRIGHT_EMPTY)
        assert summary.total_errors == 0
        assert summary.total_warnings == 0
        assert summary.total_files_checked == 5
        assert summary.files_with_errors == 0
        assert summary.file_results == {}
        assert summary.tool == "pyright"

    def test_single_error(self):
        summary = parse_pyright_json(PYRIGHT_SINGLE_ERROR)
        assert summary.total_errors == 1
        assert summary.files_with_errors == 1
        assert "/project/src/foo.py" in summary.file_results
        fr = summary.file_results["/project/src/foo.py"]
        assert fr.error_count == 1
        assert fr.warning_count == 0
        assert len(fr.diagnostics) == 1
        assert fr.diagnostics[0].rule == "reportAssignmentType"
        assert fr.diagnostics[0].line == 10

    def test_multiple_files(self):
        summary = parse_pyright_json(PYRIGHT_MULTIPLE_FILES)
        assert summary.total_errors == 3
        assert summary.files_with_errors == 2
        assert summary.file_results["/project/src/a.py"].error_count == 2
        assert summary.file_results["/project/src/b.py"].error_count == 1

    def test_mixed_severities(self):
        summary = parse_pyright_json(PYRIGHT_MIXED_SEVERITIES)
        assert summary.total_errors == 1
        assert summary.total_warnings == 1
        fr = summary.file_results["/project/src/c.py"]
        assert fr.error_count == 1
        assert fr.warning_count == 1
        assert fr.info_count == 1

    def test_missing_fields_handled(self):
        raw = {
            "generalDiagnostics": [
                {"file": "x.py", "severity": "error"},
            ],
        }
        summary = parse_pyright_json(raw)
        assert summary.total_errors == 1
        d = summary.file_results["x.py"].diagnostics[0]
        assert d.line == 0
        assert d.column == 0
        assert d.message == ""
        assert d.rule == ""


# ---------------------------------------------------------------------------
# parse_mypy_json tests
# ---------------------------------------------------------------------------


class TestParseMypyJson:
    def test_empty_output(self):
        summary = parse_mypy_json("")
        assert summary.total_errors == 0
        assert summary.file_results == {}
        assert summary.tool == "mypy"

    def test_single_error(self):
        summary = parse_mypy_json(MYPY_SINGLE_ERROR)
        assert summary.total_errors == 1
        assert "src/foo.py" in summary.file_results
        fr = summary.file_results["src/foo.py"]
        assert fr.error_count == 1
        assert fr.diagnostics[0].rule == "assignment"

    def test_multiple_files(self):
        summary = parse_mypy_json(MYPY_MULTIPLE_FILES)
        assert summary.total_errors == 3
        assert summary.files_with_errors == 2
        assert summary.file_results["src/a.py"].error_count == 2
        assert summary.file_results["src/b.py"].error_count == 1

    def test_notes_counted_as_warnings(self):
        summary = parse_mypy_json(MYPY_MULTIPLE_FILES)
        assert summary.file_results["src/b.py"].warning_count == 1

    def test_invalid_json_lines_skipped(self):
        output = 'not json\n{"file": "x.py", "severity": "error", "message": "m", "code": "c", "line": 1, "column": 0}\n'
        summary = parse_mypy_json(output)
        assert summary.total_errors == 1


# ---------------------------------------------------------------------------
# build_metric_result tests
# ---------------------------------------------------------------------------


class TestBuildMetricResult:
    def test_direction_is_minimize(self):
        summary = parse_pyright_json(PYRIGHT_SINGLE_ERROR)
        result = build_metric_result(summary)
        assert result.direction is Direction.MINIMIZE

    def test_metric_name_and_unit(self):
        summary = parse_pyright_json(PYRIGHT_SINGLE_ERROR)
        result = build_metric_result(summary)
        assert result.metric_name == "type_error_count"
        assert result.unit == "count"

    def test_breakdown_maps_file_to_error_count(self):
        summary = parse_pyright_json(PYRIGHT_MULTIPLE_FILES)
        result = build_metric_result(summary)
        assert result.value == 3.0
        assert result.breakdown["/project/src/a.py"] == 2.0
        assert result.breakdown["/project/src/b.py"] == 1.0

    def test_zero_errors(self):
        summary = parse_pyright_json(PYRIGHT_EMPTY)
        result = build_metric_result(summary)
        assert result.value == 0.0
        assert result.breakdown == {}

    def test_tool_name_preserved(self):
        summary = parse_pyright_json(PYRIGHT_SINGLE_ERROR)
        result = build_metric_result(summary)
        assert result.tool == "pyright"

        summary_mypy = parse_mypy_json(MYPY_SINGLE_ERROR)
        result_mypy = build_metric_result(summary_mypy)
        assert result_mypy.tool == "mypy"


# ---------------------------------------------------------------------------
# normalize_paths tests
# ---------------------------------------------------------------------------


class TestNormalizePaths:
    def test_absolute_to_relative(self):
        summary = parse_pyright_json(PYRIGHT_SINGLE_ERROR)
        normalized = normalize_paths(summary, "/project/src")
        assert "foo.py" in normalized.file_results
        assert normalized.file_results["foo.py"].file_path == "foo.py"

    def test_paths_outside_base_unchanged(self):
        summary = parse_pyright_json(PYRIGHT_SINGLE_ERROR)
        normalized = normalize_paths(summary, "/other/base")
        # Path can't be made relative, so it stays as-is
        assert any("foo.py" in k for k in normalized.file_results)


# ---------------------------------------------------------------------------
# Build command tests
# ---------------------------------------------------------------------------


class TestBuildCommand:
    def test_pyright_default(self):
        adapter = TypeSafetyAdapter()
        cmd = adapter._build_command("/some/path")
        assert cmd[0] == "pyright"
        assert "--outputjson" in cmd
        assert "--pythonpath" in cmd
        assert cmd[-1] == "/some/path"

    def test_pyright_extra_args(self):
        adapter = TypeSafetyAdapter(extra_args=["--threads", "4"])
        cmd = adapter._build_command("/path")
        assert "--threads" in cmd
        assert "4" in cmd

    def test_mypy_default(self):
        adapter = TypeSafetyAdapter(tool="mypy")
        cmd = adapter._build_command("/some/path")
        assert cmd[0] == "mypy"
        assert "--output=json" in cmd
        assert "--no-error-summary" in cmd
        assert cmd[-1] == "/some/path"

    def test_mypy_extra_args(self):
        adapter = TypeSafetyAdapter(tool="mypy", extra_args=["--strict"])
        cmd = adapter._build_command("/path")
        assert "--strict" in cmd


# ---------------------------------------------------------------------------
# identify_targets tests
# ---------------------------------------------------------------------------


class TestIdentifyTargets:
    def test_returns_worst_files_first(self):
        adapter = TypeSafetyAdapter()
        result = MetricResult(
            metric_name="type_error_count",
            value=10.0,
            unit="count",
            direction=Direction.MINIMIZE,
            breakdown={"a.py": 2.0, "b.py": 5.0, "c.py": 3.0},
        )
        targets = adapter.identify_targets(result, n=2)
        assert targets == ["b.py", "c.py"]

    def test_returns_all_when_n_exceeds(self):
        adapter = TypeSafetyAdapter()
        result = MetricResult(
            metric_name="type_error_count",
            value=3.0,
            unit="count",
            direction=Direction.MINIMIZE,
            breakdown={"a.py": 1.0, "b.py": 2.0},
        )
        targets = adapter.identify_targets(result, n=100)
        assert len(targets) == 2

    def test_empty_breakdown(self):
        adapter = TypeSafetyAdapter()
        result = MetricResult(
            metric_name="type_error_count",
            value=0.0,
            unit="count",
            direction=Direction.MINIMIZE,
        )
        assert adapter.identify_targets(result, n=5) == []


# ---------------------------------------------------------------------------
# Prerequisites tests
# ---------------------------------------------------------------------------


class TestPrerequisites:
    def test_pyright_available(self):
        adapter = TypeSafetyAdapter()
        with patch.object(adapter, "check_tool_available", return_value=True):
            assert adapter.check_prerequisites("/any") is True

    def test_pyright_not_available(self):
        adapter = TypeSafetyAdapter()
        with patch.object(adapter, "check_tool_available", return_value=False):
            assert adapter.check_prerequisites("/any") is False

    def test_mypy_mode_checks_mypy(self):
        adapter = TypeSafetyAdapter(tool="mypy")
        with patch.object(adapter, "check_tool_available", return_value=True) as mock:
            adapter.check_prerequisites("/any")
            mock.assert_called_once_with("mypy")


# ---------------------------------------------------------------------------
# Measure integration tests (mocked subprocess)
# ---------------------------------------------------------------------------


class TestMeasure:
    def _mock_run(self, stdout, returncode=0, stderr=""):
        """Create a mock subprocess.CompletedProcess."""
        from unittest.mock import MagicMock

        result = MagicMock()
        result.stdout = stdout
        result.stderr = stderr
        result.returncode = returncode
        return result

    def test_measure_pyright_success(self):
        adapter = TypeSafetyAdapter()
        with patch("autoforge_type_safety._adapter.subprocess.run") as mock_run:
            mock_run.return_value = self._mock_run(
                stdout=json.dumps(PYRIGHT_MULTIPLE_FILES), returncode=1
            )
            result = adapter.measure("/project", "/project/src")
            assert result.metric_name == "type_error_count"
            assert result.value == 3.0
            assert result.direction is Direction.MINIMIZE
            assert result.tool == "pyright"

    def test_measure_pyright_no_errors(self):
        adapter = TypeSafetyAdapter()
        with patch("autoforge_type_safety._adapter.subprocess.run") as mock_run:
            mock_run.return_value = self._mock_run(
                stdout=json.dumps(PYRIGHT_EMPTY), returncode=0
            )
            result = adapter.measure("/project", "/project/src")
            assert result.value == 0.0

    def test_measure_pyright_crash_raises(self):
        adapter = TypeSafetyAdapter()
        with patch("autoforge_type_safety._adapter.subprocess.run") as mock_run:
            mock_run.return_value = self._mock_run(
                stdout="", returncode=2, stderr="crash"
            )
            with pytest.raises(RuntimeError, match="crashed"):
                adapter.measure("/project", "/project/src")

    def test_measure_pyright_no_output_raises(self):
        adapter = TypeSafetyAdapter()
        with patch("autoforge_type_safety._adapter.subprocess.run") as mock_run:
            mock_run.return_value = self._mock_run(stdout="", returncode=0)
            with pytest.raises(RuntimeError, match="no output"):
                adapter.measure("/project", "/project/src")

    def test_measure_mypy_success(self):
        adapter = TypeSafetyAdapter(tool="mypy")
        with patch("autoforge_type_safety._adapter.subprocess.run") as mock_run:
            mock_run.return_value = self._mock_run(
                stdout=MYPY_MULTIPLE_FILES, returncode=1
            )
            result = adapter.measure("/project", "/project/src")
            assert result.value == 3.0
            assert result.tool == "mypy"

    def test_measure_mypy_fatal_raises(self):
        adapter = TypeSafetyAdapter(tool="mypy")
        with patch("autoforge_type_safety._adapter.subprocess.run") as mock_run:
            mock_run.return_value = self._mock_run(
                stdout="", returncode=2, stderr="fatal"
            )
            with pytest.raises(RuntimeError, match="fatal"):
                adapter.measure("/project", "/project/src")

    def test_measure_timeout_raises(self):
        import subprocess as sp

        adapter = TypeSafetyAdapter(timeout=1)
        with patch("autoforge_type_safety._adapter.subprocess.run") as mock_run:
            mock_run.side_effect = sp.TimeoutExpired(cmd="pyright", timeout=1)
            with pytest.raises(RuntimeError, match="timed out"):
                adapter.measure("/project", "/project/src")

    def test_measure_caches_detailed_results(self):
        adapter = TypeSafetyAdapter()
        with patch("autoforge_type_safety._adapter.subprocess.run") as mock_run:
            mock_run.return_value = self._mock_run(
                stdout=json.dumps(PYRIGHT_SINGLE_ERROR), returncode=1
            )
            adapter.measure("/project", "/project/src")
            assert adapter._detailed_results is not None
            assert adapter._detailed_results.total_errors == 1
