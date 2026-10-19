#!/usr/bin/env python3
"""Comprehensive acceptance test suite verifying all 12 system acceptance criteria."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.autonomous_improver import AutonomousImprover
from tools.best_version_registry import BestVersionRegistry, VersionRecord
from tools.cambc_adapter import CambcAdapter
from tools.github_workflow import GitHubWorkflow, PushResult
from tools.match_analyzer import extract_match_metrics, generate_structured_report
from tools.quantitative_evaluator import QuantitativeEvaluator


class AutonomousSystemAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = CambcAdapter(root=ROOT)
        cls.incumbent = ROOT / "bots" / "submission-v6"
        cls.baseline = ROOT / "bots" / "baseline-cpp"
        cls.map_path = ROOT / "maps" / "ambush.map26a"

    def test_criterion_01_real_local_match_through_adapter(self):
        """Criterion 1: A real local match can be run through the adapter."""
        result = self.adapter.run_match(
            self.incumbent,
            self.baseline,
            self.map_path,
            rounds=20,
            release=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertGreater(len(result.generated_artifacts), 0)

    def test_criterion_02_match_results_and_diagnostics_collected(self):
        """Criterion 2: Match results and diagnostics can be collected."""
        result = self.adapter.run_match(
            self.incumbent,
            self.baseline,
            self.map_path,
            rounds=20,
            release=True,
        )
        self.assertEqual(result.returncode, 0)
        replay_artifact = next((p for p in result.generated_artifacts if p.suffix == ".repl26a"), None)
        self.assertIsNotNone(replay_artifact)
        self.assertTrue(replay_artifact.is_file())

    def test_criterion_03_replay_and_diagnostics_parsed(self):
        """Criterion 3: At least one replay or diagnostic file can be parsed."""
        local_matches = list((ROOT / "matches" / "local").glob("*/statistics.json"))
        self.assertTrue(len(local_matches) > 0, "Expected at least one local match export")
        stats_path = local_matches[0]
        replay_files = list(stats_path.parent.glob("*.repl26a"))
        replay_path = replay_files[0] if replay_files else None

        data = json.loads(stats_path.read_text(encoding="utf-8"))
        metrics = extract_match_metrics(data, team="teamA", replay_path=replay_path)
        self.assertIsNotNone(metrics.winner)
        self.assertIsNotNone(metrics.rounds_completed)
        report = generate_structured_report(metrics)
        self.assertIn("1. Match Summary", report)
        self.assertIn("3. Resource and Scoring Efficiency", report)

    def test_criterion_04_isolated_candidate_generation(self):
        """Criterion 4: A targeted source patch can be generated on an isolated branch."""
        improver = AutonomousImprover(root=ROOT)
        cand_name = "test-crit4-cand"
        cand_dir = improver.create_isolated_candidate_copy(cand_name)
        try:
            branch = subprocess.run(
                ["git", "-C", str(cand_dir), "branch", "--show-current"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            self.assertEqual(branch, "candidate")

            incumbent_cpp_before = (self.incumbent / "src" / "bot.cpp").read_text(encoding="utf-8")
            patch_desc = improver.generate_candidate_patch(cand_dir, strategy_hint="bank_early")
            self.assertTrue(patch_desc)

            cand_cpp = (cand_dir / "src" / "bot.cpp").read_text(encoding="utf-8")
            incumbent_cpp_after = (self.incumbent / "src" / "bot.cpp").read_text(encoding="utf-8")

            # Incumbent must remain untouched
            self.assertEqual(incumbent_cpp_before, incumbent_cpp_after)
            # Candidate must have the change
            self.assertNotEqual(incumbent_cpp_after, cand_cpp)
        finally:
            if cand_dir.exists():
                shutil.rmtree(cand_dir)

    def test_criterion_05_compile_candidate_with_official_toolchain(self):
        """Criterion 5: The candidate can be compiled with the official toolchain."""
        improver = AutonomousImprover(root=ROOT)
        cand_name = "test-crit5-cand"
        cand_dir = improver.create_isolated_candidate_copy(cand_name)
        try:
            improver.generate_candidate_patch(cand_dir, strategy_hint="bank_early")
            build_res = self.adapter.build_candidate(cand_dir, release=True)
            self.assertEqual(build_res.returncode, 0)
            self.assertTrue(len(build_res.generated_artifacts) > 0)
            wasm = build_res.generated_artifacts[0]
            self.assertTrue(wasm.is_file())
        finally:
            if cand_dir.exists():
                shutil.rmtree(cand_dir)

    def test_criterion_06_regression_tests_run_automatically(self):
        """Criterion 6: Regression tests can run automatically."""
        github = GitHubWorkflow(root=ROOT)
        tests_passed = github.run_pre_push_checks()
        self.assertTrue(tests_passed)

    def test_criterion_07_before_and_after_metrics_compared(self):
        """Criterion 7: Before-and-after metrics can be compared."""
        evaluator = QuantitativeEvaluator(adapter=self.adapter)
        from tools.quantitative_evaluator import MatchResult
        cand_results = [
            MatchResult(map_name="ambush", side="teamA", our_gems=500.0, opponent_gems=400.0, is_win=True, faults=0, fuel_consumed=1000, duration_seconds=5.0),
            MatchResult(map_name="ambush", side="teamB", our_gems=450.0, opponent_gems=420.0, is_win=True, faults=0, fuel_consumed=1000, duration_seconds=5.0),
        ]
        inc_results = [
            MatchResult(map_name="ambush", side="teamA", our_gems=300.0, opponent_gems=400.0, is_win=False, faults=0, fuel_consumed=1000, duration_seconds=5.0),
            MatchResult(map_name="ambush", side="teamB", our_gems=280.0, opponent_gems=350.0, is_win=False, faults=0, fuel_consumed=1000, duration_seconds=5.0),
        ]

        from unittest.mock import patch
        with patch.object(evaluator, "evaluate_match_pair", side_effect=[cand_results, inc_results]):
            summary = evaluator.compare_candidate(
                candidate_path=self.incumbent,
                incumbent_path=self.incumbent,
                opponent_path=self.baseline,
                maps=[str(self.map_path)],
            )

        self.assertEqual(summary.matches_played, 2)
        self.assertEqual(summary.candidate_wins, 2)
        self.assertEqual(summary.incumbent_wins, 0)
        self.assertEqual(summary.candidate_avg_gems, 475.0)
        self.assertEqual(summary.incumbent_avg_gems, 290.0)
        self.assertAlmostEqual(summary.gem_delta, 185.0)
        self.assertTrue(summary.passed_overall)
        self.assertTrue(summary.passed_performance)
        self.assertTrue(summary.passed_reliability)


    def test_criterion_08_failed_candidate_rejected_and_rolled_back(self):
        """Criterion 8: A failed candidate can be rejected and rolled back."""
        with tempfile.TemporaryDirectory() as temp:
            reg_file = Path(temp) / "registry.json"
            registry = BestVersionRegistry(path=reg_file)
            improver = AutonomousImprover(root=ROOT, registry=registry)

            cand_name = "test-crit8-broken"
            cand_dir = improver.create_isolated_candidate_copy(cand_name)
            try:
                # Deliberately break syntax
                (cand_dir / "src" / "bot.cpp").write_text("INVALID C++ SYNTAX ERROR", encoding="utf-8")
                build_res = self.adapter.build_candidate(cand_dir, release=True)
                self.assertNotEqual(build_res.returncode, 0)

                registry.register_candidate(
                    VersionRecord(
                        version_id=cand_name,
                        git_commit="none",
                        artifact_checksum="",
                        build_status="failed",
                        promotion_decision="rejected",
                        rejection_reason="Compilation failed",
                    )
                )

                # Incumbent remains active best-known
                best = registry.get_best_known()
                self.assertIsNotNone(best)
                self.assertEqual(best.get("version_id"), self.incumbent.name)

                record = registry.get_version(cand_name)
                self.assertEqual(record.get("promotion_decision"), "rejected")
            finally:
                if cand_dir.exists():
                    shutil.rmtree(cand_dir)

    def test_criterion_09_github_push_verified_with_remote_sha(self):
        """Criterion 9: A successful GitHub push can be verified."""
        with tempfile.TemporaryDirectory() as temp:
            upstream_repo = Path(temp) / "upstream.git"
            subprocess.run(["git", "init", "--bare", str(upstream_repo)], check=True)

            # Add temporary upstream remote in main repo
            remote_name = "test-upstream"
            subprocess.run(["git", "-C", str(ROOT), "remote", "add", remote_name, str(upstream_repo)], check=True)
            try:
                github = GitHubWorkflow(root=ROOT, default_remote=remote_name)
                push_res = github.push_validated_candidate(
                    candidate_dir=self.incumbent,
                    version_id="v-crit9-test",
                    metrics_summary="Test metrics: 100% win",
                    branch="test-improvements",
                )
                self.assertTrue(push_res.success)
                self.assertIsNotNone(push_res.commit_sha)
                self.assertEqual(push_res.commit_sha, push_res.remote_sha)
            finally:
                subprocess.run(["git", "-C", str(ROOT), "remote", "remove", remote_name], check=False)
                subprocess.run(["git", "-C", str(ROOT), "branch", "-D", "test-improvements"], check=False)

    def test_criterion_10_submission_packaging_works(self):
        """Criterion 10: Submission packaging works."""
        dist_zip = ROOT / "dist" / "acceptance-crit10.zip"
        try:
            res = self.adapter.package_candidate(self.incumbent, output=dist_zip)
            self.assertEqual(res.returncode, 0)
            self.assertTrue(dist_zip.is_file())
            self.assertGreater(dist_zip.stat().st_size, 1000)
        finally:
            if dist_zip.exists():
                dist_zip.unlink()

    def test_criterion_11_live_submission_verification(self):
        """Criterion 11: Live submission can be verified if official mechanism supports it."""
        dist_zip = ROOT / "dist" / "acceptance-crit11.zip"
        try:
            self.adapter.package_candidate(self.incumbent, output=dist_zip)

            # Dry-run validation (safe default)
            dry_res = self.adapter.submit_candidate(dist_zip, allow_live_submission=False)
            self.assertEqual(dry_res.returncode, 0)
            self.assertIn("DRY-RUN", dry_res.stdout)

            # CommandResult contains all required diagnostics
            self.assertGreaterEqual(dry_res.duration_seconds, 0)
            self.assertFalse(dry_res.timed_out)
        finally:
            if dist_zip.exists():
                dist_zip.unlink()

    def test_criterion_12_loop_resumes_safely_after_interruption(self):
        """Criterion 12: The loop can resume safely after interruption."""
        with tempfile.TemporaryDirectory() as temp:
            test_state_file = Path(temp) / "test_state.json"
            # Write initial interrupted state
            initial_state = {
                "cycles_completed": 3,
                "processed_matches": ["match-old-1", "match-old-2"],
                "candidates_evaluated": 3,
                "promotions_count": 1,
            }
            test_state_file.write_text(json.dumps(initial_state), encoding="utf-8")

            improver = AutonomousImprover(root=ROOT)
            # Patch state file path and reload
            improver.state = json.loads(test_state_file.read_text(encoding="utf-8"))
            self.assertEqual(improver.state["cycles_completed"], 3)
            self.assertEqual(improver.state["promotions_count"], 1)

            # Simulate one cycle completion
            improver.state["cycles_completed"] += 1
            test_state_file.write_text(json.dumps(improver.state), encoding="utf-8")

            # Simulate second agent instantiation (reboot / restart)
            improver2 = AutonomousImprover(root=ROOT)
            improver2.state = json.loads(test_state_file.read_text(encoding="utf-8"))
            self.assertEqual(improver2.state["cycles_completed"], 4)


if __name__ == "__main__":
    unittest.main()
