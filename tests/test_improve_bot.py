import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from email.message import Message
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "improve_bot.py"
SPEC = importlib.util.spec_from_file_location("improve_bot", MODULE_PATH)
improve_bot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(improve_bot)
SYNC_PATH = Path(__file__).resolve().parents[1] / "tools" / "sync_online_matches.py"
SYNC_SPEC = importlib.util.spec_from_file_location("sync_online_matches", SYNC_PATH)
sync_online_matches = importlib.util.module_from_spec(SYNC_SPEC)
SYNC_SPEC.loader.exec_module(sync_online_matches)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.body


class ImproveBotTests(unittest.TestCase):
    def test_candidate_git_branch_is_isolated_from_incumbent_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incumbent = root / "incumbent"
            candidate = root / "candidate"
            (incumbent / "src").mkdir(parents=True)
            (candidate / "src").mkdir(parents=True)
            incumbent_file = incumbent / "src" / "bot.cpp"
            candidate_file = candidate / "src" / "bot.cpp"
            incumbent_file.write_text("known-good\n", encoding="utf-8")
            candidate_file.write_text("known-good\n", encoding="utf-8")

            baseline_commit = improve_bot.create_candidate_branch(candidate)
            branch = subprocess.run(
                ["git", "-C", str(candidate), "branch", "--show-current"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            candidate_file.write_text("deliberately failing candidate\n", encoding="utf-8")

            self.assertEqual(branch, "candidate")
            self.assertTrue(baseline_commit)
            self.assertEqual(incumbent_file.read_text(encoding="utf-8"), "known-good\n")
            self.assertIn("bot.cpp", subprocess.run(
                ["git", "-C", str(candidate), "status", "--short"],
                check=True, capture_output=True, text=True,
            ).stdout)

    def test_gemini_candidate_retry_honours_retry_after_header(self):
        proposal = {
            "file": "src/bot.cpp",
            "diff": "--- a/src/bot.cpp\n+++ b/src/bot.cpp\n@@ -1 +1 @@\n-old\n+new\n",
            "rationale": "test-only patch",
        }
        response = FakeResponse(json.dumps({
            "choices": [{"message": {"content": json.dumps(proposal)}}],
        }).encode())
        headers = Message()
        headers["Retry-After"] = "17"
        error = HTTPError("https://example.test", 429, "rate limited", headers, BytesIO(b"{}"))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            candidate = root / "candidate"
            (source / "src").mkdir(parents=True)
            (candidate / "src").mkdir(parents=True)
            (source / "src" / "bot.cpp").write_text("old\n", encoding="utf-8")
            (candidate / "src" / "bot.cpp").write_text("old\n", encoding="utf-8")
            with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
                with patch.object(improve_bot, "urlopen", side_effect=[error, response]) as urlopen:
                    with patch.object(improve_bot.time, "sleep") as sleep:
                        improve_bot.generate_candidate_patch(
                            {"match": {}}, "teamA", root / "statistics.json", source, candidate)
            self.assertEqual(urlopen.call_count, 2)
            sleep.assert_called_once_with(17.0)
            self.assertEqual((source / "src" / "bot.cpp").read_text(encoding="utf-8"), "old\n")
        error.close()

    def test_improve_cli_no_longer_exposes_automatic_promotion(self):
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--help"],
            check=True, capture_output=True, text=True,
        )
        self.assertNotIn("--auto-promote", result.stdout)

    def test_loss_evidence_accepts_string_and_object_owners(self):
        evidence = improve_bot.compact_loss_evidence({
            "match": {},
            "teams": [],
            "diagnostics": {},
            "champions": [],
            "teamTimelines": [
                {"metric": "submittedGems", "owner": "teamA", "runs": [{"value": 12}]},
                {"metric": "submittedGems", "owner": {"team": "teamB"}, "runs": [{"value": 8}]},
            ],
            "events": [
                {"kind": "death", "owner": {"team": "teamA"}, "entries": [{"round": 1}]},
                {"kind": "death", "owner": {"team": "teamB"}, "entries": [{"round": 2}]},
            ],
        }, "teamA", Path("missing-statistics.json"))
        self.assertEqual(len(evidence["team_timelines"]), 2)
        self.assertEqual(len(evidence["relevant_events"]), 2)

    def test_benchmark_requires_gem_gain_without_win_or_fault_regression(self):
        incumbent = [
            {"gems": 100, "win": True, "faults": 0},
            {"gems": 80, "win": False, "faults": 1},
        ]
        self.assertTrue(improve_bot.benchmark_passes({
            "incumbent": incumbent,
            "candidate": [
                {"gems": 110, "win": True, "faults": 0},
                {"gems": 90, "win": False, "faults": 1},
            ],
        }))
        self.assertFalse(improve_bot.benchmark_passes({
            "incumbent": incumbent,
            "candidate": [
                {"gems": 200, "win": True, "faults": 1},
                {"gems": 90, "win": False, "faults": 1},
            ],
        }))
        self.assertFalse(improve_bot.benchmark_passes({
            "incumbent": incumbent,
            "candidate": [
                {"gems": 90, "win": True, "faults": 0},
                {"gems": 120, "win": False, "faults": 1},
            ],
        }))

    def test_gemini_patch_is_applied_only_inside_candidate_source(self):
        proposal = {
            "file": "src/bot.cpp",
            "diff": "--- a/src/bot.cpp\n+++ b/src/bot.cpp\n@@ -1 +1 @@\n-old\n+new\n",
            "rationale": "test-only patch",
        }
        response = FakeResponse(json.dumps({
            "choices": [{"message": {"content": json.dumps(proposal)}}],
        }).encode())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            candidate = root / "candidate"
            (source / "src").mkdir(parents=True)
            (candidate / "src").mkdir(parents=True)
            (source / "src" / "bot.cpp").write_text("old\n", encoding="utf-8")
            (candidate / "src" / "bot.cpp").write_text("old\n", encoding="utf-8")
            with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
                with patch.object(improve_bot, "urlopen", return_value=response):
                    filename, _ = improve_bot.generate_candidate_patch(
                        {"match": {}}, "teamA", root / "statistics.json", source, candidate)
            self.assertEqual(filename, "src/bot.cpp")
            self.assertEqual((candidate / filename).read_text(encoding="utf-8"), "new\n")
            self.assertEqual((source / filename).read_text(encoding="utf-8"), "old\n")

    def test_gemini_patch_rejects_paths_outside_allowed_sources(self):
        proposal = {
            "file": "../../.env",
            "diff": "--- a/../../.env\n+++ b/../../.env\n@@ -1 +1 @@\n-old\n+new\n",
            "rationale": "invalid path",
        }
        response = FakeResponse(json.dumps({
            "choices": [{"message": {"content": json.dumps(proposal)}}],
        }).encode())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            candidate = root / "candidate"
            (source / "src").mkdir(parents=True)
            (candidate / "src").mkdir(parents=True)
            (source / "src" / "bot.cpp").write_text("old\n", encoding="utf-8")
            (candidate / "src" / "bot.cpp").write_text("old\n", encoding="utf-8")
            with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
                with patch.object(improve_bot, "urlopen", return_value=response):
                    with self.assertRaises(ValueError):
                        improve_bot.generate_candidate_patch(
                            {"match": {}}, "teamA", root / "statistics.json", source, candidate)
            self.assertEqual((source / "src" / "bot.cpp").read_text(encoding="utf-8"), "old\n")

    def test_candidate_command_does_not_retry_entire_job_on_rate_limit(self):
        error = subprocess.CalledProcessError(
            1, ["candidate"], stderr="HTTP 429 rate limit")
        with patch.object(sync_online_matches.subprocess, "run", side_effect=error) as run:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(subprocess.CalledProcessError):
                    sync_online_matches.run(
                        ["candidate"], cwd=Path.cwd(), capture=True, retry_rate_limits=False)
        self.assertEqual(run.call_count, 1)

    def test_failed_candidate_is_recorded_and_match_is_not_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cambc = root / ".venv" / "bin" / "cambc"
            cambc.parent.mkdir(parents=True)
            cambc.touch()
            match = {
                "matchId": "match-1",
                "status": "finished",
                "finishedAt": "2026-10-19T04:00:00Z",
                "map": "ambush",
                "teams": [
                    {"teamId": "team-id", "name": "decrest", "side": "a", "result": "loss"},
                    {"teamId": "opponent-id", "name": "opponent", "side": "b", "result": "win"},
                ],
            }
            candidate_attempts = 0

            def fake_run(command, *, cwd, capture=False, retry_rate_limits=True):
                nonlocal candidate_attempts
                self.assertEqual(cwd, root)
                if "matches" in command and "list" in command:
                    return json.dumps({"matches": [match]})
                if "matches" in command and "summary" in command:
                    stats_path = Path(command[command.index("--output") + 1])
                    stats_path.parent.mkdir(parents=True, exist_ok=True)
                    stats_path.write_text('{"match": {}}', encoding="utf-8")
                    return ""
                if "review_match.py" in command[1]:
                    return "review completed"
                if "improve_bot.py" in command[1]:
                    self.assertTrue(capture)
                    self.assertFalse(retry_rate_limits)
                    candidate_attempts += 1
                    raise subprocess.CalledProcessError(
                        2, command, output="candidate failed",
                        stderr="HTTP 429; GEMINI_API_KEY=test-secret",
                    )
                self.fail(f"unexpected command: {command}")

            argv = ["sync_online_matches.py", "--team-id", "team-id", "--team-name", "decrest",
                    "--stats-only", "--root", "reviews"]
            with patch("pathlib.Path.cwd", return_value=root):
                with patch.object(sys, "argv", argv):
                    with patch.object(sync_online_matches, "run", side_effect=fake_run):
                        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}):
                            with contextlib.redirect_stderr(io.StringIO()):
                                self.assertEqual(sync_online_matches.main(), 2)

                            state_path = root / "reviews" / "state.json"
                            state = json.loads(state_path.read_text(encoding="utf-8"))
                            record = state["processed"]["match-1"]
                            self.assertEqual(record["candidateExperiment"]["status"], "failed")
                            self.assertEqual(record["candidateExperiment"]["returncode"], 2)
                            log_path = Path(record["candidateExperiment"]["log"])
                            log_text = log_path.read_text(encoding="utf-8")
                            self.assertIn("HTTP 429", log_text)
                            self.assertNotIn("test-secret", log_text)
                            self.assertIn("[redacted]", log_text)

                            with patch.object(sys, "argv", argv):
                                with contextlib.redirect_stdout(io.StringIO()):
                                    self.assertEqual(sync_online_matches.main(), 0)
            self.assertEqual(candidate_attempts, 1)


if __name__ == "__main__":
    unittest.main()
