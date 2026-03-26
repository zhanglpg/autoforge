"""Tests for autoforge.adapters.test_quality — data models, helpers, and adapter."""

import ast
import os
import textwrap
import tempfile
from pathlib import Path

import pytest

from autoforge.adapters.test_quality import (
    AssertionInfo,
    AssertionStrength,
    FileAssertionReport,
    FileCoverageData,
    FileTestQuality,
    FunctionCoverageResult,
    FunctionInfo,
    MutationResult,
    TQSWeights,
    TestQualityAdapter,
    analyze_test_file_assertions,
    classify_assertion,
    compute_assertion_quality_score,
    compute_coverage_score,
    compute_effective_weights,
    compute_file_tqs,
    discover_python_source_files,
    discover_test_files,
    extract_public_functions,
    find_uncovered_functions,
    map_tests_to_sources,
    parse_coverage_json,
)
from autoforge.models import Direction, MetricResult


# ===========================================================================
# AssertionStrength enum
# ===========================================================================

class TestAssertionStrength:
    def test_strong_weight(self):
        assert AssertionStrength.STRONG.weight == 1.0

    def test_structural_weight(self):
        assert AssertionStrength.STRUCTURAL.weight == 0.5

    def test_weak_weight(self):
        assert AssertionStrength.WEAK.weight == 0.2

    def test_all_values(self):
        assert set(AssertionStrength) == {
            AssertionStrength.STRONG,
            AssertionStrength.STRUCTURAL,
            AssertionStrength.WEAK,
        }


# ===========================================================================
# FileCoverageData
# ===========================================================================

class TestFileCoverageData:
    def test_combined_score(self):
        cov = FileCoverageData(
            file_path="a.py",
            line_coverage_pct=80.0,
            branch_coverage_pct=60.0,
            covered_lines=frozenset(),
            missing_lines=frozenset(),
            covered_branches=3,
            total_branches=5,
        )
        assert cov.combined_score == pytest.approx(72.0)  # 0.6*80 + 0.4*60

    def test_combined_score_zero(self):
        cov = FileCoverageData(
            file_path="b.py",
            line_coverage_pct=0.0,
            branch_coverage_pct=0.0,
            covered_lines=frozenset(),
            missing_lines=frozenset(),
            covered_branches=0,
            total_branches=0,
        )
        assert cov.combined_score == 0.0

    def test_combined_score_full(self):
        cov = FileCoverageData(
            file_path="c.py",
            line_coverage_pct=100.0,
            branch_coverage_pct=100.0,
            covered_lines=frozenset(range(1, 50)),
            missing_lines=frozenset(),
            covered_branches=10,
            total_branches=10,
        )
        assert cov.combined_score == 100.0

    def test_frozen(self):
        cov = FileCoverageData(
            file_path="a.py", line_coverage_pct=50.0, branch_coverage_pct=50.0,
            covered_lines=frozenset(), missing_lines=frozenset(),
            covered_branches=0, total_branches=0,
        )
        with pytest.raises(AttributeError):
            cov.line_coverage_pct = 99.0  # type: ignore[misc]


# ===========================================================================
# FunctionCoverageResult
# ===========================================================================

class TestFunctionCoverageResult:
    def test_score_all_tested(self):
        r = FunctionCoverageResult(
            file_path="a.py", total_public_functions=3,
            tested_functions=("f1", "f2", "f3"), untested_functions=(),
        )
        assert r.score == 100.0

    def test_score_none_tested(self):
        r = FunctionCoverageResult(
            file_path="a.py", total_public_functions=2,
            tested_functions=(), untested_functions=("f1", "f2"),
        )
        assert r.score == 0.0

    def test_score_no_functions(self):
        r = FunctionCoverageResult(
            file_path="a.py", total_public_functions=0,
            tested_functions=(), untested_functions=(),
        )
        assert r.score == 100.0

    def test_score_partial(self):
        r = FunctionCoverageResult(
            file_path="a.py", total_public_functions=4,
            tested_functions=("f1",), untested_functions=("f2", "f3", "f4"),
        )
        assert r.score == pytest.approx(25.0)


