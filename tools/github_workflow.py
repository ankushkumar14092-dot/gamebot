#!/usr/bin/env python3
"""Phase 9: Automated, safe Git and GitHub push workflow for validated CAMBC bot candidates."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROTECTED_BRANCHES = {"main", "master", "production", "release"}


@dataclass
class PushResult:
    success: bool
    commit_sha: str
    remote_sha: str | None
    branch: str
    remote: str
    tag: str | None
    error: str | None = None


class GitHubWorkflow:
    def __init__(self, root: Path = ROOT, default_remote: str = "origin"):
        self.root = root.resolve()
        self.default_remote = default_remote

    def _run_git(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.root)] + args,
            capture_output=True,
            text=True,
            check=check,
        )

    def verify_no_secrets_staged(self) -> None:
        """Ensure no sensitive files like .env or files with API keys are staged."""
        staged = self._run_git(["diff", "--cached", "--name-only"]).stdout.splitlines()
        for f in staged:
            if f.strip() in {".env", ".env.local"} or f.strip().startswith(".env."):
                raise ValueError(f"Security error: Attempting to commit forbidden file '{f}'")
            # Verify staged diff content does not contain raw API keys
            diff_text = self._run_git(["diff", "--cached", f]).stdout
            if re.search(r"(?i)(?:GEMINI_API_KEY|FIREWORKS_API_KEY)\s*[:=]\s*[a-zA-Z0-9_\-]{20,}", diff_text):
                raise ValueError(f"Security error: Potential API key detected in staged diff for '{f}'")

    def run_pre_push_checks(self) -> bool:
        """Run the unit test suite before pushing."""
        test_files = [
            "tests/test_cambc_adapter.py",
            "tests/test_improve_bot.py",
            "tests/test_gemini_retry.py",
            "tests/test_agent_reports.py",
        ]
        test_res = subprocess.run(
            [sys.executable, "-m", "unittest"] + test_files,
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )
        return test_res.returncode == 0


    def push_validated_candidate(
        self,
        candidate_dir: Path | str,
        version_id: str,
        metrics_summary: str,
        branch: str = "improvements",
        remote: str | None = None,
        create_tag: bool = True,
    ) -> PushResult:
        """Commit validated candidate source, tag, push to remote improvement branch, and verify remote SHA."""
        target_remote = remote or self.default_remote
        cand_path = Path(candidate_dir).resolve()

        if branch in PROTECTED_BRANCHES:
            raise ValueError(f"Safety violation: Direct push to protected branch '{branch}' is forbidden")

        # 1. Run pre-push checks
        if not self.run_pre_push_checks():
            return PushResult(
                success=False,
                commit_sha="",
                remote_sha=None,
                branch=branch,
                remote=target_remote,
                tag=None,
                error="Pre-push regression test suite failed",
            )

        # 2. Check if remote exists
        remotes_out = self._run_git(["remote"], check=False).stdout.splitlines()
        if target_remote not in [r.strip() for r in remotes_out]:
            return PushResult(
                success=False,
                commit_sha="",
                remote_sha=None,
                branch=branch,
                remote=target_remote,
                tag=None,
                error=f"Remote '{target_remote}' is not configured in git repository",
            )

        # 3. Check current branch or switch to improvement branch
        current_branch = self._run_git(["branch", "--show-current"], check=False).stdout.strip()
        branches = self._run_git(["branch", "--list", branch], check=False).stdout
        if not branches.strip():
            self._run_git(["checkout", "-b", branch])
        else:
            self._run_git(["checkout", branch])

        try:
            # 4. Copy candidate source files to active bot directory or stage them
            src_dest = self.root / "bots" / "submission-v6" / "src"
            cand_src = cand_path / "src" if (cand_path / "src").is_dir() else cand_path
            if cand_src.is_dir() and cand_src != src_dest:
                import shutil
                for item in cand_src.glob("*.cpp"):
                    shutil.copy2(item, src_dest / item.name)
                for item in cand_src.glob("*.h"):
                    shutil.copy2(item, src_dest / item.name)

            self._run_git(["add", "bots/submission-v6/src"])
            self.verify_no_secrets_staged()

            # 5. Create descriptive commit
            commit_msg = (
                f"feat(bot): promote candidate {version_id}\n\n"
                f"Metrics: {metrics_summary}\n"
                f"Validated by autonomous benchmark suite."
            )
            commit_res = self._run_git([
                "-c", "user.name=CAMBC Autonomous Agent",
                "-c", "user.email=cambc-agent@localhost",
                "commit", "-m", commit_msg,
            ], check=False)

            commit_sha = self._run_git(["rev-parse", "HEAD"]).stdout.strip()

            # 6. Create tag
            tag_name = f"best-known-{version_id}" if create_tag else None
            if tag_name:
                self._run_git(["tag", "-f", tag_name, commit_sha])

            # 7. Push branch and tag to remote
            push_cmd = ["push", target_remote, f"{branch}:{branch}"]
            push_res = self._run_git(push_cmd, check=False)
            if push_res.returncode != 0:
                return PushResult(
                    success=False,
                    commit_sha=commit_sha,
                    remote_sha=None,
                    branch=branch,
                    remote=target_remote,
                    tag=tag_name,
                    error=f"Git push failed: {push_res.stderr.strip()}",
                )

            if tag_name:
                self._run_git(["push", target_remote, tag_name], check=False)

            # 8. Verify remote SHA matches commit SHA
            ls_remote = self._run_git(["ls-remote", target_remote, f"refs/heads/{branch}"], check=False)
            remote_sha = ls_remote.stdout.split()[0] if ls_remote.stdout.strip() else None

            if remote_sha != commit_sha:
                return PushResult(
                    success=False,
                    commit_sha=commit_sha,
                    remote_sha=remote_sha,
                    branch=branch,
                    remote=target_remote,
                    tag=tag_name,
                    error=f"Remote verification mismatch: expected {commit_sha}, got {remote_sha}",
                )

            return PushResult(
                success=True,
                commit_sha=commit_sha,
                remote_sha=remote_sha,
                branch=branch,
                remote=target_remote,
                tag=tag_name,
                error=None,
            )

        finally:
            # Restore branch
            if current_branch and current_branch != branch:
                self._run_git(["checkout", current_branch], check=False)
