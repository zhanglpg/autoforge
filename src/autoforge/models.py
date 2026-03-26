"""
Core data models for AutoForge.

Defines the standard interfaces for metrics, workflow configuration,
budget tracking, iteration state, and run reports. These are pure data
containers — presentation logic lives in reporting.py.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Direction — shared enum for metric optimization direction
# ---------------------------------------------------------------------------

class Direction(enum.Enum):
    """Whether a metric should be maximized or minimized."""
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"

    def is_improved(self, before: float, after: float) -> bool:
        """Check if 'after' is an improvement over 'before'."""
        if self is Direction.MINIMIZE:
            return after < before
        return after > before


# ---------------------------------------------------------------------------
# Metric Result — standard output from every metric adapter
# ---------------------------------------------------------------------------

@dataclass
class MetricResult:
    """Normalized result from a metric adapter measurement.

    This is the universal exchange format between adapters and the framework.
    Every adapter must produce MetricResult instances regardless of the
    underlying tool.
    """

    metric_name: str              # e.g., "net_complexity_score"
    value: float                  # e.g., 7.23
    unit: str                     # e.g., "score", "percent", "count"
    direction: Direction          # whether to maximize or minimize
    breakdown: dict[str, float] = field(default_factory=dict)  # per-file values
    tool: str = ""                # e.g., "complexity-accounting"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def improved_over(self, previous: MetricResult, threshold: float = 0.0) -> bool:
        """Check if this result is an improvement over a previous one.

        Args:
            previous: The prior measurement to compare against.
            threshold: Minimum delta to count as a real improvement.
        """
        if self.direction is Direction.MINIMIZE:
            return (previous.value - self.value) > threshold
        return (self.value - previous.value) > threshold

    def degraded_beyond(self, baseline: MetricResult, tolerance_percent: float) -> bool:
        """Check if this result has degraded beyond tolerance from baseline.

        Used by the regression guard to enforce constraint metrics.
        Returns False if tolerance_percent <= 0 (disabled).
        """
        if tolerance_percent <= 0:
            return False
        if baseline.value == 0:
            return self.value != 0
        change_pct = abs(self.value - baseline.value) / abs(baseline.value) * 100
        if self.direction is Direction.MINIMIZE:
            return self.value > baseline.value and change_pct > tolerance_percent
        return self.value < baseline.value and change_pct > tolerance_percent


# ---------------------------------------------------------------------------
# Metric Adapter Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class MetricAdapter(Protocol):
    """Interface that every metric adapter must implement.

    Adapters are thin wrappers that normalize tool output into MetricResult.
    They must not contain workflow logic — only measurement and targeting.
    """

    name: str
    supported_languages: list[str]

    def check_prerequisites(self, repo_path: str) -> bool:
        """Verify the underlying tool is installed and the repo is compatible."""
        ...

    def measure(self, repo_path: str, target_path: str) -> MetricResult:
        """Run the metric tool and return a normalized result."""
        ...

    def identify_targets(self, result: MetricResult, n: int) -> list[str]:
        """Return top-n file paths to target for improvement (worst first)."""
        ...


# ---------------------------------------------------------------------------
# Workflow Configuration — loaded from YAML
# ---------------------------------------------------------------------------

@dataclass
class MetricConstraint:
    """A constraint metric that must not degrade beyond tolerance."""
    name: str
    tolerance_percent: float
    direction: Direction


@dataclass
class BudgetConfig:
    """Hard limits for a workflow run."""
    max_iterations: int = 15
    max_tokens: int = 500_000
    max_wall_clock_minutes: int = 30
    stall_patience: int = 3
    min_improvement_percent: float = 0.5
    max_files_per_iteration: int = 5


@dataclass
class PrimaryMetricConfig:
    """Primary optimization target for a workflow."""
    name: str
    direction: Direction
    default_target: float = 0.0


@dataclass
class AgentConfig:
    """Agent configuration for a workflow."""
    skill: str = ""
    system_prompt_addendum: str = ""


@dataclass
class LanguageToolConfig:
    """Language-specific tool configuration for a workflow."""
    metric_tool: str = ""
    metric_command: str = ""
    metric_parser: str = ""


@dataclass
class WorkflowConfig:
    """Complete workflow configuration, loaded from YAML."""
    name: str
    version: str = "1.0"
    description: str = ""
    adapter: str = ""  # adapter name to use (e.g., "complexity")
    primary_metric: PrimaryMetricConfig = field(
        default_factory=lambda: PrimaryMetricConfig(name="", direction=Direction.MINIMIZE)
    )
    constraint_metrics: list[MetricConstraint] = field(default_factory=list)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    language_support: dict[str, LanguageToolConfig] = field(default_factory=dict)
    scope_priority: str = "worst_first"

    @staticmethod
    def from_dict(data: dict[str, Any]) -> WorkflowConfig:
        """Parse a workflow config from a dictionary (e.g., loaded from YAML).

        Raises ValueError if required fields are invalid.
        """
        def _parse_direction(raw: str, field_name: str) -> Direction:
            try:
                return Direction(raw)
            except ValueError:
                raise ValueError(
                    f"Invalid direction '{raw}' for {field_name}. "
                    f"Must be 'minimize' or 'maximize'."
                )

        primary = data.get("primary_metric", {})
        primary_cfg = PrimaryMetricConfig(
            name=primary.get("name", ""),
            direction=_parse_direction(
                primary.get("direction", "minimize"), "primary_metric.direction"
            ),
            default_target=primary.get("default_target", 0.0),
        )

        constraints = []
        for i, c in enumerate(data.get("constraint_metrics", [])):
            constraints.append(MetricConstraint(
                name=c.get("name", ""),
                tolerance_percent=c.get("tolerance_percent", 10.0),
                direction=_parse_direction(
                    c.get("direction", "minimize"),
                    f"constraint_metrics[{i}].direction",
                ),
            ))

        budget_data = data.get("budget", {})
        budget = BudgetConfig(
            max_iterations=budget_data.get("max_iterations", 15),
            max_tokens=budget_data.get("max_tokens", 500_000),
            max_wall_clock_minutes=budget_data.get("max_wall_clock_minutes", 30),
            stall_patience=budget_data.get("stall_patience", 3),
            min_improvement_percent=budget_data.get("min_improvement_percent", 0.5),
            max_files_per_iteration=budget_data.get("max_files_per_iteration", 5),
        )

        agent_data = data.get("agent", {})
        agent = AgentConfig(
            skill=agent_data.get("skill", ""),
            system_prompt_addendum=agent_data.get("system_prompt_addendum", ""),
        )

        lang_support = {}
        for lang, cfg in data.get("language_support", {}).items():
            lang_support[lang] = LanguageToolConfig(
                metric_tool=cfg.get("metric_tool", ""),
                metric_command=cfg.get("metric_command", ""),
                metric_parser=cfg.get("metric_parser", ""),
            )

        return WorkflowConfig(
            name=data.get("name", ""),
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
            adapter=data.get("adapter", ""),
            primary_metric=primary_cfg,
            constraint_metrics=constraints,
            budget=budget,
            agent=agent,
            language_support=lang_support,
            scope_priority=data.get("scope", {}).get("priority", "worst_first"),
        )


# ---------------------------------------------------------------------------
# Run Outcome
# ---------------------------------------------------------------------------

class RunOutcome(enum.Enum):
    """Possible outcomes for a workflow run."""
    TARGET_MET = "target_met"
    BUDGET_EXHAUSTED = "budget_exhausted"
    STALLED = "stalled"
    CONSTRAINT_VIOLATED = "constraint_violated"
    ERROR = "error"
    ABORTED = "aborted"


# ---------------------------------------------------------------------------
# Iteration Record
# ---------------------------------------------------------------------------

@dataclass
class IterationRecord:
    """Record of a single measure-act-validate iteration."""
    n: int
    metric_before: float
    metric_after: float
    files_modified: list[str] = field(default_factory=list)
    constraint_violations: list[str] = field(default_factory=list)
    tokens_used: int = 0
    duration_seconds: float = 0.0
    commit_sha: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Run Report
# ---------------------------------------------------------------------------

@dataclass
class RunReport:
    """Complete report for a workflow run.

    Pure data — use reporting.py for serialization and formatting.
    """
    workflow: str
    target: dict[str, float] = field(default_factory=dict)
    iterations: list[IterationRecord] = field(default_factory=list)
    outcome: RunOutcome = RunOutcome.ERROR
    initial_metric: float = 0.0
    final_metric: float = 0.0
    total_tokens: int = 0
    total_duration_seconds: float = 0.0
    branch: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str = ""
    error: str = ""
