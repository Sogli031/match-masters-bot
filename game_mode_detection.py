"""Conservative game-mode recognition from the icon beside the RULES button."""

from __future__ import annotations

import base64
import zlib
from dataclasses import dataclass

import numpy as np
from PIL import Image

from move_strategy import GameMode


_REFERENCE_SIZE = 12
_MAX_DISTANCE = 0.055
_MIN_MARGIN = 0.008

# Canonical 12x12 RGB fingerprints cropped from saved state.png references.
# Mighty Mushrooms and Bombs Away intentionally map to None mode because their
# board pieces are already handled by normal simulation.
_REFERENCE_DATA = {
    # Captured from Debug/runs/2026-07-30_17-10-42_198/state.png while the
    # manual mode selector and the live game were both on Color Crush Mode.
    "color_crush": (
        GameMode.COLOR_CRUSH,
        "eJwBsAFP/ikZUisbVC4bVSwSTC0eVS0qYS0qYi0qYSwoYCopYywqZSwqZSkZUiMVUxwPTx1NjyGM2iaW7ieZ7yWa8Suf+TSf8jOd7zOe7yIVTj0mRWZFToB2eIp3fn5rd3JfcXBjfU5iii+Q7TWe/zSb/hcOTqNnVv+lafiTXf+bY7l4SK+SSbSCPrtrRDF7xjSh/zSa+AwILaJnVfmbZ+6YZtOCYamIKv//OszDKKRkUjmCzDOg/zSa+XaWuKxzYvqbZfmWa7BqXpuOeNrFKJSCKo1aRDqBzDGf/zOZ+Gmj7K54aPqYY5mEN06aTGhkeItWQM9/Yc18Vi52xC+Y/TCS8VKT3qp1YbhvbMmWjo2BMrBtTPycavueadB/WClsuiqL7yqF5FCS4JxwaJVMOJk7c55aaPeaY+qSZPicadiHXSRhsCJ84CN21kSK2YlaVK9lSK9wSP6jZ/acavacauaOZJhVQhtUoyBw1B9qykqS5zdfnExCV4VTTcByWMNxVYBFQj8rRhcwbBdXthpdwRlbvkKJ5keT9St51QBIhhtAZiI4WgtSjwxquhR2zBVxxBRwwRRwwkdhyNg=",
    ),
    "crazy_columns": (
        GameMode.CRAZY_COLUMNS,
        "eNoBsAFP/ikZUisbVC4bVSsSTCsdVCspYSwqYi0qYSwoYCopYywqZSwqZSkZUiMVUxsPTyFRkSqR3CyY7CiY7iWZ8iyg+TSf8jOd7zOe7yIVTj0nRWtHTW5obV9ed1JZe2hhdnBneUxhii+Q7TWe/zSb/hUOTqpqVcSFaYh8k5qSpqapyZBsbf+eXM93Six4xTWi/zSa+AoHLa1tVq1yXHSDraaszaOw1ph1ediHXsh9WjJ9yjSh/zSa+XaWuK52ZPiTWoBvfY6Yu36CqWRhbXt3V6RoUTiAyjGf/zOZ+Gmj7K13afuWXIl0gJGdv5mhxXVseo92UaNpUDZ6xi6X/TCS8VKT3ql1Z/2WXZN4fKCsy66405OFlt6DWM9/WClsuiqL7yqF5EuP37N9bfCRXHNwjIubxouVv2x7rMF/YuSOXyFgsCJ84CN21kSL2oRWU+eIW4xkY3FWY3tYXZBiWtKCX5xXQxpToyBw1B9qykqS5zdfnEU9VIFORcRzUsx1U4xMQkMtRxcvbBdXthpdwRlbvkKJ5keT9S161QBJhxtBaCA3WwhRjwtpuhR2zBVxxBRwwRRwwrkZyR0=",
    ),
    "chest": (
        GameMode.CHEST,
        "eNoBsAFP/isZVSwbVC4bVSwSTC0eVS0qYSwqYiwpYSwpYCopYywqZSwqZR8ZRyIVUhsOTxxNjiKN2ieX7i2b7yib8yuf+TSf8jOd7zOe72wcoEsoVGtHSYZ5fIZ2g3hpe1dWc2Vgd1Bkiy+P7TWe/zSb/pwE57BmY8SJZZldQaZeL59TF4ViRqV+c9FzQSx5xzWi/zSa+I0C1ZRXXoaHg6RlIpNWHJlgLLGGU4iWpZNgVDuByjKg/zSa+YgE04JQX46Tk4p+exyexhGp4mt6lGl2inZSUD2ByTCf/zOZ+H4E0YNNWXJ8h3t5gA2EwACT03JkWoGHkI9bTDh7xi2X/DCS8WgBy6hgWpB9eY1yT3s8CHs/FJddHoeGjLhuTy5wvCmL7yqF5FcAw71wZ7mCaHeEjpd7XY98Z4iFf318hb52VipmsSF74CN21lAAvYhTU8+EWZNsZqN5a7J9Z75+Yr1zVZdUQhtUoyBw1R9qylUDxT4HhkksUYRUR8t0VM51VIpKQ0cwSRgwbBZXthpdwRlbvkMCu0kAxiwKsQBChBlBZyA2WghRjgppuhR2zBVxxBRwwRRwwoiduR4=",
    ),
    # Captured from the stable Red and Blue Mode frames in the latest complete
    # Debug run (2026-08-01_02-54-57_717).
    "red_and_blue": (
        GameMode.RED_AND_BLUE,
        "eJwBsAFP/isZVSwbVC4bVSwSTC0eVS4qYS4rYi0qYSwpYCopYywqZSwqZR8ZRyMVUhsOTxtOkSOP3SKU7iOW7iWZ8iyf+TSf8jOd7zOe720coEknU2pJTIt0b4RrcIx0eoRud29mek1iii+Q7TWe/zSb/psD57VqZeaQXGlxiIqQoc14Wv+ZXv+bYc92SSx4xTWi/zSa+IYA1rNlW2FjjUZ72+R8n7xKbbl4XP+ibMt9WTF9yjSh/zSa+YEA06ZmYY1GY/wnTfwmRXOAxlVulOmJV9SDWi57yDOg/zOZ+HIAzrVwZ5xPSoo9iWqa2TC1/7BYkaM/VMKAWjB2xC+Y/TCS8WYAybJrZtyLWSFKoi+B8ZponPAsVk9Jo6ttUTFwuyiK7yqF5FoAw65raP+lZrNzV2EoVqEcVExBoFdahNeCVCRjsSF74CN21lEAvYNRUemTYP+fbOKOW6x3Y6V5adqDWJ1YRBpToiBw1R9qylUDxT8HhkYqUHlQSsZ1Ws53VY1KQEItSBYvbBdXthldwRlbvkMCu0kAxi0KsQBDgxpBZiA2WghRjwtpuhR2zBVxxBRwwRRwwr3cwZA=",
    ),
    "mighty_mushrooms": (
        GameMode.NONE,
        "eNoBsAFP/iEjACIlASQmASQcACUnACYzESczEiczESYxDyQxESUzEiUzEiIkARsgABIaABdTWSOOySWX5yKW5ySZ6iug8jOg6zKe6DOe6BcbADYqHWZIO4d8fIB2gn5teYlxeHRpfUxhizCQ7zae/zSb/4RcLaVnUv+mcL5qT8NLP8hcULVwWfSSW9N5Sit4xTWi/jSa+NLGuLZ4WrNjUctDT/lVWPlWWNdGT5tPT8iAWzN9yjSh/zSa+cafgJZpWs9dX/9BQPJCQvtpa/pKScg/SpVaTTmCyjGf/zOZ+H9TJpJgULA1PashJ7hPTcReXqQrLqQcKIlLRDh+xy2W/DCS8TZLHKxwVpdTQl4+SPbz3v//8pB8fGUuLsB3Vi1vuymL7yqF5F82FLVwWP+oaqd2Y66ai8Cnj5R5cfKYZd6LYCNhryJ84CN21ng6F4NSTemRau6SZL52U7p1Ut6KX+uQZpZUQhtUoyBw1B9qyoNEGlwwHEwzOXtRUMx5Ws54WYVJRD4qRhgwbBdXthpdwRlbvntDG4VFFlo/KwBFexlAaCA2WApRjgxquhR2zBVxxBRwwRRwwoKouQU=",
    ),
    "bombs_away": (
        GameMode.NONE,
        "eJwBsAFP/i4jETElEzEjETglCDQpES8sHi8tHy4sHi4rHCwrHiwsHy0sH3GSRGSLPmePP0+fiCeY1CWZ6iib6yyd7iug9TSg7jOe6zOf62GJN1hcNnhmS4V7fJF3g4Jmem9ddFRWd1JjiS+Q7zWe/zSb/0dvMKRrVf+ea+yHU75zToiPP5qfco6Ci6plRzF7xDSh/jSa+FB8O692V9eFYYGPcHjKSm/XN2XIOm2AXJVfWjeAyDOh/zSa+TlZKaloVoiPS7H6e06aKkeeIlTFKXqBQNh5Vy99yDOg/zOZ+DZEG5RbUm2lPFezJApZCESdJGXQMFGENcRyWDB5xC+Y/TCS8UBfKqFjVWOLOSWNFBRfDzaKHD+vHlx9OM11WCpvuimL7yqF5E18N7p8Xa57VCuCISmOFzejHTOHJbN7VuOLYCFhryJ84CN21lmLPYJVTu2LaLF3VXZ3Q3Z3Q7V5WeuOZZhWQhtUoyBw1R9qymiYQUtkNEg+PoRRUMVuV8htVolKRD8rRhcwbBdXthpdwRlbvmiWQnGhQE2FTABJfRpBaCE5WQhRjgxquhR2zBVxxBRwwRRwwkWzs+0=",
    ),
    "drillin_down": (
        GameMode.DRILLIN_DOWN,
        "eJwBsAFP/iALUyEMUiMNUyACSiEOUyIcXyMcYSMcYCEbXyAbYSAcYyAcYxQJRhcGUBAATRpHjyaO3CiY7iaX7SSY8Sqe+TOe8jKc7zKc72YUn0cjU2VDTW9odG1idG1ee3FienJpf09jii+Q7Taf/zSc/p0F5rBmZdSMUs+MN9mbQNqWEM9/Fst2QMx1Sy14xDWi/zSa+IwC15dVWKGLYsnBsLytm7aRK8KWDKV+HKhoVTmCyzOg/zSa+XwA07dsZZNkUZiNkbWWjZ92c5BgV4ZhWsd4UzJ9yTOg/zOZ+HIAz7VtaNmGVpqHiNO7r6Z1XHBMRbhzVtuFWSt0wzCY/TCS8WgAyalmY/+jZ5drX7ioo6yEc4dnZfW2ktB/WSlsuiqL7yqF5FoAw7BraP+kat2OZauTj5qCgcqJbP+tfNaGXSRhsCJ84CN21lEAvYNRUumSX/+caa1yWpFjVf2cZeWLYZhVQhtUoyBw1B9qylUDxT8HhkYqUHxSS8BxVsBvU4JHRD8rRhcwbBdXthpdwRlbvkMCu0kAxi0KsQBCgxxDZyM4WwpSjgxquhR2zBVxxBRwwRRwwutEw4k=",
    ),
    "green_leaf": (
        GameMode.GREEN_LEAF,
        "eNoBsAFP/isZVSwbVC4bVSwSTC0eVS0qYS0qYi0qYSwpYCopYywqZSwqZR8ZRyIVUhwOTxtNjh+O2iKV7SiZ7yaZ8iyf+TSf8jOd7zOe72wcoEooU2VGS4p3e5RxgZBxfHJhc21mek1iii+Q7TWe/zSb/pwD569nY/+hZad6TnWMO5x4SUR7L+yNW9V7Syp3xTWi/zSa+IUA1LFoYtOKaG20WhPAHSKzLRqjKZt3VtmBXC58yTSh/zSa+XwA0rVlZKONWj3CNibBISy9JSHCICqkLrZrUzWAyTKg/zOZ+HAAzr1qaZGBSxKyIC3GJSHBIUXLMlu+R45dRjt8yC2X/DCS8WUAybZlZ3x/Rh3FIzHOJybJJIzlYG+CTq1mSzByvSiK7yqF5FgAwrhra21tPQuBHBOUGxGPHB1eI6NtT+OMYCFgryJ74CN21lAAvYVTUuSLXbduV5dnSpxoTNOAYPGTaJdVQhtUoyBw1R9qylUDxT4HhkgsUYZZTc95W9F5WYdLRD0qRRcwbBdXthpdwRlbvkMCu0kAxiwKsABBgxhBZh82WQlRjgxquhR2zBVxxBRwwRRwwuSStFo=",
    ),
    "funky_tiles": (
        GameMode.FUNKY_TILES,
        "eNoBsAFP/isZVSwbVC4bVSwTTCsdVC0qYS4rYi0qYSwpYCopYywqZSwqZR8ZRyIVUhwPTxtMjiiR2yeX7iGU7SWZ8iyg+TSf8jOd7zOe72wcoEooU2NES4t+fGhienVoeJB5enJoekxhiTCQ7TWe/zSb/pwD5q5mZP+lZOGAWrNqMsJjPshpU/KQXdF4Sit4xTWi/zSa+IQA1LhrYrt/ZyqPSNXHJsxYUcIZV61lV9uMXC96yjSh/zSa+XsA07tsYKV2dRCQkXNkUndcYLQ7U9Q2VIROSzWAyTKf/zOZ+H4E0X1OVotVtEpw5J1wTuWAWblwN8xmSHZGTTd8xC6X/TCS8WoCy59gYIZbVZNZ2WxrwCOAZnHKLqCXOct2WStvuimL7yqF5FgAw7lxbPOaWmdBgmxSukV41jVdYaJyWt+JXiJhsCJ84CN21lEAvYJQUeyUYdiJW7t5T25EZ+CEY/KSZJdVQhtUoyBw1R9qylUDxT8HhkYqUIJVTct4W7ptTIFIQz4qRhcwbBdXthpdwRlbvkMCu0kAxi0KsQBCgxlBZiQ4XApSjgxquhR2zBVxxBRwwRRwwk+avPA=",
    ),
}


