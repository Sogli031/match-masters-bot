# Move Intent Debug Audit - Design

Status: **Draft for user review**
Date: 2026-05-25

## 1. Goal and Scope

Add a debug-only audit trail that explains what the bot expected a selected
move to do, in words, so a saved game can be reviewed after the fact.

The audit should answer questions like:

1. Did the bot know that the swapped bomb would explode from its destination
   cell?
2. Did it expect that explosion to activate another special piece?
3. Did it expect that chained special to clear blue tiles or create value?
4. Did the final selected move win because of an intentional chain, or because
   later random refill happened to be lucky?

The first implementation should focus on the selected move in each debug run.
It should keep the current screenshots and JSON files, and add one human-readable
intent file per run plus a session-level audit index.

### Non-goals

- No move-ranking changes.
- No recognition or ML changes.
- No new gameplay UI flow.
- No claim that unknown refill cascades were known in advance.
- No visual overlay drawing in the first slice.
- No attempt to explain every rejected candidate in prose.

## 2. Existing Runtime Anchors

The current debug flow already creates one folder per decision under
`Debug/runs/<timestamp>/`.

Important existing files:

- `board.png` - raw board screenshot for the run.
- `recognized.png` - recognized board overlay.
- `move.json` - selected action, board state, selected move, score fields, and
  top-level debug context.
- `candidates.json` - serialized ranked candidates.
- `observed_delta.json` - later observation for the previous run when available.

The current runtime already serializes:

- `reason`
- `explanation`
- `expected_cascades`
- `cleared_cells`
- `blue_cells`
- `activated_specials`
- `cascade_count`
- `extra_moves`
- `direct_extra_moves`

Those fields are useful, but they are not enough to explain a causal chain like
"bomb clears a vertical arrow, then the vertical arrow clears 3 blue tiles".

## 3. Considered Approaches

### Option A: Only add more fields to `move.json`

Pros:
- Minimal disk churn.
- Easy to test with the current serializer tests.

Cons:
- Hard to read after a game.
- The user still has to inspect nested JSON to understand intent.

Verdict: not enough for the requested review workflow.

### Option B: Structured `intent_events` plus per-run `intent.txt`

Add machine-readable intent events to the serialized selected move, then render
the selected action into `Debug/runs/<timestamp>/intent.txt`.

Pros:
- Human-readable after a game.
- Keeps detailed evidence in JSON for future tests.
- Fits the existing `write_move_debug_report(...)` flow.
- Does not affect ranking or live play.

Cons:
- Requires threading causal events through the pure simulation path.
- Needs careful wording to avoid overstating unknown refill cascades.

Recommendation: implement Option B.

### Option C: Add an annotated image overlay

Draw arrows and numbered chain steps directly onto `recognized.png` or a new
image file.

Pros:
- Fastest to visually inspect.

Cons:
- Larger UI/debug rendering scope.
- Can become cluttered on chain-heavy boards.
- Still needs structured data underneath to be trustworthy.

Verdict: defer until the text audit proves useful.

## 4. Proposed Design

### 4.1 Structured intent events

Add a debug-only structured event list to the pure move simulation output. The
event list should be carried into `MoveEvaluation` and then serialized by
`runtime.serialize_move_evaluation(...)`.

Proposed field name:

```python
intent_events: list[dict]
```

Each event should be small, stable, and JSON-friendly. Example event shapes:

```json
{
  "type": "match",
  "cascade": 1,
  "kind": "three",
  "color": 1,
  "cells": [[2, 2], [2, 3], [2, 4]]
}
```

```json
{
  "type": "special_activation",
  "cascade": 1,
  "special": "bomb",
  "cell": [2, 4],
  "source": "matched_cell"
}
```

```json
{
  "type": "special_effect",
  "cascade": 1,
  "special": "bomb",
  "cell": [2, 4],
  "cleared_cells": 13,
  "blue_cells": 3,
  "activated_specials": [[2, 6]]
}
```

```json
{
  "type": "uncertain_refill_boundary",
  "after_cascade": 2,
  "reason": "board_wipe_or_unknown_refill"
}
```

The exact internal representation can be a dataclass or a plain dict list. The
serialized contract should be plain JSON.

### 4.2 Causal chain capture

The simulation currently resolves special chains inside `_resolve_special_chain`
and `_clear_cells_with_specials`. That is where the trace should record:

- which special activated,
- which cells it cleared,
- how many of those cells were blue,
- which additional specials were added to the chain queue,
- whether this was a normal bomb, Bomb+Bomb combo, horizontal, vertical, disco,
  color clear, or another known special type.

For direct Bomb+Bomb swaps, the trace should explicitly say that the combo blast
is centered on `candidate.target`.

For ordinary bomb matches, the trace should explicitly reflect the bomb's
post-swap location from `candidate.special_board`.

### 4.3 Human-readable `intent.txt`

For each debug run, write:

```text
Debug run: 2026-05-25_...
Selected action: move
Move: (3,4) -> (2,4)

Plan:
- Bomb ends on (2,4) and explodes from that cell.
- Bomb clears 13 cells, including 3 blue cells.
- Bomb activates vertical arrow at (2,6).
- Vertical arrow clears column 6, including 3 blue cells.
- Expected total: 18 cleared cells, 6 blue cells, 2 activated specials, 2 cascades.

Why selected:
- pokrece kaskadu
- skuplja plave
- pravi ili aktivira specijal

Limits:
- Later refill-dependent cascades are not counted as known intent.
```

