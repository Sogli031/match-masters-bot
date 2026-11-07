# Move Intent Debug Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:subagent-driven-development (recommended) or superpowers-optimized:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a debug-only intent audit that writes a readable `intent.txt` per debug run plus a `Debug/intent_audit.md` review index showing what the bot expected the selected move to do.
**Architecture:** The pure simulator in `move_strategy.py` will collect side-effect-free `intent_events` while preserving existing scoring. `runtime.py` will serialize those events, summarize them, render selected-action prose, write `intent.txt`, and append the audit index from the existing `write_move_debug_report(...)` path. The live ranking and action-selection behavior must not change.
**Tech Stack:** Python 3, dataclasses, pytest, existing `move_strategy.py`, `runtime.py`, `tests/test_move_strategy.py`, `tests/test_move_debug.py`.
**Assumptions:**
- Assumes debug reports are written only through `runtime.write_move_debug_report(...)` - will NOT work for code paths that bypass that function and still expect disk audit files.
- Assumes current deterministic simulator results are the source of truth for intent - will NOT claim unknown refill or post-wipe random cascades as planned intent.
- Assumes this checkout may not have a reliable Git baseline - do NOT add commit steps or revert unrelated local changes.

---

## Approved Scope

Approved design: `docs/specs/2026-05-25-move-intent-debug-audit-design.md`.

Implement Option B from the spec:

- Add structured `intent_events` to selected move evaluations.
- Add `intent_summary` to serialized move payloads.
- Write `Debug/runs/<timestamp>/intent.txt` from the selected action.
- Append a compact section to `Debug/intent_audit.md`.
- Keep all changes audit-only: no ranking, recognition, ML, or gameplay UI changes.

## Non-Goals

- No move ranking changes.
- No recognition or ML changes.
- No visual overlay drawing.
- No prose explanation for every rejected candidate.
- No disk writes when debug report generation is not called.
- No claim that refill-dependent luck was known intent.

## File Structure

- Modify `move_strategy.py`
  - Add `intent_events` fields to `SimulationResult` and `MoveEvaluation`.
  - Add small helpers for event cells, special names, match events, and special-chain events.
  - Thread event collection through `simulate_candidate(...)`, `_simulate_special_swap_candidate(...)`, `_clear_matches_with_details(...)`, `_clear_cells_with_specials(...)`, and `_resolve_special_chain(...)`.
  - Preserve all existing return values and score calculations.

- Modify `runtime.py`
  - Add `summarize_move_intent(evaluation)`.
  - Add `render_move_intent_text(move_payload)`.
  - Add `write_intent_debug_files(run_path, move_payload)`.
  - Extend `serialize_move_evaluation(...)` with `intent_events` and `intent_summary`.
  - Extend `write_move_debug_report(...)` to write `intent.txt`, append `intent_audit.md`, and include `"intent_file": "intent.txt"` in `move.json`.

- Modify `tests/test_move_strategy.py`
  - Add simulator-level tests proving bomb post-swap, Bomb+Bomb target-center, and chain special intent events.
  - Add uncertainty-boundary coverage for Color Crush/random-refill boundaries.

- Modify `tests/test_move_debug.py`
  - Add serializer and text-rendering tests.
  - Add file-output tests for `intent.txt` and `intent_audit.md`.

## Stop Conditions

Stop and report before continuing if:

- Any intent collection change alters existing scores, selected move ordering, or current test expectations unrelated to new intent fields.
- `intent.txt` cannot be written without risking failure of `move.json` / `candidates.json` generation.
- A required causal claim cannot be derived from deterministic current-board simulation.
- Full pytest shows order-sensitive failures; rerun once with `python -m pytest --cache-clear` before changing production code again.

---

## Task 1: Add Intent Fields and Serialization Contract

**Files:**
- Modify: `move_strategy.py`
- Modify: `runtime.py`
- Test: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:**
- Does not collect causal special-chain events yet.
- Does not write `intent.txt` yet.
- Does not append `Debug/intent_audit.md` yet.

- [x] **Step 1: Write failing serializer test**

Add this test near the existing `serialize_move_evaluation` tests in `tests/test_move_debug.py`:

