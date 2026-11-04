from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

import recognition
from board_profiles import SUPERSIZE_PROFILE
from move_strategy import BOOSTER_MAX_CHARGE
from recognition import detect_booster_activate_in_image


AUTO_CONFIDENCE_THRESHOLD = 0.78

BOOSTER_FULL_SCORE_THRESHOLD = 0.78
BOOSTER_BLUE_MIN_COLUMN_RATIO = 0.24
BOOSTER_MIN_ACTIVATION_REGION_SIZE = 8
BOOSTER_MIN_METER_REGION_SIZE = 4
BOOSTER_BLUE_HSV_LOW = np.array([85, 55, 65], dtype=np.uint8)
BOOSTER_BLUE_HSV_HIGH = np.array([125, 255, 255], dtype=np.uint8)
BOOSTER_TEXT_BINARY_THRESHOLD = 180
BOOSTER_TEXT_DIGIT_THRESHOLD = 0.62
# The charge text is "<numerator>/<denominator>" where the denominator is the
# meter size for the current mode. The slash is the white glyph with the lowest fill
# ratio (a thin diagonal stroke), which lets us split numerator from
# denominator regardless of the mode's scale.
BOOSTER_TEXT_SLASH_MAX_FILL = 0.40
BOOSTER_TEXT_MIN_DENOMINATOR = 3
BOOSTER_TEXT_MAX_DENOMINATOR = 99
# Some events print the word "FULL" on the charged pill instead of ACTIVATE, so
# neither the fraction parser nor the ACTIVATE matcher recognises it and the
# meter fallback stays unaccepted -- with Cekaj anim. that stalls Auto forever
# (Debug 2026-08-14 22:30-23:00, five runs, "booster nije sigurno vidljiv").
# A full bar measures 0.873 of the meter columns while 6/7 measures 0.739, so a
# word printed over a saturated meter can only mean a full booster.
BOOSTER_FULL_WORD_MIN_METER_RATIO = 0.82
BOOSTER_FULL_WORD_MIN_GLYPHS = 3

DIGIT_TEMPLATE_SIZE = (28, 42)
DIGIT_MIN_COMPONENT_HEIGHT_RATIO = 0.35
DIGIT_MIN_COMPONENT_WIDTH = 4
DIGIT_MATCH_THRESHOLD = 0.62

# The cumulative versus score is already captured in every debug run, but used
# to be image-only.  Its glyphs are the game's white outlined score font, not the
# smaller booster/move-counter font, so keep a separate classifier and a lower
# (empirically validated) template threshold.  Layout/width checks provide most
# of the confidence; the template score distinguishes the remaining glyphs.
SCORE_REGION_X_OFFSET_RATIO = 0.22
# 0.55 cropped 11px off the top of the 32px score glyphs (Debug 2026-08-08 chest
# run: every component box came back y=0/h=21 and the whole match was misread --
# 12-53 as 14-35, 286-363 as 460-405).  0.62 clears the panel top with margin.
SCORE_REGION_Y_ABOVE_BOARD_RATIO = 0.62
SCORE_REGION_WIDTH_RATIO = 0.56
SCORE_REGION_HEIGHT_RATIO = 0.17
# Solo Challenge draws one centred blue score pill instead of the two versus
# plates, and it sits *below* the versus band -- the region above caught only
# the purple backdrop, so every solo game read nothing (Debug 2026-08-10: 0/52
# in the O'Rama game, 0/48 in the Laser supersize one). Measured on both, the
# pill lands at the same place relative to the board (x 0.47, top 0.42 above the
# board, 0.35 wide, 0.09 tall); these bounds keep margin on every side while
# staying clear of the ACTIVATE button on the left and the turn banner below.
SOLO_SCORE_REGION_X_OFFSET_RATIO = 0.40
SOLO_SCORE_REGION_Y_ABOVE_BOARD_RATIO = 0.50
SOLO_SCORE_REGION_WIDTH_RATIO = 0.50
SOLO_SCORE_REGION_HEIGHT_RATIO = 0.20
# Party has no opponent: the header is a leaderboard of every player, and our
# own total sits in the blue pill under the "You" avatar. The versus crop spans
# that whole leaderboard, so it used to pair random neighbours' digits into a
# fake "us vs them" reading (Debug 2026-08-12: 71-41, 7674, 57 while the real
# total ran 2495 -> 9638). Read only our own pill; the avatar column keeps a
# fixed offset from the board, verified across that run.
PARTY_SCORE_REGION_X_OFFSET_RATIO = 0.15
PARTY_SCORE_REGION_Y_ABOVE_BOARD_RATIO = 0.44
PARTY_SCORE_REGION_WIDTH_RATIO = 0.25
PARTY_SCORE_REGION_HEIGHT_RATIO = 0.14
SCORE_TOP_BAND_RATIO = 0.55
SCORE_WHITE_LOW = np.array([180, 180, 180], dtype=np.uint8)
SCORE_WHITE_HIGH = np.array([255, 255, 255], dtype=np.uint8)
SCORE_DIGIT_TEMPLATE_SIZE = (28, 42)
SCORE_DIGIT_MATCH_THRESHOLD = 0.52
SCORE_MAX_DIGITS = 4
SCORE_MAX_COMPONENT_HEIGHT_RATIO = 0.70
# The two score panels are solid blue (ours) and pink (opponent) plates inside
# the header.  Anchoring the digit search to those plates is what keeps the
# "+15" gain bubble -- drawn on a dark disc just outside the plate -- and the
# round-indicator strip below out of the glyph list, and it survives the panel
# sliding sideways as the score grows.
SCORE_PANEL_OURS_HSV = ((95, 120, 190), (120, 255, 255))
SCORE_PANEL_OPPONENT_HSV = ((160, 80, 150), (178, 255, 255))
SCORE_PANEL_MIN_HEIGHT_RATIO = 0.15
# The header is wrapped in a rounded frame painted the same pink as the
# opponent's plate, and that frame is often the LARGER blob -- 272x95 at 30%
# fill against the plate's 124x59 at 62% (Debug 2026-08-10 21:44 versus game).
# Picking it made the digit search run over the whole header and read the
# opponent as "1", "2" or "1017" all game. A frame is a hollow ring, a plate is
# solid, so fill ratio separates them with a wide margin.
SCORE_PANEL_MIN_FILL_RATIO = 0.45
SCORE_PANEL_GLYPH_MIN_HEIGHT_RATIO = 0.35
SCORE_PANEL_GLYPH_MIN_AREA = 20
SCORE_PANEL_GLYPH_HEIGHT_TOLERANCE = 0.75
# The forced-7 geometry rule below fires on glyphs a real 3 also matches
# (width/height 0.59, fill 0.57).  Only let it override the templates when 7 is
# still a contender -- a 3 beats 7 by ~0.08 there, a real 7 wins outright.
SCORE_SEVEN_TEMPLATE_MARGIN = 0.03

MOVE_DOT_EXPECTED_COUNT = 6
SOLO_MOVE_DOT_MAX_COUNT = 12
SOLO_MOVE_DOT_MIN_COUNT = 1
MOVE_DOT_YELLOW_HSV_LOW = np.array([18, 80, 80], dtype=np.uint8)
MOVE_DOT_YELLOW_HSV_HIGH = np.array([40, 255, 255], dtype=np.uint8)
MOVE_DOT_BLUE_HSV_LOW = np.array([85, 55, 65], dtype=np.uint8)
MOVE_DOT_BLUE_HSV_HIGH = np.array([125, 255, 255], dtype=np.uint8)
MOVE_DOT_MIN_BLUE_RATIO = 0.35
MOVE_DOT_AMBIGUOUS_MARGIN = 0.08
MOVE_DOT_ACCEPT_CONFIDENCE = 0.70
# Regular versus layouts can expose either two or three player-side turn dots.
# This is a detection cap, not a required count: keeping it at three preserves
# the older 0-2-dot layouts while allowing the current three-turn tracker.
VERSUS_DOT_EXPECTED_COUNT = 3
# Party lays out exactly six move rings. Requiring all six is deliberate: the
# generic solo reader accepts any ring count it happens to find, so mid-cascade
# frames where the banner washes out the tracker returned "0/1" or "1/2" and the
# bot believed it was on its last move. An all-or-nothing read fails over to the
# numeric crop instead of inventing a move count.
PARTY_MOVE_DOT_EXPECTED_COUNT = 6
SUPERSIZE_SHOWDOWN_DOT_MAX_COUNT = 7
SUPERSIZE_SHOWDOWN_DOT_MIN_COUNT = 5
SUPERSIZE_VERSUS_DOT_EXPECTED_COUNT = 3
SUPERSIZE_DOT_BLUE_HSV_LOW = np.array([95, 100, 200], dtype=np.uint8)
SUPERSIZE_DOT_BLUE_HSV_HIGH = np.array([115, 255, 255], dtype=np.uint8)
SUPERSIZE_DOT_MIN_BLOB_SIZE = 8
SUPERSIZE_DOT_MIN_BLOB_AREA = 80

# Versus rounds are shown directly below the cumulative score. The active
# number is rendered roughly 1.5x taller than the inactive numbers. This is a
# safer signal than a move-dot refill, which an extra move can also cause.
ROUND_INDICATOR_Y_ABOVE_BOARD_RATIO = 0.43
ROUND_INDICATOR_SLOT_SPACING_RATIO = 0.064
ROUND_INDICATOR_SLOT_HALF_WIDTH_RATIO = 0.024
ROUND_INDICATOR_HEIGHT_RATIO = 0.07
ROUND_INDICATOR_MIN_ACTIVE_SPAN_RATIO = 0.036
ROUND_INDICATOR_MIN_SPAN_MARGIN_RATIO = 0.008
ROUND_INDICATOR_MIN_WHITE_PIXELS_RATIO = 0.20
ROUND_INDICATOR_MIN_VISIBLE_SPAN_RATIO = 0.016
ROUND_INDICATOR_MIN_VISIBLE_PIXELS_RATIO = 0.05
ROUND_INDICATOR_MAX_ROUNDS = 9
ROUND_INDICATOR_WHITE_LOW = np.array([180, 180, 180], dtype=np.uint8)
ROUND_INDICATOR_WHITE_HIGH = np.array([255, 255, 255], dtype=np.uint8)
# The numbered round cards themselves are blue.  Their geometry is more stable
# than the white digit: completed cards can acquire a full-height white shine,
# while the active card is consistently taller than the others.  Prefer this
# signal when it is available and retain the digit reader below as a fallback
# for themes/fixtures without blue cards.
ROUND_INDICATOR_BLUE_HSV_LOW = np.array([85, 55, 50], dtype=np.uint8)
ROUND_INDICATOR_BLUE_HSV_HIGH = np.array([130, 255, 255], dtype=np.uint8)
ROUND_INDICATOR_MARKER_MIN_WIDTH_RATIO = 0.025
ROUND_INDICATOR_MARKER_MAX_WIDTH_RATIO = 0.070
ROUND_INDICATOR_MARKER_MIN_HEIGHT_RATIO = 0.035
ROUND_INDICATOR_MARKER_MIN_AREA_RATIO = 0.0008
ROUND_INDICATOR_MARKER_SPACING_TOLERANCE_RATIO = 0.24
ROUND_INDICATOR_MARKER_CENTER_TOLERANCE_RATIO = 0.24
# In some versus themes only the active round number is white.  Inactive round
# numbers are rendered as a dim neutral gray, so they need a separate mask when
# deciding how many marker slots are actually present.  Keep the stricter white
# mask above for selecting the active round.
ROUND_INDICATOR_VISIBLE_LOW = np.array([120, 120, 120], dtype=np.uint8)
# Popups ("NICE!", the round-transition splash) slide straight over the round
# strip.  Their artwork is broad saturated colour, while the strip itself is
# only blue cards, white digits and a near-neutral panel, so a region drowning
# in foreign chroma is an overlay rather than a readable row of markers.
ROUND_INDICATOR_FOREIGN_CHROMA_LOW = np.array([0, 90, 60], dtype=np.uint8)
ROUND_INDICATOR_FOREIGN_CHROMA_HIGH = np.array([179, 255, 255], dtype=np.uint8)
ROUND_INDICATOR_MAX_FOREIGN_CHROMA_RATIO = 0.35

