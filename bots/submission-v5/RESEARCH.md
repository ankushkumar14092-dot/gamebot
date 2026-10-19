# CAMBC 2026A strategy research and V5 source change

## Research status

The requested official `game/home` route is JavaScript-rendered and was not readable through the available web research tool. The official public homepage describes the competition goal as collecting gems and offering them at altars, and mentions the live ladder and sprint format: [Cambridge Battlecode 2026A](https://2026a.battlecode.co.uk/).

For gameplay details, I used the official rules and C++ API documents already present in this workspace: `~/Downloads/GameRules.md` and `~/Downloads/BotAPICpp.md`, cross-checking API signatures in `sdk/cpp/cambc.h`. Their relevant rules say:

- Tributed gems determine the winner; reaching 1,000 first wins, and the 2,000-round tiebreak order is tributed gems, lifetime gold, then kills.
- Gems carried on death can be lost. Recall preserves the bag. Tribute duration is based on the starting bag, but the entire bag is submitted when the channel completes.
- An enemy altar lock blocks tribute; it takes three basic attacks to remove. The SDK exposes visible altar-lock observations and `champion::attack(const altar_lock&)`.

## Evidence from our runs

The V2/V3/V4 comparison uses the same 17 maps, seeds and baseline opponent. V4 batches small bags until 44 gems while banking immediately at spawn, below 70% health, or when visible threats exist.

| Candidate | Wins | Submitted gems | Collected gems | Gold | Deaths | Team A faults |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| V2 | 11/17 | 12,730 | 13,270 | 55,685 | 192 | 0 |
| V3 | 10/17 | 13,546 | 14,012 | 58,532 | 200 | 0 |
| V4 | 11/17 | 14,039 | 15,062 | 62,051 | 204 | 0 |

V4 submitted 493 more gems than V3 and won one more of the 17 paired matches. Its median first tribute was slower (98 rounds versus 64.5), so banking later is a real tradeoff, not an unqualified improvement. A timeline read showed 22 gems was the most common submission increment in V3; V4 had fewer submission-value transitions (413 versus 483 over the match set), consistent with less frequent banking.

A team-memory camp reservation experiment scored 9/17, with 12,410 submitted gems and 12,937 collected. It is rejected. The current evidence does not justify keeping that camp-selection change. V4 retains the existing reward/travel/combat/risk camp score.

## Codebase mistakes found

1. **Locked altar dead end (addressed in V5 source).** V4 skipped locked altars both when submitting and when constructing movement goals. If every nearby altar was enemy-locked, a champion carrying gems could receive no delivery goal. V5 now reads the visible lock owner, attacks a visible enemy lock when in attack range and able to attack, and approaches to attack range. It continues to submit normally at an unlocked altar or one protected by an allied lock.
2. **Small repeated deliveries (addressed in validated V4).** Immediate banking after every positive bag generated frequent short deposits. V4’s 44-gem threshold improved totals on this seed set while preserving immediate banking for health/threat conditions.
3. **Camp assignment coordination (tested, rejected).** Shared-memory deduplication performed worse on the same 17 maps. Do not ship that experiment based on current evidence.
4. **Fuel headroom (known limitation).** V3’s captured peak was 998,400 against a 1,000,000 ceiling. The batch JSON used for the V4 run does not export per-turn fuel consumption, so there is no V4 numeric fuel profile to compare.
5. **Draft and purchases (open area).** The draft uses a hand-tuned score and purchases only selected Monster shards. The baseline test set does not isolate whether alternative champion or consumable choices win more often; changing these without a controlled matchup experiment would be guesswork.

## V5 source change and validation state

V5 copies V4 and changes altar-lock handling in the gem-delivery loop in `src/bot.cpp`. It checks a visible lock with `vision::has_altar_lock` and `vision::altar_lock_at`, attacks an enemy lock only when `me.can_attack()` and within `me.attack_range()`, and includes its attack ring in altar approach goals. Allied locks still allow submissions. This uses the documented `champion::attack(altar_lock)` API and avoids attempting to submit into an enemy lock.

**V5 has compiled in both normal and release modes, but has not been run in matches.** The first compile found a missing brace in the altar-lock branch; it was fixed and both builds then completed with `injected 0 checks into 0 functions`. Treat the behavior as unvalidated. Preserve V4 as the validated rollback at `bots/submission-v4/src` and `dist/submission-v4.zip`.

Next, validate locked-altar behavior against a bot that buys and places altar locks. The current `bots/baseline-cpp` comparison produced no altar-lock events, so the 17-map baseline set cannot validate this new behavior. Then rerun the same 17 paired maps/seeds and capture per-turn fuel logs from a runner export that includes them.
