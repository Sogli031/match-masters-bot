# Auto Early Special Stability - Design

Status: **Approved for implementation**
Date: 2026-06-04

## Goal

Let Auto play sooner when the board is logically stable but a visible tile
animation is still running over an already recognized extra-move star tile.

## Scope

- Auto mode only.
- Keep the existing `AutoMoveStability` state machine.
- Keep the existing async auto scan and `pre_scanned_board` handoff.
- Only bypass visual/motion waiting when the same clean logical board signature
  repeats and the stable `special_board` contains `SPECIAL_XTRA_MOVE_TILE`.

## Non-Goals

- No move ranking changes.
- No ML model, dataset, or confidence threshold changes.
- No manual `Check Best Move` behavior changes.
- No broad "play during any animation" behavior.
- No bypass when the board still has unrecognized cells.
- No bypass while Auto is still waiting for the previously played board
  signature to change.

## Design

`AutoMoveStability.observe(...)` already tracks both logical board signatures and
visual image stability. The new rule adds a narrow exception:

1. Build the current logical signature from `board` and `special_board`.
2. If the board has unrecognized cells, keep the existing block.
3. If the signature matches the previous recognized signature and
   `special_board` includes `SPECIAL_XTRA_MOVE_TILE`, then visual motion or a
   visual hash jump can count as another stable logical observation instead of
   resetting the gate. This includes the post-move case where the first changed
   board was seen during motion and the next scans keep reporting that same
   changed logical signature.
4. The active scan requirement still applies: normally 2 scans, and 3 scans
   after suspicious/post-move evidence.
5. If Auto is waiting for the old played signature to change, the exception is
   not allowed for that old signature.

## Failure Modes

- If recognition falsely reports the same logical board while pieces are still
  falling, Auto could play early. The exception is limited to repeated clean
  signatures with an extra-move star tile to reduce the blast radius.
- If the game ignores swipes during the remaining star animation, the bot may
  still gain little speed. Debug timings and observed deltas should be used to
  judge live value after implementation.
- If other tile animations need similar treatment later, they should be added
  as explicit allowlisted markers rather than weakening the global motion gate.

## Testing

Add regression tests in `tests/test_move_debug.py` proving:

- A repeated clean board with `SPECIAL_XTRA_MOVE_TILE` can count through high
  motion.
- A repeated clean board with `SPECIAL_XTRA_MOVE_TILE` can count through a visual
  hash jump.
- Existing no-marker motion/visual tests continue to require cautious recovery.
