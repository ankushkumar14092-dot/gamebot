// Champion decisions. main.cpp dispatches here after the draft.
#include <cambc.h>
#include "bot.h"
#include <algorithm>
#include <array>
#include <variant>
#include <utility>
#include <vector>
#include <type_traits>

using cambc::vec2;
using cambc::team;

int distance(vec2 a, vec2 b) {
    return static_cast<int>(a.chebyshev_distance(b));
}

cambc::bitboard tiles_around(vec2 position, int radius) {
    cambc::bitboard tiles;
    tiles.clear();
    tiles.draw_chebyshev(position, radius);
    return tiles;
}

// Combine terrain and visible occupants using native bitboard operations.
cambc::bitboard blocked_tiles() {
    auto blocked = cambc::map::walls() | cambc::map::holes() | cambc::map::altars()
        | cambc::map::spawn_region(team::enemy) | cambc::vision::champion_tiles()
        | cambc::vision::camp_tiles() | cambc::vision::teleport_tiles();
    blocked.set(cambc::self().position(), false);
    return blocked;
}

// ability.valid_tiles() describes range only. Before a dash, conservatively
// require a clear one- or two-step landing path using our observed occupancy.
bool dash_path_is_clear(vec2 from, vec2 to, const cambc::bitboard& blocked) {
    if (!cambc::map::is_in_bounds(to) || blocked.is_set(to)) return false;
    const int dx = to.x - from.x;
    const int dy = to.y - from.y;
    const int ax = dx < 0 ? -dx : dx;
    const int ay = dy < 0 ? -dy : dy;
    const int steps = std::max(ax, ay);
    if (steps <= 1) return true;
    if (steps > 2) return false;

    // A 2-step dash needs at least one unblocked adjacent tile on a shortest
    // path. This may reject a dash that could cross a hole, but avoids trying
    // destinations whose route is visibly obstructed.
    for (int sx = -1; sx <= 1; ++sx) {
        for (int sy = -1; sy <= 1; ++sy) {
            if (sx == 0 && sy == 0) continue;
            const vec2 middle = from + vec2{sx, sy};
            if (cambc::map::is_in_bounds(middle) && !blocked.is_set(middle)
                && middle.chebyshev_distance(to) == 1)
                return true;
        }
    }
    return false;
}

bool move_towards_closest(cambc::bitboard goals) {
    auto& me = cambc::self();
    if (!me.can_move() || goals.is_set(me.position()))
        return false;

    // Only free goals or occupied camp tiles can seed the field.
    const auto blocked = blocked_tiles();
    goals &= ~blocked | cambc::vision::camp_tiles();
    if (goals.is_empty())
        return false;
    if (goals.count() == 1 && !blocked.is_set(goals.positions()[0]))
        return me.move_towards(goals.positions()[0]);

    // Expand from the goals until our current tile is reached.
    const auto path_walls = blocked & ~goals;
    cambc::distance_field field;
    cambc::bitboard visited;
    field.compute_to(path_walls, goals, tiles_around(me.position(), 0), visited);

    // Prefer a ready dash when its legal destination advances at least two
    // path steps. The SDK mask accounts for dash geometry and terrain.
    const auto current_distance = field.get(me.position());
    bool dashed = false;
    if (me.can_cast()) {
        for (const auto& ability : me.abilities()) {
            if (!ability.is_dash() || !ability.is_ready()
                || ability.get<cambc::ability_dash>().exclusive_with_movement)
                continue;
            const auto legal = ability.valid_tiles();
            auto best_tile = me.position();
            auto best_distance = current_distance;
            for (const auto tile : legal.positions()) {
                if (!dash_path_is_clear(me.position(), tile, blocked)) continue;
                const auto tile_distance = field.get(tile);
                if (tile_distance < best_distance) {
                    best_distance = tile_distance;
                    best_tile = tile;
                }
            }
            if (best_tile != me.position()
                && best_distance + 1 < current_distance
                && ability.use(best_tile)) {
                dashed = true;
                break;
            }
        }
    }

    // A dash is compatible with a normal move for the released dash kits.
    // Follow it with the SDK's first optimal step when movement remains.
    if (me.can_move()) {
        if (const auto direction = field.next_move_from(me.position()))
            return me.move_absolute(me.position() + *direction) || dashed;
    }
    return dashed;
}

