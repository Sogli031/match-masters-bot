from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class PerkExecutionStage(str, Enum):
    ACTIVATE = "activate"
    TARGET = "target"
    FOLLOW_UP = "follow_up"
    VERIFY = "verify"
    RESCAN = "rescan"
    RETRY = "retry"
    ABORT = "abort"
    COMPLETE = "complete"


@dataclass(frozen=True)
class PerkExecutionFrame:
    signature: object | None
    perk_status: str = "unknown"
    board_valid: bool = True
    board: object | None = None
    special_board: object | None = None


@dataclass
class PerkExecutionResult:
    success: bool
    reason: str
    stages: list[dict] = field(default_factory=list)
    retried: bool = False
    board_changed: bool = False
    final_frame: PerkExecutionFrame | None = None
    follow_up_recalculated: bool = False


def execute_perk_flow(
    *,
    perk_key: str,
    slot_number: int,
    target_points: list[tuple[int, int]],
    before_frame: PerkExecutionFrame,
    click_activate: Callable[[], None],
    click_target: Callable[[tuple[int, int]], None],
    capture_frame: Callable[[], PerkExecutionFrame],
    requires_next_move: bool = False,
    follow_up=None,
    play_follow_up: Callable[[object], bool] | None = None,
    recalculate_follow_up: Callable[[PerkExecutionFrame], object | None] | None = None,
    sleep: Callable[[float], None] | None = None,
    prompt_delay: float = 0.2,
    verify_delay: float = 0.25,
    verify_attempts: int = 8,
) -> PerkExecutionResult:
    """Execute one complete perk transaction and confirm it from later frames.

    A mouse click is never treated as success. Targeted perks are sent as one
    uninterrupted activation -> target transaction so an animation or a slow
    recognition pass cannot make the executor skip the required target click.
    One retry is allowed only while both the board signature and perk status
    remain unchanged.
    """

    sleeper = sleep or (lambda _seconds: None)
    stages: list[dict] = []

    def record(stage: PerkExecutionStage, **payload) -> None:
        stages.append(
            {
                "perk_execution_stage": stage.value,
                "perk": perk_key,
                "slot": slot_number,
                **payload,
            }
        )

    def changed(frame: PerkExecutionFrame) -> bool:
        return bool(
            before_frame.signature is not None
            and frame.signature is not None
            and frame.signature != before_frame.signature
        )

    def attempt_clicks(is_retry: bool) -> tuple[bool, PerkExecutionFrame | None, str | None]:
        if is_retry:
            record(PerkExecutionStage.RETRY, reason="unchanged_board_and_perk")
        click_activate()
        record(
            PerkExecutionStage.ACTIVATE,
            retry=is_retry,
            expected="perk_prompt_or_effect",
            prompt_delay=prompt_delay,
        )
        sleeper(prompt_delay)

        for index, point in enumerate(target_points):
            click_target(point)
            record(
                PerkExecutionStage.TARGET,
                target_index=index + 1,
                target_count=len(target_points),
                target=list(point),
                expected="target_selection",
                prompt_delay=prompt_delay,
            )
            # Only a following target needs another prompt transition.  The
            # final click goes straight into verification, which already waits
            # for the effect and avoids a redundant fixed pause.
            if index < len(target_points) - 1:
                sleeper(prompt_delay)
        # Capture only after every required target was clicked. Board/perk
        # recognition can take long enough for the in-game target prompt to
        # disappear, which was the source of intermittent missing target clicks.
        activation_frame = capture_frame()
        return True, activation_frame, None

    latest = before_frame
    follow_up_recalculated = False
    for attempt in range(2):
        clicked, activation_frame, abort_reason = attempt_clicks(attempt == 1)
        if not clicked:
            return PerkExecutionResult(
                False,
                abort_reason or "stale_target",
                stages,
                retried=attempt == 1,
                board_changed=bool(activation_frame and changed(activation_frame)),
                final_frame=activation_frame,
            )

        if requires_next_move:
            # Energy Boost remains visually "available" while it is armed and
            # changes to "used" only after the swipe consumes it. Therefore the
            # required order is click -> prompt delay -> swipe -> verification;
            # waiting for "used" here would deadlock before the swipe.
            latest = activation_frame or capture_frame()
            selected_follow_up = follow_up
            recalculated = False
            if changed(latest):
                if recalculate_follow_up is None:
                    record(PerkExecutionStage.RESCAN, reason="board_changed_before_follow_up")
                    return PerkExecutionResult(
                        False,
                        "board_changed_before_follow_up",
                        stages,
                        retried=attempt == 1,
                        board_changed=True,
                        final_frame=latest,
                    )
                selected_follow_up = recalculate_follow_up(latest)
                recalculated = True
                follow_up_recalculated = True
                record(PerkExecutionStage.RESCAN, reason="recalculate_follow_up")
            if selected_follow_up is None or play_follow_up is None:
                record(PerkExecutionStage.ABORT, reason="missing_legal_follow_up")
                return PerkExecutionResult(
                    False,
                    "missing_legal_follow_up",
                    stages,
                    retried=attempt == 1,
                    board_changed=changed(latest),
                    final_frame=latest,
                    follow_up_recalculated=recalculated,
                )
            played = bool(play_follow_up(selected_follow_up))
            record(
                PerkExecutionStage.FOLLOW_UP,
                expected="swipe",
                confirmed_effect="swipe_sent" if played else "swipe_failed",
                recalculated=recalculated,
            )
            if not played:
                return PerkExecutionResult(
                    False,
                    "follow_up_failed",
                    stages,
                    retried=attempt == 1,
                    final_frame=latest,
                    follow_up_recalculated=recalculated,
                )

        confirmed = False
        post_signature = None
        stable_post_frames = 0
        effect_observed = False
        for verify_index in range(max(1, int(verify_attempts))):
            sleeper(verify_delay)
            latest = capture_frame()
            board_changed = changed(latest)
            perk_used = latest.perk_status == "used"
            effect_observed = effect_observed or board_changed or perk_used
            if latest.board_valid and latest.signature == post_signature:
                stable_post_frames += 1
            elif latest.board_valid:
                post_signature = latest.signature
                stable_post_frames = 1
            else:
                post_signature = None
                stable_post_frames = 0
            if requires_next_move:
                # A changed board alone could be an ordinary swipe after a
                # missed perk click. Energy Boost succeeds only when both the
                # swipe changed the board and the perk became used.
                confirmed_effect = board_changed and perk_used
                expected_effect = "board_changed_and_perk_used_after_follow_up"
            else:
                confirmed_effect = effect_observed
                expected_effect = "board_change_or_perk_used"
            # A positively recognized used-slot is direct evidence that the
            # perk was consumed. Requiring two identical board frames as well
            # made animated Hammer/Remove Cross effects wait through all eight
            # attempts and sometimes report a false failure even after the slot
            # visibly changed to used.
            confirmed = bool(perk_used or (confirmed_effect and stable_post_frames >= 2))
            record(
                PerkExecutionStage.VERIFY,
                attempt=verify_index + 1,
                expected=expected_effect,
                confirmed_effect=(
                    "board_changed" if board_changed else "perk_used" if perk_used else "none"
                ),
                stable_post_frames=stable_post_frames,
            )
            if confirmed:
                record(PerkExecutionStage.RESCAN, confirmed_effect="stable_post_perk_frame")
                record(PerkExecutionStage.COMPLETE, confirmed_effect="verified")
                return PerkExecutionResult(
                    True,
                    "verified",
                    stages,
                    retried=attempt == 1,
                    board_changed=board_changed,
                    final_frame=latest,
                    follow_up_recalculated=follow_up_recalculated,
                )

        unchanged = (
            latest.signature == before_frame.signature
            and latest.perk_status == before_frame.perk_status
        )
        if attempt == 0 and unchanged:
            continue
        break

    record(PerkExecutionStage.ABORT, reason="effect_not_confirmed")
    return PerkExecutionResult(
        False,
        "effect_not_confirmed",
        stages,
        retried=True,
        board_changed=changed(latest),
        final_frame=latest,
    )
