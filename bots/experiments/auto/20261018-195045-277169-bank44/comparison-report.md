# Candidate bot experiment

- **Source bot:** `/Users/ankushkumarguptapahleja/gamebot/bots/submission-v6`
- **Opponent:** `/Users/ankushkumarguptapahleja/gamebot/bots/baseline-cpp`
- **Reviewed loss:** `/Users/ankushkumarguptapahleja/gamebot/matches/online-reviews/9796326b-378b-42a5-a9f2-4de3a445e4d3/statistics.json`
- **Bank threshold:** 22 → 44
- **Maps:** 17

## Why this candidate

The bot had few deaths and no observed collection-to-submission gap; test batching two 22-gem hauls.

## Evaluation plan

The manifest contains 68 matches: incumbent and candidate on each selected map, each with both team sides. It keeps all source versions separate.

- Candidate source: `/Users/ankushkumarguptapahleja/gamebot/bots/experiments/auto/20261018-195045-277169-bank44/candidate`
- Match manifest: `/Users/ankushkumarguptapahleja/gamebot/bots/experiments/auto/20261018-195045-277169-bank44/comparison.txt`

Both player sides are included for each map. The CLI does not expose a fixed seed here, so repeat the batch and test varied opponents before promoting a strategy change.
