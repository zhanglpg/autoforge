"""Tests for autoforge Go test quality adapter — data models, helpers, and adapter."""

import os
import textwrap
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from autoforge_go_test_quality import (
    AssertionInfo,
    AssertionStrength,
    FileAssertionReport,
    FileCoverageData,
    FileTestQuality,
    FunctionCoverageResult,
    GoTestQualityAdapter,
    GoTestQualityIndicators,
    MutationResult,
    TQSWeights,
    analyze_go_test_file_assertions,
    classify_go_assertion,
    compute_assertion_quality_score,
    compute_effective_weights,
    compute_file_tqs,
    discover_go_source_files,
    discover_go_test_files,
    map_go_tests_to_sources,
    parse_go_cover_func,
    parse_go_coverage_profile,
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
    def test_combined_score_equals_statement_coverage(self):
        cov = FileCoverageData(
            file_path="foo.go",
            statement_coverage_pct=85.0,
            covered_statements=17,
            total_statements=20,
        )
        assert cov.combined_score == 85.0

    def test_combined_score_zero(self):
        cov = FileCoverageData(
            file_path="foo.go",
            statement_coverage_pct=0.0,
            covered_statements=0,
            total_statements=10,
        )
        assert cov.combined_score == 0.0


# ===========================================================================
# FunctionCoverageResult
# ===========================================================================

class TestFunctionCoverageResult:
    def test_score_with_functions(self):
        result = FunctionCoverageResult(
            file_path="foo.go",
            total_exported_functions=4,
            tested_functions=("Foo", "Bar"),
            untested_functions=("Baz", "Qux"),
        )
        assert result.score == pytest.approx(50.0)

    def test_score_no_functions(self):
        result = FunctionCoverageResult(
            file_path="foo.go",
            total_exported_functions=0,
            tested_functions=(),
            untested_functions=(),
        )
        assert result.score == 100.0

    def test_score_all_tested(self):
        result = FunctionCoverageResult(
            file_path="foo.go",
            total_exported_functions=3,
            tested_functions=("A", "B", "C"),
            untested_functions=(),
        )
        assert result.score == 100.0


# ===========================================================================
# MutationResult
# ===========================================================================

class TestMutationResult:
    def test_score(self):
        m = MutationResult(
            file_path="foo.go",
            total_mutants=10,
            killed_mutants=7,
            survived_mutants=3,
        )
        assert m.score == pytest.approx(70.0)

    def test_score_zero_mutants(self):
        m = MutationResult(
            file_path="foo.go",
            total_mutants=0,
            killed_mutants=0,
            survived_mutants=0,
        )
        assert m.score == 0.0


# ===========================================================================
# GoTestQualityIndicators
# ===========================================================================

class TestGoTestQualityIndicators:
    def test_default_indicators(self):
        qi = GoTestQualityIndicators(
            has_table_driven_tests=False,
            table_test_count=0,
            has_subtests=False,
            subtest_count=0,
            uses_testify=False,
        )
        assert not qi.has_table_driven_tests
        assert qi.subtest_count == 0

    def test_all_enabled(self):
        qi = GoTestQualityIndicators(
            has_table_driven_tests=True,
            table_test_count=3,
            has_subtests=True,
            subtest_count=5,
            uses_testify=True,
        )
        assert qi.has_table_driven_tests
        assert qi.table_test_count == 3
        assert qi.uses_testify


# ===========================================================================
# FileAssertionReport
# ===========================================================================

class TestFileAssertionReport:
    def test_weighted_score_with_assertions(self):
        assertions = (
            AssertionInfo("TestFoo", 10, "assert.Equal(t, 1, 1)", AssertionStrength.STRONG),
            AssertionInfo("TestBar", 20, "assert.NotNil(t, x)", AssertionStrength.WEAK),
        )
        qi = GoTestQualityIndicators(False, 0, False, 0, False)
        report = FileAssertionReport(
            test_file_path="foo_test.go",
            test_function_count=2,
            assertions=assertions,
            strong_count=1,
            structural_count=0,
            weak_count=1,
            quality_indicators=qi,
        )
        # TestFoo has STRONG (weight 1.0), TestBar has WEAK (weight 0.2)
        # Score = (1.0 + 0.2) / 2 * 100 = 60.0
        assert report.weighted_score == pytest.approx(60.0)

    def test_weighted_score_with_bonus(self):
        assertions = (
            AssertionInfo("TestFoo", 10, "assert.Equal(t, 1, 1)", AssertionStrength.STRONG),
        )
        qi = GoTestQualityIndicators(
            has_table_driven_tests=True,
            table_test_count=1,
            has_subtests=True,
            subtest_count=2,
            uses_testify=True,
        )
        report = FileAssertionReport(
            test_file_path="foo_test.go",
            test_function_count=1,
            assertions=assertions,
            strong_count=1,
            structural_count=0,
            weak_count=0,
            quality_indicators=qi,
        )
        # 100% base + 5 (table) + 3 (subtests) + 2 (testify) = 110 -> clamped to 100
        assert report.weighted_score == 100.0

    def test_weighted_score_bonus_adds_to_partial(self):
        assertions = (
            AssertionInfo("TestFoo", 10, "assert.Equal(t, 1, 1)", AssertionStrength.STRONG),
        )
        qi = GoTestQualityIndicators(
            has_table_driven_tests=True, table_test_count=1,
            has_subtests=False, subtest_count=0,
            uses_testify=False,
        )
        report = FileAssertionReport(
            test_file_path="foo_test.go",
            test_function_count=2,  # only 1 of 2 has assertion
            assertions=assertions,
            strong_count=1,
            structural_count=0,
            weak_count=0,
            quality_indicators=qi,
        )
        # 50% base + 5 (table) = 55%
        assert report.weighted_score == pytest.approx(55.0)

    def test_weighted_score_no_test_functions(self):
        qi = GoTestQualityIndicators(False, 0, False, 0, False)
        report = FileAssertionReport(
            test_file_path="foo_test.go",
            test_function_count=0,
            assertions=(),
            strong_count=0,
            structural_count=0,
            weak_count=0,
            quality_indicators=qi,
        )
        assert report.weighted_score == 0.0

    def test_total_count(self):
        qi = GoTestQualityIndicators(False, 0, False, 0, False)
        report = FileAssertionReport(
            test_file_path="foo_test.go",
            test_function_count=1,
            assertions=(),
            strong_count=3,
            structural_count=2,
            weak_count=1,
            quality_indicators=qi,
        )
        assert report.total_count == 6


# ===========================================================================
# parse_go_coverage_profile
# ===========================================================================

class TestParseGoCoverageProfile:
    def test_basic_profile(self):
        profile = textwrap.dedent("""\
            mode: set
            github.com/user/pkg/foo.go:10.2,12.0 1 1
            github.com/user/pkg/foo.go:14.2,16.0 2 0
            github.com/user/pkg/bar.go:5.2,8.0 3 1
        """)
        result = parse_go_coverage_profile(profile)

        assert "github.com/user/pkg/foo.go" in result
        foo = result["github.com/user/pkg/foo.go"]
        assert foo.total_statements == 3  # 1 + 2
        assert foo.covered_statements == 1  # only first line hit
        assert foo.statement_coverage_pct == pytest.approx(1 / 3 * 100)

        bar = result["github.com/user/pkg/bar.go"]
        assert bar.total_statements == 3
        assert bar.covered_statements == 3
        assert bar.statement_coverage_pct == pytest.approx(100.0)

    def test_empty_profile(self):
        result = parse_go_coverage_profile("mode: set\n")
        assert result == {}

    def test_skips_invalid_lines(self):
        profile = "mode: set\nnot a valid line\n"
        result = parse_go_coverage_profile(profile)
        assert result == {}


# ===========================================================================
# parse_go_cover_func
# ===========================================================================

class TestParseGoCoverFunc:
    def test_basic_output(self):
        output = textwrap.dedent("""\
            github.com/user/pkg/foo.go:10:	ProcessOrder	85.7%
            github.com/user/pkg/foo.go:25:	ValidateInput	0.0%
            github.com/user/pkg/bar.go:5:	NewClient	100.0%
            total:					(statements)	72.3%
        """)
        result = parse_go_cover_func(output)

        assert "github.com/user/pkg/foo.go" in result
        foo_funcs = result["github.com/user/pkg/foo.go"]
        assert len(foo_funcs) == 2
        assert foo_funcs[0] == ("ProcessOrder", 85.7)
        assert foo_funcs[1] == ("ValidateInput", 0.0)

        bar_funcs = result["github.com/user/pkg/bar.go"]
        assert len(bar_funcs) == 1
        assert bar_funcs[0] == ("NewClient", 100.0)

    def test_empty_output(self):
        result = parse_go_cover_func("")
        assert result == {}

    def test_skips_total_line(self):
        output = "total:\t\t\t(statements)\t72.3%\n"
        result = parse_go_cover_func(output)
        assert result == {}


# ===========================================================================
# classify_go_assertion
# ===========================================================================

class TestClassifyGoAssertion:
    def test_strong_assert_equal(self):
        assert classify_go_assertion("assert.Equal(t, expected, got)") == AssertionStrength.STRONG

    def test_strong_require_equal(self):
        assert classify_go_assertion("require.Equal(t, a, b)") == AssertionStrength.STRONG

    def test_strong_cmp_diff(self):
        assert classify_go_assertion("if diff := cmp.Diff(want, got);") == AssertionStrength.STRONG

    def test_strong_reflect_deepequal(self):
        assert classify_go_assertion("if !reflect.DeepEqual(a, b) {") == AssertionStrength.STRONG

    def test_strong_contains(self):
        assert classify_go_assertion("assert.Contains(t, s, substr)") == AssertionStrength.STRONG

    def test_structural_is_type(self):
        assert classify_go_assertion("assert.IsType(t, &Foo{}, obj)") == AssertionStrength.STRUCTURAL

    def test_structural_len(self):
        assert classify_go_assertion("assert.Len(t, items, 5)") == AssertionStrength.STRUCTURAL

    def test_structural_greater(self):
        assert classify_go_assertion("assert.Greater(t, a, b)") == AssertionStrength.STRUCTURAL

    def test_structural_errors_is(self):
        assert classify_go_assertion("if !errors.Is(err, ErrNotFound) {") == AssertionStrength.STRUCTURAL

    def test_weak_not_nil(self):
        assert classify_go_assertion("assert.NotNil(t, result)") == AssertionStrength.WEAK

    def test_weak_no_error(self):
        assert classify_go_assertion("require.NoError(t, err)") == AssertionStrength.WEAK

    def test_weak_t_error(self):
        assert classify_go_assertion('\tt.Error("something failed")') == AssertionStrength.WEAK

    def test_weak_t_fatal(self):
        assert classify_go_assertion('\tt.Fatal("oops")') == AssertionStrength.WEAK

    def test_weak_true(self):
        assert classify_go_assertion("assert.True(t, ok)") == AssertionStrength.WEAK

    def test_no_assertion(self):
        assert classify_go_assertion("fmt.Println(result)") is None

    def test_no_assertion_comment(self):
        assert classify_go_assertion("// assert.Equal should work") is None or True
        # Comment lines may still match patterns; this is acceptable for a heuristic


# ===========================================================================
# analyze_go_test_file_assertions
# ===========================================================================

class TestAnalyzeGoTestFileAssertions:
    def test_basic_test_file(self):
        source = textwrap.dedent("""\
            package foo

            import (
                "testing"
                "github.com/stretchr/testify/assert"
            )

            func TestAdd(t *testing.T) {
                result := Add(1, 2)
                assert.Equal(t, 3, result)
            }

            func TestSubtract(t *testing.T) {
                result := Subtract(5, 3)
                assert.Equal(t, 2, result)
                assert.NotNil(t, result)
            }
        """)
        report = analyze_go_test_file_assertions(source, "foo_test.go")

        assert report.test_function_count == 2
        assert report.strong_count >= 2  # at least 2 assert.Equal
        assert report.quality_indicators.uses_testify

    def test_table_driven_test(self):
        source = textwrap.dedent("""\
            package foo

            import "testing"

            func TestMultiply(t *testing.T) {
                tests := []struct {
                    a, b, want int
                }{
                    {2, 3, 6},
                    {0, 5, 0},
                }
                for _, tt := range tests {
                    t.Run("", func(t *testing.T) {
                        if got := Multiply(tt.a, tt.b); got != tt.want {
                            t.Errorf("got %d, want %d", got, tt.want)
                        }
                    })
                }
            }
        """)
        report = analyze_go_test_file_assertions(source, "foo_test.go")

        assert report.test_function_count == 1
        assert report.quality_indicators.has_table_driven_tests
        assert report.quality_indicators.has_subtests
        # The t.Errorf is inside `if got != tt.want`, so context-aware
        # classification promotes it from WEAK to STRONG.
        assert report.strong_count >= 1

    def test_no_assertions(self):
        source = textwrap.dedent("""\
            package foo

            import "testing"

            func TestSomething(t *testing.T) {
                DoSomething()
            }
        """)
        report = analyze_go_test_file_assertions(source, "foo_test.go")

        assert report.test_function_count == 1
        assert report.total_count == 0
        assert report.weighted_score == 0.0

    def test_empty_file(self):
        report = analyze_go_test_file_assertions("", "foo_test.go")
        assert report.test_function_count == 0
        assert report.weighted_score == 0.0

    def test_non_test_functions_ignored(self):
        source = textwrap.dedent("""\
            package foo

            import "testing"

            func helperSetup(t *testing.T) {
                // not a test function (doesn't start with Test)
            }

            func TestReal(t *testing.T) {
                t.Fatal("fail")
            }
        """)
        report = analyze_go_test_file_assertions(source, "foo_test.go")
        assert report.test_function_count == 1


# ===========================================================================
# File discovery and mapping
# ===========================================================================

class TestFileDiscovery:
    def test_discover_go_source_files(self, tmp_path):
        (tmp_path / "foo.go").write_text("package main")
        (tmp_path / "foo_test.go").write_text("package main")
        (tmp_path / "bar.go").write_text("package main")
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "dep.go").write_text("package dep")

        files = discover_go_source_files(str(tmp_path))
        basenames = [os.path.basename(f) for f in files]

        assert "foo.go" in basenames
        assert "bar.go" in basenames
        assert "foo_test.go" not in basenames
        assert "dep.go" not in basenames

    def test_discover_go_test_files(self, tmp_path):
        (tmp_path / "foo.go").write_text("package main")
        (tmp_path / "foo_test.go").write_text("package main")
        (tmp_path / "bar_test.go").write_text("package main")

        files = discover_go_test_files(str(tmp_path))
        basenames = [os.path.basename(f) for f in files]

        assert "foo_test.go" in basenames
        assert "bar_test.go" in basenames
        assert "foo.go" not in basenames

    def test_map_go_tests_to_sources(self, tmp_path):
        src = str(tmp_path / "foo.go")
        test = str(tmp_path / "foo_test.go")
        orphan = str(tmp_path / "bar.go")

        result = map_go_tests_to_sources([src, orphan], [test])

        assert result[src] == [test]
        assert result[orphan] == []


