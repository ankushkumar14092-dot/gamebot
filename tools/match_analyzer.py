#!/usr/bin/env python3
"""Phase 3 & 4: Structured match data, replay analysis, and autonomous debugging pipeline."""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FuelStats:
    total_fuel: int = 0
    record_count: int = 0
    max_fuel_turn: int = 0
    min_fuel_turn: int = 0
    average_fuel_turn: float = 0.0


@dataclass
class MatchMetrics:
    match_id: str = "unknown"
    map_name: str = "unknown"
    seed: str = "unknown"
    team: str = "teamA"
    opponent_team: str = "teamB"
    winner: str = "unknown"
    is_win: bool = False
    rounds_completed: int = 0
    score_submitted: float = 0.0
    score_opponent: float = 0.0
    gems_collected: float = 0.0
    gems_lost: float = 0.0
    carried_at_death_max: float = 0.0
    time_to_first_tribute_round: int | None = None
    camps_cleared: int = 0
    kills: int = 0
    deaths: int = 0
    recalls_attempted: int = 0
    recalls_interrupted: int = 0
    upgrades_purchased: int = 0
    bot_faults: int = 0
    failed_actions_count: int = 0
    fuel_exhausted_events: int = 0
    fuel_stats: FuelStats = field(default_factory=FuelStats)
    event_counts: dict[str, int] = field(default_factory=dict)
    runtime_issues: list[str] = field(default_factory=list)
    turning_points: list[dict[str, Any]] = field(default_factory=list)


def parse_fuel_binary(data: bytes) -> FuelStats:
    """Decode CAMBC fuel binary format: magic 'fuel26a\\0', uint32 version, uint64 records."""
    if len(data) < 28:
        return FuelStats()
    # Check for 'a62leuf\0' or 'fuel26a\0'
    magic = data[:8]
    if b"leuf" not in magic and b"fuel" not in magic:
        return FuelStats()

    # Records start at offset 12 (or after header)
    # Each record represents fuel consumed in a step / turn as uint64
    stats = FuelStats()
    turn_values: list[int] = []
    # Scan uint64 values
    offset = 12
    while offset + 8 <= len(data):
        val = struct.unpack("<Q", data[offset : offset + 8])[0]
        offset += 8
        # Filter reasonable fuel numbers (< 100,000,000)
        if 0 < val < 100_000_000:
            turn_values.append(val)

    if turn_values:
        stats.total_fuel = sum(turn_values)
        stats.record_count = len(turn_values)
        stats.max_fuel_turn = max(turn_values)
        stats.min_fuel_turn = min(turn_values)
        stats.average_fuel_turn = stats.total_fuel / len(turn_values)

    return stats


