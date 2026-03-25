"""
Core data models for AutoForge.

Defines the standard interfaces for metrics, workflow configuration,
budget tracking, iteration state, and run reports.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Metric Result — standard output from every metric adapter
# ---------------------------------------------------------------------------

@dataclass
class MetricResult:
    """Normalized result from a metric adapter measurement."""

    metric_name: str          # e.g., "net_complexity_score"
    value: float              # e.g., 7.23
    unit: str                 # e.g., "score", "percent", "count"
    direction: str            # "maximize" | "minimize"
    breakdown: dict[str, float] = field(default_factory=dict)  # per-file
    raw_output: str = ""      # full tool output for debugging
    tool: str = ""            # e.g., "complexity-accounting"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def improved_over(self, previous: MetricResult, threshold: float = 0.0) -> bool:
        """Check if this result is an improvement over a previous one."""
        if self.direction == "minimize":
            return (previous.value - self.value) > threshold
        else:
            return (self.value - previous.value) > threshold

    def degraded_beyond(self, baseline: MetricResult, tolerance_percent: float) -> bool:
        """Check if this result has degraded beyond tolerance from baseline."""
        if tolerance_percent <= 0:
            return False
        if baseline.value == 0:
            return self.value != 0
        change_pct = abs(self.value - baseline.value) / abs(baseline.value) * 100
        if self.direction == "minimize":
            return self.value > baseline.value and change_pct > tolerance_percent
        else:
            return self.value < baseline.value and change_pct > tolerance_percent


# ---------------------------------------------------------------------------
# Metric Adapter Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class MetricAdapter(Protocol):
    """Interface that every metric adapter must implement."""

    name: str
    supported_languages: list[str]

    def check_prerequisites(self, repo_path: str) -> bool:
        """Verify tool is installed and repo is compatible."""
        ...

    def measure(self, repo_path: str, target_path: str) -> MetricResult:
        """Run the metric tool and return normalized result."""
        ...

    def identify_targets(self, result: MetricResult, n: int) -> list[str]:
        """Return top-n files to target for improvement (worst first)."""
        ...


# ---------------------------------------------------------------------------
# Workflow Configuration — loaded from YAML
# ---------------------------------------------------------------------------

@dataclass
class MetricConstraint:
    """A constraint metric that must not degrade beyond tolerance."""
    name: str
    tolerance_percent: float
    direction: str  # "maximize" | "minimize"
    source_workflow: str = ""


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
    direction: str  # "maximize" | "minimize"
    default_target: float = 0.0


@dataclass
class AgentConfig:
    """Agent configuration for a workflow."""
    skill: str = ""
    system_prompt_addendum: str = ""


@dataclass
class LanguageToolConfig:
    """Language-specific tool configuration."""
    metric_tool: str = ""
    metric_command: str = ""
    metric_parser: str = ""
    mutation_tool: str = ""


@dataclass
class WorkflowConfig:
    """Complete workflow configuration, loaded from YAML."""
    name: str
    version: str = "1.0"
    description: str = ""
    primary_metric: PrimaryMetricConfig = field(
        default_factory=lambda: PrimaryMetricConfig(name="", direction="minimize")
    )
    constraint_metrics: list[MetricConstraint] = field(default_factory=list)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    language_support: dict[str, LanguageToolConfig] = field(default_factory=dict)
    scope_priority: str = "worst_first"

    @staticmethod
    def from_dict(data: dict[str, Any]) -> WorkflowConfig:
        """Parse a workflow config from a dictionary (e.g., loaded from YAML)."""
        primary = data.get("primary_metric", {})
        primary_cfg = PrimaryMetricConfig(
            name=primary.get("name", ""),
            direction=primary.get("direction", "minimize"),
            default_target=primary.get("default_target", 0.0),
        )

        constraints = []
        for c in data.get("constraint_metrics", []):
            constraints.append(MetricConstraint(
                name=c.get("name", ""),
                tolerance_percent=c.get("tolerance_percent", 10.0),
                direction=c.get("direction", "minimize"),
                source_workflow=c.get("source_workflow", ""),
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
                mutation_tool=cfg.get("mutation_tool", ""),
            )

        return WorkflowConfig(
            name=data.get("name", ""),
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
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
    """Complete report for a workflow run."""
    workflow: str
    target: dict[str, float] = field(default_factory=dict)
    iterations: list[IterationRecord] = field(default_factory=list)
    outcome: RunOutcome = RunOutcome.ERROR
    initial_metric: float = 0.0
    final_metric: float = 0.0
    total_tokens: int = 0
    total_duration_seconds: float = 0.0
    branch: str = ""
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    finished_at: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "workflow": self.workflow,
            "target": self.target,
            "iterations": [
                {
                    "n": it.n,
                    "metric_before": it.metric_before,
                    "metric_after": it.metric_after,
                    "files_modified": it.files_modified,
                    "constraint_violations": it.constraint_violations,
                    "tokens_used": it.tokens_used,
                    "duration_seconds": round(it.duration_seconds, 2),
                    "commit_sha": it.commit_sha,
                    "error": it.error,
                }
                for it in self.iterations
            ],
            "outcome": self.outcome.value,
            "initial_metric": self.initial_metric,
            "final_metric": self.final_metric,
            "total_tokens": self.total_tokens,
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "branch": self.branch,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }

    def to_markdown(self) -> str:
        """Generate a human-readable markdown summary."""
        lines = [
            f"# AutoForge Run Report: {self.workflow}",
            "",
            f"**Outcome:** {self.outcome.value}",
            f"**Branch:** `{self.branch}`",
            f"**Started:** {self.started_at}",
            f"**Finished:** {self.finished_at}",
            "",
            "## Metrics",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Initial | {self.initial_metric} |",
            f"| Final | {self.final_metric} |",
            f"| Target | {self.target} |",
            f"| Improvement | {abs(self.initial_metric - self.final_metric):.2f} |",
            "",
            "## Iterations",
            "",
            f"| # | Before | After | Files | Tokens | Duration |",
            f"|---|--------|-------|-------|--------|----------|",
        ]
        for it in self.iterations:
            files_str = ", ".join(it.files_modified[:3])
            if len(it.files_modified) > 3:
                files_str += f" (+{len(it.files_modified) - 3})"
            lines.append(
                f"| {it.n} | {it.metric_before} | {it.metric_after} "
                f"| {files_str} | {it.tokens_used} | {it.duration_seconds:.1f}s |"
            )

        lines.extend([
            "",
            "## Summary",
            "",
            f"- **Total iterations:** {len(self.iterations)}",
            f"- **Total tokens:** {self.total_tokens}",
            f"- **Total duration:** {self.total_duration_seconds:.1f}s",
        ])

        if self.error:
            lines.extend(["", f"**Error:** {self.error}"])

        return "\n".join(lines)
