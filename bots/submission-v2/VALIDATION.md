# CAMBC 2026A v2 validation

## Build and regression run

- Built with `.venv/bin/cambc build bots/submission-v2 --release` (WASI SDK 33); CAMBC reported `injected 0 checks into 0 functions`.
- Ran the release artifact against `bots/baseline-cpp` on all 17 official maps with `cambc run-batch --jobs 4 --release --json`.
- The v1 and v2 runs used the same recorded seed on each map. The original `bots/starter-cpp/src` files remain byte-identical to the six source files in `dist/starter-cpp.zip`.
- Runner failures: 0. Team A runtime error lines in the final v2 replay logs: 0.

## Runtime errors

| Error | v1 occurrences | v2 occurrences |
| --- | ---: | ---: |
| 5 — invalid map/tile coordinate | 20 | 0 |
| 22 — known occupied move destination | 78 | 0 |
| 97 — unit/tile not in vision | 550 | 0 |
| 26 — spell cast rejected | 1 | 0 |
| 32 — illegal spell destination | 3 | 0 |

V2 now exits path searches when a champion has no valid map position, ignores only stale target observations that return `api_not_in_vision` or `api_not_found`, and replans after the engine reports an occupied movement or dash landing. Other errors still propagate to the top-level handler and remain visible in stdout.

## Match metrics

Team A totals over the 17 paired maps:

| Metric | v1 | v2 | Change |
| --- | ---: | ---: | ---: |
| Wins | 16 | 11 | −5 |
| Submitted gems | 15,912 | 12,730 | −20.0% |
| Collected gems | 16,847 | 13,270 | −21.2% |
| Earned gold | 68,472 | 55,685 | −18.7% |
| Deaths | 219 | 192 | −27 |
| Kills | 85 | 89 | +4 |

Runtime reliability improved, but v2’s score and win rate regressed on the same map seeds. This is a material tradeoff for the current revision.

## Fuel

Across 16,266 v2 fuel samples from the 17 release replays:

- Mean: 115,665 fuel
- 95th percentile: 152,064 fuel
- Peak: 998,656 fuel, against a 1,000,000 fuel limit
- Samples at or above 900,000: 75; samples at or above 990,000: 6

No bot faults occurred, but rare turns approach the fuel ceiling. For comparison, v1 had 156 samples at or above 900,000 and a peak of 995,840.

## Remaining limits

- The attack-reset ability use was removed because the engine rejected it when an attack allowance remained available; this can reduce combat damage.
- A stale occupied-tile observation is handled by skipping that candidate and replanning. If no legal step remains, that champion waits for a later turn.
- Match quality needs another pass if v2 must retain v1’s performance while keeping these runtime fixes.
