# Fireworks Directional Tiles - Design

Status: **Approved**
Date: 2026-05-27

## Goal

Represent Fireworks rockets as direction-aware special tiles so recognition,
dataset review, and strategy can distinguish left, right, up, and down arrows.

## Scope

- Add four runtime special codes: firework left, firework right, firework up,
  and firework down.
- Add color-bound dataset classes such as `yellow_firework_up` and
  `orange_firework_left` so the reviewer can choose both color and direction.
- Map Fireworks mode templates to the directional special codes.
- Simulate directional Fireworks effects from the rocket cell to the board edge.
- Keep existing normal horizontal and vertical arrow behavior unchanged.

## Non-Goals

- No retraining in this change.
- No new GUI layout or controls.
- No changes to non-Fireworks arrow recognition.
- No change to the existing rule that Fireworks rockets do not count as
  adjacent special-special activations in Fireworks mode.

## Design

Fireworks rockets stay color-bound because move scoring still needs the tile
color. The dataset class shape is:

```text
<color>_firework_<direction>
```

Examples:

```text
yellow_firework_up
orange_firework_left
purple_firework_down
```

Recognition writes the real board color and the directional special code into
`board` and `special_board`. Strategy treats the directional codes as Fireworks
rockets and clears only the path indicated by the arrow:

- left clears row cells from the rocket to column 0.
- right clears row cells from the rocket to the last column.
- up clears column cells from the rocket to row 0.
- down clears column cells from the rocket to the last row.

The old `SPECIAL_HORIZONTAL` and `SPECIAL_VERTICAL` codes remain valid for
normal arrows and existing tests.

## Verification

Run:

```powershell
python -m pytest tests\test_dataset_classes.py tests\test_special_detection.py tests\test_move_strategy.py -q
python -m py_compile move_strategy.py recognition.py runtime.py dataset_classes.py test.py
rg -n "TODO|FIXME|placeholder|NotImplementedError|raise NotImplementedError" move_strategy.py recognition.py runtime.py dataset_classes.py
```