```python
def test_serialize_move_evaluation_includes_intent_events_and_summary():
    events = [
        {
            "type": "special_effect",
            "cascade": 1,
            "special": "bomb",
            "cell": [2, 4],
            "cleared_cells": 13,
            "blue_cells": 3,
            "activated_specials": [[2, 6]],
        }
    ]
    evaluation = MoveEvaluation(
        candidate=MoveCandidate((2, 4), (3, 4), Direction.DOWN, [], []),
        score=42.0,
        instant_score=13.0,
        special_bonus=12.0,
        blue_bonus=3.0,
        mode_bonus=0.0,
        extra_move_bonus=0.0,
        disco_move_bonus=0.0,
        extra_moves=0.0,
        disco_moves=0.0,
        cascade_count=1.0,
        board_potential=0.0,
        lookahead_bonus=0.0,
        explanation="instant=13.0, special=12.0",
        blue_cells=3.0,
        cleared_cells=13.0,
        activated_specials=1.0,
        intent_events=events,
    )

    payload = bot.serialize_move_evaluation(evaluation)

    assert payload["intent_events"] == events
    assert payload["intent_summary"] == {
        "event_count": 1,
        "cleared_cells": 13.0,
        "blue_cells": 3.0,
        "activated_specials": 1.0,
        "cascade_count": 1.0,
        "has_chain": True,
        "has_uncertain_boundary": False,
    }
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_move_debug.py -q -k intent_events_and_summary`

Expected: FAIL with `TypeError: MoveEvaluation.__init__() got an unexpected keyword argument 'intent_events'` or `KeyError: 'intent_events'`.

- [x] **Step 3: Implement fields and serializer contract**

In `move_strategy.py`, add `intent_events` to both dataclasses:

```python
@dataclass
class SimulationResult:
    ...
    cleared_color_counts: dict[int, float] = field(default_factory=dict)
    intent_events: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class MoveEvaluation:
    ...
    decision_gate: str = DECISION_GATE_UNKNOWN
    cleared_cells: float = 0.0
    activated_specials: float = 0.0
    intent_events: list[dict] = field(default_factory=list)
```

In `evaluate_simulation(...)`, pass the field through:

```python
return MoveEvaluation(
    ...
    cascade_matches=result.cascade_matches,
    cleared_cells=result.cleared_cells,
    activated_specials=result.activated_specials,
    intent_events=result.intent_events,
)
```

In `runtime.py`, add:

```python
def summarize_move_intent(evaluation):
    if evaluation is None:
        return None
    events = list(getattr(evaluation, "intent_events", []) or [])
    return {
        "event_count": len(events),
        "cleared_cells": float(getattr(evaluation, "cleared_cells", 0.0)),
        "blue_cells": float(getattr(evaluation, "blue_cells", 0.0)),
        "activated_specials": float(getattr(evaluation, "activated_specials", 0.0)),
        "cascade_count": float(getattr(evaluation, "cascade_count", 0.0)),
        "has_chain": any(
            event.get("type") == "special_effect" and event.get("activated_specials")
            for event in events
        ),
        "has_uncertain_boundary": any(
            event.get("type") == "uncertain_refill_boundary"
            for event in events
        ),
    }
```

Extend `serialize_move_evaluation(...)` payload:

```python
"intent_events": list(getattr(evaluation, "intent_events", []) or []),
"intent_summary": summarize_move_intent(evaluation),
"cleared_cells": evaluation.cleared_cells,
"activated_specials": evaluation.activated_specials,
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_move_debug.py -q -k intent_events_and_summary`

Expected: PASS.

---

## Task 2: Collect Match and Bomb Intent Events in the Simulator

**Files:**
- Modify: `move_strategy.py`
- Test: `tests/test_move_strategy.py`

**Security flag:** `none`

**Does NOT cover:**
- Does not render human-readable text.
- Does not write audit files.
- Does not trace perk or booster-only actions.

- [x] **Step 1: Write failing simulator tests**

Add these tests next to the existing bomb tests in `tests/test_move_strategy.py`:

```python
def test_swapped_bomb_match_records_post_swap_intent_event():
    board = make_base_board()
    board[2][2] = BLUE
    board[2][3] = BLUE
    board[2][4] = RED
    board[3][4] = BLUE
    special_board = make_special_board()
    special_board[3][4] = SPECIAL_BOMB
    candidate = next(
        candidate
        for candidate in generate_candidates(board, special_board)
        if candidate.start == (2, 4) and candidate.target == (3, 4)
    )
    result = simulate_candidate(
        candidate,
        initial_matches=find_matches(candidate.board),
        max_cascades=1,
    )

    effects = [
        event for event in result.intent_events
        if event["type"] == "special_effect" and event["special"] == "bomb"
    ]

    assert effects
    assert effects[0]["cell"] == [2, 4]
    assert effects[0]["cleared_cells"] == 13
    assert effects[0]["blue_cells"] >= 1


def test_bomb_bomb_swap_records_combo_centered_on_target():
    board = make_base_board()
    special_board = make_special_board()
    special_board[3][2] = SPECIAL_BOMB
    special_board[3][3] = SPECIAL_BOMB
    candidate = MoveCandidate((3, 2), (3, 3), Direction.RIGHT, board, special_board)

    result = strategy._simulate_special_swap_candidate(candidate, max_cascades=1)

    combo_events = [
        event for event in result.intent_events
        if event["type"] == "special_effect" and event["special"] == "bomb_bomb"
    ]
    assert combo_events == [
        {
            "type": "special_effect",
            "cascade": 1,
            "special": "bomb_bomb",
            "cell": [3, 3],
            "cleared_cells": 21,
            "blue_cells": combo_events[0]["blue_cells"],
            "activated_specials": [],
        }
    ]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_move_strategy.py -q -k "records_post_swap_intent_event or records_combo_centered_on_target"`

