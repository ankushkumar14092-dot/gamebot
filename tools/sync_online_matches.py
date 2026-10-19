#!/usr/bin/env python3
"""Fetch and review completed CAMBC matches for a team using the saved CLI login.

Requires a signed-in `cambc` CLI (`cambc login`). Statistics and replays are
stored under matches/online-reviews/, which is ignored by git. Losses are also
passed to improve_bot.py so Gemini can propose and benchmark an isolated
evidence-based source fix without modifying or submitting the incumbent.
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
from pathlib import Path
from typing import Any


def run(command: list[str], *, cwd: Path, capture: bool = False,
        retry_rate_limits: bool = True) -> str:
    # CAMBC applies a fairly tight per-account request limit. Match sync is
    # sequential, so honour Retry-After and allow a longer window instead of
    # abandoning a match after three short retries.
    for attempt in range(8):
        try:
            result = subprocess.run(command, cwd=cwd, check=True, text=True,
                                    stdout=subprocess.PIPE if capture else None,
                                    stderr=subprocess.PIPE)
            if result.stderr:
                sys.stderr.write(result.stderr)
            return result.stdout if capture else ""
        except subprocess.CalledProcessError as exc:
            error = exc.stderr or ""
            retryable = (retry_rate_limits
                         and ("rate limit" in error.casefold() or "http 429" in error.casefold()))
            if not retryable or attempt == 7:
                if error:
                    sys.stderr.write(error)
                raise
            match = re.search(r"retry after (\d+) seconds?", error, flags=re.IGNORECASE)
            delay = min(120, int(match.group(1)) + 1) if match else min(60, 5 * (attempt + 1))
            print(f"CAMBC rate limited; retrying in {delay} seconds (attempt {attempt + 2}/8).",
                  file=sys.stderr, flush=True)
            time.sleep(delay)
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-name", default=os.environ.get("CAMBC_TEAM_NAME", "decrest"),
                        help="Team name to select (default: CAMBC_TEAM_NAME or decrest)")
    parser.add_argument("--team-id", default=os.environ.get("CAMBC_TEAM_ID"),
                        help="Optional CAMBC team UUID; avoids matching by team name")
    parser.add_argument("--kind", choices=("ranked", "unranked", "tournament"), default="ranked")
    parser.add_argument("--limit", type=int, default=10,
                        help="How many of this team's recent matches to inspect per sync (default: 10)")
    parser.add_argument("--max-experiments", type=int, default=1,
                        help="Maximum loss candidates to benchmark per sync (default: 1; 0 disables)")
    parser.add_argument("--root", type=Path, default=Path("matches/online-reviews"),
                        help="Local output directory (default: matches/online-reviews)")
    parser.add_argument("--no-experiments", action="store_true",
                        help="Review matches without preparing candidate experiments for losses")
    parser.add_argument("--stats-only", action="store_true",
                        help="Do not download replay bundles; review match statistics only")
    args = parser.parse_args()
    if args.max_experiments < 0:
        parser.error("--max-experiments must not be negative")

    root = Path.cwd()
    cambc = root / ".venv" / "bin" / "cambc"
    if not cambc.exists():
        found = shutil.which("cambc")
        if not found:
            print("sync_online_matches: cambc CLI not found; install the project venv or add cambc to PATH",
                  file=sys.stderr)
            return 2
        cambc = Path(found)
    output_root = (root / args.root).resolve() if not args.root.is_absolute() else args.root
    output_root.mkdir(parents=True, exist_ok=True)

    try:
        state_path = output_root / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"processed": {}}
        known_team_id = args.team_id or state.get("teamId")
        team_name = args.team_name.casefold()

        def fetch_list(team_id: str | None) -> dict[str, Any]:
            command = [str(cambc), "matches", "list", "--kind", args.kind,
                       "--json", "--limit", str(args.limit)]
            if team_id:
                command += ["--team", team_id]
            return json.loads(run(command, cwd=root, capture=True))

        listing = fetch_list(known_team_id)
        matches = listing.get("matches", [])
        if not known_team_id:
            discovery = fetch_list(None) if args.limit >= 100 else json.loads(run(
                [str(cambc), "matches", "list", "--kind", args.kind, "--json", "--limit", "100"],
                cwd=root, capture=True))
            identity_match = next((match for match in matches
                                   if any(str(team.get("name", "")).casefold() == team_name
                                          for team in match.get("teams", []))), None)
            if identity_match is None:
                identity_match = next((match for match in discovery.get("matches", [])
                                       if any(str(team.get("name", "")).casefold() == team_name
                                              for team in match.get("teams", []))), None)
            if identity_match:
                known_team_id = next(team["teamId"] for team in identity_match.get("teams", [])
                                     if str(team.get("name", "")).casefold() == team_name)
                listing = fetch_list(known_team_id)
                matches = listing.get("matches", [])
            else:
                raise ValueError(f"team '{args.team_name}' was not found in the latest {args.limit} matches; "
                                 "pass --team-id or set CAMBC_TEAM_ID")

        selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for match in matches:
            ours = next((team for team in match.get("teams", [])
                         if team.get("teamId") == known_team_id), None)
            if ours and match.get("status") == "finished":
                selected.append((match, ours))
        selected.sort(key=lambda pair: pair[0].get("finishedAt") or "", reverse=True)

        state["teamId"] = known_team_id
        processed = state.setdefault("processed", {})
        todo = [(match, ours) for match, ours in selected if match.get("matchId") not in processed]
        print(f"Found {len(selected)} finished {args.kind} match(es) for "
              f"{args.team_name} ({known_team_id}); {len(todo)} new.")

        experiments_started = 0
        for match, ours in todo:
            match_id = str(match["matchId"])
            folder = output_root / match_id
            folder.mkdir(parents=True, exist_ok=True)
            stats_path = folder / "statistics.json"
            replay_path = folder / "replay.repl26a"
            report_path = folder / "review.md"
            if not stats_path.exists():
                run([str(cambc), "matches", "summary", match_id, "--json", "--output", str(stats_path)], cwd=root)
            replay_ok = replay_path.exists()
            if not args.stats_only and not replay_ok:
                try:
                    run([str(cambc), "matches", "download", match_id, "--output", str(replay_path)], cwd=root)
                    replay_ok = True
                except subprocess.CalledProcessError as exc:
                    replay_ok = False
                    print(f"Replay download failed for {match_id}; reviewing statistics only ({exc}).",
                          file=sys.stderr)

            side = "teamA" if ours.get("side") == "a" else "teamB"
            review_cmd = [sys.executable, "tools/review_match.py", str(stats_path), "--team", side]
            if replay_ok:
                review_cmd += ["--replay", str(replay_path)]
            review = run(review_cmd, cwd=root, capture=True)
            report_path.write_text(review, encoding="utf-8")

            result = ours.get("result") or "unknown"
            print(f"{match.get('finishedAt', 'time unknown')} | {match.get('map', 'map?')} | "
                  f"{result.upper()} vs "
                  f"{next((t.get('name', 'unknown') for t in match.get('teams', []) if t is not ours), 'unknown')} "
                  f"| {report_path}")

            experiment_note = ""
            if (result == "loss" and not args.no_experiments
                    and experiments_started < args.max_experiments):
                improve_command = [sys.executable, "tools/improve_bot.py", str(stats_path),
                                   "--team", side, "--run", "--gemini-fix"]
                map_path = root / "maps" / f"{match.get('map', '')}.map26a"
                if map_path.is_file():
                    improve_command += ["--maps", str(map_path)]
                improve = run(improve_command, cwd=root, capture=True, retry_rate_limits=False)
                experiments_started += 1
                experiment_note = improve.strip()
                if experiment_note:
                    (folder / "experiment.txt").write_text(experiment_note + "\n", encoding="utf-8")
                    print(experiment_note)
            elif result == "loss" and not args.no_experiments:
                print(f"Candidate experiment limit reached ({args.max_experiments}); "
                      f"reviewed {match_id} without generating another candidate.")

            opponent = next((t for t in match.get("teams", []) if t.get("teamId") != known_team_id), {})
            processed[match_id] = {"team": ours.get("name"), "result": result,
                                   "finishedAt": match.get("finishedAt"), "map": match.get("map"),
                                   "side": side, "opponent": opponent.get("name", "unknown"),
                                   "characters": ours.get("characters", []),
                                   "review": str(report_path), "replayDownloaded": replay_ok}
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

        if not selected:
            print("No finished matches found for that team. Check --team-name or --team-id.")
        elif not todo:
            print("No new finished matches to review.")
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"sync_online_matches: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