TURN_OWNER_US = "us"
TURN_OWNER_OPPONENT = "opponent"
TURN_BANNER_Y_ABOVE_BOARD_RATIO = 0.12
TURN_BANNER_HEIGHT_RATIO = 0.085
TURN_BANNER_BLUE_LOW = np.array([90, 80, 80], dtype=np.uint8)
TURN_BANNER_BLUE_HIGH = np.array([125, 255, 255], dtype=np.uint8)
TURN_BANNER_PINK_LOW = np.array([145, 80, 80], dtype=np.uint8)
TURN_BANNER_PINK_HIGH = np.array([179, 255, 255], dtype=np.uint8)
TURN_BANNER_RED_LOW = np.array([0, 80, 80], dtype=np.uint8)
TURN_BANNER_RED_HIGH = np.array([10, 255, 255], dtype=np.uint8)
# The banner doubles as the turn timer: the coloured fill drains away and the
# uncovered part of the bar shows a dark indigo track (H~134, S~246, V~92).
# Measuring that track tells "banner is there, the clock just ran out" apart
# from "there is no banner at all", so a nearly empty bar is still readable.
TURN_BANNER_TRACK_LOW = np.array([126, 110, 25], dtype=np.uint8)
TURN_BANNER_TRACK_HIGH = np.array([144, 255, 150], dtype=np.uint8)
# Fill plus track measures ~0.87 of the inner strip at every drain level, so a
# little under half is a safe "this really is the banner" gate.
TURN_BANNER_MIN_PRESENCE_RATIO = 0.45
# The owner is decided by which colour holds the fill, not by how much fill is
# left, so the absolute floor only has to survive the last seconds of the timer.
TURN_BANNER_MIN_FILL_RATIO = 0.02
TURN_BANNER_MIN_FILL_DOMINANCE = 0.70
TURN_BANNER_SOURCE_DRAINED = "turn_banner_drained"


@dataclass(frozen=True)
class StateFieldRead:
    value: int | str | None
    confidence: float
    source: str
    region: tuple[int, int, int, int] | None = None
    reason: str = ""
    maximum: int | None = None

    @property
    def accepted(self) -> bool:
        return self.value is not None and self.confidence >= AUTO_CONFIDENCE_THRESHOLD

    def to_debug_payload(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "confidence": float(self.confidence),
            "source": self.source,
            "accepted": self.accepted,
            "region": list(self.region) if self.region is not None else None,
            "reason": self.reason,
            "maximum": self.maximum,
        }


@dataclass(frozen=True)
class ScoreRead:
    our_score: int | None = None
    opponent_score: int | None = None
    confidence: float = 0.0
    source: str = "unknown"
    region: tuple[int, int, int, int] | None = None
    reason: str = ""
    # Solo Challenge has one score and no opponent, so "opponent_score is None"
    # is the correct reading rather than a failed one. Without this flag such a
    # read could never be accepted and the solo score stayed unavailable.
    solo: bool = False

    @classmethod
    def unknown(cls, reason: str = "score unavailable") -> "ScoreRead":
        return cls(reason=reason)

    @property
    def accepted(self) -> bool:
        if self.our_score is None or self.confidence < SCORE_DIGIT_MATCH_THRESHOLD:
            return False
        return self.solo or self.opponent_score is not None

    @property
    def deficit(self) -> int | None:
        if self.our_score is None or self.opponent_score is None:
            return None
        return int(self.opponent_score) - int(self.our_score)

    def to_debug_payload(self) -> dict[str, Any]:
        return {
            "our_score": self.our_score,
            "opponent_score": self.opponent_score,
            "score_deficit": self.deficit,
            "confidence": float(self.confidence),
            "source": self.source,
            "accepted": self.accepted,
            "region": list(self.region) if self.region is not None else None,
            "reason": self.reason,
            "solo": bool(self.solo),
        }


@dataclass(frozen=True)
class ScreenStateRead:
    booster_charge: StateFieldRead
    remaining_moves: StateFieldRead
    current_round: StateFieldRead = field(
        default_factory=lambda: StateFieldRead(
            value=None,
            confidence=0.0,
            source="unavailable",
            reason="round indicator not requested",
        )
    )
    turn_owner: StateFieldRead = field(
        default_factory=lambda: StateFieldRead(
            value=None,
            confidence=0.0,
            source="unavailable",
            reason="turn banner not requested",
        )
    )
    score: ScoreRead = field(default_factory=ScoreRead.unknown)
    screenshot_region: tuple[int, int, int, int] | None = None
    manual_booster_charge: int | None = None
    manual_remaining_moves: int | None = None

    def resolved_booster_charge(self) -> int | None:
        return resolve_state_value(self.booster_charge, self.manual_booster_charge)[0]

    def resolved_booster_maximum(self) -> int:
        maximum = self.booster_charge.maximum
        if self.booster_charge.accepted and maximum is not None and maximum > 0:
            return int(maximum)
        return BOOSTER_MAX_CHARGE

    def resolved_remaining_moves(self) -> int | None:
        return resolve_state_value(self.remaining_moves, self.manual_remaining_moves)[0]

    def resolved_sources(self) -> dict[str, str]:
        return {
            "booster_charge": resolve_state_value(
                self.booster_charge,
                self.manual_booster_charge,
            )[1],
            "remaining_moves": resolve_state_value(
                self.remaining_moves,
                self.manual_remaining_moves,
            )[1],
        }

    def to_debug_payload(self) -> dict[str, Any]:
        return {
            "booster_charge": self.booster_charge.to_debug_payload(),
            "remaining_moves": self.remaining_moves.to_debug_payload(),
            "current_round": self.current_round.to_debug_payload(),
            "turn_owner": self.turn_owner.to_debug_payload(),
            "score": self.score.to_debug_payload(),
            "resolved": {
                "booster_charge": self.resolved_booster_charge(),
                "booster_maximum": self.resolved_booster_maximum(),
                "remaining_moves": self.resolved_remaining_moves(),
                "current_round": (
                    self.current_round.value if self.current_round.accepted else None
                ),
                "total_rounds": (
                    self.current_round.maximum if self.current_round.accepted else None
                ),
                "turn_owner": (
                    self.turn_owner.value if self.turn_owner.accepted else None
                ),
                "our_score": self.score.our_score if self.score.accepted else None,
                "opponent_score": (
                    self.score.opponent_score if self.score.accepted else None
                ),
                "score_deficit": self.score.deficit if self.score.accepted else None,
                "sources": self.resolved_sources(),
            },
            "screenshot_region": (
                list(self.screenshot_region)
                if self.screenshot_region is not None
                else None
            ),
        }


def resolve_state_value(
    field: StateFieldRead,
    manual_value: int | None,
) -> tuple[int | None, str]:
    if field.accepted:
        return field.value, field.source
    if manual_value is not None:
        return manual_value, "manual"
    return None, "unknown"


def _as_bgr_array(image) -> np.ndarray | None:
    if image is None:
        return None
    if isinstance(image, Image.Image):
        return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    if isinstance(image, np.ndarray):
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        return image.copy()
    return None


def _crop_region(
    image_bgr: np.ndarray,
    region: tuple[int, int, int, int],
) -> np.ndarray | None:
    x, y, width, height = region
    if width <= 0 or height <= 0:
        return None
    image_height, image_width = image_bgr.shape[:2]
    x2 = x + width
    y2 = y + height
    if x < 0 or y < 0 or x2 > image_width or y2 > image_height:
        return None
    crop = image_bgr[y:y2, x:x2]
    if crop.size == 0:
        return None
    return crop


def turn_banner_region_from_board() -> tuple[int, int, int, int]:
    """Return the full-width status banner directly above the board."""

    board_width = max(1, int(getattr(recognition, "width", 0)))
    x = int(getattr(recognition, "left", 0))
    board_top = int(getattr(recognition, "up", 0))
    y = board_top - int(round(board_width * TURN_BANNER_Y_ABOVE_BOARD_RATIO))
    height = max(12, int(round(board_width * TURN_BANNER_HEIGHT_RATIO)))
    return max(0, x), max(0, y), board_width, height


def _classify_turn_banner(
    crop: np.ndarray | None,
    *,
    region: tuple[int, int, int, int],
) -> StateFieldRead:
    if crop is None or crop.size == 0:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="invalid_region",
            region=region,
            reason="turn banner crop outside image",
        )

    height, width = crop.shape[:2]
    # Ignore the gold border and the scene visible around its rounded ends. The
    # central fill remains blue for our turn (including the Time Left variant)
    # and pink/red for the opponent's turn.
    inner = crop[
        int(round(height * 0.18)) : max(1, int(round(height * 0.86))),
        int(round(width * 0.02)) : max(1, int(round(width * 0.98))),
    ]
    if inner.size == 0:
        inner = crop
    hsv = cv2.cvtColor(inner, cv2.COLOR_BGR2HSV)
    blue_mask = cv2.inRange(hsv, TURN_BANNER_BLUE_LOW, TURN_BANNER_BLUE_HIGH)
    pink_mask = cv2.inRange(hsv, TURN_BANNER_PINK_LOW, TURN_BANNER_PINK_HIGH)
    red_mask = cv2.inRange(hsv, TURN_BANNER_RED_LOW, TURN_BANNER_RED_HIGH)
    pink_mask = cv2.bitwise_or(pink_mask, red_mask)
    track_mask = cv2.inRange(hsv, TURN_BANNER_TRACK_LOW, TURN_BANNER_TRACK_HIGH)
    pixel_count = max(1, inner.shape[0] * inner.shape[1])
    blue_ratio = float(np.count_nonzero(blue_mask)) / pixel_count
    pink_ratio = float(np.count_nonzero(pink_mask)) / pixel_count
    track_ratio = float(np.count_nonzero(track_mask)) / pixel_count

    fill_ratio = blue_ratio + pink_ratio
    banner_ratio = fill_ratio + track_ratio
    ratio_text = (
        f"blue={blue_ratio:.3f}, pink={pink_ratio:.3f}, track={track_ratio:.3f}"
    )
    banner_present = banner_ratio >= TURN_BANNER_MIN_PRESENCE_RATIO

    if fill_ratio < TURN_BANNER_MIN_FILL_RATIO:
        # No fill left. With the empty track visible the banner is still on
        # screen and only the clock ran out, which the caller can bridge with
        # the last known owner instead of treating the turn as unknown.
        source = TURN_BANNER_SOURCE_DRAINED if banner_present else "low_confidence"
        reason = (
            "turn banner drained (timer expired)"
            if banner_present
            else "turn banner ambiguous"
        )
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source=source,
            region=region,
            reason=f"{reason}; {ratio_text}",
        )

    if blue_ratio >= pink_ratio:
        owner = TURN_OWNER_US
        dominant_ratio = blue_ratio
        banner_text = "Your Turn"
    else:
        owner = TURN_OWNER_OPPONENT
        dominant_ratio = pink_ratio
        banner_text = "Opponent's Turn"
    # Which colour owns the fill, measured against the fill alone. The timer
    # shrinks the fill towards zero, so comparing it to the whole banner would
    # drop a perfectly legible bar just because only a sliver of it is left.
    dominance = dominant_ratio / fill_ratio
    if not banner_present or dominance < TURN_BANNER_MIN_FILL_DOMINANCE:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="low_confidence",
            region=region,
            reason=f"turn banner ambiguous; {ratio_text}",
        )

    confidence = min(
        0.99, 0.80 + dominance * 0.15 + min(fill_ratio, 0.5) * 0.10
    )
    return StateFieldRead(
        value=owner,
        confidence=float(confidence),
        source="auto_turn_banner_color",
        region=region,
        reason=f"{banner_text}; {ratio_text}",
    )


def read_turn_owner_crop(
    image,
    *,
    region: tuple[int, int, int, int] | None = None,
) -> StateFieldRead:
    """Classify an image already cropped to the turn-status banner."""

    resolved_region = region or turn_banner_region_from_board()
    return _classify_turn_banner(_as_bgr_array(image), region=resolved_region)


def read_turn_owner(image) -> StateFieldRead:
    """Read whether the visible versus banner belongs to us or the opponent."""

    image_bgr = _as_bgr_array(image)
    region = turn_banner_region_from_board()
    crop = _crop_region(image_bgr, region) if image_bgr is not None else None
    return _classify_turn_banner(crop, region=region)


def round_indicator_region_from_board(total_rounds: int) -> tuple[int, int, int, int]:
    board_width = max(1, int(getattr(recognition, "width", 0)))
    board_center_x = float(getattr(recognition, "left", 0)) + board_width / 2.0
    center_y = float(getattr(recognition, "up", 0)) - (
        board_width * ROUND_INDICATOR_Y_ABOVE_BOARD_RATIO
    )
    spacing = board_width * ROUND_INDICATOR_SLOT_SPACING_RATIO
    half_width = max(2, int(round(board_width * ROUND_INDICATOR_SLOT_HALF_WIDTH_RATIO)))
    height = max(8, int(round(board_width * ROUND_INDICATOR_HEIGHT_RATIO)))
    first_center = board_center_x - ((int(total_rounds) - 1) * spacing / 2.0)
    last_center = board_center_x + ((int(total_rounds) - 1) * spacing / 2.0)
    x = int(round(first_center)) - half_width
    width = int(round(last_center)) + half_width - x
    return max(0, x), max(0, int(round(center_y))), max(1, width), height