Expected: FAIL because `SimulationResult` has no populated `intent_events`.

- [x] **Step 3: Implement event helpers and collection**

In `move_strategy.py`, add helpers near `_bomb_effect_cells(...)`:

```python
SPECIAL_INTENT_NAMES = {
    SPECIAL_HORIZONTAL: "horizontal",
    SPECIAL_VERTICAL: "vertical",
    SPECIAL_BOMB: "bomb",
    SPECIAL_LIGHTNING: "lightning",
    SPECIAL_HEART: "heart",
    SPECIAL_KNIGHT: "knight",
    SPECIAL_CLEO_BUG: "cleo_bug",
    SPECIAL_COLOR_CRYSTAL: "color_crystal",
    SPECIAL_DISCO_BALL: "disco",
    SPECIAL_MUSHROOM: "mushroom",
    SPECIAL_ALL_ABOARD_BANDIT: "all_aboard_bandit",
    SPECIAL_JOOJOO_SKULL: "joojoo_skull",
}


def _intent_cell(cell: tuple[int, int]) -> list[int]:
    return [int(cell[0]), int(cell[1])]


def _intent_cells(cells) -> list[list[int]]:
    return [_intent_cell(cell) for cell in sorted(cells)]


def _special_intent_name(special: int) -> str:
    if _is_created_special(special):
        return "created_special"
    return SPECIAL_INTENT_NAMES.get(special, f"special_{special}")


def _append_match_intent_events(intent_events, matches, cascade_number: int) -> None:
    if intent_events is None:
        return
    for match in matches:
        intent_events.append(
            {
                "type": "match",
                "cascade": int(cascade_number),
                "kind": match.kind,
                "color": int(match.color),
                "cells": _intent_cells(match.cells),
                "tile_count": len(match.cells),
            }
        )


def _special_chain_targets(board, special_board, effect_cells, source_cell, excluded_cells=None):
    excluded_cells = excluded_cells or set()
    return [
        cell
        for cell in sorted(effect_cells)
        if cell != source_cell
        and cell not in excluded_cells
        and special_board[cell[0]][cell[1]] not in {EMPTY, SPECIAL_MODE_TARGET, SPECIAL_BILLIE_DRONE}
    ]
```

Update `_resolve_special_chain(...)` signature:

```python
def _resolve_special_chain(
    board,
    special_board,
    initial_cells,
    suppressed_special_effect_cells: set[tuple[int, int]] | None = None,
    intent_events: list[dict] | None = None,
    cascade_number: int = 1,
) -> tuple[set[tuple[int, int]], int]:
```

Inside the `while queue:` loop, after `activated.add((row, col))`, append activation:

```python
if intent_events is not None:
    intent_events.append(
        {
            "type": "special_activation",
            "cascade": int(cascade_number),
            "special": _special_intent_name(special),
            "cell": _intent_cell((row, col)),
            "source": "cleared_cell",
        }
    )
```

After computing `effect_cells`, append the effect event before queueing:

```python
chain_targets = _special_chain_targets(board, special_board, effect_cells, (row, col))
if intent_events is not None:
    intent_events.append(
        {
            "type": "special_effect",
            "cascade": int(cascade_number),
            "special": _special_intent_name(special),
            "cell": _intent_cell((row, col)),
            "cleared_cells": len(effect_cells),
            "blue_cells": sum(1 for r, c in effect_cells if board[r][c] == BLUE),
            "activated_specials": _intent_cells(chain_targets),
        }
    )
```

Update `_clear_cells_with_specials(...)` to accept and pass `intent_events` and `cascade_number`.

In `simulate_candidate(...)`, initialize `intent_events = []`, call `_append_match_intent_events(intent_events, matches, cascade_index + 1)` before clearing each cascade, pass `intent_events=intent_events` and `cascade_number=cascade_index + 1` into `_clear_matches_with_details(...)`, and return it in `SimulationResult(..., intent_events=intent_events)`.

Update `_clear_matches_with_details(...)` signature to accept:

```python
intent_events: list[dict] | None = None
cascade_number: int = 1
```

and pass those into `_clear_cells_with_specials(...)`.

In `_simulate_special_swap_candidate(...)`, initialize `intent_events = []`. For Bomb+Bomb, append this event before `_clear_cells_with_specials(...)`:

