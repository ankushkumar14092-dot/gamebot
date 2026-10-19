# CAMBC environment audit

Audit date: 2026-10-19

## Verified environment

- Installed CLI: `cambc 2.2.5`; the project declares SDK `2.2.3`. Builds work,
  but CAMBC warns that the SDK is older than the CLI. `cambc init` was not run
  because it would refresh project SDK files as a separate, unreviewed change.
- CLI login is usable: `cambc matches list --kind ranked --limit 1 --json`
  returned match data. The output at audit time was queued, not completed.
  Existing finished-match exports are present, and the adapter successfully
  fetched a finished match summary and replay.
- Official CLI help was inspected for `build`, `run`, `run-batch`, `matches
  list/show/summary/download`, `bundle`, `submit`, `maps list/pull`, and
  `login`.
- Supported operations include release WASM builds, local matches, four-column
  batch manifests, online result/replay access, source ZIP bundling, and a
  separate submission command. Neither `run` nor `run-batch` documents a seed
  option.
- `GameRules.md` and `BotAPICpp.md` are not present in this workspace. The
  installed SDK and CLI are available, but rules not represented there could
  not be independently checked against those requested documents.
- The checkout is not a normal project Git repository: Git resolves to the
  parent home directory, which has no commit and tracks no gamebot files. The
  experiment workflow therefore creates a Git repository and `candidate`
  branch only inside each isolated experiment copy; it does not initialize or
  commit the user's whole project.

## End-to-end checks performed

- Built `bots/submission-v6` in release mode with the installed CLI.
- Ran a complete local release match on `ambush`; the official runner finished
  at round 1844, wrote JSON statistics and a `.repl26a` replay, and the
  statistics were parsed by `review_match.py`.
- In that sample, `submission-v6` submitted 288 gems against `baseline-cpp`'s
  1038; the match summary reports zero bot faults for both teams. The
  `fuelExhausted` event count for `submission-v6` was 8,039. This is an event
  count, not an exact fuel-consumption total.
- The current bot log recorded a rejected occupied move with no pre-action
  blocker but a champion visible afterward. The current movement code checks
  occupancy, catches `invalid_action_move_bad_destination`, logs context, and
  retries a different route step. The match summary still reports zero bot
  faults. This single observation does not prove all historical Error 22
  cases are resolved. Its diagnostics contain no runtime error codes; current
  source also handles stale-target `api_not_in_vision`/`api_not_found` errors.
- The adapter fetched a finished online match's statistics, downloaded its
  replay, and packaged the current source as a ZIP. The ZIP passed
  `zipfile.is_zipfile`; no upload or submission was performed.
- A threshold-only candidate was built on its own `candidate` Git branch and
  tested against the incumbent on `ambush` from both sides (four matches).
  Both versions averaged 252 submitted gems, each won 0/2, and both had zero
  bot faults. The candidate failed the strict improvement gate and remained
  isolated; the incumbent source hashes were unchanged. This is a one-map,
  unseeded smoke comparison, not evidence about overall win rate.
- A deliberately syntax-broken candidate failed compilation in a temporary
  isolated copy; the incumbent source hash remained unchanged. No promotion
  or submission path was invoked.
- The 21 focused Python unit tests cover CLI adapter capture/redaction/timeouts,
  candidate branch isolation, failed-build artifacts, report rendering, and
  bounded Gemini retry behavior. Retry tests simulate `Retry-After` and Gemini
  `retryDelay` responses.

## Important limits and remaining work

- The live Gemini endpoint was returning HTTP 429. Retry handling is bounded
  to six attempts, honors `Retry-After`/Gemini retry-delay data up to five
  minutes per wait, and was tested with simulated responses. A successful live
  Gemini repair after the rate limit clears has not yet been observed.
- The poller was restarted with the candidate-only policy. It can review
  matches and benchmark candidates, but an AI-generated source patch was not
  produced during this audit because of the live 429 responses.
- Statistics expose event counters, including `fuelExhausted`, plus team and
  champion aggregates. They do not expose an exact fuel-consumption total in
  the inspected export. `.repl26a` files can be opened with `cambc view`, but
  the current reviewer does not decode every binary replay action.
- The CLI does not provide fixed-seed paired runs. Current candidate testing
  uses both player sides but cannot guarantee identical seeds; broader,
  multi-map/multi-opponent repeated evaluation is still needed.
- The current acceptance comparison gates on submitted gems, wins, and bot
  faults. Dedicated safety regression scenarios for every historical error,
  a reliable best-version registry, richer fuel profiling, and complete
  replay-derived movement/ability/recall analysis remain to be built.
- Live submission remains a human-only step. The agent code no longer exposes
  automatic promotion/submission; package a passing, reviewed candidate and
  explicitly run the verified CAMBC submission command only after approval.

## Implemented in this pass

- Added `tools/cambc_adapter.py` for environment inspection, builds, local
  matches, online summaries, replay downloads, diagnostics, and source
  packaging. It captures command output, exit code, duration, timeout state,
  and generated artifacts, and redacts API-key-shaped output.
- Added bounded retry-delay parsing shared by match analysis and candidate
  generation; sync now limits candidate experiments to one per run by default.
- Removed automatic incumbent promotion and `cambc submit` from the loss
  workflow. Candidate source is initialized in a separate local Git repository
  and branch; a passing comparison still requires human review. Generated
  candidate reports include the verified manual `cambc bundle` and `cambc
  submit` command forms and warn against using them for a failed benchmark.
- Deduplicated generated-artifact reporting when a local match's statistics
  file is also discovered inside its output directory.
- Fixed report rendering when Gemini returns a single evidence string instead
  of a list, and documented the verified CLI behavior and limitations.

## Follow-up verification

- The current `gamebot` directory is its own Git repository on `main`, but it
  has no commits and no configured remote. The source files are untracked, so
  committing/pushing a promotion would require an explicitly configured
  repository and branch; no push was attempted.
- A candidate attempt that failed with Gemini HTTP 429 left its match out of
  `matches/online-reviews/state.json`, so the poller would retry that same
  loss on each sync. Sync now writes candidate stdout/stderr to the match's
  `experiment.txt`, redacts key-shaped values and known API-key values, records
  failed attempt status in state, and returns a nonzero status. That processed
  match is not automatically re-experimented on every poll.
- The added regression test exercises a complete simulated match sync: a
  candidate failure is captured, the API key is redacted, the match is marked
  processed, and a second sync does not repeat the failed attempt.
- Submission integration remains disabled: CAMBC help confirms `bundle` and
  `submit` command shapes, but no safe end-to-end upload test or server-side
  accepted submission ID has been performed.