def _round_indicator_foreign_chroma_ratio(crop: np.ndarray) -> float:
    """Fraction of the round strip taken by saturated colour that is not a card."""

    if crop is None or crop.size == 0:
        return 0.0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    chroma_mask = cv2.inRange(
        hsv,
        ROUND_INDICATOR_FOREIGN_CHROMA_LOW,
        ROUND_INDICATOR_FOREIGN_CHROMA_HIGH,
    )
    card_mask = cv2.inRange(
        hsv,
        ROUND_INDICATOR_BLUE_HSV_LOW,
        ROUND_INDICATOR_BLUE_HSV_HIGH,
    )
    foreign = cv2.bitwise_and(chroma_mask, cv2.bitwise_not(card_mask))
    return float(np.count_nonzero(foreign)) / max(1, crop.shape[0] * crop.shape[1])


def _read_current_round_from_blue_markers(
    image_bgr: np.ndarray | None,
) -> StateFieldRead | None:
    """Read round cards from their blue panel geometry.

    Returns ``None`` only when no trustworthy row of blue round cards is
    present, allowing the legacy white-glyph reader to handle other themes.
    Once a complete row is found, an ambiguous active card is returned as a
    rejected read instead of falling through to a potentially false 1/9 match.
    """

    region = round_indicator_region_from_board(ROUND_INDICATOR_MAX_ROUNDS)
    crop = _crop_region(image_bgr, region) if image_bgr is not None else None
    if crop is None:
        return None

    board_width = max(1, int(getattr(recognition, "width", 0)))
    crop_hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    blue_mask = cv2.inRange(
        crop_hsv,
        ROUND_INDICATOR_BLUE_HSV_LOW,
        ROUND_INDICATOR_BLUE_HSV_HIGH,
    )
    # Close tiny anti-aliased digit cuts without joining neighbouring cards.
    blue_mask = cv2.morphologyEx(
        blue_mask,
        cv2.MORPH_CLOSE,
        np.ones((3, 3), dtype=np.uint8),
    )
    component_count, _labels, stats, centroids = cv2.connectedComponentsWithStats(
        blue_mask,
        connectivity=8,
    )

    min_width = max(
        8,
        int(round(board_width * ROUND_INDICATOR_MARKER_MIN_WIDTH_RATIO)),
    )
    max_width = max(
        min_width,
        int(round(board_width * ROUND_INDICATOR_MARKER_MAX_WIDTH_RATIO)),
    )
    min_height = max(
        10,
        int(round(board_width * ROUND_INDICATOR_MARKER_MIN_HEIGHT_RATIO)),
    )
    min_area = max(
        40,
        int(round((board_width**2) * ROUND_INDICATOR_MARKER_MIN_AREA_RATIO)),
    )
    markers = []
    for component in range(1, component_count):
        x, y, width, height, area = (int(value) for value in stats[component])
        if not (
            min_width <= width <= max_width
            and min_height <= height <= crop.shape[0]
            and area >= min_area
        ):
            continue
        markers.append(
            {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "area": area,
                "center_x": float(centroids[component][0]) + region[0],
            }
        )

    markers.sort(key=lambda marker: marker["center_x"])
    total = len(markers)
    if total < 2 or total > ROUND_INDICATOR_MAX_ROUNDS:
        return None

    spacing = board_width * ROUND_INDICATOR_SLOT_SPACING_RATIO
    spacing_tolerance = max(
        3.0,
        spacing * ROUND_INDICATOR_MARKER_SPACING_TOLERANCE_RATIO,
    )
    gaps = [
        markers[index + 1]["center_x"] - markers[index]["center_x"]
        for index in range(total - 1)
    ]
    if any(abs(gap - spacing) > spacing_tolerance for gap in gaps):
        return None

    board_center_x = float(getattr(recognition, "left", 0)) + board_width / 2.0
    marker_center_x = sum(marker["center_x"] for marker in markers) / total
    center_tolerance = max(
        3.0,
        spacing * ROUND_INDICATOR_MARKER_CENTER_TOLERANCE_RATIO,
    )
    if abs(marker_center_x - board_center_x) > center_tolerance:
        return None

    ranked = sorted(
        range(total),
        key=lambda index: (markers[index]["height"], markers[index]["area"]),
        reverse=True,
    )
    best_index = ranked[0]
    best_height = markers[best_index]["height"]
    second_height = markers[ranked[1]]["height"] if len(ranked) > 1 else 0
    min_height_margin = max(
        3,
        int(round(board_width * ROUND_INDICATOR_MIN_SPAN_MARGIN_RATIO)),
    )
    marker_text = ",".join(
        f"r{index + 1}:h{marker['height']}/a{marker['area']}"
        for index, marker in enumerate(markers)
    )
    if best_height - second_height < min_height_margin:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="low_confidence",
            region=region,
            reason=f"round card geometry ambiguous; total={total}; {marker_text}",
            maximum=total,
        )

    height_margin = best_height - second_height
    confidence = min(0.99, 0.90 + height_margin / max(1.0, board_width * 0.10))
    return StateFieldRead(
        value=best_index + 1,
        confidence=float(confidence),
        source="auto_round_indicator_cards",
        region=region,
        reason=f"active={best_index + 1}/{total}; cards; {marker_text}",
        maximum=total,
    )


def _read_current_round_for_total(
    image_bgr: np.ndarray | None,
    total: int,
    *,
    require_all_slots_visible: bool,
) -> StateFieldRead:
    region = round_indicator_region_from_board(total)
    crop = _crop_region(image_bgr, region) if image_bgr is not None else None
    if crop is None:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="invalid_region",
            region=region,
            reason="round indicator crop outside image",
        )

    foreign_chroma = _round_indicator_foreign_chroma_ratio(crop)
    if foreign_chroma > ROUND_INDICATOR_MAX_FOREIGN_CHROMA_RATIO:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="low_confidence",
            region=region,
            reason=f"round indicator covered by overlay; chroma={foreign_chroma:.3f}",
        )

    board_width = max(1, int(getattr(recognition, "width", 0)))
    spacing = board_width * ROUND_INDICATOR_SLOT_SPACING_RATIO
    half_width = max(2, int(round(board_width * ROUND_INDICATOR_SLOT_HALF_WIDTH_RATIO)))
    center_x = float(getattr(recognition, "left", 0)) + board_width / 2.0
    crop_x = region[0]
    metrics = []
    visible_metrics = []
    for index in range(total):
        slot_center = center_x + (index - (total - 1) / 2.0) * spacing
        local_center = int(round(slot_center)) - crop_x
        slot = crop[:, max(0, local_center - half_width) : local_center + half_width]
        white_mask = cv2.inRange(
            slot,
            ROUND_INDICATOR_WHITE_LOW,
            ROUND_INDICATOR_WHITE_HIGH,
        )
        white_y = np.where(white_mask > 0)[0]
        span = int(white_y.max() - white_y.min() + 1) if white_y.size else 0
        metrics.append((span, int(np.count_nonzero(white_mask))))
        visible_mask = cv2.inRange(
            slot,
            ROUND_INDICATOR_VISIBLE_LOW,
            ROUND_INDICATOR_WHITE_HIGH,
        )
        visible_y = np.where(visible_mask > 0)[0]
        visible_span = (
            int(visible_y.max() - visible_y.min() + 1) if visible_y.size else 0
        )
        visible_metrics.append(
            (visible_span, int(np.count_nonzero(visible_mask)))
        )

    ranked = sorted(range(total), key=lambda index: metrics[index], reverse=True)
    best_index = ranked[0]
    best_span, best_pixels = metrics[best_index]
    second_span = metrics[ranked[1]][0] if len(ranked) > 1 else 0
    min_active_span = max(
        8,
        int(round(board_width * ROUND_INDICATOR_MIN_ACTIVE_SPAN_RATIO)),
    )
    min_span_margin = max(
        3,
        int(round(board_width * ROUND_INDICATOR_MIN_SPAN_MARGIN_RATIO)),
    )
    min_white_pixels = max(
        30,
        int(round(board_width * ROUND_INDICATOR_MIN_WHITE_PIXELS_RATIO)),
    )
    min_visible_span = max(
        7,
        int(round(board_width * ROUND_INDICATOR_MIN_VISIBLE_SPAN_RATIO)),
    )
    min_visible_pixels = max(
        18,
        int(round(board_width * ROUND_INDICATOR_MIN_VISIBLE_PIXELS_RATIO)),
    )
    visible_slots = sum(
        1
        for span, pixels in visible_metrics
        if span >= min_visible_span and pixels >= min_visible_pixels
    )
    metric_text = ",".join(
        (
            f"r{index + 1}:h{span}/w{pixels}"
            f"/vh{visible_metrics[index][0]}/vw{visible_metrics[index][1]}"
        )
        for index, (span, pixels) in enumerate(metrics)
    )
    accepted = (
        best_span >= min_active_span
        and best_span - second_span >= min_span_margin
        and best_pixels >= min_white_pixels
        and (not require_all_slots_visible or visible_slots == total)
    )
    if not accepted:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="low_confidence",
            region=region,
            reason=(
                f"round glyph ambiguous; visible={visible_slots}/{total}; "
                f"{metric_text}"
            ),
        )

    span_margin = best_span - second_span
    confidence = min(0.98, 0.88 + span_margin / max(1.0, board_width * 0.10))
    return StateFieldRead(
        value=best_index + 1,
        confidence=float(confidence),
        source="auto_round_indicator",
        region=region,
        reason=f"active={best_index + 1}/{total}; {metric_text}",
        maximum=total,
    )


def read_current_round(image, *, total_rounds: int | None) -> StateFieldRead:
    """Read current and total versus rounds from the score-panel markers.

    When ``total_rounds`` is omitted, test every supported layout and accept
    only candidates where every expected round glyph is visibly present. The
    largest complete layout is the real total; smaller centred subsets can
    otherwise look like valid two/three-round matches inside a longer match.
    """

    image_bgr = _as_bgr_array(image)
    card_read = _read_current_round_from_blue_markers(image_bgr)
    if card_read is not None:
        if total_rounds is None:
            return StateFieldRead(
                value=card_read.value,
                confidence=card_read.confidence,
                source=(
                    "auto_round_indicator_cards_detected_total"
                    if card_read.accepted
                    else card_read.source
                ),
                region=card_read.region,
                reason=f"total=auto; {card_read.reason}",
                maximum=card_read.maximum,
            )
        try:
            requested_total = int(total_rounds)
        except (TypeError, ValueError):
            requested_total = 0
        if card_read.maximum == requested_total:
            return StateFieldRead(
                value=card_read.value,
                confidence=card_read.confidence,
                source=(
                    "auto_round_indicator_cards"
                    if card_read.accepted
                    else card_read.source
                ),
                region=card_read.region,
                reason=card_read.reason,
                maximum=card_read.maximum,
            )
        if card_read.accepted:
            return StateFieldRead(
                value=None,
                confidence=0.0,
                source="low_confidence",
                region=card_read.region,
                reason=(
                    f"visible round cards total={card_read.maximum}, "
                    f"configured total={requested_total}"
                ),
                maximum=card_read.maximum,
            )
    if total_rounds is None:
        candidates = [
            _read_current_round_for_total(
                image_bgr,
                total,
                require_all_slots_visible=True,
            )
            for total in range(2, ROUND_INDICATOR_MAX_ROUNDS + 1)
        ]
        accepted = [candidate for candidate in candidates if candidate.accepted]
        if accepted:
            detected = max(accepted, key=lambda candidate: int(candidate.maximum or 0))
            return StateFieldRead(
                value=detected.value,
                confidence=detected.confidence,
                source="auto_round_indicator_detected_total",
                region=detected.region,
                reason=f"total=auto; {detected.reason}",
                maximum=detected.maximum,
            )
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="low_confidence",
            region=round_indicator_region_from_board(ROUND_INDICATOR_MAX_ROUNDS),
            reason="round total not detected from complete visible markers",
        )

    try:
        total = int(total_rounds)
    except (TypeError, ValueError):
        total = 0
    if total < 2 or total > ROUND_INDICATOR_MAX_ROUNDS:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="unavailable",
            reason=f"round total unsupported={total_rounds}",
        )
    return _read_current_round_for_total(
        image_bgr,
        total,
        require_all_slots_visible=False,
    )


def score_region_from_board() -> tuple[int, int, int, int]:
    board_width = max(1, recognition.width)
    region_x = int(round(recognition.left + board_width * SCORE_REGION_X_OFFSET_RATIO))
    region_y = int(round(recognition.up - board_width * SCORE_REGION_Y_ABOVE_BOARD_RATIO))
    region_width = max(1, int(round(board_width * SCORE_REGION_WIDTH_RATIO)))
    region_height = max(1, int(round(board_width * SCORE_REGION_HEIGHT_RATIO)))
    return max(0, region_x), max(0, region_y), region_width, region_height


def solo_score_region_from_board() -> tuple[int, int, int, int]:
    board_width = max(1, recognition.width)
    region_x = int(round(recognition.left + board_width * SOLO_SCORE_REGION_X_OFFSET_RATIO))
    region_y = int(round(recognition.up - board_width * SOLO_SCORE_REGION_Y_ABOVE_BOARD_RATIO))
    region_width = max(1, int(round(board_width * SOLO_SCORE_REGION_WIDTH_RATIO)))
    region_height = max(1, int(round(board_width * SOLO_SCORE_REGION_HEIGHT_RATIO)))
    return max(0, region_x), max(0, region_y), region_width, region_height


