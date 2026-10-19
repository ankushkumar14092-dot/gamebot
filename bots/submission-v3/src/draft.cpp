#include <cambc.h>
#include "draft.h"
#include <algorithm>
#include <array>
#include <string_view>

namespace {
float score(cambc::champion_draft pick, unsigned multi_camp_groups, float gold_on_map) {
    // A transparent heuristic derived from the published base stats and kits.
    // Indices follow champion_draft: sturdier/faster camp clear scores well;
    // AoE and splash gain value on maps with multi-monster groups.
    static constexpr std::array<float, 11> base{
        53.0f, 50.0f, 61.0f, 65.0f, 60.0f, 49.0f,
        54.0f, 45.0f, 52.0f, 55.0f, 58.0f
    };
    static constexpr std::array<float, 11> cluster_bonus{
        1.0f, 0.0f, 0.0f, 0.5f, 1.5f, 1.0f,
        0.0f, 0.0f, 0.0f, 2.0f, 0.0f
    };
    const auto index = static_cast<std::size_t>(pick);
    float value = base[index] + cluster_bonus[index] * multi_camp_groups;
    if (pick == cambc::champion_draft::vesper_vale)
        value += gold_on_map * 0.004f; // Vesper earns 20% extra gold.
    return value;
}
} // namespace

void play_draft() {
    // Map-aware: count multi-monster groups for splash/AoE value, and weigh
    // Vesper's gold passive by the available camp rewards.
    unsigned multi_camp_groups = 0;
    float gold_on_map = 0.0f;
    for (const auto& group : cambc::map::camp_groups()) {
        if (group.camps().size() > 1) ++multi_camp_groups;
        gold_on_map += static_cast<float>(group.gold_value());
    }

    const auto chosen = cambc::draft::current_draft(cambc::team::ally);
    auto best = cambc::champion_draft::ryth;
    float best_score = -1.0f;
    for (int i = 0; i < 11; ++i) { // Released champions only.
        const auto pick = static_cast<cambc::champion_draft>(i);
        if (std::find(chosen.begin(), chosen.end(), pick) != chosen.end()) continue;
        const float candidate = score(pick, multi_camp_groups, gold_on_map);
        if (candidate > best_score) {
            best = pick;
            best_score = candidate;
        }
    }

    // The same versioned plan is copied to gameplay instances.
    cambc::draft_memory = std::string_view("CAMBC26A\1");
    cambc::draft::pick(best);
}
