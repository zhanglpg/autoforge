"""
Budget Manager for AutoForge.

Enforces hard limits on iterations, tokens, wall-clock time, and detects
improvement stalls to prevent runaway loops.
"""

from __future__ import annotations

import logging
import time

from autoforge.models import BudgetConfig

logger = logging.getLogger(__name__)


class BudgetExhausted(Exception):
    """Raised when any budget limit is exceeded."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class BudgetManager:
    """Tracks and enforces budget constraints for a workflow run."""

    def __init__(self, config: BudgetConfig):
        self.config = config
        self.iterations_used = 0
        self.tokens_used = 0
        self.start_time = time.monotonic()
        self._recent_improvements: list[float] = []

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.start_time

    @property
    def elapsed_minutes(self) -> float:
        return self.elapsed_seconds / 60.0

    def record_iteration(self, tokens: int = 0, improvement_pct: float = 0.0) -> None:
        """Record completion of one iteration."""
        self.iterations_used += 1
        self.tokens_used += tokens
        self._recent_improvements.append(improvement_pct)

    def check_budget(self) -> None:
        """Check all budget constraints. Raises BudgetExhausted if any exceeded."""
        if self.iterations_used >= self.config.max_iterations:
            raise BudgetExhausted(
                f"Max iterations reached ({self.config.max_iterations})"
            )

        if self.tokens_used >= self.config.max_tokens:
            raise BudgetExhausted(
                f"Token budget exhausted ({self.tokens_used}/{self.config.max_tokens})"
            )

        if self.elapsed_minutes >= self.config.max_wall_clock_minutes:
            raise BudgetExhausted(
                f"Wall-clock time exceeded ({self.elapsed_minutes:.1f}/"
                f"{self.config.max_wall_clock_minutes} min)"
            )

    def check_stall(self) -> bool:
        """Check if improvement has stalled. Returns True if stalled."""
        patience = self.config.stall_patience
        threshold = self.config.min_improvement_percent

        if len(self._recent_improvements) < patience:
            return False

        recent = self._recent_improvements[-patience:]
        stalled = all(abs(imp) < threshold for imp in recent)

        if stalled:
            logger.warning(
                "Improvement stall detected: last %d iterations showed "
                "< %.1f%% improvement each",
                patience,
                threshold,
            )

        return stalled

    def remaining_iterations(self) -> int:
        return max(0, self.config.max_iterations - self.iterations_used)

    def remaining_tokens(self) -> int:
        return max(0, self.config.max_tokens - self.tokens_used)

    def summary(self) -> dict:
        """Return a summary of budget usage."""
        return {
            "iterations": f"{self.iterations_used}/{self.config.max_iterations}",
            "tokens": f"{self.tokens_used}/{self.config.max_tokens}",
            "wall_clock_minutes": f"{self.elapsed_minutes:.1f}/{self.config.max_wall_clock_minutes}",
            "stall_detected": self.check_stall(),
        }
