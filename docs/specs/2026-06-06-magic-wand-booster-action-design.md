# Magic Wand Booster Action - Design

Status: **Approved**
Date: 2026-06-06

## Goal

Add `Magic Wand` as a booster action option beside the existing plain booster
and `High Voltage` actions. When the ready booster is activated, the bot should
click one board tile color. The game then removes every piece of that color.

## Scope

In scope:

- Add `Magic Wand` to `booster_action_mode`.
- Reuse the existing `Activate -> prompt delay -> board tile click -> cursor restore`
  flow used by High Voltage.
- Add a pure strategy target chooser that scores one selected color by simulating
  removal of every normal tile of that color.
- Include special pieces on the chosen color in the existing special-chain
  simulation, so a special painted with that color can blow up.
- Serialize `magic_wand_target` into debug output separately from
  `high_voltage_target`.

Non-goals:

- No ML model, dataset, or asset-label changes.
- No High Voltage scoring changes.
- No change to the existing extra-move-before-booster gates.
- No new manual instructions in the UI.

## Strategy

`move_strategy.py` remains the source of truth for target choice. The new
Magic Wand evaluator should:

- Consider present colors from `BLUE` through `ORANGE`.
- Pick a concrete click cell from that color, preferring plain cells near board
  center and falling back to special cells when needed.
- Simulate clearing all cells of the selected color, then use the existing drop,
  cascade, mode-target, mushroom, special, blue, extra-move, and future-potential
  scoring components.
- Prefer the highest total score, with cleared cells as a deterministic tie
  breaker.

This naturally covers the user tips:

- Purple Gem / Gem Grab favors purple when purple targets are recognized as
  mode targets.
- Multiplier Mushrooms favors colors carrying mushrooms.
- Bounty / Dustville favors orange outlaws when recognized as mode targets.
- Specials on the chosen color are included in the clear and can trigger chains.

## Runtime

`runtime.py` should branch on `booster_action_mode == "magic_wand"` only when
the selected action is already `activate_booster`. If no valid target exists,
it should not click the booster target and should return the existing no-action
result path.

## Debug

`move.json` should include:

- `booster_action_mode: "magic_wand"`
- `magic_wand_target`, using the same compact field shape as
  `high_voltage_target`
- `will_click_magic_wand_target` for intent visibility

`high_voltage_target` stays reserved for High Voltage.

## Failure Modes

- If the bot treats Wand as High Voltage, it may click a color that is good for
  a path clear but bad for full-color removal. The target chooser must be
  separate.
- If specials on the chosen color are ignored, the bot will undervalue strong
  Wand targets. The simulation must go through `_clear_cells_with_specials`.
- If old GUI state is invalid, normalization must fall back to `none`, as today.
