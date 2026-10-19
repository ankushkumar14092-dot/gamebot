#!/usr/bin/env python3
"""Phase 7: Quantitative Evaluation and Benchmark Engine."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cambc_adapter import CambcAdapter
from tools.match_analyzer import extract_match_metrics


DEFAULT_BENCHMARK_MAPS = [
    "maps/ambush.map26a",
]
DEFAULT_VALIDATION_MAPS = [
    "maps/contest.map26a",
    "maps/collision.map26a",
]


@dataclass
class MatchResult:
    map_name: str
    side: str
    our_gems: float
    opponent_gems: float
    is_win: bool
    faults: int
    fuel_consumed: int
    duration_seconds: float


@dataclass
class EvaluationSummary:
    candidate_id: str
    incumbent_id: str
    matches_played: int
    incumbent_avg_gems: float
    candidate_avg_gems: float
    gem_delta: float
    gem_delta_pct: float
    incumbent_wins: int
    candidate_wins: int
    incumbent_faults: int
    candidate_faults: int
    passed_reliability: bool
    passed_performance: bool
    passed_overall: bool
    rejection_reason: str | None = None
    candidate_matches: list[dict[str, Any]] = field(default_factory=list)
    incumbent_matches: list[dict[str, Any]] = field(default_factory=list)


class QuantitativeEvaluator:
    def __init__(self, adapter: CambcAdapter | None = None):
        self.adapter = adapter or CambcAdapter()

    def evaluate_match_pair(
        self,
        bot_version: str | Path,
        opponent_version: str | Path,
        map_path: str | Path,
        rounds: int | None = None,
        release: bool = True,
    ) -> list[MatchResult]:
        """Run paired matches on a single map with player sides swapped."""
        results: list[MatchResult] = []

        # Side 1: bot as teamA, opponent as teamB
        run1 = self.adapter.run_match(bot_version, opponent_version, map_path, rounds=rounds, release=release)
        stats1_path = next((p for p in run1.generated_artifacts if p.name == "statistics.json"), None)
        replay1_path = next((p for p in run1.generated_artifacts if p.suffix == ".repl26a"), None)
        if stats1_path and stats1_path.is_file():
            s1 = json.loads(stats1_path.read_text(encoding="utf-8"))
            m1 = extract_match_metrics(s1, team="teamA", replay_path=replay1_path)
            results.append(MatchResult(
                map_name=str(map_path),
                side="teamA",
                our_gems=m1.score_submitted,
                opponent_gems=m1.score_opponent,
                is_win=m1.is_win,
                faults=m1.bot_faults,
                fuel_consumed=m1.fuel_stats.total_fuel,
                duration_seconds=run1.duration_seconds,
            ))

        # Side 2: opponent as teamA, bot as teamB
        run2 = self.adapter.run_match(opponent_version, bot_version, map_path, rounds=rounds, release=release)
        stats2_path = next((p for p in run2.generated_artifacts if p.name == "statistics.json"), None)
        replay2_path = next((p for p in run2.generated_artifacts if p.suffix == ".repl26a"), None)
        if stats2_path and stats2_path.is_file():
            s2 = json.loads(stats2_path.read_text(encoding="utf-8"))
            m2 = extract_match_metrics(s2, team="teamB", replay_path=replay2_path)
            results.append(MatchResult(
                map_name=str(map_path),
                side="teamB",
                our_gems=m2.score_submitted,
                opponent_gems=m2.score_opponent,
                is_win=m2.is_win,
                faults=m2.bot_faults,
                fuel_consumed=m2.fuel_stats.total_fuel,
                duration_seconds=run2.duration_seconds,
            ))

        return results

    def compare_candidate(
        self,
        candidate_path: str | Path,
        incumbent_path: str | Path,
        opponent_path: str | Path = "bots/baseline-cpp",
        maps: list[str] | None = None,
        rounds: int | None = None,
        release: bool = True,
    ) -> EvaluationSummary:
        """Run paired evaluations of candidate vs incumbent on benchmark maps."""
        eval_maps = maps or DEFAULT_BENCHMARK_MAPS
        cand_results: list[MatchResult] = []
        inc_results: list[MatchResult] = []

        for m in eval_maps:
            cand_results.extend(self.evaluate_match_pair(candidate_path, opponent_path, m, rounds=rounds, release=release))
            inc_results.extend(self.evaluate_match_pair(incumbent_path, opponent_path, m, rounds=rounds, release=release))

        inc_matches = [asdict(r) for r in inc_results]
        cand_matches = [asdict(r) for r in cand_results]

        if not inc_results or not cand_results or len(inc_results) != len(cand_results):
            return EvaluationSummary(
                candidate_id=str(candidate_path),
                incumbent_id=str(incumbent_path),
                matches_played=0,
                incumbent_avg_gems=0.0,
                candidate_avg_gems=0.0,
                gem_delta=0.0,
                gem_delta_pct=0.0,
                incumbent_wins=0,
                candidate_wins=0,
                incumbent_faults=0,
                candidate_faults=0,
                passed_reliability=False,
                passed_performance=False,
                passed_overall=False,
                rejection_reason="Incomplete match runs or missing statistics",
                candidate_matches=cand_matches,
                incumbent_matches=inc_matches,
            )

        inc_gems = sum(r.our_gems for r in inc_results) / len(inc_results)
        cand_gems = sum(r.our_gems for r in cand_results) / len(cand_results)
        inc_wins = sum(1 for r in inc_results if r.is_win)
        cand_wins = sum(1 for r in cand_results if r.is_win)
        inc_faults = sum(r.faults for r in inc_results)
        cand_faults = sum(r.faults for r in cand_results)

        gem_delta = cand_gems - inc_gems
        gem_delta_pct = (gem_delta / inc_gems * 100) if inc_gems > 0 else 0.0

        # Gates
        passed_reliability = (cand_faults <= inc_faults) and (cand_faults == 0)
        passed_performance = (cand_gems > inc_gems) and (cand_wins >= inc_wins)

        rejection_reason = None
        if not passed_reliability:
            rejection_reason = f"Reliability gate failed: candidate produced {cand_faults} faults (incumbent: {inc_faults})"
        elif not passed_performance:
            if cand_gems <= inc_gems:
                rejection_reason = f"Performance gate failed: candidate avg gems {cand_gems:.1f} <= incumbent {inc_gems:.1f} (delta {gem_delta:+.1f})"
            elif cand_wins < inc_wins:
                rejection_reason = f"Performance gate failed: candidate wins {cand_wins} < incumbent {inc_wins}"

        passed_overall = passed_reliability and passed_performance

        return EvaluationSummary(
            candidate_id=str(candidate_path),
            incumbent_id=str(incumbent_path),
            matches_played=len(cand_results),
            incumbent_avg_gems=inc_gems,
            candidate_avg_gems=cand_gems,
            gem_delta=gem_delta,
            gem_delta_pct=gem_delta_pct,
            incumbent_wins=inc_wins,
            candidate_wins=cand_wins,
            incumbent_faults=inc_faults,
            candidate_faults=cand_faults,
            passed_reliability=passed_reliability,
            passed_performance=passed_performance,
            passed_overall=passed_overall,
            rejection_reason=rejection_reason,
            candidate_matches=cand_matches,
            incumbent_matches=inc_matches,
        )