```python
combo_activated = _special_chain_targets(
    board,
    special_board,
    initial_cells,
    candidate.target,
    excluded_cells={candidate.start, candidate.target},
)
intent_events.append(
    {
        "type": "special_effect",
        "cascade": 1,
        "special": "bomb_bomb",
        "cell": _intent_cell(candidate.target),
        "cleared_cells": len(initial_cells),
        "blue_cells": sum(1 for r, c in initial_cells if board[r][c] == BLUE),
        "activated_specials": _intent_cells(combo_activated),
    }
)
```

Pass `intent_events=intent_events` and `cascade_number=1` into `_clear_cells_with_specials(...)`, pass the same into later cascade `_clear_matches_with_details(...)` calls, and return `SimulationResult(..., intent_events=intent_events)`.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_move_strategy.py -q -k "records_post_swap_intent_event or records_combo_centered_on_target"`

Expected: PASS.

---

## Task 3: Record Chain Details and Uncertain Refill Boundaries

**Files:**
- Modify: `move_strategy.py`
- Test: `tests/test_move_strategy.py`

**Security flag:** `none`

**Does NOT cover:**
- Does not change extra-move counting.
- Does not change where Color Crush stops trusting random refill.
- Does not render prose.

- [x] **Step 1: Write failing chain and uncertainty tests**

Add these tests in `tests/test_move_strategy.py`:

```python
def test_bomb_bomb_intent_records_downstream_special_activation():
    board = make_base_board()
    special_board = make_special_board()
    special_board[3][2] = SPECIAL_BOMB
    special_board[3][3] = SPECIAL_BOMB
    special_board[1][3] = SPECIAL_VERTICAL
    candidate = MoveCandidate((3, 2), (3, 3), Direction.RIGHT, board, special_board)

    result = strategy._simulate_special_swap_candidate(candidate, max_cascades=1)

    combo = next(
        event for event in result.intent_events
        if event["type"] == "special_effect" and event["special"] == "bomb_bomb"
    )
    vertical = next(
        event for event in result.intent_events
        if event["type"] == "special_effect" and event["special"] == "vertical"
    )

    assert combo["activated_specials"] == [[1, 3]]
    assert vertical["cell"] == [1, 3]
    assert vertical["blue_cells"] >= 1


def test_color_crush_intent_marks_uncertain_refill_boundary():
    board = [
        [2, 2, 2, 3, 5, 6, 1],
        [3, 4, 5, 6, 1, 2, 3],
        [4, 5, 6, 1, 3, 4, 2],
        [5, 6, 1, 3, 4, 5, 6],
        [6, 1, 2, 3, 5, 6, 1],
        [1, 2, 3, 5, 6, 1, 2],
        [2, 3, 4, 6, 1, 2, 3],
    ]
    candidate = MoveCandidate((0, 0), (0, 1), Direction.RIGHT, board, make_special_board())

    with strategy.color_crush_active(True):
        result = simulate_candidate(candidate, initial_matches=find_matches(board), max_cascades=4)

    assert any(
        event["type"] == "uncertain_refill_boundary"
        for event in result.intent_events
    )
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_move_strategy.py -q -k "downstream_special_activation or uncertain_refill_boundary"`

Expected: FAIL because downstream chain details or uncertainty event is missing.

- [x] **Step 3: Implement chain and uncertainty details**

In `_resolve_special_chain(...)`, ensure `chain_targets` includes special cells inside the base effect even when the target cell is already in `cleared`. Do not require `effect_cell not in cleared` for intent reporting.

In `simulate_candidate(...)`, when `first_wipe_cascade` is set for the first time, append:

```python
if intent_events is not None:
    intent_events.append(
        {
            "type": "uncertain_refill_boundary",
            "after_cascade": int(cascade_index + 1),
            "reason": "board_wipe_or_unknown_refill",
        }
    )
```

Use the local `intent_events` list in `simulate_candidate(...)`; there is no need for `intent_events is not None` guard inside that function because the local list always exists.

For `_simulate_special_swap_candidate(...)`, append match events for later cascades with cascade numbers starting at `2`:

```python
cascade_number = len(cascade_matches) + 2
_append_match_intent_events(intent_events, matches, cascade_number)
...
_clear_matches_with_details(..., intent_events=intent_events, cascade_number=cascade_number)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_move_strategy.py -q -k "downstream_special_activation or uncertain_refill_boundary"`

Expected: PASS.

---

## Task 4: Render Human-Readable Intent Text

**Files:**
- Modify: `runtime.py`
- Test: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:**
- Does not write files yet.
- Does not append `Debug/intent_audit.md` yet.
- Does not add image overlays.

- [x] **Step 1: Write failing renderer tests**

Add these tests in `tests/test_move_debug.py`:

```python
def test_render_move_intent_text_describes_selected_move_chain():
    move_payload = {
        "created_at": "2026-05-25T12:00:00",
        "selected_action": "move",
        "best_move": {
            "start": [3, 4],
            "target": [2, 4],
            "direction": "up",
            "reason": "Odigrao sam ovo jer pravi ili aktivira specijal i skuplja plave.",
            "cleared_cells": 18.0,
            "blue_cells": 6.0,
            "activated_specials": 2.0,
            "cascade_count": 2.0,
            "intent_events": [
                {
                    "type": "special_effect",
                    "cascade": 1,
                    "special": "bomb",
                    "cell": [2, 4],
                    "cleared_cells": 13,
                    "blue_cells": 3,
                    "activated_specials": [[2, 6]],
                },
                {
                    "type": "special_effect",
                    "cascade": 1,
                    "special": "vertical",
                    "cell": [2, 6],
                    "cleared_cells": 7,
                    "blue_cells": 3,
                    "activated_specials": [],
                },
            ],
        },
    }

    text = bot.render_move_intent_text(move_payload)

    assert "Selected action: move" in text
    assert "Move: (3,4) -> (2,4) up" in text
    assert "Bomb explodes from (2,4), clears 13 cells, including 3 blue cells." in text
    assert "Bomb activates special at (2,6)." in text
    assert "Vertical clears 7 cells, including 3 blue cells." in text
    assert "Expected total: 18 cleared cells, 6 blue cells, 2 activated specials, 2 cascades." in text


