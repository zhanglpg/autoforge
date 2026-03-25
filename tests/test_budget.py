"""Tests for autoforge.budget."""

import pytest

from autoforge.budget import BudgetExhausted, BudgetManager
from autoforge.models import BudgetConfig


class TestBudgetManager:
    def test_initial_state(self):
        bm = BudgetManager(BudgetConfig(max_iterations=5))
        assert bm.iterations_used == 0
        assert bm.tokens_used == 0
        assert bm.remaining_iterations() == 5

    def test_record_iteration(self):
        bm = BudgetManager(BudgetConfig(max_iterations=5))
        bm.record_iteration(tokens=1000, improvement_pct=5.0)
        assert bm.iterations_used == 1
        assert bm.tokens_used == 1000
        assert bm.remaining_iterations() == 4

    def test_check_budget_iterations(self):
        bm = BudgetManager(BudgetConfig(max_iterations=2))
        bm.record_iteration()
        bm.record_iteration()
        with pytest.raises(BudgetExhausted, match="Max iterations"):
            bm.check_budget()

    def test_check_budget_tokens(self):
        bm = BudgetManager(BudgetConfig(max_tokens=1000))
        bm.record_iteration(tokens=1500)
        with pytest.raises(BudgetExhausted, match="Token budget"):
            bm.check_budget()

    def test_stall_detection_no_stall(self):
        bm = BudgetManager(BudgetConfig(stall_patience=3, min_improvement_percent=0.5))
        bm.record_iteration(improvement_pct=5.0)
        bm.record_iteration(improvement_pct=3.0)
        bm.record_iteration(improvement_pct=2.0)
        assert not bm.check_stall()

    def test_stall_detection_stalled(self):
        bm = BudgetManager(BudgetConfig(stall_patience=3, min_improvement_percent=0.5))
        bm.record_iteration(improvement_pct=0.1)
        bm.record_iteration(improvement_pct=0.2)
        bm.record_iteration(improvement_pct=0.3)
        assert bm.check_stall()

    def test_stall_detection_not_enough_iterations(self):
        bm = BudgetManager(BudgetConfig(stall_patience=3, min_improvement_percent=0.5))
        bm.record_iteration(improvement_pct=0.1)
        bm.record_iteration(improvement_pct=0.1)
        assert not bm.check_stall()  # Only 2 iterations, need 3

    def test_summary(self):
        bm = BudgetManager(BudgetConfig(max_iterations=10, max_tokens=50000))
        bm.record_iteration(tokens=5000, improvement_pct=10.0)
        s = bm.summary()
        assert s["iterations"] == "1/10"
        assert s["tokens"] == "5000/50000"

    def test_remaining_tokens(self):
        bm = BudgetManager(BudgetConfig(max_tokens=10000))
        bm.record_iteration(tokens=3000)
        assert bm.remaining_tokens() == 7000
