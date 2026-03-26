"""Tests for autoforge.git_manager — GitManager with real git repos."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from autoforge.git_manager import GitError, GitManager, _run_git


def _init_repo(path: str) -> None:
    """Initialize a fresh git repo with an initial commit."""
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True, capture_output=True)
    # Initial commit
    (Path(path) / "README.md").write_text("# test\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path):
    """Provide a temp directory with a fresh git repo."""
    _init_repo(str(tmp_path))
    return tmp_path


class TestRunGit:
    def test_success(self, git_repo):
        result = _run_git(["status"], str(git_repo))
        assert result.returncode == 0

    def test_failure_raises(self, git_repo):
        with pytest.raises(GitError, match="failed"):
            _run_git(["checkout", "nonexistent-branch"], str(git_repo))

    def test_failure_no_check(self, git_repo):
        result = _run_git(["checkout", "nonexistent-branch"], str(git_repo), check=False)
        assert result.returncode != 0


class TestGitManagerBasics:
    def test_get_current_branch(self, git_repo):
        gm = GitManager(str(git_repo))
        assert gm.get_current_branch() == "main"

    def test_get_head_sha(self, git_repo):
        gm = GitManager(str(git_repo))
        sha = gm.get_head_sha()
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_is_clean(self, git_repo):
        gm = GitManager(str(git_repo))
        assert gm.is_clean() == True

    def test_is_not_clean_with_changes(self, git_repo):
        (git_repo / "new_file.py").write_text("x = 1\n")
        gm = GitManager(str(git_repo))
        assert gm.is_clean() == False


class TestGitManagerBranching:
    def test_create_branch(self, git_repo):
        gm = GitManager(str(git_repo))
        branch = gm.create_branch("test_workflow")
        assert branch.startswith("autoforge/test_workflow/")
        assert gm.get_current_branch() == branch
        assert gm.original_branch == "main"
        assert gm.branch_name == branch

    def test_return_to_original(self, git_repo):
        gm = GitManager(str(git_repo))
        gm.create_branch("test_workflow")
        gm.return_to_original()
        assert gm.get_current_branch() == "main"

    def test_return_to_original_noop_without_branch(self, git_repo):
        gm = GitManager(str(git_repo))
        gm.return_to_original()  # should not raise
        assert gm.get_current_branch() == "main"


class TestGitManagerCommit:
    def test_commit_iteration_with_changes(self, git_repo):
        gm = GitManager(str(git_repo))
        gm.create_branch("wf")
        (git_repo / "new.py").write_text("x = 1\n")
        sha = gm.commit_iteration("wf", 1, 10.0, 8.0)
        assert len(sha) == 40
        assert gm.is_clean() == True
        assert gm.get_iteration_count() == 1

        # Verify commit message format
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(git_repo), capture_output=True, text=True
        )
        assert "autoforge: wf iter 1" in log.stdout
        assert "10.00 -> 8.00" in log.stdout

    def test_commit_iteration_no_changes(self, git_repo):
        gm = GitManager(str(git_repo))
        gm.create_branch("wf")
        sha = gm.commit_iteration("wf", 1, 10.0, 10.0)
        assert len(sha) == 40  # returns HEAD sha
        assert gm.get_iteration_count() == 0  # no commit was made

    def test_multiple_commits(self, git_repo):
        gm = GitManager(str(git_repo))
        gm.create_branch("wf")

        (git_repo / "a.py").write_text("a = 1\n")
        sha1 = gm.commit_iteration("wf", 1, 10.0, 8.0)

        (git_repo / "b.py").write_text("b = 2\n")
        sha2 = gm.commit_iteration("wf", 2, 8.0, 6.0)

        assert sha1 != sha2
        assert gm.get_iteration_count() == 2


class TestGitManagerRollback:
    def test_rollback_committed_iteration(self, git_repo):
        gm = GitManager(str(git_repo))
        gm.create_branch("wf")

        (git_repo / "new.py").write_text("x = 1\n")
        gm.commit_iteration("wf", 1, 10.0, 8.0)
        assert (git_repo / "new.py").exists() == True
        assert gm.get_iteration_count() == 1

        gm.rollback_iteration()
        assert (git_repo / "new.py").exists() == False
        assert gm.get_iteration_count() == 0

    def test_rollback_uncommitted_changes(self, git_repo):
        gm = GitManager(str(git_repo))
        gm.create_branch("wf")

        (git_repo / "uncommitted.py").write_text("x = 1\n")
        assert gm.is_clean() == False

        gm.rollback_iteration()
        assert gm.is_clean() == True
        assert (git_repo / "uncommitted.py").exists() == False

    def test_rollback_preserves_earlier_commits(self, git_repo):
        gm = GitManager(str(git_repo))
        gm.create_branch("wf")

        (git_repo / "keep.py").write_text("keep\n")
        gm.commit_iteration("wf", 1, 10.0, 8.0)

        (git_repo / "discard.py").write_text("discard\n")
        gm.commit_iteration("wf", 2, 8.0, 7.0)

        gm.rollback_iteration()
        assert (git_repo / "keep.py").exists() == True
        assert (git_repo / "discard.py").exists() == False


class TestGitManagerModifiedFiles:
    def test_modified_files_unstaged(self, git_repo):
        gm = GitManager(str(git_repo))
        (git_repo / "README.md").write_text("changed\n")
        files = gm.get_modified_files()
        assert "README.md" in files

    def test_modified_files_untracked(self, git_repo):
        gm = GitManager(str(git_repo))
        (git_repo / "new.py").write_text("new\n")
        files = gm.get_modified_files()
        assert "new.py" in files

    def test_modified_files_clean(self, git_repo):
        gm = GitManager(str(git_repo))
        files = gm.get_modified_files()
        assert files == []

    def test_modified_files_mixed(self, git_repo):
        gm = GitManager(str(git_repo))
        (git_repo / "README.md").write_text("changed\n")
        (git_repo / "untracked.py").write_text("new\n")
        files = gm.get_modified_files()
        assert len(files) == 2