def test_render_move_intent_text_marks_uncertain_boundary():
    move_payload = {
        "selected_action": "move",
        "best_move": {
            "start": [0, 0],
            "target": [0, 1],
            "direction": "right",
            "reason": "Odigrao sam ovo jer pokrece kaskadu.",
            "cleared_cells": 20.0,
            "blue_cells": 2.0,
            "activated_specials": 0.0,
            "cascade_count": 4.0,
            "intent_events": [
                {
                    "type": "uncertain_refill_boundary",
                    "after_cascade": 1,
                    "reason": "board_wipe_or_unknown_refill",
                }
            ],
        },
    }

    text = bot.render_move_intent_text(move_payload)

    assert "Later refill-dependent cascades are not counted as known intent." in text
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_move_debug.py -q -k "render_move_intent_text"`

Expected: FAIL with `AttributeError: module 'test' has no attribute 'render_move_intent_text'` or equivalent missing function on `runtime`.

- [x] **Step 3: Implement text renderer**

In `runtime.py`, add helpers near `describe_move_reason(...)`:

```python
INTENT_SPECIAL_LABELS = {
    "bomb": "Bomb",
    "bomb_bomb": "Bomb+Bomb",
    "horizontal": "Horizontal",
    "vertical": "Vertical",
    "lightning": "Lightning",
    "heart": "Heart",
    "knight": "Knight",
    "created_special": "Created special",
    "color_crystal": "Color crystal",
    "disco": "Disco",
}


def _format_intent_cell(cell):
    if not isinstance(cell, (list, tuple)) or len(cell) != 2:
        return "(?,?)"
    return f"({cell[0]},{cell[1]})"


def _format_intent_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.1f}"


def _intent_special_label(name):
    return INTENT_SPECIAL_LABELS.get(name, str(name).replace("_", " ").title())
```

Add:

```python
def render_move_intent_text(move_payload: dict) -> str:
    lines = []
    selected_action = move_payload.get("selected_action", "unknown")
    lines.append(f"Selected action: {selected_action}")
    best_move = move_payload.get("best_move") or {}
    if best_move:
        start = _format_intent_cell(best_move.get("start"))
        target = _format_intent_cell(best_move.get("target"))
        direction = best_move.get("direction", "unknown")
        lines.append(f"Move: {start} -> {target} {direction}")
    lines.append("")
    lines.append("Plan:")
    events = list(best_move.get("intent_events") or [])
    plan_lines = []
    for event in events:
        event_type = event.get("type")
        if event_type == "special_effect":
            special = _intent_special_label(event.get("special"))
            cell = _format_intent_cell(event.get("cell"))
            cleared = _format_intent_number(event.get("cleared_cells", 0))
            blue = _format_intent_number(event.get("blue_cells", 0))
            plan_lines.append(
                f"- {special} clears {cleared} cells from {cell}, including {blue} blue cells."
            )
            if event.get("special") == "bomb":
                plan_lines[-1] = (
                    f"- Bomb explodes from {cell}, clears {cleared} cells, including {blue} blue cells."
                )
            if event.get("special") == "bomb_bomb":
                plan_lines[-1] = (
                    f"- Bomb+Bomb explodes from target {cell}, clears {cleared} cells, including {blue} blue cells."
                )
            for activated in event.get("activated_specials") or []:
                plan_lines.append(f"- {special} activates special at {_format_intent_cell(activated)}.")
        elif event_type == "uncertain_refill_boundary":
            plan_lines.append("- Later refill-dependent cascades are not counted as known intent.")
    if not plan_lines:
        plan_lines.append("- No detailed intent events were recorded; using score summary only.")
    lines.extend(plan_lines)
    lines.append("")
    lines.append("Why selected:")
    reason = best_move.get("reason") or "No readable reason recorded."
    lines.append(f"- {reason}")
    lines.append("")
    lines.append(
        "Expected total: "
        f"{_format_intent_number(best_move.get('cleared_cells', 0))} cleared cells, "
        f"{_format_intent_number(best_move.get('blue_cells', 0))} blue cells, "
        f"{_format_intent_number(best_move.get('activated_specials', 0))} activated specials, "
        f"{_format_intent_number(best_move.get('cascade_count', 0))} cascades."
    )
    return "\n".join(lines) + "\n"
