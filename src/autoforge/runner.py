"""
Workflow Runner for AutoForge (legacy autonomous mode).

Executes the core measure -> act -> validate iteration loop by spawning
the agent as a subprocess each iteration. This is the legacy autonomous mode;
the recommended approach is for AI agents to call `autoforge measure` and
`autoforge targets` as tools directly (see skill.py).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
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
        # CLI --agent-command provides a full custom command (used as-is)
        self.agent_command = agent_command
        # Configured agent binary from workflow YAML (used in prompt-building path)
        self.agent_binary = config.agent.command or "claude"

        self.budget = BudgetManager(config.budget)
        self.git = GitManager(repo_path) if not skip_git else None
        self.guard = RegressionGuard(repo_path, test_command=test_command)

        self.report = RunReport(
            workflow=config.name,
            target={config.primary_metric.name: self.target_value},
        )

    def _check_agent_available(self) -> None:
        """Verify the configured agent command is available on PATH.

        Raises RuntimeError if the agent binary cannot be found.
        """
        # For custom commands, check the first token; otherwise check the configured binary
        if self.agent_command:
            binary = self.agent_command.split()[0]
        else:
            binary = self.agent_binary
        if not shutil.which(binary):
            raise RuntimeError(
                f"Agent command '{binary}' not found on PATH. "
                f"Install it or use --agent-command to specify an alternative."
            )
        logger.info("Agent binary found: %s", shutil.which(binary))

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

        # Fail fast if agent is not available
        if not self.dry_run:
            self._check_agent_available()

        # Create git branch
        if self.git:
            self.report.branch = self.git.create_branch(self.config.name)

        try:
            # Baseline measurement
            baseline = self._measure("baseline")
            self.report.initial_metric = baseline.value
            logger.info("Baseline %s: %.2f", baseline.metric_name, baseline.value)

            # Set constraint baselines on the regression guard
            self._set_constraint_baselines()

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
                stop = self._check_loop_termination()
                if stop:
                    break

                current = self._run_iteration(current)

                if self._target_met(current):
                    logger.info("Target met!")
                    self.report.outcome = RunOutcome.TARGET_MET
                    break

            self.report.final_metric = current.value

        except Exception as e:
            logger.error("Workflow error: %s", e, exc_info=True)
            self.report.outcome = RunOutcome.ERROR
            self.report.error = str(e)

        self._finalize()
        return self.report

    def _check_loop_termination(self) -> bool:
        """Check budget and stall conditions. Returns True if the loop should stop."""
        try:
            self.budget.check_budget()
        except BudgetExhausted as e:
            logger.warning("Budget exhausted: %s", e.reason)
            self.report.outcome = RunOutcome.BUDGET_EXHAUSTED
            self.report.error = e.reason
            return True

        if self.budget.check_stall():
            self.report.outcome = RunOutcome.STALLED
            self.report.error = (
                f"Improvement stalled for {self.config.budget.stall_patience} "
                f"consecutive iterations"
            )
            return True

        return False

    def _run_iteration(self, current: MetricResult) -> MetricResult:
        """Execute a single measure-act-validate iteration.

        Returns the updated MetricResult (or the same one if the iteration failed).
        """
        iteration_num = self.budget.iterations_used + 1
        logger.info("=== Iteration %d ===", iteration_num)

        iter_start = time.monotonic()
        record = IterationRecord(n=iteration_num, metric_before=current.value, metric_after=current.value)
        iter_tokens = 0

        try:
            # ACT: Run the agent
            if not self.dry_run:
                iter_tokens = self._run_agent(current, iteration_num)
            record.tokens_used = iter_tokens

            # MEASURE: Re-measure after agent action
            after = self._measure(f"iteration {iteration_num}")
            record.metric_after = after.value

            # Get modified files
            if self.git:
                record.files_modified = self.git.get_modified_files()

            # VALIDATE: Regression guard (tests + constraint metrics)
            if not self.skip_tests:
                passed, issues = self.guard.validate_iteration(
                    run_tests=True,
                    adapter=self.adapter,
                    repo_path=self.repo_path,
                    target_path=self.target_path,
                    tolerance_map=self._build_tolerance_map(),
                )
                if not passed:
                    return self._handle_failed_validation(
                        record, issues, iteration_num, iter_start, iter_tokens, current,
                    )

            # Commit this iteration
            if self.git:
                sha = self.git.commit_iteration(
                    self.config.name, iteration_num, current.value, after.value,
                )
                record.commit_sha = sha

            # Calculate improvement
            improvement_pct = self._compute_improvement(current.value, after.value)
            record.duration_seconds = time.monotonic() - iter_start
            self.report.iterations.append(record)
            self.budget.record_iteration(tokens=iter_tokens, improvement_pct=improvement_pct)

            logger.info(
                "Iteration %d: %.2f -> %.2f (%.1f%% improvement)",
                iteration_num, current.value, after.value, improvement_pct,
            )
            return after

        except Exception as e:
            logger.error("Iteration %d error: %s", iteration_num, e)
            record.error = str(e)
            record.duration_seconds = time.monotonic() - iter_start
            self.report.iterations.append(record)
            self.budget.record_iteration(tokens=iter_tokens, improvement_pct=0.0)
            if self.git:
                try:
                    self.git.rollback_iteration()
                except Exception:
                    pass
            return current

    def _handle_failed_validation(
        self,
        record: IterationRecord,
        issues: list[str],
        iteration_num: int,
        iter_start: float,
        iter_tokens: int,
        current: MetricResult,
    ) -> MetricResult:
        """Handle a failed validation by rolling back and recording the failure."""
        record.constraint_violations = issues
        logger.warning("Iteration %d failed validation: %s", iteration_num, issues)
        if self.git:
            self.git.rollback_iteration()
        record.error = "; ".join(issues)
        record.duration_seconds = time.monotonic() - iter_start
        self.report.iterations.append(record)
        self.budget.record_iteration(tokens=iter_tokens, improvement_pct=0.0)
        return current

    @staticmethod
    def _compute_improvement(before: float, after: float) -> float:
        """Calculate percentage improvement between two metric values."""
        if before != 0:
            return abs(after - before) / abs(before) * 100
        return 100.0 if after != before else 0.0

    def _set_constraint_baselines(self) -> None:
        """Measure and record constraint baselines on the regression guard."""
        for constraint in self.config.constraint_metrics:
            try:
                result = self.adapter.measure(self.repo_path, self.target_path)
                self.guard.set_constraint_baseline(constraint.name, result)
                logger.info(
                    "Constraint baseline '%s': %.2f (tolerance: %.1f%%)",
                    constraint.name,
                    result.value,
                    constraint.tolerance_percent,
                )
            except Exception as e:
                logger.warning(
                    "Failed to measure constraint baseline '%s': %s",
                    constraint.name,
                    e,
                )

    def _build_tolerance_map(self) -> dict[str, float]:
        """Build a tolerance map from the workflow config's constraint metrics."""
        return {
            c.name: c.tolerance_percent
            for c in self.config.constraint_metrics
        }

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

    def _run_agent(self, current_metric: MetricResult, iteration: int) -> int:
        """Invoke the coding agent to make improvements.

        Returns:
            Best-effort token count extracted from agent output (0 if unavailable).
        """
        if self.agent_command:
            # Use explicit custom command as-is
            cmd = self.agent_command
        else:
            # Build default agent invocation using configured binary
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

            cmd = f"{self.agent_binary} --print --output-format json -p \"$(cat {prompt_file})\""

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

        # Best-effort token extraction
        tokens = self._parse_token_usage(result)
        if tokens > 0:
            logger.info("Agent token usage: %d", tokens)
        else:
            logger.debug("Token usage not available from agent output")
        return tokens

    @staticmethod
    def _parse_token_usage(result: subprocess.CompletedProcess) -> int:
        """Best-effort extraction of token usage from Claude Code output.

        Tries two strategies:
        1. Parse JSON output (--output-format json) for usage fields.
        2. Scan stderr for token usage summary lines.

        Returns 0 if token usage cannot be determined. This is expected —
        Claude Code does not guarantee structured token reporting in all modes.
        """
        # Strategy 1: JSON output with usage field
        if result.stdout:
            try:
                data = json.loads(result.stdout)
                # Claude --output-format json may include a usage object
                usage = data.get("usage", {}) if isinstance(data, dict) else {}
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                if input_tokens or output_tokens:
                    return input_tokens + output_tokens
            except (json.JSONDecodeError, AttributeError):
                pass

        # Strategy 2: Regex scan of stderr for token summary
        # Claude Code may print lines like "Total tokens: 12345" or
        # "input: 1000 output: 2000" to stderr
        if result.stderr:
            # Pattern: "Total tokens: <number>" or "total_tokens: <number>"
            match = re.search(r"[Tt]otal.?tokens\D+(\d[\d,]*)", result.stderr)
            if match:
                return int(match.group(1).replace(",", ""))
            # Pattern: input/output token counts
            in_match = re.search(r"input.?tokens\D+(\d[\d,]*)", result.stderr)
            out_match = re.search(r"output.?tokens\D+(\d[\d,]*)", result.stderr)
            if in_match or out_match:
                total = 0
                if in_match:
                    total += int(in_match.group(1).replace(",", ""))
                if out_match:
                    total += int(out_match.group(1).replace(",", ""))
                return total

        return 0

    def _finalize(self) -> None:
        """Finalize the run report."""
        self.report.finished_at = datetime.now(timezone.utc).isoformat()
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