void Bot::buy_items() {
    auto& me = cambc::self();
    // The Monster emblem grants 10% more damage to camps after five shards.
    // Farm speed is the core objective, so use its shard family instead of
    // buying Power shards that provide stats but no camp-damage passive.
    const std::array items{cambc::item_type::monster_shard_of_strength,
        cambc::item_type::monster_shard_of_focus, cambc::item_type::monster_shard_of_health};
    const auto item = items[chosen_stat];
    const unsigned count = me.gold_count() / item.cost();
    if (count && me.can_buy(item, count)) me.buy(item, count);
}

// Use the support effects present in the champion roster instead of treating
// every ready ability as an offensive spell. Willow heals a nearby ally; Varg
// shields itself before taking visible damage.
bool cast_support_ability(bool under_threat) {
    auto& me = cambc::self();
    if (!me.can_cast()) return false;
    const auto allies = cambc::vision::champions(team::ally);
    for (const auto& ability : me.abilities()) {
        if (!ability.is_ready()) continue;
        if (ability.is_heal() && ability.can_target_allies()) {
            const auto valid = ability.valid_tiles();
            const cambc::champion* best = nullptr;
            float best_heal = 0.0f;
            for (const auto& ally : allies) {
                if (!ally.is_alive() || ally.position() == me.position()
                    || !valid.is_set(ally.position())) continue;
                const float missing = ally.max_health() - ally.health();
                const float heal = ability.heal_amount(ally);
                if (missing >= ally.max_health() * 0.25f && heal > best_heal) {
                    best = &ally;
                    best_heal = heal;
                }
            }
            if (best && ability.use(*best)) return true;
        }
        if (ability.is_shield() && ability.can_target_self() && under_threat
            && ability.use()) return true;
    }
    return false;
}

// Compute the attack mask once, rather than once per visible target.
template<class Targets>
bool attack_first_in_range(const Targets& targets) {
    auto& me = cambc::self();
    if (targets.empty() || !me.can_attack()) return false;
    const auto attack_tiles = me.attack_tiles();
    for (const auto& target : targets) {
        if (target.is_visible() && attack_tiles.is_set(target.position()) && target.health() > 0) {
            me.attack(target);
            // Attack-reset abilities are valuable only after the first attack has
            // consumed this turn's allowance. Avoid wasting them on a dead target.
            if (target.health() > 0 && me.can_cast()) {
                for (const auto& ability : me.abilities()) {
                    if (ability.is_attack_reset() && ability.is_ready() && ability.use()) {
                        if (me.can_attack() && attack_tiles.is_set(target.position()) && target.health() > 0)
                            me.attack(target);
                        break;
                    }
                }
            }
            return true;
        }
    }
    return false;
}

// Cast a ready, direct damage or crowd-control ability on a legal visible target.
// Basic attacks remain available, so callers may still attack afterwards.
template<class Targets>
bool cast_offensive_ability(const Targets& targets) {
    auto& me = cambc::self();
    if (targets.empty() || !me.can_cast()) return false;
    constexpr bool camps = std::is_same_v<typename Targets::value_type, cambc::camp>;
    for (const auto& ability : me.abilities()) {
        if ((!ability.is_damage() && !ability.is_cc()) || !ability.is_ready()) continue;
        if constexpr (camps) {
            if (!ability.can_target_camps()) continue;
        } else {
            if (!ability.can_target_enemies()) continue;
        }
        const auto valid = ability.valid_tiles();
        for (const auto& target : targets) {
            if (!target.is_visible() || target.health() <= 0 || !valid.is_set(target.position())) continue;
            if (ability.use(target)) return true;
        }
    }
    return false;
}

template<class Targets>
bool cast_area_ability(const Targets& targets) {
    auto& me = cambc::self();
    if (targets.size() < 2 || !me.can_cast()) return false;
    for (const auto& ability : me.abilities()) {
        if (!ability.is_aoe_damage() || !ability.is_ready() || !ability.can_target_ground()) continue;
        const auto range = ability.valid_tiles();
        const float radius = ability.get<cambc::ability_aoe_damage>().radius;
        auto best_tile = me.position();
        std::size_t best_hits = 1;
        for (const auto tile : range.positions()) {
            std::size_t hits = 0;
            for (const auto& target : targets) {
                if (target.is_visible() && target.health() > 0
                    && tile.chebyshev_distance(target.position()) <= radius)
                    ++hits;
            }
            if (hits > best_hits) {
                best_hits = hits;
                best_tile = tile;
            }
        }
        if (best_hits > 1 && ability.use(best_tile)) return true;
    }
    return false;
}

