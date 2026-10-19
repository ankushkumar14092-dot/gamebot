# CAMBC 2026A V3 validation

## Source and scope

V1 source is available in `bots/starter-cpp/src`; the six V1 source files are byte-identical to `dist/starter-cpp.zip`. V2 source is in `bots/submission-v2/src`, and the existing `dist/submission-v2.zip` is left untouched. V3 is a copy of V2 with a small dash sequencing fix and two narrowly scoped stale-observation guards.

The bot is C++20 and is built with the project’s CAMBC 2.2.3 CLI and WASI SDK 33. `src/main.cpp` constructs the draft/game bot and dispatches draft callbacks and per-champion turns. Drafting, shopping, combat priorities, recall policy, camp reward model, and general objective scoring are unchanged from V2.

## V2 audit

- **Draft and economy:** `draft.cpp` selects the roster; `Bot::on_shop` purchases upgrades. These files are unchanged across V1, V2, and V3.
- **Turn flow:** `Bot::play_turn` handles respawn/recall and survival, delivers gems, engages visible enemies, then farms camps and moves toward altars/objectives. The broad flow is unchanged.
- **Combat:** visible enemies/camps are checked before live reads. Damage and area abilities are evaluated before a basic attack. Attack-reset use is disabled in V2/V3 because the engine rejected the attempted use.
- **Objectives and pathfinding:** camp groups are ranked by expected gems plus a small gold value, divided by travel, estimated combat turns, and estimated danger. V2 paths to unoccupied attack-ring positions for living camps and free spawn tiles for cleared rewards. Distance-field origins and candidate goals are checked; blocked tiles include terrain and visible occupants.
- **Movement and dash:** V2 bounds retries, refreshes occupancy, skips known occupied destinations, and catches the specific engine rejection for newly occupied movement/dash destinations. The confirmed V2 defect was that one `dashed` flag also suppressed ordinary movement on every later replan after a successful dash.
- **Visibility and lifetime:** camps are revalidated before `camp_at`; stale target reads ignore only the documented not-visible/not-found cases. Engine-backed observations are rebuilt in the current turn rather than cached across turns.
- **Diagnostics:** unexpected exceptions are logged with operation and champion/position context, then rethrown. V3 retains that behavior.
- **Fuel:** V2 used 16,266 samples; mean 115,665, p95 152,064, peak 998,656 (limit 1,000,000), with 75 samples at or above 900,000 and 6 at or above 990,000.

## V1/V2 code comparison and likely regressions

Both source versions are present, so this is a direct comparison. Safety changes between V1 and V2 include input-position checks, bounded path replanning, visibility guards, refreshed occupancy, and legal camp approach roots. The most important confirmed strategic defect found was in V2 movement: after a successful dash, the loop replanned but continued checking the persistent `dashed` flag and skipped its normal move. This wasted the remaining movement opportunity and repeated up to eight distance searches.

Ranked findings:

1. **Dash followed by movement (confirmed defect; small positive result).** V3 scopes the “replan after dash” decision to the attempt in which the dash happened. Same-seed results improve collected/submitted gems and kills over V2, but V3 wins one fewer match. This is a resource/tempo improvement, not a demonstrated win-rate improvement.
2. **Attack-reset removal (plausible, unsafe to restore).** A separate reset experiment improved aggregate resources relative to V2 but still won 11/17 and emitted two rejected-action errors (code 26). The failure was not repaired; the ability remains disabled.
3. **Camp goal scoring (hypothesis tested and rejected).** A controlled experiment scored travel to living camp spawn tiles while retaining legal attack-ring movement goals. It kept 10/17 wins but lowered submitted gems and delayed first tribute versus V3. Do not infer that V1’s invalid occupied camp roots should be restored.
4. **Recall/tribute and retreat (open hypothesis).** Median first tribute was 51 rounds for V1, 63 for V2, and 64.5 for V3 among matches that submitted gems. The timing is consistent with slower delivery contributing to lower scores, but it does not identify whether route choice, deaths, or retreat policy caused the delay.
5. **Draft/upgrades (low likelihood for the V1/V2 delta).** Draft and shop source are unchanged, so this comparison provides no evidence that those systems caused the regression.

## Paired release results

All versions used the same 17 maps, baseline opponent, and per-map seeds. V3’s final run was rebuilt from `bots/submission-v3` and repeated on the same seeds. Each cell below is Team A’s aggregate over 17 maps.

| Version | Wins | Submitted gems | Collected gems | Gold earned | Deaths | Kills | Bot faults / runtime codes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| V1 | 16/17 | 15,912 | 16,847 | 68,472 | 219 | 85 | 0 faults; error codes 5:20, 22:78, 97:550, 26:1, 32:3 |
| V2 | 11/17 | 12,730 | 13,270 | 55,685 | 192 | 89 | 0 / 0 |
| V3 | 10/17 | 13,546 | 14,012 | 58,532 | 200 | 109 | 0 / 0 |

V3 versus V2: +816 submitted gems, +742 collected gems, +2,847 gold, +20 kills, +8 deaths, and −1 win. The paired sample is only 17 maps; this does not establish a general win-rate change. V1 submitted gems in 17/17 matches; V2 in 15/17; V3 in 16/17. Team A’s median first-tribute time among submitting matches was 51, 63, and 64.5 rounds respectively.

The final V3 release run recorded 17 matches, zero runner failures, zero Team A bot faults, and an empty runtime error-code list. The captured V3 fuel profile for the same source and seeds was 17,058 samples: mean 110,318.5, p95 109,568, peak 998,400 against the 1,000,000 limit. The peak remains close to the limit and merits monitoring.

## Rejected experiment

The camp-distance experiment used the V3 movement and safety code but ranked living camps by distance to their spawn tiles. It produced 10/17 wins, 13,188 submitted gems, 13,486 collected gems, and 55,094 gold. Median first tribute among submitting matches was 74 rounds. It had zero Team A bot faults, but its performance was worse than the attack-ring scoring candidate, so it is not included in the V3 artifact.

The attack-reset experiment is also excluded: 11/17 wins and two code-26 rejected actions. V3 keeps V2’s safe disabled behavior.

## Reproduction and rollback

From the project root:

```sh
.venv/bin/cambc build bots/submission-v3
.venv/bin/cambc build bots/submission-v3 --release
.venv/bin/cambc run-batch /private/tmp/cambc-v3-final-maps.txt --jobs 4 --release --json
```

The final manifest names all 17 official maps and Team B `bots/baseline-cpp`; match JSON and replays are in `/private/tmp/cambc-v3-final-*`. The manifest is local to this validation run. For rollback, use the untouched `bots/submission-v2/src` or `dist/submission-v2.zip`.

Only the baseline C++ opponent was available in this workspace, so no diverse-opponent or current-ladder validation was possible. No independent standalone smoke-test suite was present; the release build and all-map batch run were used as the smoke/regression check.