# ===========================================================================
# FileAssertionReport
# ===========================================================================

class TestFileAssertionReport:
    def test_total_count(self):
        r = FileAssertionReport(
            test_file_path="t.py", test_function_count=2,
            assertions=(), strong_count=3, structural_count=2, weak_count=1,
        )
        assert r.total_count == 6

    def test_weighted_score_no_tests(self):
        r = FileAssertionReport(
            test_file_path="t.py", test_function_count=0,
            assertions=(), strong_count=0, structural_count=0, weak_count=0,
        )
        assert r.weighted_score == 0.0

    def test_weighted_score_one_strong_per_test(self):
        a = AssertionInfo("test_x", 1, "assertEqual(a, b)", AssertionStrength.STRONG)
        r = FileAssertionReport(
            test_file_path="t.py", test_function_count=1,
            assertions=(a,), strong_count=1, structural_count=0, weak_count=0,
        )
        # density = 1.0/1 = 1.0, score = min(100, 1.0 * 33.3) = 33.3
        assert r.weighted_score == pytest.approx(33.3)

    def test_weighted_score_capped_at_100(self):
        asserts = tuple(
            AssertionInfo(f"test_{i}", i, "assertEqual(a, b)", AssertionStrength.STRONG)
            for i in range(5)
        )
        r = FileAssertionReport(
            test_file_path="t.py", test_function_count=1,
            assertions=asserts, strong_count=5, structural_count=0, weak_count=0,
        )
        # density = 5.0/1 = 5.0, score = min(100, 166.5) = 100
        assert r.weighted_score == 100.0


# ===========================================================================
# MutationResult
# ===========================================================================

class TestMutationResult:
    def test_score_all_killed(self):
        m = MutationResult("a.py", total_mutants=10, killed_mutants=10,
                           survived_mutants=0, timeout_mutants=0, error_mutants=0)
        assert m.score == 100.0

    def test_score_none_killed(self):
        m = MutationResult("a.py", total_mutants=10, killed_mutants=0,
                           survived_mutants=10, timeout_mutants=0, error_mutants=0)
        assert m.score == 0.0

    def test_score_no_mutants(self):
        m = MutationResult("a.py", total_mutants=0, killed_mutants=0,
                           survived_mutants=0, timeout_mutants=0, error_mutants=0)
        assert m.score == 0.0

    def test_score_partial(self):
        m = MutationResult("a.py", total_mutants=4, killed_mutants=3,
                           survived_mutants=1, timeout_mutants=0, error_mutants=0)
        assert m.score == pytest.approx(75.0)


# ===========================================================================
# TQSWeights
# ===========================================================================

class TestTQSWeights:
    def test_defaults(self):
        w = TQSWeights()
        assert w.coverage == 0.30
        assert w.function_coverage == 0.20
        assert w.assertion_quality == 0.30
        assert w.mutation == 0.20

    def test_effective_weights_all_active(self):
        w = TQSWeights()
        eff = w.effective_weights()
        assert eff["coverage"] == pytest.approx(0.30)
        assert eff["mutation"] == pytest.approx(0.20)
        assert sum(eff.values()) == pytest.approx(1.0)

    def test_effective_weights_mutation_disabled(self):
        w = TQSWeights(mutation=0.0)
        eff = w.effective_weights()
        assert eff["mutation"] == 0.0
        assert eff["coverage"] == pytest.approx(0.30 / 0.80)
        assert eff["function_coverage"] == pytest.approx(0.20 / 0.80)
        assert eff["assertion_quality"] == pytest.approx(0.30 / 0.80)
        assert sum(eff.values()) == pytest.approx(1.0)


# ===========================================================================
# compute_effective_weights
# ===========================================================================

class TestComputeEffectiveWeights:
    def test_all_zero_fallback(self):
        w = TQSWeights(coverage=0, function_coverage=0, assertion_quality=0, mutation=0)
        eff = compute_effective_weights(w)
        assert sum(eff.values()) == pytest.approx(1.0)
        assert all(v == pytest.approx(0.25) for v in eff.values())

    def test_single_active(self):
        w = TQSWeights(coverage=0.5, function_coverage=0, assertion_quality=0, mutation=0)
        eff = compute_effective_weights(w)
        assert eff["coverage"] == pytest.approx(1.0)
        assert eff["mutation"] == 0.0