def party_score_region_from_board() -> tuple[int, int, int, int]:
    """Our own score pill in the Party leaderboard, under the "You" avatar."""
    board_width = max(1, recognition.width)
    region_x = int(round(recognition.left + board_width * PARTY_SCORE_REGION_X_OFFSET_RATIO))
    region_y = int(
        round(recognition.up - board_width * PARTY_SCORE_REGION_Y_ABOVE_BOARD_RATIO)
    )
    region_width = max(1, int(round(board_width * PARTY_SCORE_REGION_WIDTH_RATIO)))
    region_height = max(1, int(round(board_width * PARTY_SCORE_REGION_HEIGHT_RATIO)))
    return max(0, region_x), max(0, region_y), region_width, region_height


def _activation_region_from_board() -> tuple[int, int, int, int] | None:
    try:
        activation_region = recognition.booster_activation_region()
        crop_region = tuple(int(round(value)) for value in activation_region)
    except Exception:
        return None
    if len(crop_region) != 4:
        return None
    _x, _y, width, height = crop_region
    if (
        width < BOOSTER_MIN_ACTIVATION_REGION_SIZE
        or height < BOOSTER_MIN_ACTIVATION_REGION_SIZE
    ):
        return None
    return crop_region


def _activation_detection_region(
    detection: dict[str, Any],
    activation_region: tuple[int, int, int, int],
) -> tuple[int, int, int, int] | None:
    activation_x, activation_y, _width, _height = activation_region
    region = detection.get("region")
    if isinstance(region, tuple) and len(region) == 4:
        x, y, width, height = region
        return (
            activation_x + int(round(x)),
            activation_y + int(round(y)),
            int(round(width)),
            int(round(height)),
        )

    location = detection.get("location")
    template_size = detection.get("template_size")
    if (
        isinstance(location, tuple)
        and len(location) == 2
        and isinstance(template_size, tuple)
        and len(template_size) == 2
    ):
        x, y = location
        width, height = template_size
        return (
            activation_x + int(round(x)),
            activation_y + int(round(y)),
            int(round(width)),
            int(round(height)),
        )

    return None


def booster_meter_region_from_board() -> tuple[int, int, int, int] | None:
    activation_region = _activation_region_from_board()
    if activation_region is None:
        return None
    activation_x, activation_y, activation_width, activation_height = activation_region
    meter_width = int(round(activation_width * 0.58))
    meter_height = int(round(activation_height * 0.30))
    if (
        meter_width < BOOSTER_MIN_METER_REGION_SIZE
        or meter_height < BOOSTER_MIN_METER_REGION_SIZE
    ):
        return None
    return (
        int(round(activation_x + activation_width * 0.30)),
        int(round(activation_y + activation_height * 0.32)),
        meter_width,
        meter_height,
    )


def booster_charge_text_region_from_board() -> tuple[int, int, int, int] | None:
    activation_region = _activation_region_from_board()
    if activation_region is None:
        return None
    activation_x, activation_y, activation_width, activation_height = activation_region
    text_width = int(round(activation_width * 0.30))
    text_height = int(round(activation_height * 0.55))
    if (
        text_width < BOOSTER_MIN_METER_REGION_SIZE
        or text_height < BOOSTER_MIN_METER_REGION_SIZE
    ):
        return None
    return (
        int(round(activation_x + activation_width * 0.38)),
        int(round(activation_y + activation_height * 0.20)),
        text_width,
        text_height,
    )


def _booster_text_glyph_boxes(
    binary: np.ndarray,
) -> list[tuple[int, int, int, int, float]]:
    """Return ``(x, y, width, height, fill_ratio)`` for each text glyph.

    ``fill_ratio`` is the fraction of the bounding box occupied by white pixels;
    digits sit around 0.4-0.6 while the diagonal "/" stroke is the lowest of the
    row, which is how :func:`_parse_booster_fraction` locates the separator.
    """
    contours, _hierarchy = cv2.findContours(
        binary,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    crop_height, crop_width = binary.shape[:2]
    min_height = max(10, int(round(crop_height * 0.22)))
    max_height = max(min_height, int(round(crop_height * 0.72)))
    max_width = max(8, int(round(crop_width * 0.40)))
    boxes = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width < 3 or width > max_width:
            continue
        if height < min_height or height > max_height:
            continue
        if cv2.contourArea(contour) < 15:
            continue
        component = binary[y:y + height, x:x + width]
        fill = float(np.count_nonzero(component)) / float(max(1, width * height))
        boxes.append((x, y, width, height, fill))
    boxes.sort(key=lambda item: item[0])
    return boxes


def _parse_booster_fraction(
    binary: np.ndarray,
) -> tuple[int, int, float] | None:
    """Parse ``numerator/denominator`` from the booster charge text.

    Returns ``(numerator, denominator, min_digit_score)`` or ``None`` when the
    text is not a clean fraction (e.g. the "ACTIVATE" button, occlusion). The
    Both numerator and denominator are recognised. Reading the denominator is
    required because live events can change a booster from /7 to /6, /4, etc.
    """
    boxes = _booster_text_glyph_boxes(binary)
    if len(boxes) < 3:
        return None

    # The slash always has a digit on either side, so only interior glyphs can
    # be it. Searching the whole row made a sparse "7" at the end win the
    # lowest-fill vote over the slash itself (0.366 vs 0.368 in Debug
    # 2026-08-14 22:32:40), which left the denominator empty and dropped a
    # perfectly readable "3/7".
    fills = [box[4] for box in boxes]
    slash_index = min(range(1, len(boxes) - 1), key=lambda index: fills[index])
    if fills[slash_index] >= BOOSTER_TEXT_SLASH_MAX_FILL:
        return None

    numerator_boxes = boxes[:slash_index]
    denominator_boxes = boxes[slash_index + 1:]
    if not 1 <= len(numerator_boxes) <= 2:
        return None
    if not 1 <= len(denominator_boxes) <= 2:
        return None

    templates = _digit_templates()
    numerator_digits = []
    denominator_digits = []
    scores = []
    for x, y, width, height, _fill in numerator_boxes:
        digit, score = _match_digit(binary[y:y + height, x:x + width], templates)
        numerator_digits.append(str(digit))
        scores.append(score)
    for x, y, width, height, _fill in denominator_boxes:
        digit, score = _match_digit(binary[y:y + height, x:x + width], templates)
        denominator_digits.append(str(digit))
        scores.append(score)

    try:
        numerator = int("".join(numerator_digits))
        denominator = int("".join(denominator_digits))
    except ValueError:
        return None
    if not BOOSTER_TEXT_MIN_DENOMINATOR <= denominator <= BOOSTER_TEXT_MAX_DENOMINATOR:
        return None
    # Charge can never exceed the meter, so a numerator above the denominator
    # means we mis-segmented (e.g. read letters from the ACTIVATE button).
    if numerator > denominator:
        return None
    return numerator, denominator, (min(scores) if scores else 0.0)


def _read_booster_charge_text(
    image_bgr: np.ndarray,
    region: tuple[int, int, int, int],
) -> StateFieldRead:
    crop = _crop_region(image_bgr, region)
    if crop is None:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="invalid_region",
            region=region,
            reason="booster text crop outside image",
        )

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(
        gray,
        BOOSTER_TEXT_BINARY_THRESHOLD,
        255,
        cv2.THRESH_BINARY,
    )
    parsed = _parse_booster_fraction(binary)
    if parsed is None:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="low_confidence",
            region=region,
            reason="booster text not a valid X/Y fraction",
        )

    numerator, denominator, score = parsed
    if score < BOOSTER_TEXT_DIGIT_THRESHOLD:
        # The slash+digit structure was found, only the digit identities are
        # unsure -- callers use this to rule out the ACTIVATE button (which has
        # no fraction) without trusting the numerals.
        return StateFieldRead(
            value=None,
            confidence=float(score),
            source="low_confidence_fraction",
            region=region,
            reason=(
                f"booster {numerator}/{denominator}, "
                f"digit_conf={score:.3f}"
            ),
        )

    # Some booster skins expose a 0..70 sub-unit meter even though strategy
    # charge is still 0..7. Preserve that established conversion, while live
    # one-digit denominators (/4, /6, /7) remain literal and dynamic.
    if denominator == 70:
        maximum = BOOSTER_MAX_CHARGE
        charge = int(round((numerator / denominator) * maximum))
    else:
        maximum = denominator
        charge = numerator
    # The structural checks in _parse_booster_fraction (slash geometry, digit
    # count, numerator<=denominator) are the real correctness signal here; the
    # synthetic-font match score is only a sanity floor, so an accepted parse is
    # reported at the acceptance threshold while the raw score stays in reason.
    confidence = max(float(score), AUTO_CONFIDENCE_THRESHOLD)
    return StateFieldRead(
        value=charge,
        confidence=confidence,
        source="auto_booster_text",
        region=region,
        reason=(
            f"booster {numerator}/{denominator} -> charge {charge}/{maximum}, "
            f"digit_conf={score:.3f}"
        ),
        maximum=maximum,
    )


def _booster_meter_filled_ratio(crop: np.ndarray) -> float:
    """Fraction of meter columns that carry the blue charge fill."""
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    blue_mask = cv2.inRange(hsv, BOOSTER_BLUE_HSV_LOW, BOOSTER_BLUE_HSV_HIGH)
    column_blue_ratio = np.count_nonzero(blue_mask, axis=0) / max(1, blue_mask.shape[0])
    filled_columns = column_blue_ratio >= BOOSTER_BLUE_MIN_COLUMN_RATIO
    return float(np.count_nonzero(filled_columns) / max(1, filled_columns.size))


def _read_booster_full_word(
    image_bgr: np.ndarray,
    text_region: tuple[int, int, int, int] | None,
    meter_region: tuple[int, int, int, int] | None,
) -> StateFieldRead | None:
    """Read the "FULL" pill: a word printed over a completely charged meter.

    Only the combination counts -- the word alone could be any event label and a
    saturated meter alone could be a mid-animation artefact.
    """
    if text_region is None or meter_region is None:
        return None
    text_crop = _crop_region(image_bgr, text_region)
    meter_crop = _crop_region(image_bgr, meter_region)
    if text_crop is None or meter_crop is None:
        return None

    gray = cv2.cvtColor(text_crop, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, BOOSTER_TEXT_BINARY_THRESHOLD, 255, cv2.THRESH_BINARY)
    glyphs = len(_booster_text_glyph_boxes(binary))
    if glyphs < BOOSTER_FULL_WORD_MIN_GLYPHS:
        return None

    filled_ratio = _booster_meter_filled_ratio(meter_crop)
    if filled_ratio < BOOSTER_FULL_WORD_MIN_METER_RATIO:
        return None

    return StateFieldRead(
        value=BOOSTER_MAX_CHARGE,
        confidence=AUTO_CONFIDENCE_THRESHOLD,
        source="auto_booster_full_word",
        region=text_region,
        reason=(
            f"full word over saturated meter, glyphs={glyphs}, "
            f"filled_ratio={filled_ratio:.3f}"
        ),
    )


def _read_blue_meter_charge(
    image_bgr: np.ndarray,
    region: tuple[int, int, int, int],
) -> StateFieldRead:
    crop = _crop_region(image_bgr, region)
    if crop is None:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="invalid_region",
            region=region,
            reason="booster meter crop outside image",
        )

    filled_ratio = _booster_meter_filled_ratio(crop)
    raw_charge = filled_ratio * 6.0
    charge = int(round(raw_charge))
    charge = max(0, min(6, charge))
    boundary_distance = abs(raw_charge - charge)
    confidence = max(0.0, min(0.96, 0.96 - boundary_distance * 1.4))
    if filled_ratio <= 0.04:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="low_confidence",
            region=region,
            reason=f"no blue meter signal, filled_ratio={filled_ratio:.3f}",
        )

    return StateFieldRead(
        value=charge,
        confidence=confidence,
        source="auto_meter",
        region=region,
        reason=f"filled_ratio={filled_ratio:.3f}, raw_charge={raw_charge:.2f}",
    )