def extract_match_metrics(stats_data: dict[str, Any], team: str = "teamA", replay_path: Path | None = None) -> MatchMetrics:
    opponent = "teamB" if team == "teamA" else "teamA"
    match_info = stats_data.get("match", {})
    metrics = MatchMetrics(
        match_id=str(match_info.get("matchId") or "local-match"),
        map_name=str(match_info.get("map") or "unknown"),
        seed=str(match_info.get("seed") or "unknown"),
        team=team,
        opponent_team=opponent,
        winner=str(match_info.get("outcome") or "unknown"),
        is_win=str(match_info.get("outcome")) == team,
        rounds_completed=int(match_info.get("roundsCompleted") or 0),
    )

    # Team scores
    for t in stats_data.get("teams", []):
        if t.get("team") == team:
            metrics.score_submitted = float(t.get("submittedGems", 0))
        elif t.get("team") == opponent:
            metrics.score_opponent = float(t.get("submittedGems", 0))

    # Champion aggregates
    for ch in stats_data.get("champions", []):
        ch_team = ch.get("team")
        ch_metrics = ch.get("metrics") or {}
        if ch_team == team:
            metrics.gems_collected += float(ch_metrics.get("collectedGems", 0))
            metrics.kills += int(ch_metrics.get("kills", 0))
            metrics.deaths += int(ch_metrics.get("deaths", 0))

    # Diagnostics
    diag = stats_data.get("diagnostics") or {}
    metrics.bot_faults = int((diag.get("botFaults") or {}).get(team, 0) or 0)
    for code in diag.get("codes", []):
        metrics.runtime_issues.append(f"Diagnostic code: {code}")

    # Event analysis
    counts: Counter[str] = Counter()
    turning_points: list[dict[str, Any]] = []

    def get_owner_team(owner: Any) -> str | None:
        if isinstance(owner, dict):
            return owner.get("team")
        return owner if isinstance(owner, str) else None

    for ev in stats_data.get("events", []):
        ev_team = get_owner_team(ev.get("owner"))
        kind = str(ev.get("kind", "unknown"))
        entries = ev.get("entries") or []
        entry_count = len(entries) if entries else 1

        if ev_team == team:
            counts[kind] += entry_count
            if kind == "fuelExhausted":
                metrics.fuel_exhausted_events += entry_count
            elif kind == "campClear":
                metrics.camps_cleared += entry_count
            elif kind in {"buyItem", "buyConsumable"}:
                metrics.upgrades_purchased += entry_count
            elif kind == "recall":
                metrics.recalls_attempted += entry_count
            elif kind == "gemSubmission" and metrics.time_to_first_tribute_round is None and entries:
                first_round = (entries[0].get("timestamp") or {}).get("round")
                if first_round is not None:
                    metrics.time_to_first_tribute_round = int(first_round)

            # Check turning points: death, gemLoss, botFault
            if kind in {"death", "gemLoss", "botFault"}:
                for entry in entries[-5:]:
                    round_num = (entry.get("timestamp") or {}).get("round", "?")
                    turning_points.append({
                        "kind": kind,
                        "round": round_num,
                        "x": entry.get("x"),
                        "y": entry.get("y"),
                        "detail": entry.get("target") or entry.get("context") or "",
                    })

    metrics.event_counts = dict(counts)
    metrics.turning_points = turning_points

    # Replay logs and fuel
    if replay_path and replay_path.is_file():
        try:
            with zipfile.ZipFile(replay_path) as z:
                side_letter = "a" if team == "teamA" else "b"
                fuel_name = f"team-{side_letter}.fuel"
                if fuel_name in z.namelist():
                    metrics.fuel_stats = parse_fuel_binary(z.read(fuel_name))

                stdout_name = f"team-{side_letter}.stdout"
                debug_name = f"team-{side_letter}.debug"
                combined_log = ""
                if stdout_name in z.namelist():
                    combined_log += z.read(stdout_name).decode("utf-8", "replace") + "\n"
                if debug_name in z.namelist():
                    combined_log += z.read(debug_name).decode("utf-8", "replace") + "\n"

                # Check for log signals
                for line in combined_log.splitlines():
                    line_str = line.strip()
                    if re.search(r"fault|trap|abort|unreachable|error 22|error 97|error 5", line_str, re.I):
                        metrics.runtime_issues.append(line_str)
                    if "invalid_action" in line_str or "bad_destination" in line_str:
                        metrics.failed_actions_count += 1
        except Exception as exc:
            metrics.runtime_issues.append(f"Failed to read replay bundle: {exc}")

    return metrics