@dataclass(frozen=True)
class GameModeDetection:
    accepted: bool
    mode: GameMode | None
    label: str | None
    confidence: float
    distance: float
    margin: float
    region: tuple[int, int, int, int] | None = None


def mode_icon_region(
    board_left: int,
    board_up: int,
    square_size: int,
    board_size: int = 7,
) -> tuple[int, int, int, int]:
    """Return the screen crop for the icon immediately left of RULES."""
    size = max(1, int(square_size))
    left = int(board_left) + round((float(board_size) / 2.0 - 0.881) * size)
    top = int(board_up) + round((float(board_size) + 0.095) * size)
    edge = max(16, round(0.571 * size))
    return left, top, edge, edge


def _reference_images() -> dict[str, tuple[GameMode, np.ndarray]]:
    references = {}
    for label, (mode, payload) in _REFERENCE_DATA.items():
        raw = zlib.decompress(base64.b64decode(payload))
        image = np.frombuffer(raw, dtype=np.uint8).reshape(
            (_REFERENCE_SIZE, _REFERENCE_SIZE, 3)
        )
        references[label] = (mode, image.astype(np.float32))
    return references


_REFERENCES = _reference_images()


def _icon_feature(image) -> np.ndarray | None:
    if image is None:
        return None
    if not isinstance(image, Image.Image):
        try:
            image = Image.fromarray(np.asarray(image).astype(np.uint8))
        except Exception:
            return None
    if image.width < 8 or image.height < 8:
        return None
    return np.asarray(
        image.convert("RGB").resize(
            (_REFERENCE_SIZE, _REFERENCE_SIZE),
            Image.Resampling.LANCZOS,
        ),
        dtype=np.float32,
    )


