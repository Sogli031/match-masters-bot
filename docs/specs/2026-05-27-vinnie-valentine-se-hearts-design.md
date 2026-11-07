# Vinnie Valentine SE Hearts Design

## Scope

Add runtime support for Vinnie Valentine SE hearts as two-color heart specials. The bot should let the user choose ordinary hearts or SE hearts so recognition does not mix the two when both template families are plausible.

## Requirements

- Preserve ordinary Vinnie heart behavior as `SPECIAL_HEART`: a matched heart clears the heart color from the board.
- Add SE heart specials that carry exactly two normal colors. A SE heart may match as either of its two colors.
- A SE heart match clears both of the SE heart's colors from the current board state.
- A heart-heart SE combo may clear the union of both hearts' color pairs.
- Add a GUI selector for special-piece recognition mode instead of always sending `auto`.
- If the user selects ordinary hearts, only ordinary heart templates are used.
- If the user selects SE hearts, ordinary heart templates are ignored and only SE heart templates are used.
- Do not claim or simulate how many SE hearts Vinnie inserts or where they land.

## Architecture

`move_strategy.py` owns the two-color semantics. SE heart special codes encode a sorted color pair, leaving `board[row][col]` as the primary display/training color. Helper functions decode the pair wherever matching, clearing, debug naming, or dataset classification needs it.

`recognition.py` owns the recognition mode and optional template loading. SE templates are loaded from `assets/general/vinnie_se_heart_<color1>_<color2>.png` when present. Missing templates are allowed so the app can run before real crops are added.

`gui.py` adds a special-piece selector backed by `SPECIAL_PIECE_MODE_OPTIONS`, persists it in `gui_state.json`, and sends the selected value in `CheckBestMoveRequest`.

## Non-Goals

- No live SE asset creation in this change.
- No ML model retraining.
- No rule for Vinnie insertion count, targeting, or randomness.
- No change to booster activation price beyond preserving the existing `BOOSTER_MAX_CHARGE = 7`.

## Failure Modes

- If no SE template images exist, selected SE mode will not detect live SE hearts. This is acceptable; `Slikaj debug` can produce the fixture/crop needed for templates.
- Encoded SE heart specials are not color-agnostic; dataset and debug code must preserve both colors to avoid losing training/audit truth.
- Auto mode can still run all compatible detectors; explicit ordinary/SE heart modes are the safety gate when the user wants only one heart family.

## Testing Strategy

- Unit-test SE special encoding/decoding and dataset class names.
- Unit-test two-color matching and clearing in `move_strategy.py`.
- Unit-test GUI selector persistence and request propagation.
- Unit-test recognition mode gating so ordinary-heart mode skips SE detection and SE mode skips ordinary-heart detection.
