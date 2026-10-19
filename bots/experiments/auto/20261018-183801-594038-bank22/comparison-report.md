# Candidate bot experiment

- **Source bot:** `/Users/ankushkumarguptapahleja/gamebot/bots/submission-v6`
- **Opponent:** `/Users/ankushkumarguptapahleja/gamebot/bots/baseline-cpp`
- **Reviewed loss:** `/Users/ankushkumarguptapahleja/gamebot/matches/online-reviews/47a3299f-cbb7-4f89-9cd1-40b54ece4bc6/statistics.json`
- **Bank threshold:** 44 → 22
- **Maps:** 17

## Why this candidate

The loss shows up to 36 gems carried at a death and 58 more gems collected than submitted. Try banking at 22 gems and compare the result.

## Evaluation plan

The manifest contains 68 matches: incumbent and candidate on each selected map, each with both team sides. It keeps all source versions separate.

- Candidate source: `/Users/ankushkumarguptapahleja/gamebot/bots/experiments/auto/20261018-183801-594038-bank22/candidate`
- Match manifest: `/Users/ankushkumarguptapahleja/gamebot/bots/experiments/auto/20261018-183801-594038-bank22/comparison.txt`

Both player sides are included for each map. The CLI does not expose a fixed seed here, so repeat the batch and test varied opponents before promoting a strategy change.