def _feature_distance(first: np.ndarray, second: np.ndarray) -> float:
    color_distance = float(np.mean(np.abs(first - second)) / 255.0)
    first_gray = np.mean(first, axis=2)
    second_gray = np.mean(second, axis=2)
    first_edges = np.concatenate(
        (np.diff(first_gray, axis=0).ravel(), np.diff(first_gray, axis=1).ravel())
    )
    second_edges = np.concatenate(
        (np.diff(second_gray, axis=0).ravel(), np.diff(second_gray, axis=1).ravel())
    )
    edge_distance = float(np.mean(np.abs(first_edges - second_edges)) / 255.0)
    return color_distance * 0.7 + edge_distance * 0.3


def detect_mode_icon(image, *, region=None) -> GameModeDetection:
    feature = _icon_feature(image)
    if feature is None:
        return GameModeDetection(False, None, None, 0.0, 1.0, 0.0, region)

    ranked = sorted(
        (
            _feature_distance(feature, reference),
            label,
            mode,
        )
        for label, (mode, reference) in _REFERENCES.items()
    )
    best_distance, best_label, best_mode = ranked[0]
    second_distance = ranked[1][0]
    margin = max(0.0, second_distance - best_distance)
    accepted = bool(best_distance <= _MAX_DISTANCE and margin >= _MIN_MARGIN)
    distance_confidence = max(0.0, 1.0 - best_distance / _MAX_DISTANCE)
    margin_confidence = min(1.0, margin / (_MIN_MARGIN * 2.0))
    confidence = min(distance_confidence, margin_confidence)
    return GameModeDetection(
        accepted,
        best_mode if accepted else None,
        best_label,
        confidence,
        best_distance,
        margin,
        region,
    )