```

If tests require the vertical line wording exactly, special-case `"vertical"` before the generic line:

```python
if event.get("special") == "vertical":
    plan_lines[-1] = (
        f"- Vertical clears {cleared} cells, including {blue} blue cells."
    )
```

Ensure `test.py` re-exports runtime symbols as it already does for `describe_move_reason`; if it does not, import/use `runtime_bot.render_move_intent_text` in tests instead of `bot.render_move_intent_text`.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_move_debug.py -q -k "render_move_intent_text"`

Expected: PASS.

---

## Task 5: Write `intent.txt` and Append `intent_audit.md`

**Files:**
- Modify: `runtime.py`
- Test: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:**
- Does not write files outside the existing debug-report path.
- Does not create an image overlay.
- Does not remove or rewrite older audit sections.

- [x] **Step 1: Write failing file-output tests**

Add these tests in `tests/test_move_debug.py`:

```python
def test_write_move_debug_report_writes_intent_text_and_payload_path(tmp_path):
    bot.board_length = 7
    bot.squareSize = 20
    source_image = tmp_path / "source.png"
    Image.new("RGB", (140, 140), "black").save(source_image)
    board = [
        [1, 1, 2, 1, 5, 6, 2],
        [2, 3, 4, 5, 6, 1, 3],
        [3, 4, 5, 6, 1, 2, 4],
        [4, 5, 6, 1, 2, 3, 5],
        [5, 6, 1, 2, 3, 4, 6],
        [6, 1, 2, 3, 4, 5, 2],
        [2, 3, 4, 5, 6, 2, 3],
    ]
    special_board = bot.create_board()
    special_board[0][2] = 3
    best = choose_best_move(board, special_board, mode="None", lookahead_candidates=0)
    candidates = rank_moves(board, special_board, mode="None", lookahead_candidates=0)

    run_path = bot.write_move_debug_report(
        tmp_path / "run",
        source_image,
        board,
        special_board,
        best,
        candidates,
        mode="None",
        profile="regular",
        allow_square_matches=False,
        score_rally_values=None,
    )

    move = json.loads((run_path / "move.json").read_text(encoding="utf-8"))
    intent_text = (run_path / "intent.txt").read_text(encoding="utf-8")

    assert move["intent_file"] == "intent.txt"
    assert "Selected action: move" in intent_text
    assert "Expected total:" in intent_text


def test_write_move_debug_report_appends_intent_audit_index(tmp_path):
    bot.board_length = 7
    bot.squareSize = 20
    source_image = tmp_path / "source.png"
    Image.new("RGB", (140, 140), "black").save(source_image)
    board = [
        [1, 1, 2, 1, 5, 6, 2],
        [2, 3, 4, 5, 6, 1, 3],
        [3, 4, 5, 6, 1, 2, 4],
        [4, 5, 6, 1, 2, 3, 5],
        [5, 6, 1, 2, 3, 4, 6],
        [6, 1, 2, 3, 4, 5, 2],
        [2, 3, 4, 5, 6, 2, 3],
    ]
    special_board = bot.create_board()
    special_board[0][2] = 3
    best = choose_best_move(board, special_board, mode="None", lookahead_candidates=0)
    candidates = rank_moves(board, special_board, mode="None", lookahead_candidates=0)

    run_path = bot.write_move_debug_report(
        tmp_path / "runs" / "2026-05-25_12-00-00_000",
        source_image,
        board,
        special_board,
        best,
        candidates,
        mode="None",
        profile="regular",
        allow_square_matches=False,
        score_rally_values=None,
    )

    audit_path = tmp_path / "intent_audit.md"
    audit_text = audit_path.read_text(encoding="utf-8")

    assert run_path.name in audit_text
    assert "intent.txt" in audit_text
    assert "Selected action: move" in audit_text
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_move_debug.py -q -k "intent_text_and_payload_path or intent_audit_index"`

Expected: FAIL because `intent.txt`, `intent_file`, or `intent_audit.md` does not exist.

- [x] **Step 3: Implement debug file writing**

In `runtime.py`, add:

```python
INTENT_FILENAME = "intent.txt"
INTENT_AUDIT_FILENAME = "intent_audit.md"
```

Add:

