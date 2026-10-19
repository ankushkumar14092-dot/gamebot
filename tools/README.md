# Match review helper

## CAMBC adapter

`cambc_adapter.py` wraps the installed CAMBC 2.x CLI for environment inspection,
builds, local matches, online result/replay downloads, diagnostics, and ZIP
packaging. Each operation returns captured stdout/stderr, exit status, elapsed
time, and generated artifacts; command timeouts and malformed summaries are
reported explicitly. It does not expose a submit operation. Its local output is
kept under `matches/local/` and `matches/cambc-adapter/`, separate from the
existing online-review state.

The installed `cambc run` and `run-batch` help do not expose a fixed-seed
option. Requests for seeded matches are rejected instead of silently ignored.
The binary `.repl26a` bundles can be opened with `cambc view`; the built-in
reviewer uses structured `--statistics --json` exports and does not decode all
binary replay events.

`review_match.py` reads a CAMBC readable match-statistics export and can attach
the selected team's debug/stdout logs from a `.repl26a` bundle. It reports score,
faults, event counts, and the rounds/locations recorded for deaths and gem loss.
Its strategy notes are hypotheses for controlled experiments; it never edits a
bot automatically.

## Review a local match

From the project root:

```sh
.venv/bin/cambc run bots/submission-v6 bots/baseline-cpp \
  --map maps/ambush.map26a \
  --out-dir replays \
  --statistics /private/tmp/cambc-review.json \
  --json

python3 tools/review_match.py /private/tmp/cambc-review.json \
  --replay replays/NAME_OF_CREATED_BUNDLE.repl26a \
  --team teamA
```

The runner prints the replay bundle path after the match. Pass `teamB` if our bot
was the second player. For platform matches, `cambc matches summary --help` and
`cambc matches download --help` show the local export/download options; the
reviewer itself works offline once the statistics JSON and replay bundle exist.

The reviewer does not decode every action from the binary replay or patch the
incumbent source. Pair it with the visualiser to inspect an identified round,
then compare candidate behavior over repeated paired matches.

## Sync online matches automatically

Sign in once with the CAMBC CLI, then fetch new completed matches, download
their stats and replays, and write reviews with one command:

```sh
.venv/bin/cambc login
python3 tools/sync_online_matches.py
```

To keep checking automatically while a terminal stays open:

```sh
python3 tools/watch_online_matches.py
```

The sync command defaults to the `decrest` team. Change that with
`--team-name NAME` or `CAMBC_TEAM_NAME`, or select by UUID with `--team-id UUID`
or `CAMBC_TEAM_ID`. On first run, it resolves the team's ID from the latest 100
platform matches, then checks that team's latest 10 matches per sync. It skips
matches it has already reviewed and stores outputs under
`matches/online-reviews/` (git ignored). For every loss, it asks Gemini to
propose a minimal source diff from the match evidence, applies it only to an
isolated candidate, then builds and benchmarks incumbent and candidate on the
loss map from both team sides. By default, at most one loss candidate is
benchmarked per sync; use `--max-experiments 0` or `--no-experiments` to turn
that off. The report and candidate are saved under `bots/experiments/auto/`.
Candidate generation and benchmarking never modify the incumbent source or
submit to the platform. A passing result is only eligible for human review;
package and submit it manually after explicit approval. If Gemini cannot
justify a safe fix or the candidate fails to build or pass the gate, the
incumbent stays unchanged. Use `--kind` to sync unranked or tournament matches.

CAMBC login stores a short-lived CLI session locally (seven days); it does not
need a username/password in `.env`. Run `cambc login` again when the session
expires. The sync command runs when invoked; the optional watcher checks every
five minutes and stops with Ctrl-C.

## Create and compare a candidate

`improve_bot.py` can generate an isolated, evidence-based code-fix candidate
with `--gemini-fix`. Only `src/bot.cpp`, `src/draft.cpp`, `src/bot.h`, and
`src/draft.h` may be changed by the generated diff. It compares incumbent and
candidate on selected maps with both team sides represented. The current CLI
does not expose a fixed seed through this workflow, so a single passing batch
does not guarantee future wins.

```sh
python3 tools/improve_bot.py /private/tmp/cambc-review.json \
  --team teamA \
  --source bots/submission-v6 \
  --opponent bots/baseline-cpp \
  --gemini-fix --run
```

Without `--gemini-fix`, this prepares an isolated threshold candidate. The
incumbent source is always unchanged; this workflow does not upload or submit
any version. To select a specific supported threshold (22, 44, or 66)
regardless of the diagnosis, pass `--bank-threshold 22` (or 44/66).

The all-history auditor fetches match statistics with one worker by default to
respect CAMBC API limits. Use `--workers` only when you need to tune the request
rate; a rate-limited request waits for the server's retry interval.

Automatic code changes are restricted to the bot and draft C++ sources. If the
evidence does not justify a safe patch, Gemini declines to change the code.
Benchmarks cover the loss map and both player positions; they are a guardrail,
not a guarantee that every future match issue is fixed.
