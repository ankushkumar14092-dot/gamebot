#!/usr/bin/env python3
"""Keep syncing new CAMBC matches while this process is running."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval-seconds", type=int, default=300,
                        help="Seconds between checks (default: 300)")
    parser.add_argument("--team-name", default=os.environ.get("CAMBC_TEAM_NAME", "decrest"))
    parser.add_argument("--team-id", default=os.environ.get("CAMBC_TEAM_ID"))
    parser.add_argument("--kind", choices=("ranked", "unranked", "tournament"), default="ranked")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--no-experiments", action="store_true")
    args = parser.parse_args()
    if args.interval_seconds < 30:
        parser.error("--interval-seconds must be at least 30")

    sync_script = os.path.join(os.path.dirname(__file__), "sync_online_matches.py")
    command = [sys.executable, sync_script, "--team-name", args.team_name,
               "--kind", args.kind, "--limit", str(args.limit)]
    if args.team_id:
        command += ["--team-id", args.team_id]
    if args.no_experiments:
        command.append("--no-experiments")

    print(f"Watching {args.team_name}; checking every {args.interval_seconds}s. Press Ctrl-C to stop.",
          flush=True)
    try:
        while True:
            print(f"\n[{datetime.now().astimezone().isoformat(timespec='seconds')}] CAMBC sync", flush=True)
            try:
                subprocess.run(command, check=False)
            except OSError as exc:
                print(f"watch_online_matches: sync could not start: {exc}", file=sys.stderr, flush=True)
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        print("\nStopped CAMBC match watcher.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