float incoming_visible_damage(vec2 position) {
    float damage = 0.0f;
    for (const auto& camp : cambc::vision::camps()) {
        if (camp.is_awake() && distance(position, camp.position()) <= camp.attack_range())
            damage += camp.strength();
    }
    for (const auto& enemy : cambc::vision::champions(team::enemy)) {
        if (enemy.is_alive() && distance(position, enemy.position()) <= enemy.attack_range())
            damage += enemy.strength();
    }
    return damage;
}

bool retreat_from_visible_threats() {
    auto& me = cambc::self();
    if (!me.can_move()) return false;
    const auto camps = cambc::vision::camps();
    const auto enemies = cambc::vision::champions(team::enemy);
    const auto blocked = blocked_tiles();
    const auto candidates = blocked.reachable_tiles(me.position(), me.base_stats().base_move_speed).positions();
    auto best = me.position();
    int best_safety = -1;
    for (const auto tile : candidates) {
        int safety = 0;
        for (const auto& camp : camps) {
            if (camp.is_awake()) safety += distance(tile, camp.position()) - camp.attack_range();
        }
        for (const auto& enemy : enemies) {
            if (enemy.is_alive()) safety += distance(tile, enemy.position()) - enemy.attack_range();
        }
        if (safety > best_safety) {
            best = tile;
            best_safety = safety;
        }
    }
    return best != me.position() && me.move_absolute(best);
}

const auto& known_camp_groups() {
    static const auto groups = [] {
        std::vector<std::pair<cambc::map::camp_group, cambc::bitboard>> result;
        for (const auto& group : cambc::map::camp_groups())
            result.emplace_back(group, group.spawn_tiles());
        return result;
    }();
    return groups;
}

// Prefer groups that pay more gems per travel and estimated combat turn.
// Gold contributes a smaller amount because gems determine the match score.
cambc::bitboard choose_camp_goals() {
    auto& me = cambc::self();
    const auto& groups = known_camp_groups();
    cambc::bitboard all_spawns;
    all_spawns.clear();
    for (const auto& [group, spawns] : groups) all_spawns |= spawns;

    const auto visible = cambc::vision::visible_tiles();
    const auto blocked = blocked_tiles();
    cambc::bitboard destination;
    destination.clear();
    float best_score = -1.0f;

    float damage_per_turn = std::max(1.0f, me.strength());
    for (const auto& ability : me.abilities()) {
        if (!ability.info() || (!ability.is_damage() && !ability.is_aoe_damage() && !ability.is_cc()))
            continue;
        const float modifier = std::visit([](const auto& data) {
            if constexpr (requires { data.modifier; }) return data.modifier;
            else return 0.0f;
        }, *ability.info());
        const auto cooldown = std::max(1, std::visit([](const auto& data) { return data.max_cooldown; }, *ability.info()));
        damage_per_turn += me.focus() * modifier / cooldown;
    }

    for (const auto& [group, spawns] : groups) {
        bool reward_ready = false;
        if (!(spawns & visible).is_empty()) {
            const auto state = group.state();
            if (std::holds_alternative<cambc::map::camp_group_respawning>(state)) continue;
            reward_ready = std::holds_alternative<cambc::map::camp_group_reward_available>(state);
        }

        // The distance field includes terrain and visible occupancy, while
        // allowing the group's own spawn tiles to serve as roots.
        const auto roots = spawns & (~blocked | cambc::vision::camp_tiles());
        if (roots.is_empty()) continue;
        const auto path_walls = blocked & ~roots;
        cambc::distance_field field;
        cambc::bitboard visited;
        field.compute_to(path_walls, roots, tiles_around(me.position(), 0), visited);
        const auto path_distance = field.get(me.position());
        if (path_distance == cambc::distance_field::unreachable) continue;

        float combat_turns = 0.0f;
        float incoming_per_turn = 0.0f;
        if (!reward_ready) {
            for (const auto& camp : group.camps()) {
                const auto stats = camp.base_stats();
                combat_turns += stats.base_health / damage_per_turn;
                incoming_per_turn += stats.base_strength;
            }
        }
        const float danger_cost = combat_turns * incoming_per_turn
            / std::max(1.0f, me.health()) * 8.0f;
        const float reward = static_cast<float>(group.gem_value())
            + static_cast<float>(group.gold_value()) * 0.025f;
        const float cost = static_cast<float>(path_distance) + combat_turns + danger_cost + 6.0f;
        const float score = reward / cost;
        if (score > best_score) {
            best_score = score;
            destination = roots;
        }
    }

    // If every known camp is unavailable or unreachable, continue exploring
    // toward the map's camp regions; visibility may be stale for hidden groups.
    return destination.is_empty() ? all_spawns : destination;
}

