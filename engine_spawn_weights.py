"""Integer spawn pools reconstructed from Match Masters 5.817 ARM64.

Engine color numbers are used throughout. This module does not generate
tiles or resolve matches. Evidence: SpawningEngine GetColorsPriority RVA
0x5a075c4, GetColorNameForFairSort 0x5a07958, createWeightsListNew 0x5a095fc.
The returned cumulative pool is intentionally not normalized to 100.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol


class NextRng(Protocol):
    def next(self) -> int: ...


COLOR_NAMES = {0: "Empty", 1: "None", 2: "Red", 3: "Green", 4: "Blue",
               5: "Yellow", 6: "Orange", 7: "Purple", 8: "White", 12: "All"}


def _div(numerator: int, denominator: int) -> int:
    """C#/ARM64 signed division, truncating toward zero."""
    if denominator == 0:
        raise ValueError("spawn pool requires at least one count dictionary entry")
    quotient = abs(numerator) // abs(denominator)
    return -quotient if (numerator < 0) != (denominator < 0) else quotient


def get_colors_priority(
    counts: Mapping[int, int],
    spawned_colors: Mapping[int, int],
    rng: NextRng,
    game_colors: Sequence[int] | None = None,
) -> list[int]:
    """Return count-ascending, fair-name-ascending priority without mutation.

    The source LINQ sorter computes both key arrays in source-list order.
    Each Red or Blue independently consumes one Next(2), even when its
    primary count key differs from every other color. No shuffle is used.
    Pass the captured gameColors list to preserve the engine enumeration
    order; the dictionary order is only a convenience when no list is given.
    """
    priority = list(counts if game_colors is None else game_colors)
    adjusted = dict(counts)
    for color, spawned in spawned_colors.items():
        adjusted[color] += 2 * spawned
    decorated = []
    for index, color in enumerate(priority):
        primary = adjusted[color]
        if color in (2, 4):
            # RandomWrapper.Next(max) = Next() % max for positive outputs.
            bit = rng.next() % 2
            secondary = ("A" if bit == 1 else "B") if color == 4 else ("B" if bit == 1 else "A")
        else:
            secondary = COLOR_NAMES.get(color, str(color))
        decorated.append((primary, secondary, index, color))
    return [entry[3] for entry in sorted(decorated)]


# Compatibility with the singular name used in early integration notes.
get_color_priority = get_colors_priority


def create_weights_list_new(
    colors_priority: Sequence[int],
    counts: Mapping[int, int],
    color_weights: Mapping[int, int],
    *,
    rows: int = 7,
    columns: int = 7,
    max_pool_size: int = 70,
    max_pool_unit: int = 10,
) -> list[int]:
    """Port createWeightsListNew's returned cumulative integer thresholds.

    Counts are the engine's colorCountDictionary, not recounted only from
    supplied priority colors. Missing keys raise as in the dictionary indexer.
    Input maps/lists are never changed. The algorithm uses no random draws.
    """
    if not counts:
        raise ValueError("spawn pool requires color counts")
    adjusted = dict(counts)
    for color in counts:
        adjusted[color] -= min(color_weights[color] - 1, adjusted[color])
    target = _div(rows * columns, len(counts))
    deficits = {color: max(target - adjusted[color], 0) for color in colors_priority}
    total_deficit = 0
    max_deficit = 0
    max_color = 1
    # Strict '>' means the first maximum in colorsPriority gets the remainder.
    for color in colors_priority:
        deficit = deficits[color]
        total_deficit += deficit
        if deficit > max_deficit:
            max_deficit, max_color = deficit, color
    pool = min(total_deficit * max_pool_unit, max_pool_size) if total_deficit > 0 else 0
    base = _div(100 - pool, len(counts))
    per_deficit = _div(pool, total_deficit) if total_deficit > 0 else 0
    remainder = pool - per_deficit * total_deficit
    remaining_pool = pool
    cumulative = []
    running = 0
    for color in colors_priority:
        running += base
        deficit = deficits[color]
        if deficit > 0:
            extra = min(remaining_pool, deficit * per_deficit)
            remaining_pool -= extra
            running += extra + (remainder if color == max_color else 0)
        cumulative.append(running)
    return cumulative


def pick_color(colors_priority: Sequence[int], cumulative: Sequence[int], roll: int) -> int:
    """FillAllEmptySlots uses the first color as the uncovered-tail fallback."""
    if not colors_priority or len(colors_priority) != len(cumulative):
        raise ValueError("invalid priority/cumulative pool")
    if not 0 <= roll < 100:
        raise ValueError("spawn color roll must be Range(0,100)")
    for color, threshold in zip(colors_priority, cumulative):
        if roll < threshold:
            return color
    return colors_priority[0]