def read_booster_charge(
    image,
    *,
    board_profile: str,
    special_piece_mode: str,
    meter_region: tuple[int, int, int, int] | None = None,
) -> StateFieldRead:
    image_bgr = _as_bgr_array(image)
    if image_bgr is None or image_bgr.size == 0:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="invalid_image",
            region=None,
            reason="missing screenshot",
        )

    activation_region = _activation_region_from_board()
    activation_crop = (
        _crop_region(image_bgr, activation_region)
        if activation_region is not None
        else None
    )
    text_region = booster_charge_text_region_from_board()
    text_result = None
    if text_region is not None:
        text_result = _read_booster_charge_text(image_bgr, text_region)
        if text_result.accepted:
            return text_result

    # A structurally valid "X/Y" fraction only renders while the meter is still
    # counting up, so the button cannot be showing ACTIVATE. Skip the
    # full-charge fallback even when the digits were too blurry to trust,
    # instead of promoting a white-text overlay match to a bogus full read.
    fraction_structure_visible = (
        text_result is not None and text_result.source == "low_confidence_fraction"
    )
    if activation_crop is not None and not fraction_structure_visible:
        activate_detection = detect_booster_activate_in_image(activation_crop)
        if (
            activate_detection.get("active")
            and activate_detection.get("score", 0.0) >= BOOSTER_FULL_SCORE_THRESHOLD
        ):
            return StateFieldRead(
                value=BOOSTER_MAX_CHARGE,
                confidence=float(activate_detection.get("score", 1.0)),
                source="auto_activate",
                region=_activation_detection_region(
                    activate_detection,
                    activation_region,
                ),
                reason="activate button detected",
            )

    region = meter_region or booster_meter_region_from_board()
    if not fraction_structure_visible:
        full_word_result = _read_booster_full_word(image_bgr, text_region, region)
        if full_word_result is not None:
            return full_word_result
    if region is None:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="invalid_region",
            region=None,
            reason="booster meter region unavailable",
        )
    return _read_blue_meter_charge(image_bgr, region)


def remaining_moves_region_from_board() -> tuple[int, int, int, int]:
    board_width = max(1, int(getattr(recognition, "width", 0)))
    return (
        max(0, int(round(recognition.left + board_width * 0.46))),
        max(0, int(round(recognition.up - board_width * 0.23))),
        max(1, int(round(board_width * 0.43))),
        max(1, int(round(board_width * 0.09))),
    )


def party_moves_region_from_board() -> tuple[int, int, int, int]:
    return remaining_moves_region_from_board()


def remaining_moves_digit_region_from_board() -> tuple[int, int, int, int]:
    board_width = max(1, int(getattr(recognition, "width", 0)))
    return (
        max(0, int(round(recognition.left + board_width * 0.41))),
        max(0, int(round(recognition.up - board_width * 0.34))),
        max(1, int(round(board_width * 0.18))),
        max(1, int(round(board_width * 0.12))),
    )


def solo_challenge_moves_digit_region_from_board() -> tuple[int, int, int, int]:
    """Right-side numeric move counter used by Solo Challenge."""
    board_width = max(1, int(getattr(recognition, "width", 0)))
    return (
        max(0, int(round(recognition.left + board_width * 0.862))),
        max(0, int(round(recognition.up - board_width * 0.242))),
        max(1, int(round(board_width * 0.12))),
        max(1, int(round(board_width * 0.095))),
    )


def solo_challenge_moves_region_from_board() -> tuple[int, int, int, int]:
    """Full Solo Challenge dot tracker, including layouts with up to 12 dots."""
    board_width = max(1, int(getattr(recognition, "width", 0)))
    return (
        max(0, int(round(recognition.left + board_width * 0.34))),
        max(0, int(round(recognition.up - board_width * 0.23))),
        max(1, int(round(board_width * 0.66))),
        max(1, int(round(board_width * 0.09))),
    )


def supersize_showdown_moves_region_from_board() -> tuple[int, int, int, int]:
    """Full five-to-seven-dot tracker used by Supersize Showdown.

    The regular tracker crop begins inside the leftmost Supersize ring.  That
    can silently drop the leftmost ring, while the narrower PvP crop sees only
    that first ring.  Keep a dedicated profile-relative crop so both edges of
    the Supersize Showdown tracker remain visible.  Live game layouts currently
    use five rings, while older captured layouts and fixtures use seven.
    """
    board_width = max(1, int(getattr(recognition, "width", 0)))
    return (
        max(0, int(round(recognition.left + board_width * 0.42))),
        max(0, int(round(recognition.up - board_width * 0.23))),
        max(1, int(round(board_width * 0.50))),
        max(1, int(round(board_width * 0.09))),
    )


def versus_moves_region_from_board() -> tuple[int, int, int, int]:
    """Player-side PvP dots: left of the opponent's pink dot tracker."""
    base = remaining_moves_region_from_board()
    base_x, base_y, base_width, base_height = base
    return (
        max(0, int(round(base_x - base_width * 0.30))),
        base_y,
        max(1, int(round(base_width * 0.40))),
        base_height,
    )


def _move_dot_boxes(
    crop_bgr: np.ndarray,
    limit: int = MOVE_DOT_EXPECTED_COUNT,
) -> list[tuple[int, int, int, int]]:
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    yellow_mask = cv2.inRange(
        hsv,
        MOVE_DOT_YELLOW_HSV_LOW,
        MOVE_DOT_YELLOW_HSV_HIGH,
    )
    contours, _hierarchy = cv2.findContours(
        yellow_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    min_size = max(8, int(round(crop_bgr.shape[0] * 0.35)))
    min_area = float(max(40, int(round((crop_bgr.shape[0] * 0.18) ** 2))))
    boxes = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if width < min_size or height < min_size or area < min_area:
            continue
        aspect = width / max(1, height)
        if not 0.65 <= aspect <= 1.35:
            continue
        boxes.append((x, y, width, height))
    boxes = sorted(boxes, key=lambda item: item[2] * item[3], reverse=True)
    boxes = boxes[:limit]
    boxes.sort(key=lambda item: item[0])
    return boxes


def _read_colored_move_dot_count(
    image_bgr: np.ndarray,
    region: tuple[int, int, int, int],
    *,
    max_count: int,
    min_count: int,
    source: str,
    invalid_reason: str,
) -> StateFieldRead:
    crop = _crop_region(image_bgr, region)
    if crop is None:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="invalid_region",
            region=region,
            reason=invalid_reason,
        )

    boxes = _move_dot_boxes(crop, limit=max_count)
    if len(boxes) < min_count:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="low_confidence",
            region=region,
            reason=f"move dot rings found={len(boxes)}",
        )

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    blue_mask = cv2.inRange(
        hsv,
        MOVE_DOT_BLUE_HSV_LOW,
        MOVE_DOT_BLUE_HSV_HIGH,
    )
    blue_ratios = []
    for x, y, width, height in boxes:
        margin_x = max(1, int(round(width * 0.24)))
        margin_y = max(1, int(round(height * 0.24)))
        inner = blue_mask[
            y + margin_y : y + height - margin_y,
            x + margin_x : x + width - margin_x,
        ]
        if inner.size == 0:
            blue_ratios.append(0.0)
        else:
            blue_ratios.append(float(np.count_nonzero(inner) / inner.size))

    filled = [ratio >= MOVE_DOT_MIN_BLUE_RATIO for ratio in blue_ratios]
    filled_count = sum(1 for is_filled in filled if is_filled)
    if filled_count == 0:
        # A match that is still being played always has at least one move left,
        # so "no dot is filled" is never a real reading -- it is what the crop
        # looks like while the dots animate (they wash out mid-transition and no
        # ratio clears the threshold). Reporting it as 0 was actively harmful:
        # _turn_phase treats <= 1 as the final move and zeroes the value of blue
        # that cannot fill the meter, silently switching the booster rush off.
        # Unknown is the safe answer -- the phase logic then leaves charge alone.
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="low_confidence",
            region=region,
            reason=(
                "no filled move dot (animation in progress), "
                f"blue_ratios={','.join(f'{ratio:.2f}' for ratio in blue_ratios)}"
            ),
        )
    ambiguous = any(
        abs(ratio - MOVE_DOT_MIN_BLUE_RATIO) < MOVE_DOT_AMBIGUOUS_MARGIN
        for ratio in blue_ratios
    )
    confidence = 0.72 if ambiguous else 0.95
    return StateFieldRead(
        value=filled_count,
        confidence=confidence,
        source=source,
        region=region,
        reason=(
            f"filled={sum(1 for is_filled in filled if is_filled)}/"
            f"{len(boxes)}, "
            f"blue_ratios={','.join(f'{ratio:.2f}' for ratio in blue_ratios)}"
        ),
    )


def _read_solo_move_dot_count(
    image_bgr: np.ndarray,
    region: tuple[int, int, int, int],
) -> StateFieldRead:
    return _read_colored_move_dot_count(
        image_bgr,
        region,
        max_count=SOLO_MOVE_DOT_MAX_COUNT,
        min_count=SOLO_MOVE_DOT_MIN_COUNT,
        source="auto_move_dots",
        invalid_reason="remaining move dots crop outside image",
    )


def _read_party_move_dot_count(
    image_bgr: np.ndarray,
    region: tuple[int, int, int, int],
) -> StateFieldRead:
    return _read_colored_move_dot_count(
        image_bgr,
        region,
        max_count=PARTY_MOVE_DOT_EXPECTED_COUNT,
        min_count=PARTY_MOVE_DOT_EXPECTED_COUNT,
        source="auto_party_dots",
        invalid_reason="party move dots crop outside image",
    )


def _read_supersize_showdown_move_dot_count(
    image_bgr: np.ndarray,
    region: tuple[int, int, int, int],
) -> StateFieldRead:
    return _read_colored_move_dot_count(
        image_bgr,
        region,
        max_count=SUPERSIZE_SHOWDOWN_DOT_MAX_COUNT,
        min_count=SUPERSIZE_SHOWDOWN_DOT_MIN_COUNT,
        source="auto_supersize_showdown_dots",
        invalid_reason="supersize showdown move dots crop outside image",
    )


