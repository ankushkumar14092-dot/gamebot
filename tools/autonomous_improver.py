#!/usr/bin/env python3
"""Phase 11: Autonomous CAMBC Bot Engineering and Optimisation Loop."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.best_version_registry import BestVersionRegistry, VersionRecord
from tools.cambc_adapter import CambcAdapter
from tools.github_workflow import GitHubWorkflow
from tools.match_analyzer import extract_match_metrics, generate_structured_report
from tools.quantitative_evaluator import QuantitativeEvaluator

STATE_FILE = ROOT / "matches" / "autonomous_loop_state.json"


class AutonomousImprover:
    def __init__(
        self,
        root: Path = ROOT,
        incumbent_dir: str | Path = "bots/submission-v6",
        opponent_dir: str | Path = "bots/baseline-cpp",
        adapter: CambcAdapter | None = None,
        registry: BestVersionRegistry | None = None,
        max_candidates_per_cycle: int = 1,
        benchmark_rounds: int | None = None,
        allow_live_submission: bool = False,
    ):
        self.root = Path(root).resolve()
        self.incumbent_dir = (self.root / incumbent_dir).resolve() if not Path(incumbent_dir).is_absolute() else Path(incumbent_dir)
        self.opponent_dir = (self.root / opponent_dir).resolve() if not Path(opponent_dir).is_absolute() else Path(opponent_dir)
        self.adapter = adapter or CambcAdapter(root=self.root)
        self.registry = registry or BestVersionRegistry(self.root / "best_version_registry.json")
        self.evaluator = QuantitativeEvaluator(adapter=self.adapter)
        self.github = GitHubWorkflow(root=self.root)
        self.max_candidates_per_cycle = max_candidates_per_cycle
        self.benchmark_rounds = benchmark_rounds
        self.allow_live_submission = allow_live_submission
        self.state: dict[str, Any] = {
            "cycles_completed": 0,
            "processed_matches": [],
            "candidates_evaluated": 0,
            "promotions_count": 0,
            "last_cycle_timestamp": None,
        }
        self.load_state()

        # Initialize incumbent in registry if not present
        if not self.registry.get_best_known():
            inc_checksum = self.registry.calculate_artifact_checksum(self.incumbent_dir / "src")
            self.registry.register_candidate(
                VersionRecord(
                    version_id=self.incumbent_dir.name,
                    git_commit=self._get_head_commit(),
                    artifact_checksum=inc_checksum,
                    build_status="success",
                    promotion_decision="incumbent",
                    changes_introduced="Repository baseline incumbent bot",
                )
            )
            self.registry.promote_version(self.incumbent_dir.name)

    def load_state(self) -> None:
        if STATE_FILE.is_file():
            try:
                self.state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    def save_state(self) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def _get_head_commit(self) -> str:
        res = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"], capture_output=True, text=True)
        return res.stdout.strip() if res.returncode == 0 else "unknown"

    def create_isolated_candidate_copy(self, candidate_name: str) -> Path:
        """Create a dedicated, isolated candidate directory with its own git branch."""
        exp_dir = self.root / "bots" / "experiments" / "auto" / candidate_name
        if exp_dir.exists():
            shutil.rmtree(exp_dir)
        exp_dir.mkdir(parents=True, exist_ok=True)

        # Copy source files from incumbent
        shutil.copytree(self.incumbent_dir / "src", exp_dir / "src")

        # Initialize isolated git repository and candidate branch
        subprocess.run(["git", "init", str(exp_dir)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(exp_dir), "add", "src"], check=True, capture_output=True)
        subprocess.run([
            "git", "-C", str(exp_dir),
            "-c", "user.name=CAMBC Candidate",
            "-c", "user.email=candidate@localhost",
            "commit", "-m", f"baseline: cloned from {self.incumbent_dir.name}",
        ], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(exp_dir), "checkout", "-b", "candidate"], check=True, capture_output=True)

        return exp_dir

    def generate_candidate_patch(self, candidate_dir: Path, strategy_hint: str = "bank_early") -> str:
        """Apply a targeted source patch on the isolated candidate branch."""
        bot_cpp = candidate_dir / "src" / "bot.cpp"
        content = bot_cpp.read_text(encoding="utf-8")

        description = ""
        if strategy_hint == "bank_early":
            # Adjust banking threshold from 44 to 22, or 22 to 33
            if "constexpr int kGemBankThreshold = 22;" in content:
                content = content.replace("constexpr int kGemBankThreshold = 22;", "constexpr int kGemBankThreshold = 18;")
                description = "Optimized kGemBankThreshold to 18 for faster banking turnaround"
            elif "constexpr int kGemBankThreshold = 44;" in content:
                content = content.replace("constexpr int kGemBankThreshold = 44;", "constexpr int kGemBankThreshold = 22;")
                description = "Reduced kGemBankThreshold to 22 to prevent carried gem loss"
            else:
                content = content.replace("constexpr float kGemBankHealthFraction = 0.70f;", "constexpr float kGemBankHealthFraction = 0.80f;")
                description = "Increased kGemBankHealthFraction to 0.80 to prioritize health before banking"
        elif strategy_hint == "health_retreat":
            content = content.replace("constexpr float kGemBankHealthFraction = 0.70f;", "constexpr float kGemBankHealthFraction = 0.85f;")
            description = "Adjusted kGemBankHealthFraction to 0.85 for safer combat retreat"
        else:
            description = "No strategy change applied"

        bot_cpp.write_text(content, encoding="utf-8")

        # Commit inside the candidate git repository
        subprocess.run(["git", "-C", str(candidate_dir), "add", "src"], check=True, capture_output=True)
        subprocess.run([
            "git", "-C", str(candidate_dir),
            "-c", "user.name=CAMBC Candidate",
            "-c", "user.email=candidate@localhost",
            "commit", "-m", f"candidate patch: {description}",
        ], check=True, capture_output=True)

        return description

    def run_cycle(self, map_name: str = "maps/ambush.map26a") -> dict[str, Any]:
        """Execute one complete autonomous engineering cycle."""
        cycle_start = datetime.now(timezone.utc)
        cycle_id = cycle_start.strftime("%Y%m%dT%H%M%SZ")
        print(f"\n=== Starting Autonomous Optimization Cycle {cycle_id} ===")

        # 1. Run local baseline match to collect latest performance data
        print(f"Step 1: Running baseline match against {self.opponent_dir.name} on {map_name}...")
        baseline_res = self.adapter.run_match(
            self.incumbent_dir,
            self.opponent_dir,
            map_name,
            rounds=self.benchmark_rounds,
            release=True,
        )
        if baseline_res.returncode != 0:
            print(f"Baseline match failed with returncode {baseline_res.returncode}: {baseline_res.stderr}")
            return {"status": "error", "message": "Baseline match failed"}

        stats_path = next((p for p in baseline_res.generated_artifacts if p.name == "statistics.json"), None)
        replay_path = next((p for p in baseline_res.generated_artifacts if p.suffix == ".repl26a"), None)

        if not stats_path or not stats_path.is_file():
            print("Warning: Completed match did not generate statistics JSON.")
            return {"status": "error", "message": "No statistics generated"}

        # 2. Analyze match telemetry and replay
        print("Step 2: Analyzing match telemetry and replay...")
        stats_data = json.loads(stats_path.read_text(encoding="utf-8"))
        metrics = extract_match_metrics(stats_data, team="teamA", replay_path=replay_path)
        report = generate_structured_report(metrics)

        # Save analysis report
        report_file = self.root / "matches" / "local" / f"analysis_{cycle_id}.md"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
        print(f"Match report written to: {report_file}")

        # 3. Generate candidate on isolated branch
        cand_name = f"candidate-{cycle_id}"
        print(f"Step 3: Creating isolated candidate branch '{cand_name}'...")
        cand_dir = self.create_isolated_candidate_copy(cand_name)

        # Determine strategy hint from analysis
        hint = "bank_early" if metrics.gems_collected > metrics.score_submitted + 22 else "health_retreat"
        patch_desc = self.generate_candidate_patch(cand_dir, strategy_hint=hint)
        print(f"Applied candidate patch: {patch_desc}")

        # 4. Compile candidate
        print("Step 4: Compiling candidate bot with official toolchain...")
        build_res = self.adapter.build_candidate(cand_dir, release=True)
        build_success = (build_res.returncode == 0)
        cand_checksum = self.registry.calculate_artifact_checksum(cand_dir / "src")

        if not build_success:
            print(f"Compilation failed for candidate {cand_name} (exit {build_res.returncode}): {build_res.stderr}")
            self.registry.register_candidate(
                VersionRecord(
                    version_id=cand_name,
                    git_commit=self._get_head_commit(),
                    artifact_checksum=cand_checksum,
                    build_status="failed",
                    promotion_decision="rejected",
                    rejection_reason=f"Compilation failed: {build_res.stderr.strip()}",
                    changes_introduced=patch_desc,
                )
            )
            return {"status": "rejected", "reason": "compilation_failed", "candidate": cand_name}

        print("Compilation succeeded!")

        # 5. Run regression tests
        print("Step 5: Running pre-evaluation regression test suite...")
        unit_test_res = subprocess.run(
            [str(self.root / ".venv" / "bin" / "python"), "-m", "unittest", "discover", "tests"],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )
        if unit_test_res.returncode != 0:
            print(f"Regression tests failed: {unit_test_res.stderr}")
            self.registry.register_candidate(
                VersionRecord(
                    version_id=cand_name,
                    git_commit=self._get_head_commit(),
                    artifact_checksum=cand_checksum,
                    build_status="success",
                    promotion_decision="rejected",
                    rejection_reason="Regression tests failed",
                    changes_introduced=patch_desc,
                )
            )
            return {"status": "rejected", "reason": "regression_test_failure", "candidate": cand_name}

        # 6. Quantitative benchmark evaluation
        print(f"Step 6: Running paired quantitative benchmark against incumbent on {map_name}...")
        eval_summary = self.evaluator.compare_candidate(
            candidate_path=cand_dir,
            incumbent_path=self.incumbent_dir,
            opponent_path=self.opponent_dir,
            maps=[map_name],
            rounds=self.benchmark_rounds,
            release=True,
        )

        print(f"Benchmark Results:")
        print(f"  Incumbent Avg Gems: {eval_summary.incumbent_avg_gems:.1f} (Wins: {eval_summary.incumbent_wins})")
        print(f"  Candidate Avg Gems: {eval_summary.candidate_avg_gems:.1f} (Wins: {eval_summary.candidate_wins})")
        print(f"  Delta: {eval_summary.gem_delta:+.1f} gems ({eval_summary.gem_delta_pct:+.1f}%)")
        print(f"  Bot Faults: {eval_summary.candidate_faults}")
        print(f"  Overall Passed: {eval_summary.passed_overall}")

        version_record = VersionRecord(
            version_id=cand_name,
            git_commit=self._get_head_commit(),
            artifact_checksum=cand_checksum,
            build_status="success",
            evaluation_metrics=asdict(eval_summary),
            runtime_error_counts=eval_summary.candidate_faults,
            changes_introduced=patch_desc,
        )

        # 7. Promotion decision
        if not eval_summary.passed_overall:
            print(f"Step 7: Candidate REJECTED. Reason: {eval_summary.rejection_reason}")
            version_record.promotion_decision = "rejected"
            version_record.rejection_reason = eval_summary.rejection_reason
            self.registry.register_candidate(version_record)
            self.state["candidates_evaluated"] += 1
            self.save_state()
            return {"status": "rejected", "reason": eval_summary.rejection_reason, "candidate": cand_name}

        print("Step 7: Candidate PROMOTED! Passed all reliability and performance gates.")
        version_record.promotion_decision = "promoted"
        self.registry.register_candidate(version_record)
        self.registry.promote_version(cand_name)

        # 8. Package artifact
        print("Step 8: Packaging candidate bundle...")
        dist_zip = self.root / "dist" / f"{cand_name}.zip"
        pkg_res = self.adapter.package_candidate(cand_dir, output=dist_zip)
        print(f"Candidate packaged into: {dist_zip} (size: {dist_zip.stat().st_size if dist_zip.exists() else 0} bytes)")

        # 9. Automated Git / GitHub Push
        print("Step 9: Pushing candidate to Git / GitHub...")
        push_res = self.github.push_validated_candidate(
            candidate_dir=cand_dir,
            version_id=cand_name,
            metrics_summary=f"Avg gems: {eval_summary.candidate_avg_gems:.1f} (+{eval_summary.gem_delta:.1f})",
            branch="improvements",
        )
        print(f"Git push status: success={push_res.success}, commit={push_res.commit_sha}, error={push_res.error}")
        version_record.push_status = asdict(push_res)
        self.registry.register_candidate(version_record)

        # 10. CAMBC submission
        print(f"Step 10: Submitting candidate (live_allowed={self.allow_live_submission})...")
        sub_res = self.adapter.submit_candidate(dist_zip, allow_live_submission=self.allow_live_submission)
        print(f"Submission status: {sub_res.stdout.strip()}")

        self.state["cycles_completed"] += 1
        self.state["candidates_evaluated"] += 1
        self.state["promotions_count"] += 1
        self.state["last_cycle_timestamp"] = cycle_start.isoformat()
        self.save_state()

        return {
            "status": "promoted",
            "candidate": cand_name,
            "metrics": asdict(eval_summary),
            "push_status": asdict(push_res),
            "submission_status": sub_res.stdout.strip(),
        }
