# Auto Play Again Replay Design

## Scope

Add an opt-in toggle next to the existing `Auto` button. When `Auto` and the new replay toggle are both enabled, the bot should recognize the finished-match screen and click `PLAY AGAIN`, then continue auto play for the next match.

## Non-Goals

- Do not change move ranking, booster policy, perk policy, or recognition class behavior.
- Do not click `CLOSE`.
- Do not auto-replay unless the new toggle is enabled.
- Do not wipe selected mode, profile, perks, debug mode, ML mode, state checkboxes, or other persistent GUI settings after replay.

## Architecture

The existing auto loop in `gui.py` remains the single controller. Each auto scan already captures the board crop into memory through `recognition.update_board_2(...)`; before treating that crop as a playable board, the GUI checks whether the crop contains a `PLAY AGAIN` button.

Replay detection lives in `runtime.py` because it owns game-clicking helpers and coordinate conversion through the active board profile. The detector reads the lower-left/middle part of the captured board crop and looks for a large saturated horizontal button shape in the expected `PLAY AGAIN` zone. It accepts red/orange/yellow and blue button backgrounds, but the search region excludes the `CLOSE` button area.

When replay is detected and the toggle is enabled, the GUI clicks the detected button, clears transient auto state and booster latch state, applies a replay cooldown, and keeps `Auto` running. The same transient reset helper is used by the manual `Reset partije` action, but manual reset still turns `Auto` off as it does today.

## Interfaces

- `runtime.detect_play_again_button(image) -> PlayAgainDetection`
  - Returns inactive when the image is missing or the expected button shape is absent.
  - Returns crop-relative click coordinates when active.
- `runtime.click_play_again_button(detection, return_position=None) -> bool`
  - Clicks only active detections.
  - Restores the cursor to the saved position.
- `Ui_MainWindow.AutoReplayCheck`
  - New persisted checkbox in `gui_state.json` under `auto_replay`.

## Error Handling

- Missing image: replay detection returns inactive and auto proceeds through the existing board-stability path.
- Failed click helper: auto does not reset state and resumes scanning on the next timer tick.
- Replay toggle disabled: the finished-match screen is recognized but not clicked; auto status reports that replay is off.

## Testing

- Unit-test red, yellow, and blue `PLAY AGAIN` button detection with synthetic crops.
- Unit-test that the expected region does not detect a blue `CLOSE`-like button outside the play-again area.
- Unit-test that auto replay is not clicked when the toggle is off.
- Unit-test that auto replay clicks and clears transient auto/booster state when the toggle is on.
- Unit-test GUI persistence for the new toggle.

## Failure-Mode Check

- A regular board could contain saturated pieces near the bottom crop. The detector requires a connected horizontal button-like component in the expected region, which is wider than a single board tile.
- A normal blue `PLAY AGAIN` button could resemble the blue `CLOSE` button. The search region excludes the right-side close area, so close is not a valid target.
- The click could happen while a transition animation is still changing. The existing auto timer continues scanning, and replay adds a cooldown before the next board action.
