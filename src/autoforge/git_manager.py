"""
Git Manager for AutoForge.

Handles branch creation, per-iteration commits, and rollback.
Each workflow run operates on its own branch for isolation.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class GitError(Exception):
    """Raised when a git operation fails."""


def _run_git(args: list[str], cwd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    cmd = ["git"] + args
    logger.debug("git %s (cwd=%s)", " ".join(args), cwd)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=60,
    )
    if check and result.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed (exit {result.returncode}):\n"
            f"{result.stderr.strip()}"
        )
    return result


class GitManager:
    """Manages git operations for a workflow run."""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.branch_name: str = ""
        self.original_branch: str = ""
        self._iteration_shas: list[str] = []

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        return _run_git(args, self.repo_path, check=check)

    def get_current_branch(self) -> str:
        """Return the current branch name."""
        result = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip()

    def get_head_sha(self) -> str:
        """Return the current HEAD commit SHA."""
        result = self._run(["rev-parse", "HEAD"])
        return result.stdout.strip()

    def is_clean(self) -> bool:
        """Check if the working tree is clean."""
        result = self._run(["status", "--porcelain"])
        return result.stdout.strip() == ""

    def create_branch(self, workflow_name: str) -> str:
        """Create and checkout a new branch for this workflow run."""
        self.original_branch = self.get_current_branch()
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        self.branch_name = f"autoforge/{workflow_name}/{timestamp}"
        self._run(["checkout", "-b", self.branch_name])
        logger.info("Created branch: %s", self.branch_name)
        return self.branch_name

    def commit_iteration(
        self,
        workflow_name: str,
        iteration: int,
        metric_before: float,
        metric_after: float,
    ) -> str:
        """Stage all changes and commit with a structured message."""
        # Stage all changes
        self._run(["add", "-A"])

        # Check if there's anything to commit
        result = self._run(["diff", "--cached", "--quiet"], check=False)
        if result.returncode == 0:
            logger.info("No changes to commit in iteration %d", iteration)
            return self.get_head_sha()

        message = (
            f"autoforge: {workflow_name} iter {iteration} "
            f"— {metric_before:.2f} -> {metric_after:.2f}"
        )
        self._run(["commit", "-m", message])

        sha = self.get_head_sha()
        self._iteration_shas.append(sha)
        logger.info("Committed iteration %d: %s (%s)", iteration, sha[:8], message)
        return sha

    def rollback_iteration(self) -> None:
        """Rollback the last iteration's changes."""
        if self._iteration_shas:
            sha = self._iteration_shas.pop()
            self._run(["reset", "--hard", f"{sha}~1"])
            logger.warning("Rolled back iteration commit %s", sha[:8])
        else:
            # Just discard uncommitted changes
            self._run(["checkout", "."])
            self._run(["clean", "-fd"])
            logger.warning("Discarded uncommitted changes")

    def get_modified_files(self) -> list[str]:
        """Return list of files modified since last commit (or in staging)."""
        # Check staged + unstaged
        result = self._run(["diff", "--name-only", "HEAD"], check=False)
        files = result.stdout.strip().splitlines() if result.stdout.strip() else []

        # Also check untracked
        result = self._run(["ls-files", "--others", "--exclude-standard"])
        untracked = result.stdout.strip().splitlines() if result.stdout.strip() else []

        return files + untracked

    def return_to_original(self) -> None:
        """Return to the original branch."""
        if self.original_branch:
            self._run(["checkout", self.original_branch])
            logger.info("Returned to branch: %s", self.original_branch)

    def get_iteration_count(self) -> int:
        """Return the number of committed iterations."""
        return len(self._iteration_shas)