# ===========================================================================
# compute_coverage_score
# ===========================================================================

class TestComputeCoverageScore:
    def test_basic(self):
        assert compute_coverage_score(80.0, 60.0) == pytest.approx(72.0)

    def test_zero(self):
        assert compute_coverage_score(0.0, 0.0) == 0.0

    def test_full(self):
        assert compute_coverage_score(100.0, 100.0) == 100.0


# ===========================================================================
# compute_file_tqs
# ===========================================================================

class TestComputeFileTqs:
    def test_basic(self):
        weights = {"coverage": 0.5, "function_coverage": 0.2,
                   "assertion_quality": 0.3, "mutation": 0.0}
        tqs = compute_file_tqs(80, 60, 40, 0, weights)
        # 0.5*80 + 0.2*60 + 0.3*40 + 0*0 = 40+12+12 = 64
        assert tqs == pytest.approx(64.0)

    def test_clamp_to_100(self):
        weights = {"coverage": 1.0, "function_coverage": 0,
                   "assertion_quality": 0, "mutation": 0}
        assert compute_file_tqs(150, 0, 0, 0, weights) == 100.0

    def test_clamp_to_0(self):
        weights = {"coverage": 1.0, "function_coverage": 0,
                   "assertion_quality": 0, "mutation": 0}
        assert compute_file_tqs(-10, 0, 0, 0, weights) == 0.0


# ===========================================================================
# extract_public_functions
# ===========================================================================

class TestExtractPublicFunctions:
    def test_simple_functions(self):
        code = textwrap.dedent("""\
            def hello():
                pass

            def _private():
                pass

            def world():
                return 42
        """)
        funcs = extract_public_functions(code, "mod.py")
        names = [f.name for f in funcs]
        assert "hello" in names
        assert "world" in names
        assert "_private" not in names

    def test_class_methods(self):
        code = textwrap.dedent("""\
            class Foo:
                def bar(self):
                    pass

                def _secret(self):
                    pass

                @property
                def value(self):
                    return 1
        """)
        funcs = extract_public_functions(code, "mod.py")
        names = [f.name for f in funcs]
        assert "Foo.bar" in names
        assert "Foo.value" in names
        assert "Foo._secret" not in names
        prop = [f for f in funcs if f.name == "Foo.value"][0]
        assert prop.is_property is True
        assert prop.is_method is True

    def test_syntax_error_returns_empty(self):
        funcs = extract_public_functions("def broken(:", "bad.py")
        assert funcs == []

    def test_line_numbers(self):
        code = textwrap.dedent("""\
            def first():
                pass

            def second():
                x = 1
                return x
        """)
        funcs = extract_public_functions(code, "mod.py")
        first = [f for f in funcs if f.name == "first"][0]
        assert first.start_line == 1
        second = [f for f in funcs if f.name == "second"][0]
        assert second.start_line == 4


# ===========================================================================
# find_uncovered_functions
# ===========================================================================

class TestFindUncoveredFunctions:
    def test_all_covered(self):
        funcs = [
            FunctionInfo("f1", "a.py", 1, 3, False, False),
            FunctionInfo("f2", "a.py", 5, 7, False, False),
        ]
        covered = frozenset({1, 2, 3, 5, 6, 7})
        result = find_uncovered_functions(funcs, covered)
        assert result.total_public_functions == 2
        assert len(result.tested_functions) == 2
        assert len(result.untested_functions) == 0
        assert result.score == 100.0

    def test_none_covered(self):
        funcs = [
            FunctionInfo("f1", "a.py", 1, 3, False, False),
        ]
        result = find_uncovered_functions(funcs, frozenset())
        assert len(result.untested_functions) == 1
        assert result.score == 0.0

    def test_partial_coverage(self):
        funcs = [
            FunctionInfo("f1", "a.py", 1, 3, False, False),
            FunctionInfo("f2", "a.py", 5, 7, False, False),
        ]
        covered = frozenset({1})  # only f1's first line
        result = find_uncovered_functions(funcs, covered)
        assert result.tested_functions == ("f1",)
        assert result.untested_functions == ("f2",)
        assert result.score == pytest.approx(50.0)

    def test_empty_functions(self):
        result = find_uncovered_functions([], frozenset())
        assert result.total_public_functions == 0
        assert result.score == 100.0