def _read_versus_move_dot_count(
    image_bgr: np.ndarray,
    region: tuple[int, int, int, int],
) -> StateFieldRead:
    """Count player's blue dots in versus mode while ignoring pink opponent dots."""
    crop = _crop_region(image_bgr, region)
    if crop is None:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="invalid_region",
            region=region,
            reason="versus move dots crop outside image",
        )

    ring_boxes = _move_dot_boxes(crop, limit=VERSUS_DOT_EXPECTED_COUNT)
    if ring_boxes:
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        blue_mask = cv2.inRange(
            hsv,
            MOVE_DOT_BLUE_HSV_LOW,
            MOVE_DOT_BLUE_HSV_HIGH,
        )
        blue_ratios = []
        for x, y, width, height in ring_boxes:
            margin_x = max(1, int(round(width * 0.24)))
            margin_y = max(1, int(round(height * 0.24)))
            inner = blue_mask[
                y + margin_y : y + height - margin_y,
                x + margin_x : x + width - margin_x,
            ]
            if inner.size == 0:
                blue_ratios.append(0.0)
            else:
                blue_ratios.append(float(np.count_nonzero(inner) / inner.size))
        filled = [ratio >= MOVE_DOT_MIN_BLUE_RATIO for ratio in blue_ratios]
        ambiguous = any(
            abs(ratio - MOVE_DOT_MIN_BLUE_RATIO) < MOVE_DOT_AMBIGUOUS_MARGIN
            for ratio in blue_ratios
        )
        confidence = 0.72 if ambiguous else 0.95
        count = sum(1 for is_filled in filled if is_filled)
        return StateFieldRead(
            value=count,
            confidence=confidence,
            source="auto_versus_dots",
            region=region,
            reason=(
                f"filled={count}/{len(ring_boxes)}, "
                f"blue_ratios={','.join(f'{ratio:.2f}' for ratio in blue_ratios)}"
            ),
        )

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    blue_mask = cv2.inRange(
        hsv,
        MOVE_DOT_BLUE_HSV_LOW,
        MOVE_DOT_BLUE_HSV_HIGH,
    )
    contours, _hierarchy = cv2.findContours(
        blue_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    min_size = max(8, int(round(crop.shape[0] * 0.35)))
    min_area = float(max(40, int(round((crop.shape[0] * 0.18) ** 2))))
    boxes = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if width < min_size or height < min_size or area < min_area:
            continue
        aspect = width / max(1, height)
        if not 0.65 <= aspect <= 1.35:
            continue
        boxes.append((x, y, width, height))
    boxes = sorted(boxes, key=lambda item: item[2] * item[3], reverse=True)
    boxes = boxes[:VERSUS_DOT_EXPECTED_COUNT]

    count = len(boxes)
    return StateFieldRead(
        value=count,
        confidence=0.95,
        source="auto_versus_dots",
        region=region,
        reason=f"blue_boxes={count}/{VERSUS_DOT_EXPECTED_COUNT}",
    )


def _read_supersize_versus_move_dot_count(
    image_bgr: np.ndarray,
    region: tuple[int, int, int, int],
) -> StateFieldRead:
    """Count player's active turn dots in supersize versus mode.

    Supersize uses a teal background that overlaps the regular blue HSV range,
    so the dot rings are isolated by a narrower hue band with high value.
    Player dots sit on the left side of the region; opponent dots on the right
    use purple/red rings that are outside the blue band.
    """
    crop = _crop_region(image_bgr, region)
    if crop is None:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="invalid_region",
            region=region,
            reason="supersize versus move dots crop outside image",
        )

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    blue_mask = cv2.inRange(
        hsv,
        SUPERSIZE_DOT_BLUE_HSV_LOW,
        SUPERSIZE_DOT_BLUE_HSV_HIGH,
    )
    contours, _hierarchy = cv2.findContours(
        blue_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    boxes = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if width < SUPERSIZE_DOT_MIN_BLOB_SIZE or height < SUPERSIZE_DOT_MIN_BLOB_SIZE:
            continue
        if area < SUPERSIZE_DOT_MIN_BLOB_AREA:
            continue
        aspect = width / max(1, height)
        if not 0.55 <= aspect <= 1.45:
            continue
        boxes.append((x, y, width, height))
    boxes = sorted(boxes, key=lambda item: item[2] * item[3], reverse=True)
    boxes = boxes[:SUPERSIZE_VERSUS_DOT_EXPECTED_COUNT]

    count = len(boxes)
    return StateFieldRead(
        value=count,
        confidence=0.95,
        source="auto_supersize_versus_dots",
        region=region,
        reason=f"blue_boxes={count}/{SUPERSIZE_VERSUS_DOT_EXPECTED_COUNT}",
    )


def _accept_move_dot_result(result: StateFieldRead) -> bool:
    return result.value is not None and result.confidence >= MOVE_DOT_ACCEPT_CONFIDENCE


def _digit_templates() -> dict[int, np.ndarray]:
    templates: dict[int, np.ndarray] = {}
    for digit in range(10):
        canvas = np.zeros((64, 48), dtype=np.uint8)
        cv2.putText(
            canvas,
            str(digit),
            (4, 48),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.45,
            255,
            4,
            cv2.LINE_AA,
        )
        _, binary = cv2.threshold(canvas, 90, 255, cv2.THRESH_BINARY)
        contours, _hierarchy = cv2.findContours(
            binary,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        if contours:
            x, y, width, height = cv2.boundingRect(np.vstack(contours))
            binary = binary[y:y + height, x:x + width]
        templates[digit] = cv2.resize(
            binary,
            DIGIT_TEMPLATE_SIZE,
            interpolation=cv2.INTER_AREA,
        )
    return templates


def _score_digit_templates() -> dict[int, np.ndarray]:
    templates: dict[int, np.ndarray] = {}
    for digit in range(10):
        canvas = np.zeros((80, 60), dtype=np.uint8)
        cv2.putText(
            canvas,
            str(digit),
            (3, 60),
            cv2.FONT_HERSHEY_COMPLEX,
            2.0,
            255,
            3,
            cv2.LINE_AA,
        )
        _, binary = cv2.threshold(canvas, 90, 255, cv2.THRESH_BINARY)
        contours, _hierarchy = cv2.findContours(
            binary,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        if contours:
            x, y, width, height = cv2.boundingRect(np.vstack(contours))
            binary = binary[y:y + height, x:x + width]
        templates[digit] = cv2.resize(
            binary,
            SCORE_DIGIT_TEMPLATE_SIZE,
            interpolation=cv2.INTER_AREA,
        )
    return templates


def _split_wide_score_component(
    binary: np.ndarray,
    box: tuple[int, int, int, int, int],
) -> list[tuple[int, int, int, int, int]]:
    """Split two score glyphs whose white outlines touch into separate boxes."""
    x, y, width, height, area = box
    if width <= height * 1.15 or width < 12:
        return [box]
    component = binary[y:y + height, x:x + width]
    projection = np.count_nonzero(component, axis=0)
    search_start = max(2, int(round(width * 0.35)))
    search_end = min(width - 2, int(round(width * 0.65)))
    if search_end <= search_start:
        return [box]
    split = search_start + int(np.argmin(projection[search_start:search_end + 1]))
    if projection[split] > max(2, int(round(float(projection.max()) * 0.45))):
        return [box]

    split_boxes = []
    for left, right in ((0, split + 1), (split + 1, width)):
        sub = component[:, left:right]
        ys, xs = np.nonzero(sub)
        if xs.size == 0 or ys.size == 0:
            return [box]
        sub_x = int(xs.min())
        sub_y = int(ys.min())
        sub_width = int(xs.max() - xs.min() + 1)
        sub_height = int(ys.max() - ys.min() + 1)
        if sub_width < 2 or sub_height < 8:
            return [box]
        split_boxes.append(
            (
                x + left + sub_x,
                y + sub_y,
                sub_width,
                sub_height,
                int(np.count_nonzero(sub[sub_y:sub_y + sub_height, sub_x:sub_x + sub_width])),
            )
        )
    return split_boxes


def _score_component_boxes(binary: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary)
    band_height = binary.shape[0]
    min_height = max(8, int(round(band_height * 0.30)))
    min_area = max(12, int(round(band_height * 0.35)))
    max_top = max(3, int(round(band_height * 0.15)))
    max_height = max(
        min_height,
        int(round(band_height * SCORE_MAX_COMPONENT_HEIGHT_RATIO)),
    )
    boxes = [
        tuple(int(value) for value in stats[index])
        for index in range(1, count)
        if stats[index][2] >= 2
        and stats[index][3] >= min_height
        and stats[index][3] <= max_height
        and stats[index][1] <= max_top
        and stats[index][4] >= min_area
    ]
    expanded = []
    for box in boxes:
        expanded.extend(_split_wide_score_component(binary, box))
    expanded.sort(key=lambda item: item[0])
    return expanded


# How many enclosed holes each digit has in the game's score font. Measured on
# Debug/runs 2026-08-10 (Solo pills reading 517, 525, 551, 606): 5 has none, 6
# has one low hole, 0 one centred. The synthetic Hershey templates disagree
# badly here -- they read 517 as 817, 525 as 626 and 551 as 861 -- and hole
# topology separates exactly that group. 4 is left unconstrained because the
# font may draw it open-topped and no sample has pinned it down.
SCORE_DIGIT_HOLE_COUNTS = {0: 1, 1: 0, 2: 0, 3: 0, 5: 0, 6: 1, 7: 0, 8: 2, 9: 1}
SCORE_GLYPH_HOLE_MIN_AREA_RATIO = 0.02
SCORE_GLYPH_HOLE_MIN_AREA = 6


def _score_glyph_hole_count(component: np.ndarray) -> int:
    """Enclosed background regions inside a glyph (0 for 5, 1 for 6, 2 for 8)."""
    padded = cv2.copyMakeBorder(component, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        cv2.bitwise_not(padded)
    )
    min_area = max(SCORE_GLYPH_HOLE_MIN_AREA, SCORE_GLYPH_HOLE_MIN_AREA_RATIO * component.size)
    holes = 0
    for index in range(1, count):
        x, y, _width, _height, area = (int(value) for value in stats[index])
        if x == 0 and y == 0:
            continue  # the outside, which the border guarantees is one region
        if area >= min_area:
            holes += 1
    return holes


def _classify_score_glyphs(
    binary: np.ndarray,
    boxes: list[tuple[int, int, int, int, int]],
) -> tuple[int | None, float, str]:
    templates = _score_digit_templates()
    digits = []
    confidences = []
    for x, y, width, height, _area in boxes:
        width_ratio = float(width) / max(1.0, float(height))
        component = binary[y:y + height, x:x + width]
        fill_ratio = float(np.count_nonzero(component)) / max(1, component.size)
        resized = cv2.resize(
            component,
            SCORE_DIGIT_TEMPLATE_SIZE,
            interpolation=cv2.INTER_AREA,
        )
        _, resized = cv2.threshold(resized, 90, 255, cv2.THRESH_BINARY)
        scores = {
            digit: 1.0 - float(cv2.absdiff(resized, template).mean() / 255.0)
            for digit, template in templates.items()
        }
        # Drop digits whose hole topology the glyph cannot have. Measured on the
        # source component, not the resized one, so thin strokes are not closed
        # up by interpolation. If nothing survives (a broken or unusual glyph)
        # the templates are left to decide on their own.
        hole_count = _score_glyph_hole_count(component)
        allowed = {
            digit
            for digit in scores
            if SCORE_DIGIT_HOLE_COUNTS.get(digit, hole_count) == hole_count
        }
        if allowed:
            scores = {digit: score for digit, score in scores.items() if digit in allowed}
        best_score = max(scores.values())
        # The real UI's narrow 1 and 7 are more reliably separated by geometry
        # than by a generic OpenCV font template.  A 7 can be as wide as 0.65
        # of its height (Debug 2026-07-26: score 75); its sparse diagonal still
        # distinguishes it from the denser 2/3/5 glyphs.  The old width-only
        # rule classified that clean 7 as 1 and turned 75 into 15.
        # A full-height 3 lands in the same width/fill box though (Debug
        # 2026-08-08: 263 read as 267, 363 as 763), so the geometry rule only
        # wins when the templates still rate 7 a contender.
        if width_ratio <= 0.48 and 1 in scores:
            digit = 1
            confidence = max(0.90, scores[digit])
        elif (
            width_ratio <= 0.67
            and fill_ratio <= 0.58
            and 7 in scores
            and scores[7] >= best_score - SCORE_SEVEN_TEMPLATE_MARGIN
        ):
            digit = 7
            confidence = max(0.86, scores[digit])
        else:
            digit = max(scores, key=scores.get)
            confidence = scores[digit]
        digits.append(str(digit))
        confidences.append(float(confidence))

    value = int("".join(digits))
    confidence = min(confidences) if confidences else 0.0
    return value, confidence, f"digits={''.join(digits)}, confidence={confidence:.3f}"


def _score_panel_box(
    image_bgr: np.ndarray,
    hsv_range: tuple[tuple[int, int, int], tuple[int, int, int]],
) -> tuple[int, int, int, int] | None:
    """Bounding box of the solid colour plate a score is printed on."""
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    low, high = hsv_range
    mask = cv2.inRange(hsv, np.array(low, dtype=np.uint8), np.array(high, dtype=np.uint8))
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask)
    if count < 2:
        return None
    best = None
    for index in range(1, count):
        x, y, width, height, area = (int(value) for value in stats[index])
        # A plate is a wide bar spanning a good part of the crop.  The scraps
        # left when a fullscreen-hint overlay covers the header fail these.
        if height < image_bgr.shape[0] * SCORE_PANEL_MIN_HEIGHT_RATIO or width < height:
            continue
        # ...and it is solid, unlike the header's surrounding frame.
        if area < width * height * SCORE_PANEL_MIN_FILL_RATIO:
            continue
        if best is None or area > best[0]:
            best = (area, x, y, width, height)
    if best is None:
        return None
    return best[1], best[2], best[3], best[4]


def _score_panel_digits(
    image_bgr: np.ndarray,
    box: tuple[int, int, int, int],
) -> tuple[int | None, float, str]:
    x, y, width, height = box
    panel = image_bgr[y:y + height, x:x + width]
    if panel.size == 0:
        return None, 0.0, "empty score panel"
    binary = cv2.inRange(panel, SCORE_WHITE_LOW, SCORE_WHITE_HIGH)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary)
    min_height = height * SCORE_PANEL_GLYPH_MIN_HEIGHT_RATIO
    boxes = [
        tuple(int(value) for value in stats[index])
        for index in range(1, count)
        if stats[index][3] >= min_height and stats[index][4] >= SCORE_PANEL_GLYPH_MIN_AREA
    ]
    if not boxes:
        return None, 0.0, "no score digit components"
    # Digits of one number are all the same height; the plate's rounded
    # highlight and any glow bleeding in are shorter.
    tallest = max(item[3] for item in boxes)
    boxes = [
        item
        for item in boxes
        if item[3] >= tallest * SCORE_PANEL_GLYPH_HEIGHT_TOLERANCE
    ]
    expanded: list[tuple[int, int, int, int, int]] = []
    for item in boxes:
        expanded.extend(_split_wide_score_component(binary, item))
    expanded.sort(key=lambda item: item[0])
    if len(expanded) > SCORE_MAX_DIGITS:
        return None, 0.0, f"too many score digit components: {len(expanded)}"
    return _classify_score_glyphs(binary, expanded)


def _score_side_digits(side_bgr: np.ndarray) -> tuple[int | None, float, str]:
    if side_bgr is None or side_bgr.size == 0:
        return None, 0.0, "empty score side"
    band_height = max(1, int(round(side_bgr.shape[0] * SCORE_TOP_BAND_RATIO)))
    top_band = side_bgr[:band_height]
    binary = cv2.inRange(top_band, SCORE_WHITE_LOW, SCORE_WHITE_HIGH)
    boxes = _score_component_boxes(binary)
    if not boxes:
        return None, 0.0, "no score digit components"
    if len(boxes) > SCORE_MAX_DIGITS:
        return None, 0.0, f"too many score digit components: {len(boxes)}"
    return _classify_score_glyphs(binary, boxes)


def read_score_region(score_image) -> ScoreRead:
    image_bgr = _as_bgr_array(score_image)
    if image_bgr is None or image_bgr.size == 0:
        return ScoreRead.unknown("invalid score image")

    our_panel = _score_panel_box(image_bgr, SCORE_PANEL_OURS_HSV)
    opponent_panel = _score_panel_box(image_bgr, SCORE_PANEL_OPPONENT_HSV)
    if our_panel is not None and opponent_panel is not None:
        our_score, our_confidence, our_reason = _score_panel_digits(image_bgr, our_panel)
        opponent_score, opponent_confidence, opponent_reason = _score_panel_digits(
            image_bgr, opponent_panel
        )
        source_prefix = "panel"
    else:
        # No plates in view -- either the header is covered (fullscreen hint) or
        # this layout paints them differently.  Fall back to the plain
        # left/right split rather than reporting nothing.
        midpoint = image_bgr.shape[1] // 2
        our_score, our_confidence, our_reason = _score_side_digits(image_bgr[:, :midpoint])
        opponent_score, opponent_confidence, opponent_reason = _score_side_digits(
            image_bgr[:, midpoint:]
        )
        source_prefix = "split"

    confidence = min(our_confidence, opponent_confidence)
    return ScoreRead(
        our_score=our_score,
        opponent_score=opponent_score,
        confidence=confidence,
        source="auto_score_digits" if our_score is not None and opponent_score is not None else "low_confidence",
        reason=f"[{source_prefix}] our({our_reason}); opponent({opponent_reason})",
    )


def read_solo_score_region(score_image) -> ScoreRead:
    """Read the single blue score pill of a Solo Challenge header."""
    image_bgr = _as_bgr_array(score_image)
    if image_bgr is None or image_bgr.size == 0:
        return ScoreRead.unknown("invalid solo score image")

    panel = _score_panel_box(image_bgr, SCORE_PANEL_OURS_HSV)
    if panel is None:
        return ScoreRead(
            confidence=0.0,
            source="low_confidence",
            reason="[solo] no score plate",
        )
    our_score, confidence, reason = _score_panel_digits(image_bgr, panel)
    return ScoreRead(
        our_score=our_score,
        opponent_score=None,
        confidence=confidence,
        source="auto_solo_score_digits" if our_score is not None else "low_confidence",
        reason=f"[solo] {reason}",
        solo=our_score is not None,
    )


SCORE_LEGEND_TOKEN_MIN_AREA = 300.0
SCORE_LEGEND_TOKEN_MAX_AREA = 2600.0
SCORE_LEGEND_TOKEN_MIN_SIDE = 20.0
SCORE_LEGEND_TOKEN_MAX_SIDE = 70.0
# The value is printed on top of the coloured piece, and the game draws it in
# white, green or red depending on the turn. So the glyph is not "the white
# pixels" -- it is the bright pixels that are *not* the token's own colour. A
# plain gray threshold picks up the whole token body instead.
SCORE_LEGEND_TEXT_MIN_VALUE = 165
SCORE_LEGEND_TEXT_MAX_SATURATION = 80
SCORE_LEGEND_TEXT_HUE_DISTANCE = 14
SCORE_LEGEND_TEXT_SATURATION_DELTA = 25
SCORE_LEGEND_TEXT_VALUE_DELTA = 30
SCORE_LEGEND_MATCH_THRESHOLD = 0.74
SCORE_LEGEND_MATCH_MARGIN = 0.03
SCORE_LEGEND_GLYPH_SIZE = (56, 42)
SCORE_LEGEND_TEMPLATE_ASSET = "assets/score_legend/digit_templates.npz"
_SCORE_LEGEND_TEMPLATES: dict[int, np.ndarray] | None = None
SCORE_LEGEND_COLOR_HUE_RANGES = (
    (recognition.RED, ((0, 8), (172, 180))),
    (recognition.ORANGE, ((9, 22),)),
    (recognition.YELLOW, ((23, 38),)),
    (recognition.GREEN, ((39, 82),)),
    (recognition.BLUE, ((83, 112),)),
    (recognition.PURPLE, ((125, 165),)),
)


@dataclass
class ScoreLegendRead:
    """Per-colour point values printed in the "Score legend" strip."""

    values: dict[int, float]
    confidence: float
    source: str
    region: tuple[int, int, int, int] | None = None
    reason: str = ""

    @property
    def accepted(self) -> bool:
        return bool(self.values) and self.confidence >= AUTO_CONFIDENCE_THRESHOLD

    def to_debug_payload(self) -> dict[str, Any]:
        return {
            "values": {str(color): value for color, value in sorted(self.values.items())},
            "confidence": float(self.confidence),
            "source": self.source,
            "accepted": self.accepted,
            "region": list(self.region) if self.region is not None else None,
            "reason": self.reason,
        }


def score_legend_region_from_board() -> tuple[int, int, int, int]:
    """The "Score legend" token strip, centred just below the board."""
    square = max(1, int(getattr(recognition, "squareSize", 0)))
    board_length = max(1, int(getattr(recognition, "board_length", 0)))
    board_bottom = recognition.up + square * board_length
    center_x = recognition.left + square * board_length / 2.0
    return (
        max(0, int(round(center_x - square * 1.6))),
        max(0, int(round(board_bottom + square * 0.10))),
        max(1, int(round(square * 3.2))),
        max(1, int(round(square * 0.85))),
    )


def _score_legend_tokens(crop_bgr: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """Locate the coloured legend pieces as (colour, x, y, width, height)."""
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    saturated = ((saturation >= 120) & (value >= 100)) | (
        (saturation >= 50) & (value >= 190)
    )
    scale = max(0.5, float(getattr(recognition, "squareSize", 84) or 84) / 84.0)
    min_area = SCORE_LEGEND_TOKEN_MIN_AREA * scale * scale
    max_area = SCORE_LEGEND_TOKEN_MAX_AREA * scale * scale
    min_side = SCORE_LEGEND_TOKEN_MIN_SIDE * scale
    max_side = SCORE_LEGEND_TOKEN_MAX_SIDE * scale
    close_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (max(3, int(round(3 * scale))), max(5, int(round(5 * scale)))),
    )

    tokens = []
    for color, ranges in SCORE_LEGEND_COLOR_HUE_RANGES:
        hue_mask = np.zeros(hue.shape, dtype=bool)
        for low, high in ranges:
            hue_mask |= (hue >= low) & (hue <= high)
        mask = (hue_mask & saturated).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel)
        _count, _labels, stats, _centers = cv2.connectedComponentsWithStats(mask)
        for stat in stats[1:]:
            x = int(stat[cv2.CC_STAT_LEFT])
            y = int(stat[cv2.CC_STAT_TOP])
            width = int(stat[cv2.CC_STAT_WIDTH])
            height = int(stat[cv2.CC_STAT_HEIGHT])
            area = float(stat[cv2.CC_STAT_AREA])
            if not min_area <= area <= max_area:
                continue
            if not min_side <= width <= max_side:
                continue
            if not min_side <= height <= max_side:
                continue
            # Legend pieces are square-ish. The aspect gate is what rejects the
            # purple panel edge (a tall sliver) and the clipped blue info circle
            # that share the strip.
            if not 0.65 <= width / max(1.0, float(height)) <= 1.35:
                continue
            tokens.append((int(color), x, y, width, height))
    tokens.sort(key=lambda item: item[1])
    return tokens