```python
def _intent_audit_path(run_path: Path) -> Path:
    if run_path.parent.name == "runs":
        return run_path.parent.parent / INTENT_AUDIT_FILENAME
    return run_path.parent / INTENT_AUDIT_FILENAME


def _render_intent_audit_entry(run_path: Path, move_payload: dict) -> str:
    best_move = move_payload.get("best_move") or {}
    selected_action = move_payload.get("selected_action", "unknown")
    reason = best_move.get("reason") or "No readable reason recorded."
    totals = (
        f"{_format_intent_number(best_move.get('cleared_cells', 0))} cleared, "
        f"{_format_intent_number(best_move.get('blue_cells', 0))} blue, "
        f"{_format_intent_number(best_move.get('activated_specials', 0))} specials, "
        f"{_format_intent_number(best_move.get('cascade_count', 0))} cascades"
    )
    return (
        f"## {run_path.name}\n\n"
        f"- Selected action: {selected_action}\n"
        f"- Reason: {reason}\n"
        f"- Expected: {totals}\n"
        f"- Details: `{run_path.name}/{INTENT_FILENAME}`\n\n"
    )


def write_intent_debug_files(run_path: Path, move_payload: dict) -> None:
    intent_text = render_move_intent_text(move_payload)
    (run_path / INTENT_FILENAME).write_text(intent_text, encoding="utf-8")
    audit_path = _intent_audit_path(run_path)
    header = "# Move Intent Audit\n\n"
    if not audit_path.exists():
        audit_path.write_text(header, encoding="utf-8")
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(_render_intent_audit_entry(run_path, move_payload))
```

In `write_move_debug_report(...)`, add `"intent_file": INTENT_FILENAME` to `move_payload`, write `move.json` and `candidates.json` as today, then call:

```python
try:
    write_intent_debug_files(run_path, move_payload)
except Exception as exc:
    fallback = (
        "Selected action: "
        f"{move_payload.get('selected_action', 'unknown')}\n\n"
        f"Intent rendering failed: {exc}\n"
    )
    (run_path / INTENT_FILENAME).write_text(fallback, encoding="utf-8")
```

Keep the exception local to intent rendering; do not skip `move.json` or `candidates.json`.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_move_debug.py -q -k "intent_text_and_payload_path or intent_audit_index"`

Expected: PASS.

---

## Task 6: Cover Fallback Rendering, Perks, and Existing Debug Compatibility

**Files:**
- Modify: `runtime.py`
- Test: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:**
- Does not add full booster causality tracing beyond current high-voltage summary.
- Does not add rejected-candidate prose.
- Does not modify GUI controls.

- [x] **Step 1: Write failing fallback and compatibility tests**

Add these tests in `tests/test_move_debug.py`:

```python
def test_render_move_intent_text_falls_back_without_intent_events():
    move_payload = {
        "selected_action": "move",
        "best_move": {
            "start": [1, 2],
            "target": [1, 3],
            "direction": "right",
            "reason": "Odigrao sam ovo jer cisti dosta polja.",
            "cleared_cells": 5.0,
            "blue_cells": 0.0,
            "activated_specials": 0.0,
            "cascade_count": 1.0,
        },
    }

    text = bot.render_move_intent_text(move_payload)

    assert "No detailed intent events were recorded; using score summary only." in text
    assert "Odigrao sam ovo jer cisti dosta polja." in text


def test_serialize_perk_action_follow_up_keeps_intent_summary():
    follow_up = MoveEvaluation(
        candidate=MoveCandidate((1, 2), (1, 3), Direction.RIGHT, [], []),
        score=20.0,
        instant_score=8.0,
        special_bonus=12.0,
        blue_bonus=0.0,
        mode_bonus=0.0,
        extra_move_bonus=0.0,
        disco_move_bonus=0.0,
        extra_moves=0.0,
        disco_moves=0.0,
        cascade_count=1.0,
        board_potential=0.0,
        lookahead_bonus=0.0,
        explanation="instant=8.0, special=12.0",
        intent_events=[
            {
                "type": "special_effect",
                "cascade": 1,
                "special": "bomb",
                "cell": [1, 3],
                "cleared_cells": 13,
                "blue_cells": 2,
                "activated_specials": [],
            }
        ],
    )
    action = bot.PerkAction(
        perk_key=bot.PERK_HAMMER,
        target=(1, 2),
        score=25.0,
        gross_score=25.0,
        threshold=3.0,
        baseline_score=5.0,
        follow_up=follow_up,
        reason="Hammer follow-up",
        explanation="hammer_follow_up_bonus=20.0",
    )

    payload = bot.serialize_perk_action(action)

    assert payload["follow_up"]["intent_summary"]["event_count"] == 1
    assert payload["follow_up"]["intent_events"][0]["special"] == "bomb"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_move_debug.py -q -k "falls_back_without_intent_events or follow_up_keeps_intent_summary"`

Expected: FAIL if fallback text or perk follow-up serialization is missing.

- [x] **Step 3: Implement compatibility behavior**

Adjust `render_move_intent_text(...)` so it works when:

- `move_payload["best_move"]` is missing,
- `best_move["intent_events"]` is missing,
- `selected_action` is `"activate_perk"` and `selected_perk_action.follow_up` is present in serialized payload,
- `selected_action` is `"activate_booster"` and `high_voltage_target` exists.

For perk follow-up, render:

```python
if selected_action == "activate_perk":
    perk = move_payload.get("selected_perk_action") or {}
    lines.append(f"Perk: {perk.get('perk', 'unknown')}")
    follow_up = perk.get("follow_up")
    if follow_up:
        best_move = follow_up