# ===========================================================================
# classify_assertion
# ===========================================================================

class TestClassifyAssertion:
    def _parse_stmt(self, code: str) -> ast.AST:
        tree = ast.parse(code)
        return tree.body[0]  # the statement

    def _parse_expr(self, code: str) -> ast.AST:
        tree = ast.parse(code)
        return tree.body[0].value  # the call expression

    def test_assert_equal_compare(self):
        node = self._parse_stmt("assert x == 42")
        assert classify_assertion(node) == AssertionStrength.STRONG

    def test_assert_not_equal_compare(self):
        node = self._parse_stmt("assert x != 0")
        assert classify_assertion(node) == AssertionStrength.STRONG

    def test_assert_in(self):
        node = self._parse_stmt("assert x in [1, 2, 3]")
        assert classify_assertion(node) == AssertionStrength.STRUCTURAL

    def test_assert_greater_than(self):
        node = self._parse_stmt("assert x > 0")
        assert classify_assertion(node) == AssertionStrength.STRUCTURAL

    def test_bare_assert(self):
        node = self._parse_stmt("assert x")
        assert classify_assertion(node) == AssertionStrength.WEAK

    def test_assert_true_call(self):
        node = self._parse_expr("self.assertTrue(result)")
        assert classify_assertion(node) == AssertionStrength.WEAK

    def test_assert_equal_call(self):
        node = self._parse_expr("self.assertEqual(a, b)")
        assert classify_assertion(node) == AssertionStrength.STRONG

    def test_assert_isinstance_call(self):
        node = self._parse_expr("self.assertIsInstance(x, int)")
        assert classify_assertion(node) == AssertionStrength.STRUCTURAL

    def test_pytest_raises(self):
        node = self._parse_expr("pytest.raises(ValueError)")
        assert classify_assertion(node) == AssertionStrength.STRONG


# ===========================================================================
# analyze_test_file_assertions
# ===========================================================================

class TestAnalyzeTestFileAssertions:
    def test_basic_test_file(self):
        code = textwrap.dedent("""\
            def test_add():
                result = add(1, 2)
                assert result == 3

            def test_sub():
                assert sub(5, 3) == 2
                assert sub(0, 0) == 0
        """)
        report = analyze_test_file_assertions(code, "test_math.py")
        assert report.test_function_count == 2
        assert report.strong_count == 3
        assert report.total_count == 3

    def test_no_tests(self):
        code = "x = 1\n"
        report = analyze_test_file_assertions(code, "test_empty.py")
        assert report.test_function_count == 0
        assert report.total_count == 0
        assert report.weighted_score == 0.0

    def test_mixed_assertions(self):
        code = textwrap.dedent("""\
            def test_mixed():
                assert result == 42
                assert result
                assert isinstance(result, int)
        """)
        report = analyze_test_file_assertions(code, "test_mix.py")
        assert report.test_function_count == 1
        # assert result == 42 → strong
        # assert result → weak
        # assert isinstance(result, int) → weak (bare assert with call)
        assert report.strong_count >= 1

    def test_syntax_error(self):
        report = analyze_test_file_assertions("def test_bad(:", "test_bad.py")
        assert report.test_function_count == 0
        assert report.total_count == 0

    def test_unittest_style(self):
        code = textwrap.dedent("""\
            import unittest

            class TestFoo(unittest.TestCase):
                def test_equal(self):
                    self.assertEqual(1, 1)

                def test_true(self):
                    self.assertTrue(True)
        """)
        report = analyze_test_file_assertions(code, "test_foo.py")
        assert report.test_function_count == 2
        assert report.strong_count >= 1
        assert report.weak_count >= 1


# ===========================================================================
# compute_assertion_quality_score
# ===========================================================================