// Attack a camp already in range, otherwise choose a worthwhile camp group.
void farm_camps() {
    const auto visible_camps = cambc::vision::camps();
    if (!cast_area_ability(visible_camps)) cast_offensive_ability(visible_camps);
    if (attack_first_in_range(visible_camps)) return;

    const auto goals = choose_camp_goals();
    // Fresh vision after movement may reveal a camp already in range.
    if (move_towards_closest(goals))
        attack_first_in_range(cambc::vision::camps());
}

void Bot::play_turn() {
    auto& me = cambc::self();

    // Choose a permanent shard stat once per champion.
    if (chosen_stat < 0) {
        // Compare shard gains in expected repeatable damage: strength helps every
        // basic attack, while focus only helps damage spells on their cooldown.
        const auto stats = me.base_stats();
        float focus_damage_per_turn = 0.0f;
        for (const auto& ability : me.abilities()) {
            if (!ability.info() || (!ability.is_damage() && !ability.is_aoe_damage() && !ability.is_cc()))
                continue;
            const float modifier = std::visit([](const auto& data) {
                if constexpr (requires { data.modifier; }) return data.modifier;
                else return 0.0f;
            }, *ability.info());
            const auto cooldown = std::max(1, std::visit([](const auto& data) { return data.max_cooldown; }, *ability.info()));
            focus_damage_per_turn += stats.focus_growth * modifier / cooldown;
        }
        chosen_stat = focus_damage_per_turn > stats.strength_growth ? 1 : 0;
    }

    // Leave channels running and skip turns where we cannot act.
    if (me.is_recalling() || me.is_submitting_gems() || me.is_teleporting())
        return;

    // Dead champions retain shopping turns. can_buy validates champion-specific rules.
    if (!me.is_alive()) {
        buy_items();
        return;
    }

    if (!me.can_move() && !me.can_attack() && !me.can_cast()) return;

    // Shop before leaving spawn.
    const bool at_spawn = cambc::map::spawn_region(team::ally).is_set(me.position());
    if (at_spawn || me.champion_name() == cambc::champion_type::tavi)
        buy_items();

    // Recall while wounded only when visible threats cannot interrupt it. If a
    // camp or enemy can hit this tile, step out of its attack range first.
    if (!at_spawn) {
        const float threat = incoming_visible_damage(me.position());
        const bool badly_hurt = me.health() < me.max_health() * 0.35f;
        const bool at_risk = threat > 0.0f && me.health() <= threat + me.strength();
        if (badly_hurt || at_risk) {
            if (threat > 0.0f) retreat_from_visible_threats();
            else me.recall();
            return;
        }
    }

    // Shields and heals are most valuable before visible combat or while
    // surviving an active camp. This leaves attack-reset abilities available
    // to attack_first_in_range below.
    cast_support_ability(incoming_visible_damage(me.position()) > 0.0f);

    // Attack the first enemy champion already in range.
    const auto enemies = cambc::vision::champions(team::enemy);
    if (!cast_area_ability(enemies)) cast_offensive_ability(enemies);
    if (attack_first_in_range(enemies)) return;

    // Bank every haul before returning to farm; carried gems are lost on death.
    if (me.gem_count() > 0) {
        // Union all altar approach tiles: the field chooses the nearest reachable altar.
        cambc::bitboard goals;
        goals.clear();
        for (auto altar : cambc::map::altars().positions()) {
            if (distance(me.position(), altar) <= cambc::constants::submit_gems_range
                && !cambc::vision::has_altar_lock(altar)) {
                    me.submit_gems(altar);
                    return;
                }
            if (!cambc::vision::has_altar_lock(altar)) goals |= tiles_around(altar, cambc::constants::submit_gems_range);
        }
        move_towards_closest(goals);
        return;
    }

    farm_camps();

}