The text can stay mostly English or Serbian-style mixed text, matching the
current runtime prints such as `Razlog` and `Detalji`. It should be short enough
to scan quickly.

### 4.4 Session-level audit file

Append a short section to:

```text
Debug/intent_audit.md
```

Each section should include:

- run folder name,
- selected action,
- selected move or perk/booster target,
- one-line reason,
- expected totals,
- relative path to the detailed `intent.txt`.

This file is a review index. The full evidence remains in the run folder.

### 4.5 JSON serialization

Extend:

- `runtime.serialize_move_evaluation(...)`
- `runtime.serialize_perk_action(...)` for `follow_up`
- `runtime.write_move_debug_report(...)`

`move.json` should include:

- `best_move.intent_events`
- `best_move.intent_summary`
- `intent_file`: `"intent.txt"`

`candidates.json` may include `intent_summary` for the top candidates, but the
first slice should avoid huge event dumps for every candidate unless needed. Full
`intent_events` are required only for the selected move.

### 4.6 Supported selected actions

First slice:

- `selected_action == "move"`: full intent trace for `best_evaluation`.
- `selected_action == "activate_perk"`: write the perk action summary and, if
  `selected_perk_action.follow_up` exists, include that follow-up move's intent.
- `selected_action == "activate_booster"`: write the existing booster target
  summary and high-voltage summary if present. Full booster intent tracing can
  be added later.
- `selected_action == "none"`: write why no move was selected if a debug run is
  still produced.

### 4.7 Debug mode behavior

This feature should only write disk artifacts when debug output is enabled and
`write_move_debug_report(...)` is called. It must not create new files when debug
mode is off.

## 5. Interfaces and Contracts

### Strategy contract

Simulation and evaluation objects may gain:

```python
intent_events: list[dict] = field(default_factory=list)
```

Existing callers should not need to pass anything new. When no trace exists,
the serializer should emit an empty list or omit the detailed event list and
still produce a safe fallback text from existing score fields.

### Runtime contract

Add pure formatting helpers in `runtime.py`, for example:

```python
def summarize_move_intent(evaluation) -> dict:
    ...

def render_move_intent_text(move_payload: dict) -> str:
    ...
```

`write_move_debug_report(...)` owns writing `intent.txt` and appending
`Debug/intent_audit.md`, because it already owns the run folder and debug JSON.

### File contract

Per run:

```text
Debug/runs/<timestamp>/intent.txt
```

Global audit index:

```text
Debug/intent_audit.md
```

The audit index should use append-only sections. If a run is regenerated in the
same folder, replacing that run's section is optional; duplicate sections are
acceptable only if each section includes the run id and timestamp.

## 6. Error Handling

- If intent rendering fails, `move.json` and `candidates.json` should still be
  written.
- The `intent.txt` file should include a short fallback message rather than
  aborting the debug report.
- Unknown special ids should render as `special_<id>` instead of crashing.
- Empty or missing `intent_events` should render from existing totals and
  `describe_move_reason(...)`.
- Uncertain refill cascades should be marked as uncertain, not as planned
  intent.

## 7. Testing Strategy

Unit tests should cover:

1. A bomb match records that the bomb explodes from its post-swap cell.
2. A Bomb+Bomb swap records the 21-cell combo centered on `candidate.target`.
3. A special chain records the downstream special activation and blue cells.
4. `serialize_move_evaluation(...)` includes intent summary data.
5. `write_move_debug_report(...)` writes `intent.txt`.
6. `write_move_debug_report(...)` appends `Debug/intent_audit.md`.
7. Missing or empty intent events still produce a readable fallback.
8. Existing `move.json` and `candidates.json` remain valid.

Verification commands:

```powershell
python -m pytest tests/test_move_strategy.py -q
python -m pytest tests/test_move_debug.py -q
python -m pytest -q
python -m py_compile move_strategy.py runtime.py
```

Manual verification:

1. Enable debug mode.
2. Run a move with a bomb or Bomb+Bomb chain.
3. Open the newest `Debug/runs/<timestamp>/intent.txt`.
4. Confirm the text describes the same plan that appears in `move.json`.
5. Confirm `Debug/intent_audit.md` includes the run.

## 8. Failure-Mode Check

### Failure mode 1: The text makes luck look intentional

Risk: high. The whole point is to separate known intent from lucky refill.

Mitigation: trace only deterministic events from the current board and mark any
post-wipe or unknown-refill-dependent cascade with an uncertainty boundary.

### Failure mode 2: Intent trace changes ranking behavior

Risk: high. Audit should not alter gameplay.

Mitigation: keep event collection side-effect-free, preserve existing scores,
and verify with current `test_move_strategy.py` plus full pytest.

### Failure mode 3: The audit file becomes too noisy

Risk: medium. Full chain details for every candidate would make review harder.

Mitigation: write full prose for the selected action only. Keep `candidates.json`
compact and use `Debug/intent_audit.md` as an index, not a full duplicate.

### Failure mode 4: Debug-off still writes files

Risk: medium. The user already has a debug mode expectation.

Mitigation: write `intent.txt` only inside `write_move_debug_report(...)`, the
existing debug-report path.

## 9. Rollout Notes

This is an audit-only feature. It can be implemented in small slices:

1. Add intent event storage and serialization for selected move evaluations.
2. Add text rendering and per-run `intent.txt`.
3. Add `Debug/intent_audit.md`.
4. Expand event detail for special-chain causality.

The feature is useful even if the first slice produces fallback text for some
special types, as long as it does not overclaim unknown or untraced behavior.
