# CAMBC 2026A V4 validation

## Change

V4 is based on the validated V3 source. It changes only gem-delivery timing in `src/bot.cpp`:

- Continue farming with a carried bag below 44 gems when health is at least 70% and no visible threat is present.
- Bank immediately at 44 gems, at spawn, below 70% health, or when visible threats are present.
- Keep V3’s recall, pathfinding, visibility guards, combat rules, and dash sequencing.

The 44-gem threshold batches two common 22-gem camp hauls. It is a measured candidate, not a proven general optimum.

## Paired results

V3 and V4 were built in release mode and run against `bots/baseline-cpp` on the same 17 maps and per-map seeds.

| Version | Wins | Submitted gems | Collected gems | Gold earned | Deaths | Kills | Team A runtime faults / codes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| V2 | 11/17 | 12,730 | 13,270 | 55,685 | 192 | 89 | 0 / 0 |
| V3 | 10/17 | 13,546 | 14,012 | 58,532 | 200 | 109 | 0 / 0 |
| V4 | 11/17 | 14,039 | 15,062 | 62,051 | 204 | 101 | 0 / 0 |

V4 versus V3: +1 win, +493 submitted gems, +1,050 collected gems, +3,519 earned gold, +4 deaths, and −8 kills. V4 matches V2’s win count and exceeds its submitted gems by 1,309 in this sample. These are 17 paired maps against one opponent, not a reliable estimate of general win rate.

The median first tribute among matches that submitted gems moved from 64.5 rounds in V3 to 98 rounds in V4. Team A submitted gems in 16 matches for both versions. The later first tribute is the cost of batching; on this seed set, V4 still ended with more tributed gems and one additional win.

The V4 release batch completed 17/17 matches with zero runner failures, zero Team A bot faults, and an empty runtime-code list. The runner’s JSON export does not include per-turn fuel consumption, so this V4 run has no numeric fuel profile. V3’s previously captured profile was 17,058 samples, mean 110,318.5, p95 109,568, peak 998,400 against a 1,000,000 ceiling. That V3 figure must not be presented as a V4 measurement.

## Camp-selection experiment

A separate experiment used the SDK’s 8-byte team shared memory to down-weight camps already selected by another ally. It was isolated from the delivery change and ran on the same maps/seeds. It scored 9/17 wins, 12,410 submitted gems, 12,937 collected gems, 55,656 gold, and 206 deaths, with zero runtime faults. This was worse than V3 on the main resource and win metrics, so the coordination change is excluded from V4.

No camp-scoring formula change is retained. The code-level camp scoring still ranks reward against travel, estimated combat time, and danger. The measured evidence supports the delivery adjustment in this sample, but does not yet support a new camp assignment policy.

## Reproduction and rollback

```sh
.venv/bin/cambc build bots/submission-v4
.venv/bin/cambc build bots/submission-v4 --release
.venv/bin/cambc run-batch /private/tmp/cambc-v4-final-maps.txt --jobs 4 --release --json
```

The final manifest names the 17 official maps and `bots/baseline-cpp`; JSON and replay files are under `/private/tmp/cambc-v4-final-*`. V3 remains available at `bots/submission-v3/src` and `dist/submission-v3.zip`; V2 remains at `bots/submission-v2/src` and `dist/submission-v2.zip`.

Only the baseline opponent was available in this workspace. Diverse-opponent and ladder testing remain outstanding.
