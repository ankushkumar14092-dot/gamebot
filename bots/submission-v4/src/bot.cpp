// Champion decisions. main.cpp dispatches here after the draft.
#include <cambc.h>
#include "bot.h"
#include <algorithm>
#include <array>
#include <variant>
#include <utility>
#include <vector>
#include <type_traits>
#include <iostream>
#include <string>
#include <string_view>
#include <functional>

using cambc::vec2;
using cambc::team;

namespace {
template<class Target>
bool target_is_visible_and_alive(const Target& target, std::string_view operation) {
    try {
        return target.is_visible() && target.health() > 0;
    } catch (const cambc::error& error) {
        if (error.code() != cambc::error_code::api_not_in_vision
            && error.code() != cambc::error_code::api_not_found) throw;
        std::cerr << "bot context: skipped stale target operation=" << operation
                  << " code=" << static_cast<int>(error.code()) << '\n';
        return false;
    }
}

template<class Function>
bool with_stale_target_skip(std::string_view operation, Function&& function) {
    try {
        return std::invoke(std::forward<Function>(function));
    } catch (const cambc::error& error) {
        if (error.code() != cambc::error_code::api_not_in_vision
            && error.code() != cambc::error_code::api_not_found) throw;
        std::cerr << "bot context: skipped stale target operation=" << operation
                  << " code=" << static_cast<int>(error.code()) << '\n';
        return false;
    }
}

template<class Function>
decltype(auto) with_context(std::string_view operation, Function&& function) {
    try {
        return std::invoke(std::forward<Function>(function));
    } catch (...) {
        std::cerr << "bot context: operation=" << operation;
        try {
            const auto& me = cambc::self();
            const auto position = me.position();
            std::cerr << " champion=" << static_cast<int>(me.champion_name())
                      << " position=(" << position.x << ',' << position.y << ')';
        } catch (...) {
            std::cerr << " champion/position=unavailable";
        }
        std::cerr << '\n';
        throw;
    }
}
} // namespace

int distance(vec2 a, vec2 b) {
    return static_cast<int>(a.chebyshev_distance(b));
}

cambc::bitboard tiles_around(vec2 position, int radius, std::string_view source) {
    cambc::bitboard tiles;
    tiles.clear();
    if (!cambc::map::is_in_bounds(position)) {
        std::cerr << "bot context: skipped tile mask source=" << source << " center=("
                  << position.x << ',' << position.y << ")\n";
        return tiles;
    }
    tiles.draw_chebyshev(position, radius);
    return tiles;
}

// Combine terrain and visible occupants using native bitboard operations.
cambc::bitboard blocked_tiles() {
    auto blocked = with_context("blocked_tiles terrain and visible occupancy", [] {
        return cambc::map::walls() | cambc::map::holes() | cambc::map::altars()
            | cambc::map::spawn_region(team::enemy) | cambc::vision::champion_tiles()
            | cambc::vision::camp_tiles() | cambc::vision::teleport_tiles();
    });
    const auto origin = cambc::self().position();
    if (cambc::map::is_in_bounds(origin)) blocked.set(origin, false);
    return blocked;
}

// A camp can disappear between the occupancy-mask read and camp_at().
// Revalidate each tile; ignore only that narrowly defined stale observation.
std::vector<cambc::camp> visible_camps() {
    const auto& me = cambc::self();
    const auto self_position = me.position();
    if (!me.is_alive() || !cambc::map::is_in_bounds(self_position)) return {};
    const auto positions = with_context("vision::camp_tiles positions", [] {
        return cambc::vision::camp_tiles().positions();
    });
    std::vector<cambc::camp> result;
    result.reserve(positions.size());
    for (const auto position : positions) {
        try {
            if (!cambc::vision::has_camp(position)) continue;
            result.push_back(with_context("vision::camp_at tile="
                                          + std::to_string(position.x) + ","
                                          + std::to_string(position.y), [&] {
                return cambc::vision::camp_at(position);
            }));
        } catch (const cambc::error& error) {
            if (error.code() != cambc::error_code::api_not_found) throw;
            std::cerr << "bot context: skipped stale camp observation tile=("
                      << position.x << ',' << position.y << ") code="
                      << static_cast<int>(error.code()) << '\n';
        }
    }
    return result;
}