def detect_game_mode_from_screen(
    image,
    *,
    board_left: int,
    board_up: int,
    square_size: int,
    board_size: int = 7,
) -> GameModeDetection:
    region = mode_icon_region(board_left, board_up, square_size, board_size)
    if image is None:
        return GameModeDetection(False, None, None, 0.0, 1.0, 0.0, region)
    if not isinstance(image, Image.Image):
        try:
            image = Image.fromarray(np.asarray(image).astype(np.uint8))
        except Exception:
            return GameModeDetection(False, None, None, 0.0, 1.0, 0.0, region)
    left, top, width, height = region
    if left < 0 or top < 0 or left + width > image.width or top + height > image.height:
        return GameModeDetection(False, None, None, 0.0, 1.0, 0.0, region)
    icon = image.crop((left, top, left + width, top + height))
    return detect_mode_icon(icon, region=region)


def prefer_hot_color_board_detection(
    icon_detection: GameModeDetection | None,
    hot_color_candidate: dict | None,
) -> GameModeDetection | None:
    """Use decisive numbered-tile evidence when the mode icon is inconclusive."""
    if not isinstance(hot_color_candidate, dict):
        return icon_detection
    if (
        icon_detection is not None
        and icon_detection.accepted
        and icon_detection.mode not in {None, GameMode.NONE}
    ):
        return icon_detection
    confidence = float(hot_color_candidate.get("confidence", 0.0))
    margin = float(hot_color_candidate.get("confidence_margin", 0.0))
    return GameModeDetection(
        accepted=True,
        mode=GameMode.HOT_COLOR,
        label="hot_color_board",
        confidence=confidence,
        distance=max(0.0, 1.0 - confidence),
        margin=margin,
        region=(icon_detection.region if icon_detection is not None else None),
    )