def generate_structured_report(metrics: MatchMetrics) -> str:
    """Generate the comprehensive 9-section match analysis report required by Phase 3."""
    gap = metrics.score_submitted - metrics.score_opponent
    status = "WIN" if metrics.is_win else "LOSS"

    lines = [
        f"# CAMBC Match Analysis Report: {metrics.match_id}",
        "",
        "## 1. Match Summary",
        f"- **Outcome**: {status} (Winner: {metrics.winner})",
        f"- **Map**: {metrics.map_name} (Seed: {metrics.seed})",
        f"- **Rounds Completed**: {metrics.rounds_completed}",
        f"- **Score**: {metrics.score_submitted:g} gems (Opponent: {metrics.score_opponent:g}; Differential: {gap:+g})",
        f"- **Champion Kills / Deaths**: {metrics.kills} / {metrics.deaths}",
        f"- **Bot Faults**: {metrics.bot_faults}",
        f"- **Fuel Consumed**: {metrics.fuel_stats.total_fuel:,} units across {metrics.fuel_stats.record_count} records",
        f"- **Fuel Exhausted Events**: {metrics.fuel_exhausted_events}",
        "",
        "## 2. Major Turning Points",
    ]

    if metrics.turning_points:
        for tp in metrics.turning_points[:8]:
            pos = f"at ({tp.get('x')}, {tp.get('y')})" if tp.get("x") is not None else ""
            lines.append(f"- Round {tp.get('round')}: `{tp.get('kind')}` {pos} {tp.get('detail')}".strip())
    else:
        lines.append("- No abrupt death or gem-loss turning points recorded.")

    lines += [
        "",
        "## 3. Resource and Scoring Efficiency",
        f"- **Total Gems Collected**: {metrics.gems_collected:g}",
        f"- **Total Gems Tributed**: {metrics.score_submitted:g}",
        f"- **Deposit Efficiency**: {(metrics.score_submitted / metrics.gems_collected * 100 if metrics.gems_collected > 0 else 0.0):.1f}%",
        f"- **Time to First Tribute**: {f'Round {metrics.time_to_first_tribute_round}' if metrics.time_to_first_tribute_round is not None else 'None (no gems tributed)'}",
        f"- **Camps Cleared**: {metrics.camps_cleared}",
        f"- **Items / Upgrades Purchased**: {metrics.upgrades_purchased}",
        "",
        "## 4. Combat and Movement Inefficiencies",
        f"- **Failed / Rejected Actions**: {metrics.failed_actions_count}",
        f"- **Deaths Under Threat**: {metrics.deaths}",
        f"- **Recall Attempts / Interruptions**: {metrics.recalls_attempted} attempts",
    ]

    lines += [
        "",
        "## 5. Suspected Root Causes",
    ]
    if metrics.bot_faults > 0:
        lines.append(f"- **High Severity Defect**: Diagnostics reported {metrics.bot_faults} bot fault(s). Pre-action validations must prevent invalid engine calls.")
    elif not metrics.is_win:
        if metrics.gems_collected > metrics.score_submitted + 22:
            lines.append(f"- **Tribute Latency**: Collected {metrics.gems_collected} gems but only banked {metrics.score_submitted}. Bot held gems too long before depositing.")
        if metrics.deaths >= 3:
            lines.append(f"- **Combat Overextension**: Suffered {metrics.deaths} deaths, reducing farming uptime and dropping carried resources.")
        if metrics.score_submitted < metrics.score_opponent:
            lines.append(f"- **Objective Pace**: Opponent established faster altar throughput ({metrics.score_opponent:g} vs {metrics.score_submitted:g}).")
    else:
        lines.append("- **Successful Performance**: bot maintained solid gem farming and tribute efficiency.")

    lines += [
        "",
        "## 6. Supporting Replay Events or Log Evidence",
    ]
    if metrics.runtime_issues:
        for issue in metrics.runtime_issues[:6]:
            lines.append(f"- Log warning: `{issue}`")
    else:
        lines.append("- No runtime engine traps, crashes, or unhandled exceptions recorded.")

    lines += [
        "",
        "## 7. Recommended Fixes",
    ]
    if metrics.bot_faults > 0:
        lines.append("- Inspect API preconditions for failing operations; insert defensive bounds check.")
    elif not metrics.is_win:
        if metrics.gems_collected > metrics.score_submitted + 22:
            lines.append("- Adjust banking threshold (`kGemBankThreshold`) from 44 to 22 gems to bank earlier.")
        if metrics.deaths >= 3:
            lines.append("- Increase retreat health threshold (`kGemBankHealthFraction`) or disengage earlier.")
        else:
            lines.append("- Optimize camp routing and altar approach bitboard to reduce path oscillation.")
    else:
        lines.append("- Maintain baseline configuration; use this match as an incumbent control.")

    lines += [
        "",
        "## 8. Confidence and Uncertainty",
        f"- **Confidence Level**: {'Medium-High' if metrics.rounds_completed > 500 else 'Low-Medium (short match)'}",
        "- **Uncertainty Note**: Replay telemetry exposes aggregated timeline and event samples; binary replay view needed for micro-step inspection.",
        "",
        "## 9. Required Validation Tests",
        "- Multi-round local match with opponent position symmetry (sides swapped).",
        "- Regression check against `bots/baseline-cpp` on standard map pool.",
        "- Verification that bot faults remain at exactly 0.",
        "",
    ]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("statistics", type=Path, help="Path to statistics JSON")
    parser.add_argument("--replay", type=Path, help="Path to .repl26a replay file")
    parser.add_argument("--team", default="teamA", choices=["teamA", "teamB"], help="Team side (default: teamA)")
    parser.add_argument("--json", action="store_true", help="Output metrics as JSON")
    args = parser.parse_args()

    if not args.statistics.is_file():
        print(f"File not found: {args.statistics}", file=sys.stderr)
        return 1

    stats_data = json.loads(args.statistics.read_text(encoding="utf-8"))
    metrics = extract_match_metrics(stats_data, team=args.team, replay_path=args.replay)

    if args.json:
        print(json.dumps(asdict(metrics), indent=2))
    else:
        print(generate_structured_report(metrics))

    return 0


if __name__ == "__main__":
    sys.exit(main())