class TestComputeAssertionQualityScore:
    def test_delegates_to_weighted_score(self):
        a = AssertionInfo("test_x", 1, "assertEqual(a, b)", AssertionStrength.STRONG)
        r = FileAssertionReport(
            test_file_path="t.py", test_function_count=1,
            assertions=(a,), strong_count=1, structural_count=0, weak_count=0,
        )
        assert compute_assertion_quality_score(r) == r.weighted_score


# ===========================================================================
# map_tests_to_sources
# ===========================================================================

class TestMapTestsToSources:
    def test_convention_mapping(self):
        sources = ["src/foo.py", "src/bar.py"]
        tests = ["tests/test_foo.py", "tests/test_bar.py"]
        mapping = map_tests_to_sources(sources, tests)
        assert mapping["src/foo.py"] == ["tests/test_foo.py"]
        assert mapping["src/bar.py"] == ["tests/test_bar.py"]

    def test_no_match(self):
        sources = ["src/baz.py"]
        tests = ["tests/test_foo.py"]
        mapping = map_tests_to_sources(sources, tests)
        assert mapping["src/baz.py"] == []

    def test_suffix_pattern(self):
        sources = ["src/utils.py"]
        tests = ["tests/utils_test.py"]
        mapping = map_tests_to_sources(sources, tests)
        assert mapping["src/utils.py"] == ["tests/utils_test.py"]

    def test_multiple_test_files(self):
        sources = ["src/core.py"]
        tests = ["tests/test_core.py", "tests/integration/test_core.py"]
        mapping = map_tests_to_sources(sources, tests)
        assert len(mapping["src/core.py"]) == 2


# ===========================================================================
# parse_coverage_json
# ===========================================================================

class TestParseCoverageJson:
    def test_basic_parse(self):
        data = {
            "files": {
                "src/foo.py": {
                    "summary": {
                        "percent_covered": 85.0,
                        "percent_covered_branches": 70.0,
                        "covered_branches": 7,
                        "num_branches": 10,
                    },
                    "executed_lines": [1, 2, 3, 5, 6],
                    "missing_lines": [4, 7],
                }
            }
        }
        result = parse_coverage_json(data)
        assert "src/foo.py" in result
        cov = result["src/foo.py"]
        assert cov.line_coverage_pct == 85.0
        assert cov.branch_coverage_pct == 70.0
        assert 3 in cov.covered_lines
        assert 4 in cov.missing_lines
        assert cov.covered_branches == 7
        assert cov.total_branches == 10

    def test_empty_files(self):
        result = parse_coverage_json({"files": {}})
        assert result == {}

    def test_missing_fields_default_to_zero(self):
        data = {"files": {"a.py": {"summary": {}, "executed_lines": [], "missing_lines": []}}}
        result = parse_coverage_json(data)
        cov = result["a.py"]
        assert cov.line_coverage_pct == 0.0
        assert cov.branch_coverage_pct == 0.0


# ===========================================================================
# File Discovery
# ===========================================================================

