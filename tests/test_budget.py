"""Tests for autoforge.budget — BudgetManager and BudgetExhausted."""

import time

import pytest

from autoforge.budget import BudgetExhausted, BudgetManager
from autoforge.models import BudgetConfig


class TestBudgetManagerInitialization:
    def test_fresh_state(self):
        bm = BudgetManager(BudgetConfig(max_iterations=5, max_tokens=10000))
        assert bm.iterations_used == 0
        assert bm.tokens_used == 0
        assert bm.remaining_iterations() == 5
        assert bm.remaining_tokens() == 10000
        assert bm.elapsed_seconds >= 0
        assert bm.elapsed_minutes >= 0


class TestBudgetManagerRecording:
    def test_record_single_iteration(self):
        bm = BudgetManager(BudgetConfig(max_iterations=5))
        bm.record_iteration(tokens=1000, improvement_pct=5.0)
        assert bm.iterations_used == 1
        assert bm.tokens_used == 1000
        assert bm.remaining_iterations() == 4

    def test_record_multiple_iterations(self):
        bm = BudgetManager(BudgetConfig(max_iterations=10, max_tokens=50000))
        bm.record_iteration(tokens=5000, improvement_pct=10.0)
        bm.record_iteration(tokens=3000, improvement_pct=5.0)
        bm.record_iteration(tokens=7000, improvement_pct=2.0)
        assert bm.iterations_used == 3
        assert bm.tokens_used == 15000
        assert bm.remaining_iterations() == 7
        assert bm.remaining_tokens() == 35000

    def test_record_no_tokens(self):
        bm = BudgetManager(BudgetConfig())
        bm.record_iteration(improvement_pct=1.0)
        assert bm.tokens_used == 0
        assert bm.iterations_used == 1


class TestBudgetChecks:
    def test_iteration_limit(self):
        bm = BudgetManager(BudgetConfig(max_iterations=2))
        bm.record_iteration()
        bm.check_budget()  # 1/2, still ok
        bm.record_iteration()
        with pytest.raises(BudgetExhausted, match="Max iterations"):
            bm.check_budget()

    def test_token_limit(self):
        bm = BudgetManager(BudgetConfig(max_tokens=1000))
        bm.record_iteration(tokens=1500)
        with pytest.raises(BudgetExhausted, match="Token budget"):
            bm.check_budget()

    def test_token_limit_exact(self):
        bm = BudgetManager(BudgetConfig(max_tokens=1000))
        bm.record_iteration(tokens=1000)
        with pytest.raises(BudgetExhausted, match="Token budget"):
            bm.check_budget()

    def test_wall_clock_limit(self):
        bm = BudgetManager(BudgetConfig(max_wall_clock_minutes=0))  # immediate
        with pytest.raises(BudgetExhausted, match="Wall-clock time"):
            bm.check_budget()

    def test_budget_ok_when_under_limits(self):
        bm = BudgetManager(BudgetConfig(
            max_iterations=10, max_tokens=100000, max_wall_clock_minutes=30
        ))
        bm.record_iteration(tokens=500)
        bm.check_budget()  # should not raise

    def test_budget_exhausted_has_reason(self):
        bm = BudgetManager(BudgetConfig(max_iterations=1))
        bm.record_iteration()
        with pytest.raises(BudgetExhausted) as exc_info:
            bm.check_budget()
        assert exc_info.value.reason == "Max iterations reached (1)"


class TestStallDetection:
    def test_no_stall_with_good_improvements(self):
        bm = BudgetManager(BudgetConfig(stall_patience=3, min_improvement_percent=0.5))
        bm.record_iteration(improvement_pct=5.0)
        bm.record_iteration(improvement_pct=3.0)
        bm.record_iteration(improvement_pct=2.0)
        assert not bm.check_stall()

    def test_stall_when_all_below_threshold(self):
        bm = BudgetManager(BudgetConfig(stall_patience=3, min_improvement_percent=0.5))
        bm.record_iteration(improvement_pct=0.1)
        bm.record_iteration(improvement_pct=0.2)
        bm.record_iteration(improvement_pct=0.3)
        assert bm.check_stall()

    def test_no_stall_insufficient_iterations(self):
        bm = BudgetManager(BudgetConfig(stall_patience=3, min_improvement_percent=0.5))
        bm.record_iteration(improvement_pct=0.1)
        bm.record_iteration(improvement_pct=0.1)
        assert not bm.check_stall()  # only 2 < patience of 3

    def test_stall_only_checks_recent_window(self):
        """Good early iterations shouldn't mask later stalls."""
        bm = BudgetManager(BudgetConfig(stall_patience=2, min_improvement_percent=1.0))
        bm.record_iteration(improvement_pct=10.0)  # good
        bm.record_iteration(improvement_pct=8.0)   # good
        bm.record_iteration(improvement_pct=0.1)   # stall
        bm.record_iteration(improvement_pct=0.2)   # stall
        assert bm.check_stall()

    def test_stall_with_zero_improvements(self):
        bm = BudgetManager(BudgetConfig(stall_patience=2, min_improvement_percent=0.5))
        bm.record_iteration(improvement_pct=0.0)
        bm.record_iteration(improvement_pct=0.0)
        assert bm.check_stall()

    def test_no_stall_with_negative_improvement(self):
        """Negative improvement (regression) still counts as 'change' above threshold."""
        bm = BudgetManager(BudgetConfig(stall_patience=2, min_improvement_percent=0.5))
        bm.record_iteration(improvement_pct=-5.0)  # abs(-5) > 0.5
        bm.record_iteration(improvement_pct=-3.0)
        assert not bm.check_stall()

    def test_patience_of_one(self):
        bm = BudgetManager(BudgetConfig(stall_patience=1, min_improvement_percent=1.0))
        bm.record_iteration(improvement_pct=0.5)
        assert bm.check_stall()


class TestBudgetSummary:
    def test_summary_structure(self):
        bm = BudgetManager(BudgetConfig(max_iterations=10, max_tokens=50000))
        bm.record_iteration(tokens=5000, improvement_pct=10.0)
        s = bm.summary()
        assert s["iterations"] == "1/10"
        assert s["tokens"] == "5000/50000"
        assert "wall_clock_minutes" in s
        assert isinstance(s["stall_detected"], bool)

    def test_remaining_at_zero(self):
        bm = BudgetManager(BudgetConfig(max_iterations=1, max_tokens=100))
        bm.record_iteration(tokens=200)
        assert bm.remaining_iterations() == 0
        assert bm.remaining_tokens() == 0  # clamped to 0, not negative


class TestBudgetElapsed:
    def test_elapsed_increases(self):
        bm = BudgetManager(BudgetConfig())
        t1 = bm.elapsed_seconds
        # Elapsed should be >= 0 and non-decreasing
        assert t1 >= 0
        t2 = bm.elapsed_seconds
        assert t2 >= t1