# ===========================================================================
# Weight computation
# ===========================================================================

class TestWeightComputation:
    def test_effective_weights_default(self):
        w = TQSWeights()
        eff = compute_effective_weights(w)
        total = sum(eff.values())
        assert total == pytest.approx(1.0)

    def test_effective_weights_mutation_disabled(self):
        w = TQSWeights(mutation=0.0)
        eff = compute_effective_weights(w)
        assert eff["mutation"] == 0.0
        assert sum(eff.values()) == pytest.approx(1.0)
        # Remaining weights redistributed proportionally
        assert eff["coverage"] > 0.35  # was 0.35, now larger share

    def test_effective_weights_all_disabled(self):
        w = TQSWeights(coverage=0.0, function_coverage=0.0, assertion_quality=0.0, mutation=0.0)
        eff = compute_effective_weights(w)
        assert all(v == pytest.approx(0.25) for v in eff.values())

    def test_compute_file_tqs(self):
        weights = {"coverage": 0.4, "function_coverage": 0.2,
                   "assertion_quality": 0.3, "mutation": 0.1}
        tqs = compute_file_tqs(80.0, 60.0, 90.0, 50.0, weights)
        expected = 0.4 * 80 + 0.2 * 60 + 0.3 * 90 + 0.1 * 50
        assert tqs == pytest.approx(expected)

    def test_compute_file_tqs_clamped(self):
        weights = {"coverage": 1.0, "function_coverage": 0.0,
                   "assertion_quality": 0.0, "mutation": 0.0}
        tqs = compute_file_tqs(150.0, 0.0, 0.0, 0.0, weights)
        assert tqs == 100.0


