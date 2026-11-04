"""Field-for-field port of Match3Engine.RandomWrapper, game 5.817.

Evidence: ARM64 listings in Debug/reverse/simulator_all. This deliberately
does not use Python's MT implementation: the game uses a nonstandard seed
recurrence, bit-masked twist indices and a 623-output index cycle on a
624-word matrix. Callback side effects are outside this pure simulation port.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterable, TypeVar

T = TypeVar("T")
UINT32 = 0xFFFFFFFF
INT_MAX = 0x7FFFFFFF


def _s32(value: int) -> int:
    value &= UINT32
    return value - 0x100000000 if value > INT_MAX else value


def _div_trunc(a: int, b: int) -> int:
    quotient = abs(a) // abs(b)
    return -quotient if (a < 0) != (b < 0) else quotient


def _remainder(a: int, b: int) -> int:
    return a - _div_trunc(a, b) * b


def _float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


@dataclass
class EngineRNG:
    matrix: list[int]
    index: int
    seed: int
    counter: int = 0

    def __post_init__(self):
        if len(self.matrix) != 624 or any(not isinstance(v, int) or not 0 <= v <= UINT32 for v in self.matrix):
            raise ValueError("Engine RNG requires exactly 624 UInt32 words")
        if not isinstance(self.index, int) or not 0 <= self.index < 624:
            raise ValueError("Engine RNG index must be in [0,624)")
        self.matrix = list(self.matrix)
        self.seed &= UINT32
        self.counter = _s32(self.counter)

    @classmethod
    def from_seed(cls, seed: int, counter: int = 0) -> "EngineRNG":
        """ctor(int seed) 0x5af5898; ctor(seed,counter) 0x5af5958."""
        seed &= UINT32
        matrix = [seed]
        for _ in range(623):
            previous = matrix[-1]
            matrix.append((0x6C078965 * (previous ^ ((previous >> 30) + 1))) & UINT32)
        rng = cls(matrix, 0, seed, 0)
        for _ in range(max(0, counter)):
            rng.next()
        return rng

    @classmethod
    def from_capture(cls, raw: dict) -> "EngineRNG":
        """Accept the exact raw profile.rng field, or a complete profile."""
        raw = raw.get("rng", raw)
        return cls(raw["_matrix"], raw["_index"], raw["_seed"], raw["<counter>k__BackingField"])

    def to_capture(self) -> dict:
        return {"_matrix": self.matrix[:], "_index": self.index, "_seed": self.seed,
                "<counter>k__BackingField": self.counter}

    def clone(self) -> "EngineRNG":
        """Clone 0x5af5af8 copies the entire 624-word matrix."""
        # Not through __init__: its 624-word validation dominated the exact refill,
        # which clones once per candidate. These words were validated once already.
        clone = object.__new__(type(self))
        clone.matrix = self.matrix[:]
        clone.index = self.index
        clone.seed = self.seed
        clone.counter = self.counter
        return clone

    copy = clone

    def generate(self) -> None:
        """Generate 0x5af5ba8, in-place and in increasing index order."""
        matrix = self.matrix
        for i in range(624):
            packed = ((matrix[(i + 1) & 623] << 1) | (matrix[i] >> 31)) & UINT32
            matrix[i] = (matrix[(i + 397) & 623] ^ (packed >> 1)
                         ^ (0x9908B0DF if packed & 1 else 0)) & UINT32

    def next(self, maximum: int | None = None) -> int:
        """Next() 0x5af5990; Next(max) 0x5af5870 (max=0 consumes nothing)."""
        if maximum == 0:
            return 0
        if maximum is not None:
            return _remainder(self.next(), _s32(maximum))
        self.counter = _s32(self.counter + 1)
        if self.index == 0:
            self.generate()
        value = self.matrix[self.index]
        value ^= value >> 11
        value ^= (value << 7) & 0x9D2C5680
        value ^= (value << 15) & 0xEFC60000
        value ^= value >> 18
        value &= UINT32
        self.index = (self.index + 1) % 623
        # Assembly uses multiply/shift and 32-bit correction equivalent to
        # unsigned modulo int.MaxValue, not a sign-bit mask or abs(int).
        return value % INT_MAX

    def range(self, minimum: int, maximum: int) -> int:
        """Range 0x5af1fd8, upper exclusive; equal endpoints consume nothing."""
        if minimum > maximum:
            raise ValueError("minimum exceeds maximum")
        if minimum == maximum:
            return minimum
        difference = _s32(minimum - maximum)
        return _s32(minimum + _remainder(self.next(), difference))

    def chance(self, percent: int) -> bool:
        """Chance 0x5af5c4c always draws and uses <=, including at -1/100."""
        return self.next() % 100 <= percent

    def value(self) -> float:
        """get_Value 0x5af5830: float32((Next()%10000) / 10000f)."""
        return _float32((self.next() % 10000) / 10000.0)

    random = value

    def normal_range(self, minimum: int, maximum: int) -> int:
        """NormalRange 0x5af5c88: two Range draws, truncating their mean."""
        if minimum > maximum:
            raise ValueError("minimum exceeds maximum")
        return _div_trunc(_s32(self.range(minimum, maximum) + self.range(minimum, maximum)), 2)

    def choice(self, items):
        if not items:
            raise IndexError("Cannot select from an empty list")
        return items[self.range(0, len(items))]

    def random_key_order(self, items: Iterable[T], *, selector: str) -> list[T]:
        """Stable random-key ordering helper with an explicit selector."""
        items = list(items)
        if selector not in ("next", "value"):
            raise ValueError("selector must be 'next' or 'value'")
        if len(items) < 2:
            return items
        draw = self.next if selector == "next" else self.value
        return sorted(items, key=lambda _: draw())

    def shuffled(self, items: list[T]) -> list[T]:
        """ArrayExtensions.Shuffle, not Fisher-Yates and not in-place.

        Wrappers 0x3c13990 / 0x3c13b80 construct closures at 0x4073798 /
        0x40737b8. Their selector bodies 0x40737a0 / 0x40737c0 tail-call
        RandomWrapper.Next. OrderBy is stable, including on random-key ties.
        For fewer than two elements the wrapper returns the input unchanged.
        """
        if len(items) < 2:
            return items
        return self.random_key_order(items, selector="next")
