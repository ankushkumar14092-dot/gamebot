#pragma once

// Per-champion state survives between turns. Keep the best damage shard choice.
class Bot {
    int chosen_stat = -1;

    // Spend only on power shards of the selected stat.
    void buy_items();

public:
    // Priorities: shop and recall, attack enemies in range, bank gems, then farm.
    void play_turn();
};
