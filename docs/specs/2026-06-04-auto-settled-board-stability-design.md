# Auto Settled Board Stability

## Scope

Auto mode should be able to play once the board itself is stable, even when cosmetic star or sparkle animation is still moving. The stability gate must not use `SPECIAL_XTRA_MOVE_TILE` as proof that it is safe to play, because ML can misread animation or overlays as Xtra markers when the active game mode is `None`.

## Design

- Keep `auto_board_signature()` as the exact board/special signature used by existing callers.
- Add an Auto-only settled signature that keeps base colors but normalizes animation-only Xtra markers to empty specials.
- Add a core-motion score over the central region of each board cell. Full-board motion/hash changes may be ignored only when the settled signature is unchanged and core motion is below the existing Auto motion threshold.
- Reject ML `*_xtra_move` predictions while the active game mode is `None`, leaving the already-recognized base color intact.

## Non-Goals

- Do not change strategy scoring for real `SPECIAL_XTRA_MOVE_TILE` markers already present in `special_board`.
- Do not lower the existing Auto scan interval or post-move cooldown in this change.
- Do not treat high core motion as safe; falling tiles still wait for the cautious stability path.

## Failure Modes

- If a falling tile is recognized with the same base color while the cell center still moves, core motion blocks early play.
- If ML sees a false Xtra marker in `None` mode, the marker is rejected before strategy scoring can treat it as an extra move.
- If there is no explicit core-motion signal, visual/hash jumps keep the old cautious behavior instead of being bypassed.

## Testing

- Unit tests cover core-motion masking, removal of Xtra-only early play, settled-signature counting through Xtra animation, and ML rejection for Xtra in `None` mode.
- Broader runtime and recognition overlay suites must pass before live testing.
