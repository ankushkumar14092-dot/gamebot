#!/usr/bin/env python3
"""Create an evidence-based review of a local CAMBC match export.

Usage:
    python3 tools/review_match.py match.json [--replay path.repl26a] [--team teamA]

The JSON is the readable statistics export produced by `cambc run --statistics
FILE --json` or by a run-batch manifest row. Replay bundles add bot logs. This
tool reports hypotheses and experiments; it does not patch bot strategy.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def metric_for_team(data: dict[str, Any], team: str, metric: str) -> float | None:
    for row in data.get("teams", []):
        if row.get("team") == team and metric in row:
            return number(row[metric])
    # Some exports keep metrics only in the team timeline.
    for row in data.get("teamTimelines", []):
        if row.get("metric") == metric and row.get("owner") == team:
            runs = row.get("runs", [])
            return number(runs[-1].get("value")) if runs else 0.0
    return None


def champion_rows(data: dict[str, Any], team: str) -> list[dict[str, Any]]:
    return [row for row in data.get("champions", []) if row.get("team") == team]


def event_counts(data: dict[str, Any], team: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for event in data.get("events", []):
        owner = event.get("owner") or {}
        if owner.get("team") == team:
            counts[str(event.get("kind", "unknown"))] += len(event.get("entries", [])) or 1
    return counts


def event_entries(data: dict[str, Any], team: str, kinds: set[str]) -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    for event in data.get("events", []):
        owner = event.get("owner") or {}
        if owner.get("team") != team or event.get("kind") not in kinds:
            continue
        for entry in event.get("entries", []):
            found.append((str(event["kind"]), entry))
    return sorted(found, key=lambda item: (item[1].get("timestamp") or {}).get("ordinal", 0))


def replay_logs(path: Path, team: str) -> dict[str, Any]:
    side = "a" if team == "teamA" else "b"
    result: dict[str, Any] = {"debug": "", "stdout": "", "fuel_bytes": 0, "members": []}
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            result["members"] = names
            for kind in ("debug", "stdout"):
                name = f"team-{side}.{kind}"
                if name in names:
                    # Logs may contain NUL padding between invocation records.
                    raw = archive.read(name).replace(b"\x00", b"\n")
                    result[kind] = raw.decode("utf-8", "replace")
            fuel_name = f"team-{side}.fuel"
            if fuel_name in names:
                result["fuel_bytes"] = len(archive.read(fuel_name))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Cannot read replay bundle {path}: {exc}") from exc
    return result


def log_signals(logs: dict[str, Any]) -> dict[str, Any]:
    combined = logs["debug"] + "\n" + logs["stdout"]
    fault_lines = [line.strip() for line in combined.splitlines()
                   if re.search(r"fault|trap|fuel|out.of.fuel|unreachable|abort", line, re.I)]
    context_lines = [line.strip() for line in combined.splitlines()
                     if "bot context:" in line]
    repeated = Counter(context_lines)
    return {
        "fault_lines": fault_lines[:12],
        "context_lines": context_lines[:12],
        "repeated_context": [(line, count) for line, count in repeated.most_common(5) if count > 1],
    }


def review(data: dict[str, Any], team: str, logs: dict[str, Any] | None) -> str:
    match = data.get("match", {})
    outcome = match.get("outcome", "unknown")
    rounds = match.get("roundsCompleted", "unknown")
    score = metric_for_team(data, team, "submittedGems")
    other = "teamB" if team == "teamA" else "teamA"
    opponent_score = metric_for_team(data, other, "submittedGems")
    collected = sum(number(row.get("metrics", {}).get("collectedGems"))
                    for row in champion_rows(data, team))
    deaths = sum(number(row.get("metrics", {}).get("deaths"))
                 for row in champion_rows(data, team))
    faults = (data.get("diagnostics", {}).get("botFaults", {}) or {}).get(team, 0)
    counts = event_counts(data, team)

    lines = ["# Match review", "", f"- **Team:** {team}",
             f"- **Outcome:** {outcome}", f"- **Rounds completed:** {rounds}"]
    if score is not None and opponent_score is not None:
        lines += [f"- **Submitted gems:** {score:g} (opponent {opponent_score:g}; gap {score - opponent_score:+g})"]
    if collected:
        lines.append(f"- **Collected gems:** {collected:g}")
    lines += [f"- **Champion deaths:** {deaths:g}", f"- **Bot faults:** {faults}", "", "## Evidence and hypotheses", ""]

    if outcome != team and score is not None and opponent_score is not None:
        gap = opponent_score - score
        lines.append(f"- **Primary result:** the opponent submitted {gap:g} more gems. The replay can show what happened, but this score alone does not identify the cause.")
        if collected > 0 and score < collected:
            fraction = score / collected
            lines.append(f"- **Delivery hypothesis:** {fraction:.0%} of lifetime collected gems were submitted. Review the endgame and death moments for time spent carrying gems, altar access, or lost bags; this ratio is a clue, not proof that the difference was dropped.")
        if deaths >= 4:
            lines.append(f"- **Survival hypothesis:** {deaths:g} deaths may have reduced farming time. Inspect the event timeline around deaths and compare gems carried, nearby enemy pressure, and the next respawn before changing combat behavior.")
        if gap <= 100:
            lines.append("- **Close-match hypothesis:** the score gap is small. Check whether draft, purchases, or one high-value fight could explain the result before changing the general farming policy.")
    elif outcome == team:
        lines.append("- This was a win. Use it as a comparison baseline; avoid treating a single win as proof that every strategy choice is optimal.")
    else:
        lines.append("- The export does not identify a clear result and score pair. Confirm the statistics file belongs to the intended replay.")

    notable = {k: counts[k] for k in ("death", "kill", "buyItem", "buyConsumable", "gemSubmission", "gemLoss", "recall") if counts[k]}
    if notable:
        lines.append(f"- **Recorded event entries:** {', '.join(f'{k}={v}' for k, v in notable.items())}.")
    turning_points = event_entries(data, team, {"death", "gemLoss"})
    if turning_points:
        lines += ["", "## Death and gem-loss moments", ""]
        for kind, entry in turning_points[-12:]:
            timestamp = entry.get("timestamp") or {}
            target = entry.get("target")
            if isinstance(target, dict):
                target_name = target.get("name") or target.get("kind") or "unknown"
            else:
                target_name = str(target) if target is not None else "unknown"
            pos = f"({entry['x']}, {entry['y']})" if "x" in entry and "y" in entry else "location unknown"
            context = entry.get("context")
            suffix = f"; context: {context}" if context else ""
            lines.append(f"- Round {timestamp.get('round', '?')}: `{kind}` at {pos}, target {target_name}{suffix}.")
    recent = event_entries(data, team, {"campClear", "gemCollection", "gemSubmission", "gemLoss",
                                        "death", "buyItem", "buyConsumable", "kill"})
    if recent:
        lines += ["", "## Recent recorded activity", ""]
        for kind, entry in recent[-15:]:
            timestamp = entry.get("timestamp") or {}
            pos = f"({entry['x']}, {entry['y']})" if "x" in entry and "y" in entry else ""
            value = entry.get("value")
            detail = f" value {value}" if value not in (None, "0", 0) else ""
            lines.append(f"- Round {timestamp.get('round', '?')}: `{kind}` {pos}{detail}".rstrip())
    if faults:
        lines.append(f"- **Runtime issue:** diagnostics records {faults} bot fault(s); fix these before interpreting strategy performance.")
    if logs:
        signals = log_signals(logs)
        if signals["fault_lines"]:
            lines.append("- **Log warning:** matching fault/error lines were found: " + "; ".join(signals["fault_lines"][:4]))
        if signals["context_lines"]:
            lines.append(f"- **Bot diagnostics:** {len(signals['context_lines'])} `bot context` lines appear in the selected team's logs; inspect them for repeated stale-target or action issues.")

    lines += ["", "## Suggested next experiment", "",
              "Change one behavior that matches the evidence, then compare old and new bots on the same maps against the same opponent, with both team sides represented. Track submitted gems, deaths, and faults across several matches. Keep the change only if the improvement repeats.",
              "", "## Limits", "",
              "This reviewer uses the readable statistics export and optional replay-bundle logs. It does not infer hidden opponent intent, decode every action from the binary replay, or edit source code. A diagnosis is a testable hypothesis, not an automatic patch."]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("statistics", type=Path, help="Readable match statistics JSON")
    parser.add_argument("--replay", type=Path, help="Optional .repl26a replay bundle")
    parser.add_argument("--team", choices=("teamA", "teamB"), default="teamA",
                        help="Which side is our bot (default: teamA)")
    args = parser.parse_args()
    try:
        data = json.loads(args.statistics.read_text(encoding="utf-8"))
        logs = replay_logs(args.replay, args.team) if args.replay else None
        sys.stdout.write(review(data, args.team, logs))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"review_match: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
