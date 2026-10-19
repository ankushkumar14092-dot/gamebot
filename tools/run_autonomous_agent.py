#!/usr/bin/env python3
"""Phase 12: Observability, Scheduling, and Operations CLI for Autonomous CAMBC Bot System."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.autonomous_improver import AutonomousImprover
from tools.best_version_registry import BestVersionRegistry
from tools.cambc_adapter import CambcAdapter
from tools.match_analyzer import extract_match_metrics, generate_structured_report



def cmd_status(args: argparse.Namespace) -> int:
    registry = BestVersionRegistry()
    best = registry.get_best_known()
    print("=== CAMBC Autonomous Bot System Status ===")
    if best:
        print(f"Current Best-Known Version: {best.get('version_id')}")
        print(f"  Git Commit: {best.get('git_commit')}")
        print(f"  Artifact Checksum: {best.get('artifact_checksum')[:16]}...")
        print(f"  Build Status: {best.get('build_status')}")
        print(f"  Promotion Decision: {best.get('promotion_decision')}")
        print(f"  Last Updated: {best.get('timestamp')}")
    else:
        print("No best-known version registered yet.")

    print(f"\nTotal Registered Versions: {len(registry.data.get('versions', {}))}")
    print("\nRecent Candidate History:")
    for h in registry.data.get("history", [])[-5:]:
        print(f"  - {h.get('version_id')} -> {h.get('decision')} at {h.get('timestamp')}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    improver = AutonomousImprover(
        max_candidates_per_cycle=args.max_candidates,
        benchmark_rounds=args.rounds,
        allow_live_submission=args.allow_live_submission,
    )

    cycles = args.cycles
    interval = args.interval
    print(f"Starting {cycles} autonomous improvement cycle(s) (interval: {interval}s)...")

    for i in range(cycles):
        print(f"\n>>> Cycle {i + 1}/{cycles} <<<")
        result = improver.run_cycle(map_name=args.map)
        print(f"Cycle outcome: {result.get('status')}")

        if i + 1 < cycles:
            print(f"Waiting {interval} seconds before next cycle...")
            time.sleep(interval)

    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    stats_path = Path(args.statistics)
    if not stats_path.is_file():
        print(f"Error: Statistics file {stats_path} not found.", file=sys.stderr)
        return 1

    replay_path = Path(args.replay) if args.replay else None
    data = json.loads(stats_path.read_text(encoding="utf-8"))
    metrics = extract_match_metrics(data, team=args.team, replay_path=replay_path)

    if args.json:
        from dataclasses import asdict
        print(json.dumps(asdict(metrics), indent=2))
    else:
        print(generate_structured_report(metrics))

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    p_status = subparsers.add_parser("status", help="View current system and best-version status")
    p_status.set_defaults(func=cmd_status)

    # run
    p_run = subparsers.add_parser("run", help="Run autonomous improvement cycles")
    p_run.add_argument("--cycles", type=int, default=1, help="Number of cycles to run (default: 1)")
    p_run.add_argument("--interval", type=int, default=10, help="Seconds to wait between cycles (default: 10)")
    p_run.add_argument("--max-candidates", type=int, default=1, help="Max candidates per cycle (default: 1)")
    p_run.add_argument("--rounds", type=int, default=None, help="Optional max rounds per match for fast benchmarking")
    p_run.add_argument("--map", default="maps/ambush.map26a", help="Map for evaluation matches")
    p_run.add_argument("--allow-live-submission", action="store_true", help="Enable actual live upload to CAMBC platform")
    p_run.set_defaults(func=cmd_run)

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Analyze match statistics and replay")
    p_analyze.add_argument("statistics", help="Path to statistics.json")
    p_analyze.add_argument("--replay", help="Optional path to .repl26a file")
    p_analyze.add_argument("--team", default="teamA", choices=["teamA", "teamB"], help="Team side")
    p_analyze.add_argument("--json", action="store_true", help="Output JSON instead of markdown")
    p_analyze.set_defaults(func=cmd_analyze)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