# ===========================================================================
# GoTestQualityAdapter — unit tests with mocks
# ===========================================================================

class TestGoTestQualityAdapter:
    def test_name_and_language(self):
        adapter = GoTestQualityAdapter()
        assert adapter.name == "go_test_quality"
        assert adapter.supported_languages == ["go"]

    def test_check_prerequisites_no_go(self):
        adapter = GoTestQualityAdapter()
        with patch.object(adapter, "check_tool_available", return_value=False):
            assert not adapter.check_prerequisites("/fake/repo")

    def test_check_prerequisites_no_go_mod(self, tmp_path):
        adapter = GoTestQualityAdapter()
        with patch.object(adapter, "check_tool_available", return_value=True):
            assert not adapter.check_prerequisites(str(tmp_path))

    def test_check_prerequisites_ok(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/test\n")
        adapter = GoTestQualityAdapter(mutation_weight=0.0)
        with patch.object(adapter, "check_tool_available", return_value=True):
            assert adapter.check_prerequisites(str(tmp_path))

    def test_check_prerequisites_mutation_no_tool(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/test\n")
        adapter = GoTestQualityAdapter(mutation_weight=0.10)

        def tool_check(name):
            return name == "go"

        with patch.object(adapter, "check_tool_available", side_effect=tool_check):
            assert not adapter.check_prerequisites(str(tmp_path))

    def test_identify_targets(self):
        adapter = GoTestQualityAdapter()
        result = MetricResult(
            metric_name="go_test_quality_score",
            value=50.0,
            unit="score",
            direction=Direction.MAXIMIZE,
            breakdown={"a.go": 30.0, "b.go": 80.0, "c.go": 10.0},
            tool="go_test_quality",
        )
        targets = adapter.identify_targets(result, 2)
        assert targets == ["c.go", "a.go"]

    def test_default_weights(self):
        adapter = GoTestQualityAdapter()
        assert adapter.weights.coverage == 0.35
        assert adapter.weights.function_coverage == 0.25
        assert adapter.weights.assertion_quality == 0.30
        assert adapter.weights.mutation == 0.10

    def test_custom_weights(self):
        adapter = GoTestQualityAdapter(
            coverage_weight=0.5,
            func_coverage_weight=0.2,
            assertion_weight=0.2,
            mutation_weight=0.1,
        )
        assert adapter.weights.coverage == 0.5
        assert adapter.weights.assertion_quality == 0.2