def _score_legend_glyph_mask(token_bgr: np.ndarray, color: int) -> np.ndarray:
    """Isolate the printed value inside a legend token.

    The glyph is the bright pixel that is not the token's own body colour, taken
    from the token's interior so the bevel highlight and the outline ring stay
    out. The body colour is measured from the token itself rather than assumed
    from ``color``: the same rule then works for a white, green or red value.

    Keep this in step with ``tools/score_legend_dataset.py`` -- the templates are
    built from masks produced here, so the two must segment identically.
    """
    del color
    hsv = cv2.cvtColor(token_bgr, cv2.COLOR_BGR2HSV)
    height, width = hsv.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    pad_y, pad_x = int(height * 0.18), int(width * 0.18)
    inner = hsv[pad_y:height - pad_y, pad_x:width - pad_x]
    if inner.size == 0:
        return mask
    hue, saturation, value = inner[:, :, 0], inner[:, :, 1], inner[:, :, 2]
    bright = value >= SCORE_LEGEND_TEXT_MIN_VALUE
    if not bright.any():
        return mask
    dominant = int(np.bincount(hue[bright], minlength=180).argmax())
    distance = np.abs(hue.astype(int) - dominant)
    distance = np.minimum(distance, 180 - distance)
    body = bright & (distance <= SCORE_LEGEND_TEXT_HUE_DISTANCE)
    body_saturation = int(np.median(saturation[body])) if body.any() else 255
    body_value = int(np.median(value[body])) if body.any() else 255
    # The value can differ from the piece body in any of three ways: another hue
    # (a green value on a purple piece), washed out (white), or the same hue but
    # more vivid and brighter (a green value on the green piece). Only checking
    # hue and low saturation left the last case with an empty mask.
    glyph = bright & (
        (distance > SCORE_LEGEND_TEXT_HUE_DISTANCE)
        | (saturation <= SCORE_LEGEND_TEXT_MAX_SATURATION)
        | (saturation >= min(255, body_saturation + SCORE_LEGEND_TEXT_SATURATION_DELTA))
        | (value >= min(255, body_value + SCORE_LEGEND_TEXT_VALUE_DELTA))
    )
    mask[pad_y:height - pad_y, pad_x:width - pad_x] = glyph.astype(np.uint8) * 255
    return mask


def score_legend_templates() -> dict[int, list[np.ndarray]]:
    """Value templates learned from recorded frames (tools/score_legend_dataset.py).

    A value can map to several templates: the game renders some values in two
    visibly different ways, and averaging those into one shape blurred the very
    strokes that separate 8 from 6 and 5 from 6.
    """
    global _SCORE_LEGEND_TEMPLATES
    if _SCORE_LEGEND_TEMPLATES is None:
        path = Path(__file__).resolve().parent / SCORE_LEGEND_TEMPLATE_ASSET
        templates: dict[int, list[np.ndarray]] = {}
        if path.exists():
            with np.load(path) as data:
                for name in data.files:
                    value = int(name.split("_", 1)[0])
                    templates.setdefault(value, []).append(data[name])
        _SCORE_LEGEND_TEMPLATES = templates
    return _SCORE_LEGEND_TEMPLATES


