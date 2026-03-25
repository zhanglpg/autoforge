"""
Workflow Runner for AutoForge.

Executes the core measure -> act -> validate iteration loop.
The runner is the "thin driver" that manages the loop lifecycle while
delegating actual code intelligence to Claude Code agent instances.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from autoforge.budget import BudgetExhausted, BudgetManager
from autoforge.git_manager import GitManager
from autoforge.models import (
    BudgetConfig,
    Direction,
    IterationRecord,
    MetricAdapter,
    MetricResult,
    RunOutcome,
    RunReport,
    WorkflowConfig,
)
from autoforge.regression import RegressionGuard

logger = logging.getLogger(__name__)


class WorkflowRunner:
    """Executes a single workflow's measure-act-validate loop."""

    def __init__(
        self,
        config: WorkflowConfig,
        adapter: MetricAdapter,
        repo_path: str,
        target_path: str,
        *,
        target_value: float | None = None,
        test_command: str | None = None,
        skip_tests: bool = False,
        skip_git: bool = False,
        dry_run: bool = False,
        agent_command: str | None = None,
    ):
        self.config = config
        self.adapter = adapter
        self.repo_path = repo_path
        self.target_path = target_path
        self.target_value = target_value or config.primary_metric.default_target
        self.skip_tests = skip_tests
        self.skip_git = skip_git
        self.dry_run = dry_run
        self.agent_command = agent_command

        self.budget = BudgetManager(config.budget)
        self.git = GitManager(repo_path) if not skip_git else None
        self.guard = RegressionGuard(repo_path, test_command=test_command)

        self.report = RunReport(
            workflow=config.name,
            target={config.primary_metric.name: self.target_value},
        )

    def run(self) -> RunReport:
        """Execute the full workflow. Returns a RunReport."""
        logger.info(
            "Starting workflow '%s' on %s (target: %s %s %.2f)",
            self.config.name,
            self.target_path,
            self.config.primary_metric.name,
            self.config.primary_metric.direction,
            self.target_value,
        )

        # Create git branch
        if self.git:
            self.report.branch = self.git.create_branch(self.config.name)

        try:
            # Baseline measurement
            baseline = self._measure("baseline")
            self.report.initial_metric = baseline.value
            logger.info("Baseline %s: %.2f", baseline.metric_name, baseline.value)

            # Check if target already met
            if self._target_met(baseline):
                logger.info("Target already met! Nothing to do.")
                self.report.outcome = RunOutcome.TARGET_MET
                self.report.final_metric = baseline.value
                self._finalize()
                return self.report

            # Main iteration loop
            current = baseline
            while True:
                # Budget check
                try:
                    self.budget.check_budget()
                except BudgetExhausted as e:
                    logger.warning("Budget exhausted: %s", e.reason)
                    self.report.outcome = RunOutcome.BUDGET_EXHAUSTED
                    self.report.error = e.reason
                    break

                # Stall check
                if self.budget.check_stall():
                    self.report.outcome = RunOutcome.STALLED
                    self.report.error = (
                        f"Improvement stalled for {self.config.budget.stall_patience} "
                        f"consecutive iterations"
                    )
                    break

                iteration_num = self.budget.iterations_used + 1
                logger.info("=== Iteration %d ===", iteration_num)

                iter_start = time.monotonic()
                record = IterationRecord(n=iteration_num, metric_before=current.value, metric_after=current.value)

                try:
                    # ACT: Run the agent
                    if not self.dry_run:
                        self._run_agent(current, iteration_num)

                    # MEASURE: Re-measure after agent action
                    after = self._measure(f"iteration {iteration_num}")
                    record.metric_after = after.value

                    # Get modified files
                    if self.git:
                        record.files_modified = self.git.get_modified_files()

                    # VALIDATE: Regression guard
                    if not self.skip_tests:
                        passed, issues = self.guard.validate_iteration(run_tests=True)
                        if not passed:
                            record.constraint_violations = issues
                            logger.warning(
                                "Iteration %d failed validation: %s",
                                iteration_num,
                                issues,
                            )
                            # Rollback this iteration
                            if self.git:
                                self.git.rollback_iteration()
                            record.error = "; ".join(issues)
                            # Still count as an iteration for budget
                            record.duration_seconds = time.monotonic() - iter_start
                            self.report.iterations.append(record)
                            self.budget.record_iteration(improvement_pct=0.0)
                            continue

                    # Commit this iteration
                    if self.git:
                        sha = self.git.commit_iteration(
                            self.config.name,
                            iteration_num,
                            current.value,
                            after.value,
                        )
                        record.commit_sha = sha

                    # Calculate improvement
                    if current.value != 0:
                        improvement_pct = abs(after.value - current.value) / abs(current.value) * 100
                    else:
                        improvement_pct = 100.0 if after.value != current.value else 0.0

                    record.duration_seconds = time.monotonic() - iter_start
                    self.report.iterations.append(record)
                    self.budget.record_iteration(improvement_pct=improvement_pct)

                    logger.info(
                        "Iteration %d: %.2f -> %.2f (%.1f%% improvement)",
                        iteration_num,
                        current.value,
                        after.value,
                        improvement_pct,
                    )

                    current = after

                    # Check if target met
                    if self._target_met(current):
                        logger.info("Target met!")
                        self.report.outcome = RunOutcome.TARGET_MET
                        break

                except Exception as e:
                    logger.error("Iteration %d error: %s", iteration_num, e)
                    record.error = str(e)
                    record.duration_seconds = time.monotonic() - iter_start
                    self.report.iterations.append(record)
                    self.budget.record_iteration(improvement_pct=0.0)

                    # Rollback on error
                    if self.git:
                        try:
                            self.git.rollback_iteration()
                        except Exception:
                            pass

            self.report.final_metric = current.value

        except Exception as e:
            logger.error("Workflow error: %s", e, exc_info=True)
            self.report.outcome = RunOutcome.ERROR
            self.report.error = str(e)

        self._finalize()
        return self.report

    def _measure(self, label: str) -> MetricResult:
        """Run the metric adapter and return results."""
        logger.info("Measuring (%s)...", label)
        result = self.adapter.measure(self.repo_path, self.target_path)
        logger.info("%s %s = %.2f %s", label, result.metric_name, result.value, result.unit)
        return result

    def _target_met(self, result: MetricResult) -> bool:
        """Check if the target value has been met."""
        if result.direction is Direction.MINIMIZE:
            return result.value <= self.target_value
        return result.value >= self.target_value

    def _run_agent(self, current_metric: MetricResult, iteration: int) -> None:
        """Invoke the Claude Code agent to make improvements."""
        if self.agent_command:
            # Use explicit agent command
            cmd = self.agent_command
        else:
            # Build default agent invocation
            targets = self.adapter.identify_targets(
                current_metric,
                self.config.budget.max_files_per_iteration,
            )
            targets_str = ", ".join(targets[:5]) if targets else self.target_path

            skill = self.config.agent.skill
            addendum = self.config.agent.system_prompt_addendum

            prompt = (
                f"You are running iteration {iteration} of the "
                f"'{self.config.name}' workflow.\n\n"
                f"Current {current_metric.metric_name}: {current_metric.value} {current_metric.unit}\n"
                f"Target: {self.target_value}\n"
                f"Direction: {current_metric.direction}\n\n"
                f"Priority files to improve:\n{targets_str}\n\n"
            )
            if addendum:
                prompt += f"{addendum}\n\n"
            prompt += (
                "Make focused, minimal changes to improve the metric. "
                "Do not make unnecessary changes. "
                "Preserve existing behavior and tests."
            )

            # Write prompt to a temp file for the agent
            prompt_file = Path(self.repo_path) / ".autoforge-prompt.tmp"
            prompt_file.write_text(prompt)

            cmd = f"claude --print -p \"$(cat {prompt_file})\""

        logger.info("Running agent...")
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=self.repo_path,
            timeout=self.config.budget.max_wall_clock_minutes * 60,
        )

        # Clean up temp file
        prompt_file = Path(self.repo_path) / ".autoforge-prompt.tmp"
        if prompt_file.exists():
            prompt_file.unlink()

        if result.returncode != 0:
            logger.warning("Agent exited with code %d", result.returncode)
            if result.stderr:
                logger.warning("Agent stderr: %s", result.stderr[-500:])

    def _finalize(self) -> None:
        """Finalize the run report."""
        self.report.finished_at = datetime.utcnow().isoformat()
        self.report.total_tokens = self.budget.tokens_used
        self.report.total_duration_seconds = self.budget.elapsed_seconds

        # Return to original branch if we created one
        if self.git and self.report.outcome != RunOutcome.TARGET_MET:
            # Keep on the branch so user can inspect
            pass

        logger.info(
            "Workflow '%s' finished: %s (%.2f -> %.2f in %d iterations, %.1fs)",
            self.config.name,
            self.report.outcome.value,
            self.report.initial_metric,
            self.report.final_metric,
            len(self.report.iterations),
            self.report.total_duration_seconds,
        )