// ability.valid_tiles() describes range only. Before a dash, conservatively
// require a clear one- or two-step landing path using our observed occupancy.
bool dash_path_is_clear(vec2 from, vec2 to, const cambc::bitboard& blocked,
                        const cambc::bitboard& walls,
                        const cambc::bitboard& path_blocked) {
    if (!cambc::map::is_in_bounds(to) || blocked.is_set(to)) return false;
    const int dx = to.x - from.x;
    const int dy = to.y - from.y;
    const int ax = dx < 0 ? -dx : dx;
    const int ay = dy < 0 ? -dy : dy;
    const int steps = std::max(ax, ay);
    if (steps <= 1) return true;
    if (steps > 2) return false;

    // Dashes may cross holes, but cannot cross walls. Landing legality is
    // checked against all known terrain and occupancy in `blocked` above.
    for (int sx = -1; sx <= 1; ++sx) {
        for (int sy = -1; sy <= 1; ++sy) {
            if (sx == 0 && sy == 0) continue;
            const vec2 middle = from + vec2{sx, sy};
            if (cambc::map::is_in_bounds(middle) && !path_blocked.is_set(middle)
                && middle.chebyshev_distance(to) == 1)
                return true;
        }
    }
    return false;
}

bool move_towards_closest(cambc::bitboard goals) {
    auto& me = cambc::self();
    const auto start = me.position();
    if (!cambc::map::is_in_bounds(start) || !me.can_move() || goals.is_set(start))
        return false;

    // Movement roots must be legal, unoccupied destinations. Camp occupancy
    // is never exempted: living camps use attack positions and cleared camps
    // use free spawn tiles as capture goals.
    auto blocked = blocked_tiles();
    goals &= ~blocked;
    if (goals.is_empty())
        return false;

    // A newly revealed obstruction can invalidate a first step. Recompute
    // from fresh vision and try another optimal step, with a bounded retry.
    cambc::bitboard rejected_steps;
    rejected_steps.clear();
    bool dashed = false;
    for (int attempt = 0; attempt < 8; ++attempt) {
        blocked = blocked_tiles() | rejected_steps;
        const auto legal_goals = goals & ~blocked;
        if (legal_goals.is_empty()) break;

        cambc::distance_field field;
        cambc::bitboard visited;
        const auto origin = me.position();
        if (!me.is_alive() || !cambc::map::is_in_bounds(origin)) return dashed;
        const auto origin_tile = with_context("tiles_around movement origin="
                                               + std::to_string(origin.x) + ","
                                               + std::to_string(origin.y), [&] {
            return tiles_around(origin, 0, "movement origin");
        });
        if (origin_tile.is_empty()) return dashed;
        with_context("distance_field.compute_to movement origin="
                     + std::to_string(origin.x) + "," + std::to_string(origin.y), [&] {
            field.compute_to(blocked, legal_goals, origin_tile, visited);
        });

        const auto current_distance = field.get(origin);
        if (current_distance == cambc::distance_field::unreachable) break;

        // valid_tiles() describes ability range only. Check landing and
        // wall-crossing legality separately before executing a dash.
        bool dashed_this_attempt = false;
        bool retry_after_failed_dash = false;
        if (!dashed && me.can_cast()) {
            const auto walls = cambc::map::walls();
            const auto path_blocked = walls | cambc::map::altars()
                | cambc::map::spawn_region(team::enemy) | cambc::vision::champion_tiles()
                | cambc::vision::camp_tiles() | cambc::vision::teleport_tiles();
            for (const auto& ability : me.abilities()) {
                if (!ability.is_dash() || !ability.is_ready()
                    || ability.get<cambc::ability_dash>().exclusive_with_movement)
                    continue;
                const auto legal = with_context("dash ability.valid_tiles", [&] {
                    return ability.valid_tiles();
                });
                auto best_tile = origin;
                auto best_distance = current_distance;
                for (const auto tile : legal.positions()) {
                    if (!dash_path_is_clear(origin, tile, blocked, walls, path_blocked)) continue;
                    const auto tile_distance = field.get(tile);
                    if (tile_distance < best_distance) {
                        best_distance = tile_distance;
                        best_tile = tile;
                    }
                }
                if (best_tile != origin && best_distance + 1 < current_distance) {
                    const auto refreshed_blocked = blocked_tiles();
                    if (!dash_path_is_clear(origin, best_tile, refreshed_blocked, walls, path_blocked))
                        continue;
                    if (!me.is_alive() || !cambc::map::is_in_bounds(me.position()) || !me.can_cast())
                        return dashed;
                    dashed = with_context("dash ability.use landing=" + std::to_string(best_tile.x)
                                          + "," + std::to_string(best_tile.y), [&] {
                        try {
                            return ability.use(best_tile);
                        } catch (const cambc::error& error) {
                            if (error.code() != cambc::error_code::invalid_action_spell_cast_bad_destination)
                                throw;
                            std::cerr << "bot context: skipped newly occupied dash landing=("
                                      << best_tile.x << ',' << best_tile.y << ")\n";
                            return false;
                        }
                    });
                    if (dashed) {
                        dashed_this_attempt = true;
                        break;
                    }
                    rejected_steps.set(best_tile);
                    retry_after_failed_dash = true; // false reveals an obstruction
                    break;
                }
            }
        }

        if (retry_after_failed_dash) continue;
        if (!me.can_move()) return dashed;
        // A successful dash changes position and vision. Rebuild occupancy
        // and the distance field before choosing a normal movement tile.
        if (dashed_this_attempt) continue;
        const auto steps = field.next_moves_from(me.position());
        if (steps.empty()) break;
        for (const auto direction : steps) {
            const auto current_position = me.position();
            if (!cambc::map::is_in_bounds(current_position)) return dashed;
            if (current_position != origin) break; // state changed; rebuild the field
            const auto destination = current_position + direction;
            const auto action_blocked = blocked_tiles();
            const auto action_champions = cambc::vision::champion_tiles();
            const auto action_camps = cambc::vision::camp_tiles();
            const auto action_teleports = cambc::vision::teleport_tiles();
            const bool champion_at_destination = cambc::vision::has_champion(destination);
            const bool occupied_now = action_champions.is_set(destination)
                || champion_at_destination || action_camps.is_set(destination)
                || action_teleports.is_set(destination);
            if (action_blocked.is_set(destination) || occupied_now) {
                rejected_steps.set(destination);
                break;
            }
            if (!me.is_alive() || !cambc::map::is_in_bounds(me.position()) || !me.can_move())
                return dashed;
            const bool moved = with_context("champion.move_absolute destination="
                                            + std::to_string(destination.x) + ","
                                            + std::to_string(destination.y), [&] {
                try {
                    return me.move_absolute(destination);
                } catch (const cambc::error& error) {
                    if (error.code() == cambc::error_code::invalid_action_move_bad_destination) {
                        const auto after_champions = cambc::vision::champion_tiles();
                        const auto after_position = me.position();
                        std::cerr << "bot context: rejected occupied move destination=(" << destination.x << ','
                                  << destination.y << ") source=(" << current_position.x << ','
                                  << current_position.y << ") now=(" << after_position.x << ','
                                  << after_position.y << ") pre_blockers="
                                  << action_blocked.is_set(destination) << action_champions.is_set(destination)
                                  << action_camps.is_set(destination) << action_teleports.is_set(destination)
                                  << " has_champion=" << champion_at_destination
                                  << " post_champion=" << after_champions.is_set(destination) << '\n';
                        return false; // refresh occupancy and try another route step
                    }
                    throw;
                }
            });
            if (moved) return true;
            rejected_steps.set(destination);
            break; // failed movement reveals new occupancy; refresh before retrying
        }
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
    const auto attack_tiles = with_context("self attack_tiles", [&] {
        return me.attack_tiles();
    });
    constexpr bool camps = std::is_same_v<typename Targets::value_type, cambc::camp>;
    for (const auto& target : targets) {
        const bool attacked = with_context("attack target visibility/range/health", [&] {
            return with_stale_target_skip("basic attack", [&] {
                if (!target_is_visible_and_alive(target, "basic attack")) return false;
                const auto position = [&] {
                    if constexpr (camps) return target.spawn_position();
                    else return target.position();
                }();
                if (!attack_tiles.is_set(position)) return false;
                with_context("champion.attack visible target", [&] { me.attack(target); });
                // Attack-reset casts are omitted because the engine can reject
                // them while its attack allowance remains available.
                return true;
            });
        });
        if (attacked) return true;
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
            const bool usable = with_stale_target_skip("offensive ability", [&] {
                if (!target_is_visible_and_alive(target, "offensive ability")) return false;
                const auto position = [&] {
                    if constexpr (camps) return target.spawn_position();
                    else return target.position();
                }();
                return valid.is_set(position);
            });
            if (!usable) continue;
            if (with_context("offensive ability.use target", [&] { return ability.use(target); })) return true;
        }
    }
    return false;
}

