# Candidate bot experiment

- **Source bot:** `/Users/ankushkumarguptapahleja/gamebot/bots/submission-v6`
- **Opponent:** `/Users/ankushkumarguptapahleja/gamebot/bots/baseline-cpp`
- **Reviewed loss:** `/Users/ankushkumarguptapahleja/gamebot/matches/online-loss-audit/0f1d57e0-999e-45ed-9d1a-cf80cc1d3d9e/statistics.json`
- **Bank threshold:** 44 → 22
- **Maps:** 17

## Why this candidate

The loss shows up to 22 gems carried at a death and 110 more gems collected than submitted. Try banking at 22 gems and compare the result.

## Evaluation plan

The manifest contains 68 matches: incumbent and candidate on each selected map, each with both team sides. It keeps all source versions separate.

- Candidate source: `/Users/ankushkumarguptapahleja/gamebot/bots/experiments/auto/20261018-185739-254908-bank22/candidate`
- Match manifest: `/Users/ankushkumarguptapahleja/gamebot/bots/experiments/auto/20261018-185739-254908-bank22/comparison.txt`

Both player sides are included for each map. The CLI does not expose a fixed seed here, so repeat the batch and test varied opponents before promoting a strategy change.

## Incumbent results

- Matches: 34
- Average submitted gems: 827.5
- Wins: 23/34
- Bot faults: 0.0

## Candidate results

- Matches: 34
- Average submitted gems: 841.3
- Wins: 24/34
- Bot faults: 0.0

## Batch verdict

Candidate improved this batch; review the evidence before promotion.