def _normalise_score_legend_glyph(mask: np.ndarray) -> np.ndarray | None:
    """Crop the printed value and normalise it, keeping the aspect ratio.

    Width carries the information that separates a one-digit value from "10",
    so the glyph is scaled by height only and centred on a fixed canvas.
    """
    boxes = _digit_components(mask)
    if not boxes:
        return None
    x0 = min(box[0] for box in boxes)
    y0 = min(box[1] for box in boxes)
    x1 = max(box[0] + box[2] for box in boxes)
    y1 = max(box[1] + box[3] for box in boxes)
    crop = mask[y0:y1, x0:x1]
    if crop.size == 0:
        return None

    canvas_width, canvas_height = SCORE_LEGEND_GLYPH_SIZE
    scale = canvas_height / float(crop.shape[0])
    width = max(1, min(canvas_width, int(round(crop.shape[1] * scale))))
    resized = cv2.resize(crop, (width, canvas_height), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((canvas_height, canvas_width), dtype=np.uint8)
    offset = (canvas_width - width) // 2
    canvas[:, offset:offset + width] = resized
    _threshold, binary = cv2.threshold(canvas, 90, 255, cv2.THRESH_BINARY)
    return binary


def _score_legend_token_value(
    token_bgr: np.ndarray,
    color: int,
    templates: dict[int, np.ndarray],
) -> tuple[int | None, float]:
    if not templates:
        return None, 0.0
    glyph = _normalise_score_legend_glyph(_score_legend_glyph_mask(token_bgr, color))
    if glyph is None:
        return None, 0.0

    # Score each value by its best-matching variant, then rank values. The
    # margin has to compare *values*, not templates -- two variants of the same
    # value always look like a tie and would reject every read.
    ranked = sorted(
        (
            (max(
                1.0 - float(cv2.absdiff(glyph, template).mean() / 255.0)
                for template in variants
            ), value)
            for value, variants in templates.items()
        ),
        reverse=True,
    )
    best_score, best_value = ranked[0]
    if best_score < SCORE_LEGEND_MATCH_THRESHOLD:
        return None, best_score
    # A near-tie means the glyph sits between two shapes; refuse rather than
    # guess, because a silent misread feeds straight into the lotus scoring.
    if len(ranked) > 1 and best_score - ranked[1][0] < SCORE_LEGEND_MATCH_MARGIN:
        return None, best_score
    return int(best_value), best_score


def read_score_legend(image) -> ScoreLegendRead:
    """Read the per-colour point values from the strip under the board.

    NOT WIRED INTO SCORING. Measured on 11 hand-labelled frames (2026-08-08):
    token localisation is reliable (4/4 tokens in every legend frame, none on
    non-legend screens), but digit reading is only 36/44 tokens and 6/11 full
    legends. The game prints the value in white, green or red depending on
    whether it rose or fell, and a green value on the green piece differs from
    the piece body by brightness alone -- colour rules cannot separate it. Making
    this trustworthy needs a trained classifier like the tile recogniser, not
    more thresholds. Feeding a silent misread into the lotus values would be
    worse than the manual spinboxes.
    """
    image_bgr = _as_bgr_array(image)
    # The strip sits at the very bottom of the screen, so the nominal region can
    # run a few pixels past the last row. Clamp instead of rejecting the read.
    region = score_legend_region_from_board()
    if image_bgr is not None:
        image_height, image_width = image_bgr.shape[:2]
        x, y, width, height = region
        x = max(0, min(x, image_width - 1))
        y = max(0, min(y, image_height - 1))
        region = (x, y, max(1, min(width, image_width - x)), max(1, min(height, image_height - y)))
    crop = _crop_region(image_bgr, region) if image_bgr is not None else None
    if crop is None:
        return ScoreLegendRead(
            values={},
            confidence=0.0,
            source="invalid_region",
            region=region,
            reason="score legend crop outside image",
        )

    tokens = _score_legend_tokens(crop)
    if not tokens:
        return ScoreLegendRead(
            values={},
            confidence=0.0,
            source="score_legend_tokens",
            region=region,
            reason="no legend tokens found",
        )

    templates = score_legend_templates()
    values: dict[int, float] = {}
    scores = []
    unreadable = 0
    for color, x, y, width, height in tokens:
        value, score = _score_legend_token_value(
            crop[y:y + height, x:x + width], color, templates
        )
        if value is None:
            unreadable += 1
            continue
        if color in values:
            # A duplicate colour means the strip was misread; a legend never
            # lists the same colour twice.
            return ScoreLegendRead(
                values={},
                confidence=0.0,
                source="score_legend_tokens",
                region=region,
                reason=f"duplicate legend colour {color}",
            )
        values[color] = float(value)
        scores.append(score)

    if not values:
        return ScoreLegendRead(
            values={},
            confidence=0.0,
            source="score_legend_tokens",
            region=region,
            reason=f"read 0 of {len(tokens)} legend tokens",
        )

    # Partial reads are returned on purpose. A value the game prints in the
    # piece's own colour (a green value on the green piece) is the one case the
    # segmentation cannot isolate, and dropping the whole legend over it would
    # throw away three good values. The caller keeps its manual entry for the
    # colours that are missing.
    return ScoreLegendRead(
        values=values,
        confidence=float(min(scores)),
        source="score_legend_tokens",
        region=region,
        reason=f"read {len(values)} of {len(tokens)} legend tokens",
    )


def read_match_score(
    image,
    score_region: tuple[int, int, int, int] | None = None,
    *,
    party: bool = False,
) -> ScoreRead:
    image_bgr = _as_bgr_array(image)
    region = score_region or score_region_from_board()
    if image_bgr is None or image_bgr.size == 0:
        return ScoreRead.unknown("invalid full-screen image")
    if party and score_region is None:
        # No opponent exists in Party, so never run the versus reader here: it
        # reads the neighbouring players' plates and reports them as a match we
        # are winning or losing. Our pill is frequently hidden behind the combo
        # banner; returning nothing then is correct, and the caller's tracked
        # score carries the last real total forward.
        party_region = party_score_region_from_board()
        party_crop = _crop_region(image_bgr, party_region)
        if party_crop is None:
            return ScoreRead(
                confidence=0.0,
                source="invalid_region",
                region=party_region,
                reason="party score crop outside image",
            )
        party_result = read_solo_score_region(party_crop)
        return ScoreRead(
            our_score=party_result.our_score,
            opponent_score=None,
            confidence=party_result.confidence,
            source=party_result.source,
            region=party_region,
            reason=f"[party] {party_result.reason}",
            solo=party_result.our_score is not None,
        )
    crop = _crop_region(image_bgr, region)
    if crop is None:
        return ScoreRead(
            confidence=0.0,
            source="invalid_region",
            region=region,
            reason="score crop outside image",
        )
    result = read_score_region(crop)
    if not result.accepted and score_region is None:
        # No versus pair in the header -- try the Solo Challenge pill lower down
        # before giving up. Skipped when the caller pinned an explicit region,
        # since then it asked for that exact crop.
        solo_region = solo_score_region_from_board()
        solo_crop = _crop_region(image_bgr, solo_region)
        if solo_crop is not None:
            solo_result = read_solo_score_region(solo_crop)
            if solo_result.accepted:
                return ScoreRead(
                    our_score=solo_result.our_score,
                    opponent_score=None,
                    confidence=solo_result.confidence,
                    source=solo_result.source,
                    region=solo_region,
                    reason=f"{result.reason}; {solo_result.reason}",
                    solo=True,
                )
    return ScoreRead(
        our_score=result.our_score,
        opponent_score=result.opponent_score,
        confidence=result.confidence,
        source=result.source,
        region=region,
        reason=result.reason,
        solo=result.solo,
    )


def _digit_binary(crop_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 135, 255, cv2.THRESH_BINARY)
    kernel = np.ones((2, 2), dtype=np.uint8)
    return cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)


def _digit_components(binary: np.ndarray) -> list[tuple[int, int, int, int]]:
    contours, _hierarchy = cv2.findContours(
        binary,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    min_height = max(8, int(binary.shape[0] * DIGIT_MIN_COMPONENT_HEIGHT_RATIO))
    boxes = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width < DIGIT_MIN_COMPONENT_WIDTH or height < min_height:
            continue
        boxes.append((x, y, width, height))
    boxes.sort(key=lambda item: item[0])
    return boxes


def _match_digit(component: np.ndarray, templates: dict[int, np.ndarray]) -> tuple[int, float]:
    resized = cv2.resize(component, DIGIT_TEMPLATE_SIZE, interpolation=cv2.INTER_AREA)
    _, resized_binary = cv2.threshold(resized, 90, 255, cv2.THRESH_BINARY)
    best_digit = 0
    best_score = -1.0
    for digit, template in templates.items():
        difference = cv2.absdiff(resized_binary, template)
        score = 1.0 - float(difference.mean() / 255.0)
        if score > best_score:
            best_digit = digit
            best_score = score
    return best_digit, best_score


def _read_remaining_move_digits(
    image_bgr: np.ndarray,
    region: tuple[int, int, int, int],
) -> StateFieldRead:
    crop = _crop_region(image_bgr, region)
    if crop is None:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="invalid_region",
            region=region,
            reason="remaining moves crop outside image",
        )

    binary = _digit_binary(crop)
    boxes = _digit_components(binary)
    if not boxes:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="low_confidence",
            region=region,
            reason="no digit components",
        )
    if len(boxes) > 2:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="low_confidence",
            region=region,
            reason=f"too many digit components: {len(boxes)}",
        )

    templates = _digit_templates()
    digits = []
    scores = []
    for x, y, width, height in boxes:
        component = binary[y:y + height, x:x + width]
        digit, score = _match_digit(component, templates)
        # The current Showdown counter uses an extremely narrow 1. Generic
        # templates prefer 7 for that glyph, but its width/height geometry is
        # unambiguous (same safeguard used by the score reader).
        if float(width) / max(1.0, float(height)) <= 0.48:
            digit = 1
            score = max(0.90, score)
        digits.append(str(digit))
        scores.append(score)

    confidence = min(scores) if scores else 0.0
    value = int("".join(digits))
    if value > 12 or confidence < DIGIT_MATCH_THRESHOLD:
        return StateFieldRead(
            value=None,
            confidence=float(confidence),
            source="low_confidence",
            region=region,
            reason=f"digits={''.join(digits)}, confidence={confidence:.3f}",
        )

    # Passing DIGIT_MATCH_THRESHOLD means the move-counter classifier accepted
    # the glyph. StateFieldRead uses the stricter generic auto-state threshold,
    # so promote a valid digit read to that threshold; otherwise scores in the
    # 0.62-0.78 range carry a value but are paradoxically rejected and Solo
    # Challenge falls back to the unrelated regular-layout crop.
    accepted_confidence = max(float(confidence), AUTO_CONFIDENCE_THRESHOLD)
    return StateFieldRead(
        value=value,
        confidence=accepted_confidence,
        source="auto_digits",
        region=region,
        reason=f"digits={''.join(digits)}, confidence={confidence:.3f}",
    )


def read_remaining_moves(
    image,
    *,
    board_profile: str,
    showdown: bool = True,
    party: bool = False,
    solo_challenge: bool = False,
    moves_region: tuple[int, int, int, int] | None = None,
) -> StateFieldRead:
    image_bgr = _as_bgr_array(image)
    if image_bgr is None or image_bgr.size == 0:
        return StateFieldRead(
            value=None,
            confidence=0.0,
            source="invalid_image",
            region=None,
            reason="missing screenshot",
        )

    is_supersize = board_profile == SUPERSIZE_PROFILE

    if moves_region is None:
        if solo_challenge:
            # Solo Challenge has two live layouts: older challenges show a
            # numeric counter on the right, while Score Legend uses a long row
            # of up to 12 move dots. Read the explicit rings first. In the dot
            # layout the old numeric crop lands on the final two empty rings and
            # falsely classifies them as "00" (captured in the latest debug).
            dot_result = _read_solo_move_dot_count(
                image_bgr,
                solo_challenge_moves_region_from_board(),
            )
            if _accept_move_dot_result(dot_result):
                return dot_result
            numeric_result = _read_remaining_move_digits(
                image_bgr,
                solo_challenge_moves_digit_region_from_board(),
            )
            if numeric_result.accepted:
                return numeric_result
            region = remaining_moves_digit_region_from_board()
            return _read_remaining_move_digits(image_bgr, region)
        if party:
            # Party shows rings only -- there is no numeric counter to fall back
            # to. The generic digit crop lands on the leaderboard edge and hands
            # back nonsense like "6" or "8" moves, so stop at the ring read and
            # let the caller keep the last known count.
            return _read_party_move_dot_count(
                image_bgr,
                party_moves_region_from_board(),
            )
        if is_supersize and showdown:
            dot_result = _read_supersize_showdown_move_dot_count(
                image_bgr,
                supersize_showdown_moves_region_from_board(),
            )
        elif is_supersize:
            dot_result = _read_supersize_versus_move_dot_count(
                image_bgr,
                versus_moves_region_from_board(),
            )
        elif showdown:
            dot_result = _read_solo_move_dot_count(
                image_bgr,
                remaining_moves_region_from_board(),
            )
        else:
            dot_result = _read_versus_move_dot_count(
                image_bgr,
                versus_moves_region_from_board(),
            )
        if _accept_move_dot_result(dot_result):
            return dot_result
        region = remaining_moves_digit_region_from_board()
    else:
        if party:
            return _read_party_move_dot_count(image_bgr, moves_region)
        if is_supersize and showdown:
            dot_result = _read_supersize_showdown_move_dot_count(
                image_bgr,
                moves_region,
            )
            if _accept_move_dot_result(dot_result):
                return dot_result
        elif is_supersize:
            dot_result = _read_supersize_versus_move_dot_count(image_bgr, moves_region)
            if _accept_move_dot_result(dot_result):
                return dot_result
        elif not showdown:
            dot_result = _read_versus_move_dot_count(image_bgr, moves_region)
            if _accept_move_dot_result(dot_result):
                return dot_result
        region = moves_region
    return _read_remaining_move_digits(image_bgr, region)


def read_screen_state(
    image,
    *,
    board_profile: str,
    special_piece_mode: str,
    manual_booster_charge: int | None,
    manual_remaining_moves: int | None,
    showdown: bool = True,
    party: bool = False,
    solo_challenge: bool = False,
    total_rounds: int | None = None,
    auto_detect_total_rounds: bool = False,
) -> ScreenStateRead:
    booster_charge = read_booster_charge(
        image,
        board_profile=board_profile,
        special_piece_mode=special_piece_mode,
    )
    remaining_moves = read_remaining_moves(
        image,
        board_profile=board_profile,
        showdown=showdown,
        party=party,
        solo_challenge=solo_challenge,
    )
    score = read_match_score(image, party=party)
    turn_owner = read_turn_owner(image)
    single_round_mode = showdown or party or solo_challenge
    if single_round_mode:
        current_round = StateFieldRead(
            value=None,
            confidence=0.0,
            source="unavailable",
            reason="round indicator disabled for single-round mode",
        )
    elif auto_detect_total_rounds:
        current_round = read_current_round(image, total_rounds=None)
    else:
        current_round = read_current_round(image, total_rounds=total_rounds)
    return ScreenStateRead(
        booster_charge=booster_charge,
        remaining_moves=remaining_moves,
        current_round=current_round,
        turn_owner=turn_owner,
        score=score,
        screenshot_region=None,
        manual_booster_charge=manual_booster_charge,
        manual_remaining_moves=manual_remaining_moves,
    )