template<class Targets>
bool cast_area_ability(const Targets& targets) {
    auto& me = cambc::self();
    if (targets.size() < 2 || !me.can_cast()) return false;
    constexpr bool camps = std::is_same_v<typename Targets::value_type, cambc::camp>;
    for (const auto& ability : me.abilities()) {
        if (!ability.is_aoe_damage() || !ability.is_ready() || !ability.can_target_ground()) continue;
        const auto range = ability.valid_tiles();
        const float radius = ability.get<cambc::ability_aoe_damage>().radius;
        auto best_tile = me.position();
        std::size_t best_hits = 1;
        for (const auto tile : range.positions()) {
            std::size_t hits = 0;
            for (const auto& target : targets) {
                const bool counted = with_stale_target_skip("AoE ability", [&] {
                    return target_is_visible_and_alive(target, "AoE ability")
                        && tile.chebyshev_distance([&] {
                            if constexpr (camps) return target.spawn_position();
                            else return target.position();
                        }()) <= radius;
                });
                if (counted)
                    ++hits;
            }
            if (hits > best_hits) {
                best_hits = hits;
                best_tile = tile;
            }
        }
        if (best_hits > 1 && with_context("AoE ability.use destination="
                                         + std::to_string(best_tile.x) + ","
                                         + std::to_string(best_tile.y), [&] {
                return ability.use(best_tile);
            })) return true;
    }
    return false;
}

