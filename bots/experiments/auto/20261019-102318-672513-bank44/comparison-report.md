# Candidate bot experiment

- **Source bot:** `/Users/ankushkumarguptapahleja/gamebot/bots/submission-v6`
- **Opponent:** `/Users/ankushkumarguptapahleja/gamebot/bots/baseline-cpp`
- **Reviewed loss:** `/Users/ankushkumarguptapahleja/gamebot/matches/online-reviews/3f6d8f4b-a3de-4c25-ac4a-07a5816a7a31/statistics.json`
- **Candidate branch:** `candidate`
- **Candidate baseline commit:** `b85d506f5cc8eb71f61d97288536af2e4416973f`
- **Bank threshold:** 22 → 44
- **Maps:** 1

## Why this candidate

Manual experiment request: compare a 44-gem bank threshold.

## Evaluation plan

The manifest contains 4 matches: incumbent and candidate on each selected map, each with both team sides. It keeps all source versions separate.

- Candidate source: `/Users/ankushkumarguptapahleja/gamebot/bots/experiments/auto/20261019-102318-672513-bank44/candidate`
- Match manifest: `/Users/ankushkumarguptapahleja/gamebot/bots/experiments/auto/20261019-102318-672513-bank44/comparison.txt`

Both player sides are included for each map. The CLI does not expose a fixed seed here, so repeat the batch and test varied opponents before promoting a strategy change.

## Incumbent results

- Matches: 2
- Average submitted gems: 252.0
- Wins: 0/2
- Bot faults: 0.0

## Candidate results

- Matches: 2
- Average submitted gems: 252.0
- Wins: 0/2
- Bot faults: 0.0

## Batch verdict

Candidate did not beat the incumbent on submitted gems, wins, and faults; keep it as an experiment.

## Promotion policy

The incumbent source was left unchanged and no live submission was made. Human review and approval are required before packaging or submitting this candidate.
