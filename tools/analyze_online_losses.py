#!/usr/bin/env python3
"""Audit all completed ranked losses for the signed-in CAMBC team.

Uses the authenticated cambc CLI, follows match-list cursors, downloads loss
statistics/replays, writes per-match reviews, and summarizes recurring signals.
It can prepare one isolated candidate from the clearest loss; it never changes
or submits the active bot.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from improve_bot import carried_gems_at_death, champion_metric, team_metric


def command_output(command: list[str], root: Path) -> str:
    for attempt in range(8):
        try:
            result = subprocess.run(command, cwd=root, check=True, text=True, capture_output=True)
            return result.stdout
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            if attempt == 7:
                raise RuntimeError(f"command failed after retries: {command!r}\n{detail}") from exc
            retry_after = re.search(r"retry after (\d+(?:\.\d+)?) seconds", detail, re.IGNORECASE)
            time.sleep(float(retry_after.group(1)) + 1 if retry_after else min(2 * (attempt + 1), 30))


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def fault_count(data: dict[str, Any], side: str) -> float:
    diag = data.get("diagnostics") or {}
    return float((diag.get("botFaults") or {}).get(side, 0) or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-id", default=os.environ.get("CAMBC_TEAM_ID"),
                        help="CAMBC team UUID; otherwise read it from the previous sync state")
    parser.add_argument("--output", type=Path, default=Path("matches/online-loss-audit"))
    parser.add_argument("--since", help="Only include matches created at/after this ISO timestamp")
    parser.add_argument("--include-replays", action="store_true",
                        help="Download replay bundles too; statistics are enough for the aggregate audit")
    parser.add_argument("--workers", type=int, default=1,
                        help="Concurrent read-only statistics downloads (default: 1 to respect API limits)")
    parser.add_argument("--no-experiments", action="store_true",
                        help="Write the audit without preparing a strategy candidate")
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 16:
        parser.error("--workers must be between 1 and 16")
    root = Path.cwd()
    cambc = root / ".venv" / "bin" / "cambc"
    if not cambc.exists():
        found = shutil.which("cambc")
        if not found:
            print("analyze_online_losses: cambc CLI not found", file=sys.stderr)
            return 2
        cambc = Path(found)

    state_path = root / "matches/online-reviews/state.json"
    team_id = args.team_id
    if not team_id and state_path.exists():
        team_id = read_json(state_path).get("teamId")
    if not team_id:
        print("analyze_online_losses: pass --team-id or sync the team first", file=sys.stderr)
        return 2
    since = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
        except ValueError:
            parser.error("--since must be an ISO timestamp, for example 2026-10-18T00:00:00Z")

    output = (root / args.output).resolve() if not args.output.is_absolute() else args.output
    output.mkdir(parents=True, exist_ok=True)
    try:
        matches: list[dict[str, Any]] = []
        cursor: str | None = None
        cursors: set[str] = set()
        while True:
            cmd = [str(cambc), "matches", "list", "--team", team_id,
                   "--kind", "ranked", "--json", "--limit", "100"]
            if cursor:
                cmd += ["--cursor", cursor]
            page = json.loads(command_output(cmd, root))
            matches.extend(page.get("matches", []))
            next_cursor = page.get("nextCursor")
            if not next_cursor or next_cursor in cursors:
                break
            cursors.add(next_cursor)
            cursor = str(next_cursor)

        finished: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for match in matches:
            ours = next((team for team in match.get("teams", [])
                         if team.get("teamId") == team_id), None)
            # Ignore queued/unfinished records and records without a drafted
            # champion roster; both checks keep incomplete/non-playing rows out.
            if (ours and match.get("status") == "finished"
                    and ours.get("characters") and ours.get("engineVersion")):
                if since:
                    created = datetime.fromisoformat(str(match.get("createdAt", "")).replace("Z", "+00:00"))
                    if created < since:
                        continue
                finished.append((match, ours))
        losses = [(m, t) for m, t in finished if t.get("result") == "loss"]
        print(f"Fetched {len(finished)} completed ranked matches for team {team_id}; "
              f"{len(losses)} losses across {len(cursors) + 1} page(s).", flush=True)

        # Fetch the remote summaries concurrently; reviews and aggregation below
        # stay local and deterministic. Each match gets its own output path.
        def ensure_stats(item: tuple[dict[str, Any], dict[str, Any]]) -> tuple[str, str | None]:
            match, _ = item
            match_id = str(match["matchId"])
            folder = output / match_id
            folder.mkdir(parents=True, exist_ok=True)
            stats_path = folder / "statistics.json"
            previous = root / "matches/online-reviews" / match_id / "statistics.json"
            if not stats_path.exists() and previous.exists():
                shutil.copy2(previous, stats_path)
            if not stats_path.exists():
                try:
                    command_output([str(cambc), "matches", "summary", match_id,
                                    "--json", "--output", str(stats_path)], root)
                except RuntimeError as exc:
                    return match_id, str(exc)
            return match_id, None

        stats_errors: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(ensure_stats, item) for item in losses]
            for future in as_completed(futures):
                match_id, error = future.result()
                if error:
                    stats_errors[match_id] = error
                    print(f"Skipping unavailable statistics for {match_id}: {error}", file=sys.stderr, flush=True)
        print(f"Statistics ready for {len(losses) - len(stats_errors)}/{len(losses)} losses "
              f"({args.workers} concurrent workers).", flush=True)

        by_map: dict[str, Counter[str]] = defaultdict(Counter)
        for match, ours in finished:
            by_map[str(match.get("map", "unknown"))][str(ours.get("result", "unknown"))] += 1

        rows: list[dict[str, Any]] = []
        best_candidate: tuple[float, Path, str] | None = None
        for match, ours in losses:
            match_id = str(match["matchId"])
            folder = output / match_id
            folder.mkdir(parents=True, exist_ok=True)
            stats_path = folder / "statistics.json"
            replay_path = folder / "replay.repl26a"
            report_path = folder / "review.md"
            if match_id in stats_errors or not stats_path.exists():
                continue
            previous = root / "matches/online-reviews" / match_id
            replay_ok = replay_path.exists()
            if not replay_ok and (previous / "replay.repl26a").exists():
                shutil.copy2(previous / "replay.repl26a", replay_path)
                replay_ok = True
            if not replay_ok and args.include_replays:
                try:
                    command_output([str(cambc), "matches", "download", match_id,
                                    "--output", str(replay_path)], root)
                    replay_ok = True
                except subprocess.CalledProcessError:
                    print(f"Replay unavailable for {match_id}; reviewing match statistics.", file=sys.stderr)

            side = "teamA" if ours.get("side") == "a" else "teamB"
            review_cmd = [sys.executable, "tools/review_match.py", str(stats_path), "--team", side]
            if replay_ok:
                review_cmd += ["--replay", str(replay_path)]
            report = subprocess.run(review_cmd, cwd=root, check=True, text=True,
                                    capture_output=True).stdout
            report_path.write_text(report, encoding="utf-8")
            data = read_json(stats_path)
            other = "teamB" if side == "teamA" else "teamA"
            submitted = team_metric(data, side, "submittedGems")
            opponent_submitted = team_metric(data, other, "submittedGems")
            collected = champion_metric(data, side, "collectedGems")
            carried = carried_gems_at_death(data, side)
            deaths = champion_metric(data, side, "deaths")
            faults = fault_count(data, side)
            gap = max(0.0, collected - submitted)
            row = {"match": match, "team": ours, "side": side, "submitted": submitted,
                   "opponentSubmitted": opponent_submitted, "collected": collected,
                   "collectionGap": gap, "carriedAtDeath": carried,
                   "deaths": deaths, "faults": faults, "review": report_path}
            rows.append(row)
            reason = (f"{carried:g} gems carried at a death; {gap:g} collected but not submitted; "
                      f"{deaths:g} deaths; {faults:g} faults")
            print(f"{match.get('finishedAt')} | {match.get('map')} | vs "
                  f"{next((t.get('name') for t in match.get('teams', []) if t.get('teamId') != team_id), 'unknown')} | "
                  f"{submitted:g}-{opponent_submitted:g} gems | {report_path}", flush=True)
            score = max(carried, gap)
            if not args.no_experiments and (carried >= 22 or gap >= 22):
                if best_candidate is None or score > best_candidate[0]:
                    best_candidate = (score, stats_path, side)

        report_lines = ["# Ranked match history audit", "",
                        f"- Team ID: `{team_id}`", f"- Completed matches with a drafted roster: {len(finished)}",
                        f"- Losses reviewed: {len(rows)}", "",
                        f"- Lower time bound: `{args.since or 'all available history'}`",
                        "The match listing identifies your team and draft roster, but does not expose the bot submission revision. Use `--since` to exclude matches before your first active submission.", "",
                        "## Results by map", "", "| Map | Wins | Losses |", "|---|---:|---:|"]
        for map_name, counts in sorted(by_map.items()):
            report_lines.append(f"| {map_name} | {counts['win']} | {counts['loss']} |")
        report_lines += ["", "## Loss evidence", "",
                         "| Finished (UTC) | Opponent | Map | Gems (us–them) | Carried at death | Unsubmitted collected | Deaths | Faults |", "|---|---|---|---:|---:|---:|---:|---:|"]
        for row in rows:
            match = row["match"]
            opponent = next((t.get("name", "unknown") for t in match.get("teams", [])
                             if t.get("teamId") != team_id), "unknown")
            report_lines.append(
                f"| {match.get('finishedAt', '?')} | {opponent} | {match.get('map', '?')} | "
                f"{row['submitted']:.0f}–{row['opponentSubmitted']:.0f} | {row['carriedAtDeath']:.0f} | "
                f"{row['collectionGap']:.0f} | {row['deaths']:.0f} | {row['faults']:.0f} |")
        carry_losses = sum(row["carriedAtDeath"] > 0 for row in rows)
        gap_losses = sum(row["collectionGap"] >= 22 for row in rows)
        fault_losses = sum(row["faults"] > 0 for row in rows)
        avg_deaths = sum(row["deaths"] for row in rows) / max(1, len(rows))
        report_lines += ["", "## Repeating signals", "",
                         f"- Losses with gems recorded at a death: {carry_losses}/{len(rows)}.",
                         f"- Losses with at least 22 collected-but-unsubmitted gems: {gap_losses}/{len(rows)}.",
                         f"- Losses with bot faults: {fault_losses}/{len(rows)}.",
                         f"- Average champion deaths in a loss: {avg_deaths:.1f}.",
                         "- Carrying/delivery and survival are telemetry clues, not proof of opponent intent. Read the linked replay review before attributing a cause.", ""]

        if best_candidate:
            _, stats_path, side = best_candidate
            if not args.no_experiments:
                result = subprocess.run([sys.executable, "tools/improve_bot.py", str(stats_path),
                                         "--team", side], cwd=root, text=True, capture_output=True)
                if result.returncode:
                    raise RuntimeError(result.stderr or result.stdout)
                report_lines += ["## Candidate prepared", "", result.stdout.strip(), "",
                                 "The active bot has not been modified, tested, or submitted by this audit.", ""]
        else:
            report_lines += ["", "No loss met the current evidence threshold for a banking candidate.", ""]

        report_path = output / "history-audit.md"
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        print(f"History report: {report_path}")
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"analyze_online_losses: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