float incoming_visible_damage(vec2 position) {
    float damage = 0.0f;
    for (const auto& camp : visible_camps()) {
        with_context("visible camp threat spawn=" + std::to_string(camp.spawn_position().x)
                     + "," + std::to_string(camp.spawn_position().y), [&] {
            if (!camp.is_visible()) return;
            if (camp.is_awake() && distance(position, camp.position()) <= camp.attack_range())
                damage += camp.strength();
        });
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
    const auto camps = visible_camps();
    const auto enemies = cambc::vision::champions(team::enemy);
    cambc::bitboard rejected;
    rejected.clear();
    for (int attempt = 0; attempt < 8; ++attempt) {
        const auto blocked = blocked_tiles() | rejected;
        const auto candidates = blocked.reachable_tiles(
            me.position(), static_cast<std::uint16_t>(me.base_stats().base_move_speed)).positions();
        auto best = me.position();
        int best_safety = -1;
        for (const auto tile : candidates) {
            int safety = 0;
            for (const auto& camp : camps) {
                if (!camp.is_visible()) continue;
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
        if (best == me.position()) return false;
        if (with_context("retreat move_absolute destination=" + std::to_string(best.x)
                         + "," + std::to_string(best.y), [&] {
                return me.move_absolute(best);
            })) return true;
        rejected.set(best);
    }
    return false;
}

std::vector<std::pair<cambc::map::camp_group, cambc::bitboard>> known_camp_groups() {
    return with_context("map::camp_groups metadata refresh", [] {
        std::vector<std::pair<cambc::map::camp_group, cambc::bitboard>> result;
        for (const auto& group : cambc::map::camp_groups())
            result.emplace_back(group, group.spawn_tiles());
        return result;
    });
}

// Prefer groups that pay more gems per travel and estimated combat turn.
// Gold contributes a smaller amount because gems determine the match score.
cambc::bitboard choose_camp_goals() {
    auto& me = cambc::self();
    const auto start = me.position();
    if (!cambc::map::is_in_bounds(start)) {
        std::cerr << "bot context: skipped camp path search for out-of-bounds champion position=("
                  << start.x << ',' << start.y << ") alive=" << me.is_alive()
                  << " champion=" << static_cast<int>(me.champion_name()) << '\n';
        cambc::bitboard empty;
        empty.clear();
        return empty;
    }
    // Keep engine-derived handles and masks turn-local. The SDK does not
    // promise their validity across bot instances, map loads, or turns.
    const auto groups = known_camp_groups();
    const auto visible_groups = with_context("vision::camp_groups current visibility", [] {
        return cambc::vision::camp_groups();
    });
    const auto blocked = blocked_tiles();
    cambc::bitboard destination;
    destination.clear();
    cambc::bitboard all_approaches;
    all_approaches.clear();
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
        const auto current_position = me.position();
        if (!cambc::map::is_in_bounds(current_position)) {
            std::cerr << "bot context: stopped camp selection for invalid champion position=("
                      << current_position.x << ',' << current_position.y << ")\n";
            break;
        }
        bool reward_ready = false;
        const auto visible_group = std::find(visible_groups.begin(), visible_groups.end(), group);
        if (visible_group != visible_groups.end()) {
            try {
                const auto state = with_context("camp_group.state handle="
                                                + std::to_string(static_cast<std::uint32_t>(
                                                    static_cast<cambc::handle_camp_group_t>(group))), [&] {
                    return visible_group->state();
                });
                if (std::holds_alternative<cambc::map::camp_group_respawning>(state)) continue;
                reward_ready = std::holds_alternative<cambc::map::camp_group_reward_available>(state);
            } catch (const cambc::error& error) {
                if (error.code() != cambc::error_code::api_not_in_vision
                    && error.code() != cambc::error_code::api_camp_group_not_waiting_to_respawn)
                    throw;
                std::cerr << "bot context: skipped stale camp-group state code="
                          << static_cast<int>(error.code()) << '\n';
            }
        }

        // A cleared, visible group is captured by standing on a free spawn
        // tile. For living or hidden groups, path to a free attack position;
        // hidden camps expose only their documented immutable spawn metadata.
        cambc::bitboard roots;
        roots.clear();
        if (reward_ready) {
            roots = spawns & ~blocked;
        } else {
            for (const auto spawn : spawns.positions()) {
                auto approach = tiles_around(spawn, me.attack_range(), "camp spawn approach");
                approach.set(spawn, false);
                roots |= approach;
            }
            roots &= ~blocked;
            all_approaches |= roots;
        }
        if (roots.is_empty()) continue;
        cambc::distance_field field;
        cambc::bitboard visited;
        const auto origin = me.position();
        if (!cambc::map::is_in_bounds(origin)) {
            std::cerr << "bot context: skipped camp distance search for invalid champion position=("
                      << origin.x << ',' << origin.y << ") group="
                      << static_cast<std::uint32_t>(static_cast<cambc::handle_camp_group_t>(group)) << '\n';
            continue;
        }
        const auto origin_tile = with_context("tiles_around camp origin="
                                               + std::to_string(origin.x) + ","
                                               + std::to_string(origin.y), [&] {
            return tiles_around(origin, 0, "camp path origin");
        });
        if (origin_tile.is_empty()) continue;
        with_context("distance_field.compute_to camp group="
                     + std::to_string(static_cast<std::uint32_t>(
                         static_cast<cambc::handle_camp_group_t>(group)))
                     + " roots=" + std::to_string(roots.count())
                     + " walls=" + std::to_string(blocked.count()), [&] {
            field.compute_to(blocked, roots, origin_tile, visited);
        });
        const auto path_distance = field.get(origin);
        if (path_distance == cambc::distance_field::unreachable) continue;

        float combat_turns = 0.0f;
        float incoming_per_turn = 0.0f;
        if (!reward_ready) {
            for (const auto& camp : group.camps()) {
                const auto stats = with_context("camp design metadata spawn="
                                                + std::to_string(camp.spawn_position().x) + ","
                                                + std::to_string(camp.spawn_position().y), [&] {
                    return camp.base_stats();
                });
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

    // If every visible target is unavailable or unreachable, continue
    // exploring toward free approach tiles around all known camp spawns.
    all_approaches &= ~blocked;
    return destination.is_empty() ? all_approaches : destination;
}

// Attack a camp already in range, otherwise choose a worthwhile camp group.
void farm_camps() {
    auto& me = cambc::self();
    const auto visible_camp_list = with_context("farm visible camps", [] {
        return visible_camps();
    });
    const bool area_cast = with_context("camp area ability evaluation", [&] {
        return cast_area_ability(visible_camp_list);
    });
    if (!area_cast) with_context("camp offensive ability evaluation", [&] {
        cast_offensive_ability(visible_camp_list);
    });
    if (with_context("camp attack evaluation", [&] {
            return attack_first_in_range(visible_camp_list);
        })) return;
    // A camp response can kill the champion during an action; do not query a
    // dead champion's sentinel position to build a path target.
    if (!me.is_alive()) return;

    const auto goals = with_context("choose_camp_goals", [] { return choose_camp_goals(); });
    // Fresh vision after movement may reveal a camp already in range.
    if (with_context("move_towards_closest camp", [&] { return move_towards_closest(goals); })) {
        if (!me.is_alive()) return;
        const auto post_move_camps = with_context("post-move visible camps", [] {
            return visible_camps();
        });
        with_context("post-move camp attack", [&] {
            attack_first_in_range(post_move_camps);
        });
    }
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
    float visible_threat = 0.0f;
    if (!at_spawn) {
        visible_threat = with_context("pre-recall incoming_visible_damage", [&] {
            return incoming_visible_damage(me.position());
        });
        const bool badly_hurt = me.health() < me.max_health() * 0.35f;
        const bool at_risk = visible_threat > 0.0f && me.health() <= visible_threat + me.strength();
        if (badly_hurt || at_risk) {
            if (visible_threat > 0.0f) retreat_from_visible_threats();
            else me.recall();
            return;
        }
    }

    // Shields and heals are most valuable before visible combat or while
    // surviving an active camp. This leaves attack-reset abilities available
    // to attack_first_in_range below.
    const bool under_threat = with_context("support threat assessment", [&] {
        return incoming_visible_damage(me.position()) > 0.0f;
    });
    with_context("cast_support_ability", [&] { cast_support_ability(under_threat); });

    // Attack the first enemy champion already in range.
    const auto enemies = with_context("vision::champions enemy list", [] {
        return cambc::vision::champions(team::enemy);
    });
    with_context("enemy ability evaluation", [&] {
        if (!cast_area_ability(enemies)) cast_offensive_ability(enemies);
    });
    if (with_context("enemy attack evaluation", [&] { return attack_first_in_range(enemies); })) return;

    // Batch two common 22-gem camp hauls when healthy and unthreatened.
    // Bank at 44 gems, at spawn, under visible threat, or below 70% health.
    const auto carried_gems = me.gem_count();
    const bool bank_now = carried_gems >= 44 || at_spawn
        || me.health() < me.max_health() * 0.70f || visible_threat > 0.0f;
    if (carried_gems > 0 && bank_now) {
        // Union all altar approach tiles: the field chooses the nearest reachable altar.
        cambc::bitboard goals;
        goals.clear();
        for (auto altar : cambc::map::altars().positions()) {
            if (distance(me.position(), altar) <= cambc::constants::submit_gems_range
                && !cambc::vision::has_altar_lock(altar)) {
                    me.submit_gems(altar);
                    return;
                }
            if (!cambc::vision::has_altar_lock(altar))
                goals |= tiles_around(altar, cambc::constants::submit_gems_range, "altar approach");
        }
        move_towards_closest(goals);
        return;
    }

    with_context("farm_camps", [&] { farm_camps(); });

}
