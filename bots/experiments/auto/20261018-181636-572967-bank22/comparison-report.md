# Candidate bot experiment

- **Source bot:** `/Users/ankushkumarguptapahleja/gamebot/bots/submission-v6`
- **Opponent:** `/Users/ankushkumarguptapahleja/gamebot/bots/baseline-cpp`
- **Reviewed loss:** `/private/tmp/cambc-v4-final-ambush.json`
- **Bank threshold:** 44 → 22
- **Maps:** 2

## Why this candidate

Manual experiment request: compare a 22-gem bank threshold.

## Evaluation plan

The manifest contains 8 matches: incumbent and candidate on each selected map, each with both team sides. It keeps all source versions separate.

- Candidate source: `/Users/ankushkumarguptapahleja/gamebot/bots/experiments/auto/20261018-181636-572967-bank22/candidate`
- Match manifest: `/Users/ankushkumarguptapahleja/gamebot/bots/experiments/auto/20261018-181636-572967-bank22/comparison.txt`

Both player sides are included for each map. The CLI does not expose a fixed seed here, so repeat the batch and test varied opponents before promoting a strategy change.

## Incumbent results

- Matches: 4
- Average submitted gems: 517.0
- Wins: 1/4
- Bot faults: 0.0

## Candidate results

- Matches: 4
- Average submitted gems: 628.5
- Wins: 2/4
- Bot faults: 0.0

## Batch verdict

Candidate improved this batch; review the evidence before promotion.