class TestDiscoverFiles:
    def test_discover_source_files(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src"
            src.mkdir()
            (src / "foo.py").write_text("x = 1\n")
            (src / "bar.py").write_text("y = 2\n")
            (src / "test_baz.py").write_text("z = 3\n")
            tests_dir = src / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_foo.py").write_text("")

            files = discover_python_source_files(str(src))
            basenames = [os.path.basename(f) for f in files]
            assert "foo.py" in basenames
            assert "bar.py" in basenames
            assert "test_baz.py" not in basenames
            assert "test_foo.py" not in basenames

    def test_discover_test_files(self):
        with tempfile.TemporaryDirectory() as d:
            tests_dir = Path(d) / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_a.py").write_text("")
            (tests_dir / "b_test.py").write_text("")
            (tests_dir / "helper.py").write_text("")

            files = discover_test_files(d, "tests/")
            basenames = [os.path.basename(f) for f in files]
            assert "test_a.py" in basenames
            assert "b_test.py" in basenames
            assert "helper.py" not in basenames

    def test_discover_test_files_missing_dir(self):
        with tempfile.TemporaryDirectory() as d:
            files = discover_test_files(d, "nonexistent/")
            assert files == []


# ===========================================================================
# TestQualityAdapter — attributes and construction
# ===========================================================================

class TestTestQualityAdapterAttributes:
    def test_name_and_languages(self):
        adapter = TestQualityAdapter()
        assert adapter.name == "test_quality"
        assert adapter.supported_languages == ["python"]

    def test_default_weights(self):
        adapter = TestQualityAdapter()
        assert adapter.weights.coverage == 0.30
        assert adapter.weights.function_coverage == 0.20
        assert adapter.weights.assertion_quality == 0.30
        assert adapter.weights.mutation == 0.20

    def test_custom_weights(self):
        adapter = TestQualityAdapter(
            coverage_weight=0.5, func_coverage_weight=0.3,
            assertion_weight=0.2, mutation_weight=0.0,
        )
        assert adapter.weights.coverage == 0.5
        assert adapter.weights.mutation == 0.0

    def test_default_options(self):
        adapter = TestQualityAdapter()
        assert adapter.test_command == "pytest"
        assert adapter.test_dir_pattern == "tests/"
        assert adapter.branch_coverage is True
        assert adapter.mutation_sample_size == 5
        assert adapter.coverage_timeout == 300
        assert adapter.mutation_timeout == 600


# ===========================================================================
# TestQualityAdapter — identify_targets
# ===========================================================================

class TestTestQualityAdapterIdentifyTargets:
    def test_returns_worst_first(self):
        adapter = TestQualityAdapter()
        result = MetricResult(
            metric_name="test_quality_score", value=50.0,
            unit="score", direction=Direction.MAXIMIZE,
            breakdown={"a.py": 90.0, "b.py": 20.0, "c.py": 55.0},
        )
        targets = adapter.identify_targets(result, n=2)
        assert targets == ["b.py", "c.py"]

    def test_empty_breakdown(self):
        adapter = TestQualityAdapter()
        result = MetricResult(
            metric_name="test_quality_score", value=0.0,
            unit="score", direction=Direction.MAXIMIZE,
        )
        assert adapter.identify_targets(result, n=5) == []

    def test_n_exceeds_files(self):
        adapter = TestQualityAdapter()
        result = MetricResult(
            metric_name="test_quality_score", value=50.0,
            unit="score", direction=Direction.MAXIMIZE,
            breakdown={"a.py": 30.0},
        )
        assert len(adapter.identify_targets(result, n=100)) == 1


# ===========================================================================
# TestQualityAdapter — _build_coverage_command
# ===========================================================================

class TestBuildCoverageCommand:
    def test_default_command(self):
        adapter = TestQualityAdapter()
        cmd = adapter._build_coverage_command("/some/path")
        cmd_str = " ".join(cmd)
        assert "--cov=/some/path" in cmd_str
        assert "--cov-report=json" in cmd_str
        assert "--cov-branch" in cmd_str

    def test_no_branch_coverage(self):
        adapter = TestQualityAdapter(branch_coverage=False)
        cmd = adapter._build_coverage_command("/path")
        assert "--cov-branch" not in cmd


# ===========================================================================
# TestQualityAdapter — protocol compliance
# ===========================================================================

class TestTestQualityAdapterProtocol:
    def test_has_required_attributes(self):
        adapter = TestQualityAdapter()
        assert hasattr(adapter, "name")
        assert hasattr(adapter, "supported_languages")
        assert callable(adapter.check_prerequisites)
        assert callable(adapter.measure)
        assert callable(adapter.identify_targets)


# ===========================================================================
# Registry integration
# ===========================================================================

class TestRegistryIntegration:
    def test_test_quality_registered(self):
        from autoforge.registry import get_adapter, list_adapters
        assert "test_quality" in list_adapters()

    def test_get_adapter_returns_instance(self):
        from autoforge.registry import get_adapter
        adapter = get_adapter("test_quality")
        assert isinstance(adapter, TestQualityAdapter)
        assert adapter.name == "test_quality"

    def test_get_adapter_with_kwargs(self):
        from autoforge.registry import get_adapter
        adapter = get_adapter("test_quality", mutation_weight=0.0)
        assert adapter.weights.mutation == 0.0
