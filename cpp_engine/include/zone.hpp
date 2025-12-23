/**
 * Pokemon TCG Engine - Zone Container
 *
 * Represents a card zone (deck, hand, discard, prizes).
 * Optimized for fast operations and cloning.
 */

#pragma once

#include "card_instance.hpp"
#include <algorithm>
#include <random>

namespace pokemon {

/**
 * Zone - Ordered container for cards.
 *
 * Supports all zone types: Deck, Hand, Discard, Prizes.
 */
struct Zone {
    std::vector<CardInstance> cards;
    bool is_ordered = true;    // Whether card order matters (Deck, Discard)
    bool is_hidden = false;    // Whether zone is hidden from opponent
    bool is_private = false;   // Whether only owner can see contents

    // ========================================================================
    // CONSTRUCTORS
    // ========================================================================

    Zone() = default;

    Zone(bool ordered, bool hidden, bool private_)
        : is_ordered(ordered)
        , is_hidden(hidden)
        , is_private(private_)
    {}

    // ========================================================================
    // BASIC OPERATIONS
    // ========================================================================

    void add_card(CardInstance card, int position = -1) {
        if (position < 0 || position >= static_cast<int>(cards.size())) {
            cards.push_back(std::move(card));
        } else {
            cards.insert(cards.begin() + position, std::move(card));
        }
    }

    CardInstance* remove_card(const CardID& card_id) {
        for (auto it = cards.begin(); it != cards.end(); ++it) {
            if (it->id == card_id) {
                CardInstance removed = std::move(*it);
                cards.erase(it);
                // Return via static to avoid dangling pointer
                // In practice, caller should capture the return value immediately
                static CardInstance result;
                result = std::move(removed);
                return &result;
            }
        }
        return nullptr;
    }

    // Remove and return card (move semantics)
    std::optional<CardInstance> take_card(const CardID& card_id) {
        for (auto it = cards.begin(); it != cards.end(); ++it) {
            if (it->id == card_id) {
                CardInstance removed = std::move(*it);
                cards.erase(it);
                return removed;
            }
        }
        return std::nullopt;
    }

    CardInstance* find_card(const CardID& card_id) {
        for (auto& card : cards) {
            if (card.id == card_id) {
                return &card;
            }
        }
        return nullptr;
    }

    const CardInstance* find_card(const CardID& card_id) const {
        for (const auto& card : cards) {
            if (card.id == card_id) {
                return &card;
            }
        }
        return nullptr;
    }

    int count() const {
        return static_cast<int>(cards.size());
    }

    bool is_empty() const {
        return cards.empty();
    }

    // ========================================================================
    // DECK OPERATIONS
    // ========================================================================

    // Draw from top of deck (index 0)
    std::optional<CardInstance> draw_top() {
        if (cards.empty()) {
            return std::nullopt;
        }
        CardInstance top = std::move(cards.front());
        cards.erase(cards.begin());
        return top;
    }

    // Peek at top card without removing
    CardInstance* peek_top() {
        if (cards.empty()) {
            return nullptr;
        }
        return &cards.front();
    }

    // Add to bottom of deck
    void add_to_bottom(CardInstance card) {
        cards.push_back(std::move(card));
    }

    // Add to top of deck
    void add_to_top(CardInstance card) {
        cards.insert(cards.begin(), std::move(card));
    }

    // Shuffle the zone (for deck)
    template<typename RNG>
    void shuffle(RNG& rng) {
        std::shuffle(cards.begin(), cards.end(), rng);
    }

    // ========================================================================
    // CLONING
    // ========================================================================

    Zone clone() const {
        Zone copy;
        copy.is_ordered = is_ordered;
        copy.is_hidden = is_hidden;
        copy.is_private = is_private;

        copy.cards.reserve(cards.size());
        for (const auto& card : cards) {
            copy.cards.push_back(card.clone());
        }

        return copy;
    }
};

} // namespace pokemon
