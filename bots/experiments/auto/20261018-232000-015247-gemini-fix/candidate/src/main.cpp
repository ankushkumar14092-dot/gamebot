// Dispatch draft and gameplay; a failed turn is logged and still yields.
#include <cambc.h>
#include <iostream>
#include <string_view>
#include "bot.h"
#include "draft.h"

namespace {
void log_exception_context(std::string_view message) noexcept {
    static unsigned logged = 0;
    if (logged >= 8) return;
    ++logged;
    std::cerr << "bot context: operation=turn dispatch error=" << message;
    try {
        const auto& me = cambc::self();
        const auto position = me.position();
        std::cerr << " champion=" << static_cast<int>(me.champion_name())
                  << " position=(" << position.x << ',' << position.y << ')';
    } catch (...) {
        std::cerr << " champion/position=unavailable";
    }
    std::cerr << '\n';
}
} // namespace

int main() {
    Bot bot;
    while (true) {
        try {
            if (cambc::is_draft())
                play_draft();
            else
                bot.play_turn();
        } catch (const std::exception& error) {
            log_exception_context(error.what());
            std::cout << "bot error: " << error.what() << std::endl;
        } catch (...) {
            log_exception_context("unknown exception");
            std::cout << "bot error: unknown exception" << std::endl;
        }

        cambc::end_turn();
    }
}
