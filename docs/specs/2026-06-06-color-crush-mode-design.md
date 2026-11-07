# Color Crush Mode - Design

Status: **Approved**
Date: 2026-06-06

## Goal

Add `Color Crush Mode` as a first-class game mode for the playable bot.

The mode should model the live rule shown in the screenshot:

- Matching a normal non-blue, non-red color clears all board pieces of that color.
- Blue and red matches are excluded from whole-color clearing.
- Each eligible color charges/scoring value can differ. The default visible mapping is:
  - green = 1
  - orange/brown = 2
  - purple = 3
  - yellow = 4

## Scope

- Add `Color Crush Mode` to the existing game-mode enum and dropdown options.
- Keep the existing `Color Crush` checkbox as a manual override for other modes.
- When `Color Crush Mode` is selected, enable Color Crush simulation even if the checkbox is off.
- Use Color Crush default color values when the mode is selected and no custom Score Rally values are supplied.
- Use those color values both for instant score and booster-fill prioritization.
- Update debug output so saved runs show `mode: Color Crush Mode` and `color_crush: true`.

## Non-Goals

- No OCR for reading the in-game bottom color-value strip.
- No new visual detector for the game-mode banner.
- No change to red/blue regular scoring outside Color Crush mode.
- No separate UI panel for this mode; reuse existing mode dropdown and Score Rally controls.

## Architecture

`move_strategy.py` remains the pure strategy source of truth. It will know the new enum value, Color Crush default color-charge values, and a helper for effective booster charge cells.

`runtime.py` will translate the selected mode into runtime flags: `Color Crush Mode` forces Color Crush simulation and supplies default color values when the user has not enabled custom Score Rally values.

`recognition.py` and `runtime.py` will expose the new mode through existing `GAME_MODE_OPTIONS`, which the GUI already consumes.

## Failure-Mode Check

1. Red could accidentally be crushed because the existing implementation only excluded blue.
   Severity: critical. The implementation must explicitly exclude both blue and red and add a regression test.

2. The bot could score color charges correctly but still prioritize booster fill from only blue tiles.
   Severity: critical. Prioritization must use effective Color Crush charge from eligible cleared colors when the mode is selected.

3. Existing manual Color Crush checkbox behavior could regress.
   Severity: minor if tests cover the old checkbox path. Keep checkbox support and run existing Color Crush tests.