```

For high-voltage booster, render:

```python
if selected_action == "activate_booster" and move_payload.get("high_voltage_target"):
    target = move_payload["high_voltage_target"]
    lines.append(f"High Voltage target: {_format_intent_cell(target.get('target_cell'))}")
    lines.append(
        "Expected total: "
        f"{_format_intent_number(target.get('cleared_cells', 0))} cleared cells, "
        f"{_format_intent_number(target.get('blue_cells', 0))} blue cells, "
        f"{_format_intent_number(target.get('activated_specials', 0))} activated specials, "
        f"{_format_intent_number(target.get('cascade_count', 0))} cascades."
    )
    return "\n".join(lines) + "\n"
```

Confirm `serialize_perk_action(...)` does not need custom changes beyond `serialize_move_evaluation(action.follow_up)` after Task 1.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_move_debug.py -q -k "falls_back_without_intent_events or follow_up_keeps_intent_summary"`

Expected: PASS.

---

## Task 7: Full Verification and Scope Audit

**Files:**
- Verify: `move_strategy.py`
- Verify: `runtime.py`
- Verify: `tests/test_move_strategy.py`
- Verify: `tests/test_move_debug.py`
- Verify: `docs/specs/2026-05-25-move-intent-debug-audit-design.md`
- Verify: `docs/plans/2026-05-25-move-intent-debug-audit.md`

**Security flag:** `none`

**Does NOT cover:**
- Does not run live BlueStacks verification unless the user explicitly asks.
- Does not validate visual overlay output because this feature is text/JSON audit only.

- [x] **Step 1: Run targeted strategy tests**

Run: `python -m pytest tests/test_move_strategy.py -q`

Expected: PASS with all strategy tests passing.

- [x] **Step 2: Run targeted debug tests**

Run: `python -m pytest tests/test_move_debug.py -q`

Expected: PASS with all debug/runtime tests passing.

- [x] **Step 3: Run full test suite**

Run: `python -m pytest -q`

Expected: PASS. If this fails with order-sensitive or cache-sensitive behavior, run `python -m pytest --cache-clear` once before changing code.

- [x] **Step 4: Compile changed modules**

Run: `python -m py_compile move_strategy.py runtime.py tests/test_move_strategy.py tests/test_move_debug.py`

Expected: exit code 0.

- [x] **Step 5: Stub scan changed production files**

Run: `rg -n "TODO|FIXME|placeholder|NotImplementedError|raise NotImplementedError" move_strategy.py runtime.py`

Expected: no matches. Exit code 1 from `rg` is acceptable when there are no matches.

- [x] **Step 6: Scope audit**

Run: `rg -n "intent_events|intent_summary|intent.txt|intent_audit|render_move_intent_text|write_intent_debug_files" move_strategy.py runtime.py tests/test_move_strategy.py tests/test_move_debug.py`

Expected:
- Matches exist only in the planned files.
- No GUI, recognition, ML, or scoring-policy files are modified for this feature.
- Existing `move.json` and `candidates.json` tests still pass.

- [x] **Step 7: Manual debug artifact check without BlueStacks**

Use the file-output tests' temporary run folders as evidence during pytest. If manual local artifact inspection is needed, create a scratch run by calling `write_move_debug_report(...)` from an interactive Python snippet and inspect:

```text
<run>/move.json
<run>/candidates.json
<run>/intent.txt
<parent>/intent_audit.md
```

Expected:
- `move.json` includes `"intent_file": "intent.txt"`.
- `best_move.intent_events` is a JSON array.
- `best_move.intent_summary` exists.
- `intent.txt` is readable without opening JSON.
- `intent_audit.md` contains the run folder name and a link-like detail path.

---

## Expected Final Behavior

When debug mode produces a run folder, the folder will contain the existing screenshots and JSON plus:

```text
intent.txt
```

The parent debug directory will also contain or update:

```text
intent_audit.md
```

For a move where the bot intentionally uses a bomb to trigger another special, the text should say that the bomb exploded from the correct cell, how many cells and blue cells it cleared, which special it activated, and the expected totals. If the simulator reaches an unknown-refill boundary, the text must say that later refill-dependent cascades are not counted as known intent.
