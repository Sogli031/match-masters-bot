# Booster Action Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:subagent-driven-development (recommended) or superpowers-optimized:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make piece recognition automatic while the visible booster selector controls only post-Activate behavior: plain Activate or High Voltage tile click.
**Architecture:** Keep recognition-side `special_piece_mode` internally, but make the main GUI pass `SPECIAL_PIECE_MODE_AUTO` for board recognition and auto scans. Add a separate runtime `booster_action_mode` contract with two values, `none` and `high_voltage`, and use that contract for booster latch identity, High Voltage branching, GUI state, and debug output. Preserve existing ML modes, High Voltage target scoring, booster timing, perk behavior, and template fallback code.
**Tech Stack:** Python 3, PyQt5, pytest, dataclasses, existing `test.py` facade, existing `runtime.py`, `gui.py`, `recognition.py`, `move_strategy.py`.
**Assumptions:**
- Assumes ML recognition is already trained and available through existing `ML first` / `ML only` controls - will NOT work as a model-quality fix if the ONNX model misclassifies a piece.
- Assumes old named `SPECIAL_PIECE_MODE_*` constants remain internally for template fallback and tests - will NOT delete template detectors or old recognition-mode normalization.
- Assumes the checkout has no reliable Git repository - will NOT require `git commit`; use explicit verification and scope audit instead.
- Assumes the approved UI scope is exactly two booster action options: `Bez posebne akcije` and `High Voltage` - will NOT add Mixy Meow or other action boosters.

---

## Approved Scope

Implement the approved design from `docs/specs/2026-05-25-booster-action-selector-design.md`.

In scope:
- Hide/remove manual figure-family selection from the main UI.
- Recognize all supported figures automatically from the main move and auto-scan flows.
- Add `booster_action_mode` with values `none` and `high_voltage`.
- Preserve old state where `special_piece_mode = "high_voltage"` by migrating it to `booster_action_mode = "high_voltage"`.
- Gate High Voltage post-Activate behavior by `booster_action_mode`, not by recognition-side `special_piece_mode`.
- Add `booster_action_mode` to `move.json`.

Out of scope:
- ML model training, threshold changes, or dataset changes.
- High Voltage target scoring changes.
- New action boosters beyond High Voltage.
- Removal of old template fallback branches.
- Broad visual redesign.

Expected final behavior:
- The main window booster selector contains only `Bez posebne akcije` and `High Voltage`.
- Manual move checks and auto scans use automatic piece recognition.
- A ready booster with `Bez posebne akcije` clicks only Activate.
- A ready booster with `High Voltage` clicks Activate, waits, then clicks the selected target tile.
- `ML only` remains strict: if ML coverage is incomplete, the existing ML-only block behavior remains.

Stop conditions:
- Stop and ask before deleting old `SPECIAL_PIECE_MODE_*` constants or template fallback branches.
- Stop and ask before changing High Voltage scoring weights or target selection.
- Stop and ask before adding any action booster beyond `High Voltage`.
- Stop if full `python -m pytest -q` fails for reasons outside these files and cannot be isolated.

## File Structure

- `runtime.py`: owns `BOOSTER_ACTION_*` constants, `normalize_booster_action_mode(...)`, booster latch identity, `CheckBestMoveRequest.booster_action_mode`, runtime activation branching, and debug payload field.
- `gui.py`: owns the visible two-option booster action selector, GUI state migration, automatic recognition request construction, and request handoff.
- `test.py`: remains a facade; no direct edits expected unless facade forwarding changes become necessary.
- `tests/test_booster_activation.py`: covers booster action normalization, default request value, and latch key behavior.
- `tests/test_move_debug.py`: covers GUI options/state migration/request construction, High Voltage-vs-plain runtime branching, and `move.json` debug output.
- `docs/specs/2026-05-25-booster-action-selector-design.md`: already approved source of truth.

## Task 1: Add Runtime Booster Action Contract

**Files:**
- Modify: `runtime.py`
- Test: `tests/test_booster_activation.py`

**Security flag:** `none`

**Does NOT cover:** GUI changes, High Voltage click execution, debug writer changes, or recognition path changes. This task only creates the runtime contract and latch identity.

- [x] **Step 1: Write failing tests**

Add these tests to `tests/test_booster_activation.py` near the existing booster latch tests:

```python
def test_booster_action_mode_normalization_maps_legacy_values():
    assert bot.normalize_booster_action_mode(None) == bot.BOOSTER_ACTION_NONE
    assert bot.normalize_booster_action_mode("") == bot.BOOSTER_ACTION_NONE
    assert bot.normalize_booster_action_mode("nista") == bot.BOOSTER_ACTION_NONE
    assert bot.normalize_booster_action_mode("bez posebne akcije") == bot.BOOSTER_ACTION_NONE
    assert bot.normalize_booster_action_mode("high_voltage") == bot.BOOSTER_ACTION_HIGH_VOLTAGE
    assert bot.normalize_booster_action_mode("High Voltage") == bot.BOOSTER_ACTION_HIGH_VOLTAGE
    assert bot.normalize_booster_action_mode(bot.SPECIAL_PIECE_MODE_HIGH_VOLTAGE) == bot.BOOSTER_ACTION_HIGH_VOLTAGE
    assert bot.normalize_booster_action_mode(bot.SPECIAL_PIECE_MODE_KNIGHTS) == bot.BOOSTER_ACTION_NONE


def test_check_best_move_request_defaults_booster_action_mode_to_plain():
    request = bot.CheckBestMoveRequest(
        mode=bot.normalize_game_mode(None),
        special_piece_mode=bot.SPECIAL_PIECE_MODE_AUTO,
        selected_profile="regular",
        allow_square_matches=True,
        specials_explode_immediately=False,
        score_rally_values=None,
        selected_perks=(bot.PERK_NONE, bot.PERK_NONE),
        cursor_return_position=(10, 20),
    )

    assert request.booster_action_mode == bot.BOOSTER_ACTION_NONE


def test_booster_ready_latch_clears_when_booster_action_mode_changes():
    bot.clear_booster_ready_latch()
    ready_detection = {"active": True, "score": 0.81}
    missed_detection = {"active": False, "score": 0.24}

    bot.apply_booster_ready_latch(ready_detection, bot.BOOSTER_ACTION_HIGH_VOLTAGE)
    result = bot.apply_booster_ready_latch(
        missed_detection,
        bot.BOOSTER_ACTION_NONE,
    )

    assert result["active"] is False
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_booster_activation.py -q`

Expected: FAIL because `BOOSTER_ACTION_NONE`, `BOOSTER_ACTION_HIGH_VOLTAGE`, `normalize_booster_action_mode`, and `CheckBestMoveRequest.booster_action_mode` do not exist yet.

- [x] **Step 3: Implement production change**

In `runtime.py`, add constants near the existing top-level runtime constants:

```python
BOOSTER_ACTION_NONE = "none"
BOOSTER_ACTION_HIGH_VOLTAGE = "high_voltage"
BOOSTER_ACTION_OPTIONS = (
    ("Bez posebne akcije", BOOSTER_ACTION_NONE),
    ("High Voltage", BOOSTER_ACTION_HIGH_VOLTAGE),
)
BOOSTER_ACTION_LABELS = {
    BOOSTER_ACTION_NONE: "Bez posebne akcije",
    BOOSTER_ACTION_HIGH_VOLTAGE: "High Voltage",
}
```

Add normalization near the other small normalization/helper functions:

```python
def normalize_booster_action_mode(value):
    text = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    if text in {"high voltage", "voltage", "visoki napon"}:
        return BOOSTER_ACTION_HIGH_VOLTAGE
    if text in {
        "",
        "none",
        "nista",
        "nothing",
        "off",
        "bez",
        "bez boostera",
        "bez posebne akcije",
        "plain",
        "activate",
    }:
        return BOOSTER_ACTION_NONE
    return BOOSTER_ACTION_NONE
```

Change the latch state and functions in `runtime.py`:

```python
_booster_ready_latch = {
    "booster_action_mode": None,
    "detection": None,
}


def clear_booster_ready_latch():
    _booster_ready_latch["booster_action_mode"] = None
    _booster_ready_latch["detection"] = None


def apply_booster_ready_latch(detection, booster_action_mode):
    current = dict(detection or {"active": False, "score": 0.0})
    normalized_mode = normalize_booster_action_mode(booster_action_mode)
    latched_mode = _booster_ready_latch["booster_action_mode"]
    if latched_mode is not None and latched_mode != normalized_mode:
        clear_booster_ready_latch()

    if current.get("active"):
        current["latched"] = False
        _booster_ready_latch["booster_action_mode"] = normalized_mode
        _booster_ready_latch["detection"] = dict(current)
        return current

    latched_detection = _booster_ready_latch["detection"]
    if latched_detection is not None:
        result = dict(latched_detection)
        result["active"] = True
        result["latched"] = True
        result["raw_active"] = bool(current.get("active", False))
        result["raw_score"] = current.get("score", 0.0)
        return result

    current["latched"] = False
    return current
```

Add the request field to `CheckBestMoveRequest` immediately after
`cursor_return_position` so all required dataclass fields remain before default
fields:

```python
    booster_action_mode: str = BOOSTER_ACTION_NONE
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_booster_activation.py -q`

Expected: PASS.

- [x] **Step 5: Scope check**

Run: `rg -n "booster_action_mode|BOOSTER_ACTION|normalize_booster_action_mode|special_piece_mode" runtime.py tests/test_booster_activation.py`

Expected: the new action contract appears in `runtime.py`; old `SPECIAL_PIECE_MODE_*` constants are not deleted. Do not run git commit in this checkout.

## Task 2: Replace Main UI Figure Selector With Booster Action Selector

**Files:**
- Modify: `gui.py`
- Test: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:** Runtime action execution or debug writer changes. This task only changes UI state and request construction.

- [x] **Step 1: Write failing tests**

In `tests/test_move_debug.py`, add this helper near `_ml_mode_values(...)`:

```python
def _booster_action_values(ui):
    return [
        ui.BoosterActionBox.itemData(index)
        for index in range(ui.BoosterActionBox.count())
    ]
```

Update `test_main_window_has_current_score_extra_move_and_auto_action_buttons` with these assertions after the ML mode assertions:

```python
    assert _booster_action_values(ui) == [
        bot.BOOSTER_ACTION_NONE,
        bot.BOOSTER_ACTION_HIGH_VOLTAGE,
    ]
    assert [
        ui.BoosterActionBox.itemText(index)
        for index in range(ui.BoosterActionBox.count())
    ] == ["Bez posebne akcije", "High Voltage"]
    assert "Booster: Srca" not in [
        ui.BoosterActionBox.itemText(index)
        for index in range(ui.BoosterActionBox.count())
    ]
    assert ui.gui_state_payload()["booster_action_mode"] == bot.BOOSTER_ACTION_NONE
```

Add state migration tests near the existing GUI state tests:

```python
def test_load_gui_state_migrates_legacy_high_voltage_to_booster_action(monkeypatch, tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    state_path = tmp_path / "gui_state.json"
    state_path.write_text(
        json.dumps({"special_piece_mode": bot.SPECIAL_PIECE_MODE_HIGH_VOLTAGE}),
        encoding="utf-8",
    )
    monkeypatch.setattr(bot, "GUI_STATE_PATH", state_path)

    window = QtWidgets.QMainWindow()
    ui = bot.Ui_MainWindow()
    ui.setupUi(window)

    ui.load_gui_state()

    assert ui.BoosterActionBox.currentData() == bot.BOOSTER_ACTION_HIGH_VOLTAGE
    assert ui.gui_state_payload()["booster_action_mode"] == bot.BOOSTER_ACTION_HIGH_VOLTAGE


def test_load_gui_state_migrates_legacy_figure_mode_to_plain_booster_action(monkeypatch, tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    state_path = tmp_path / "gui_state.json"
    state_path.write_text(
        json.dumps({"special_piece_mode": bot.SPECIAL_PIECE_MODE_KNIGHTS}),
        encoding="utf-8",
    )
    monkeypatch.setattr(bot, "GUI_STATE_PATH", state_path)

    window = QtWidgets.QMainWindow()
    ui = bot.Ui_MainWindow()
    ui.setupUi(window)
    bot._set_combo_data(ui.BoosterActionBox, bot.BOOSTER_ACTION_HIGH_VOLTAGE)

    ui.load_gui_state()

    assert ui.BoosterActionBox.currentData() == bot.BOOSTER_ACTION_NONE
```

Update `test_auto_scan_request_includes_selected_ml_recognition_mode`:

```python
    request = ui._build_auto_scan_request()

    assert request.ml_recognition_mode == bot.ML_RECOGNITION_HYBRID
    assert request.special_piece_mode == bot.SPECIAL_PIECE_MODE_AUTO
```

Add a request construction test near `test_build_check_best_move_request_includes_ml_recognition_mode`:

```python
def test_build_check_best_move_request_uses_auto_recognition_and_selected_booster_action(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = QtWidgets.QMainWindow()
    ui = bot.Ui_MainWindow()
    ui.setupUi(window)
    monkeypatch.setattr(bot.pyautogui, "position", lambda: (10, 20))
    bot._set_combo_data(ui.BoosterActionBox, bot.BOOSTER_ACTION_HIGH_VOLTAGE)

    request = ui._build_check_best_move_request()

    assert request.special_piece_mode == bot.SPECIAL_PIECE_MODE_AUTO
    assert request.booster_action_mode == bot.BOOSTER_ACTION_HIGH_VOLTAGE
```

Remove or update direct uses of `ui.SpecialPieceBox` in `tests/test_move_debug.py`. The two existing lines that set it to `SPECIAL_PIECE_MODE_AUTO` can be deleted because auto recognition is now the default request behavior.

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_move_debug.py -q`

Expected: FAIL because `BoosterActionBox` and `booster_action_mode` GUI state do not exist yet.

- [x] **Step 3: Implement production change**

Update imports in `gui.py`:

```python
from recognition import GAME_MODE_OPTIONS, SPECIAL_PIECE_MODE_AUTO, normalize_special_piece_mode
from runtime import (
    AUTO_POST_MOVE_COOLDOWN_SECONDS,
    AUTO_SCAN_INTERVAL_MS,
    BOOSTER_ACTION_NONE,
    BOOSTER_ACTION_OPTIONS,
    BOOSTER_MAX_CHARGE,
    LIVE_LOOKAHEAD_BEAM_WIDTH,
    LIVE_LOOKAHEAD_CANDIDATES,
    LIVE_LOOKAHEAD_DEPTH,
    PERK_NONE,
    PERK_OPTIONS,
    CheckBestMoveRequest,
    CheckBestMoveResult,
    AutoMoveStability,
    normalize_booster_action_mode,
    run_check_best_move_request,
)
```

Replace the old `SpecialPieceBox` widget block in `setupUi(...)` with:

```python
        self.BoosterActionBox = QtWidgets.QComboBox(self.centralwidget)
        self.BoosterActionBox.setGeometry(QtCore.QRect(330, 60, 151, 31))
        self.BoosterActionBox.setFont(square_font)
        self.BoosterActionBox.setObjectName("BoosterActionBox")
        for label, value in BOOSTER_ACTION_OPTIONS:
            self.BoosterActionBox.addItem("")
            self.BoosterActionBox.setItemData(self.BoosterActionBox.count() - 1, value)
```

Replace the old translation loop for `SPECIAL_PIECE_MODE_OPTIONS` with:

```python
        for index, (label, _value) in enumerate(BOOSTER_ACTION_OPTIONS):
            self.BoosterActionBox.setItemText(index, _translate("MainWindow", label))
```

Update `gui_state_payload(...)`:

```python
            "booster_action_mode": self.selected_booster_action_mode(),
```

Do not write `"special_piece_mode"` from the GUI payload after this change.

Add a helper near `selected_booster_charge(...)`:

```python
    def selected_booster_action_mode(self):
        return normalize_booster_action_mode(
            self.BoosterActionBox.currentData() or BOOSTER_ACTION_NONE
        )
```

Update `load_gui_state(...)` to load the new key and migrate old state:

```python
        _set_combo_data(
            self.BoosterActionBox,
            normalize_booster_action_mode(
                payload.get("booster_action_mode", payload.get("special_piece_mode"))
            ),
        )
```

Remove the old `_set_combo_data(self.SpecialPieceBox, payload.get("special_piece_mode"))` line.

Update `_capture_auto_state_read(...)`:

```python
            special_piece_mode=SPECIAL_PIECE_MODE_AUTO,
```

Update `_build_auto_scan_request(...)`:

```python
        return AutoScanRequest(
            mode=self.ModeBox.currentData() or self.ModeBox.currentText(),
            special_piece_mode=SPECIAL_PIECE_MODE_AUTO,
            selected_profile=self.BoardSizeBox.currentData() or DEFAULT_PROFILE,
            ml_recognition_mode=self.MLRecognitionModeBox.currentData() or ML_RECOGNITION_OFF,
        )
```

Update `_build_check_best_move_request(...)`:

```python
            special_piece_mode=SPECIAL_PIECE_MODE_AUTO,
            booster_action_mode=self.selected_booster_action_mode(),
```

Keep `normalize_special_piece_mode(...)` imported if another current path still uses it; remove it only after `rg -n "normalize_special_piece_mode" gui.py` shows no remaining use.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_move_debug.py -q`

Expected: PASS for GUI state/request tests.

- [x] **Step 5: Scope check**

Run: `rg -n "SpecialPieceBox|SPECIAL_PIECE_MODE_OPTIONS|booster_action_mode|BoosterActionBox" gui.py tests/test_move_debug.py`

Expected: `SpecialPieceBox` and `SPECIAL_PIECE_MODE_OPTIONS` no longer appear in `gui.py`; `BoosterActionBox` and `booster_action_mode` appear in GUI tests and request construction. Do not run git commit in this checkout.

## Task 3: Gate Booster Execution and Debug Output by Booster Action Mode

**Files:**
- Modify: `runtime.py`
- Test: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:** GUI widget changes or High Voltage scoring. This task changes only runtime branching and debug serialization.

- [x] **Step 1: Write failing tests**

Add these tests to `tests/test_move_debug.py` near the existing active-booster runtime tests:

```python
def test_run_check_best_move_request_plain_booster_action_skips_high_voltage_flow(monkeypatch, isolated_runtime_bot):
    bot = isolated_runtime_bot
    board = [[1, 2], [3, 4]]
    special_board = [[0, 0], [0, 0]]
    booster_clicks = []
    normal = MoveEvaluation(
        candidate=MoveCandidate((0, 0), (0, 1), Direction.RIGHT, [], []),
        score=50.0,
        instant_score=50.0,
        special_bonus=0.0,
        blue_bonus=0.0,
        mode_bonus=0.0,
        extra_move_bonus=0.0,
        disco_move_bonus=0.0,
        extra_moves=0.0,
        disco_moves=0.0,
        cascade_count=0.0,
        board_potential=0.0,
        lookahead_bonus=0.0,
        explanation="normal",
    )

    monkeypatch.setattr(bot, "rank_moves", lambda *args, **kwargs: [normal])
    monkeypatch.setattr(bot, "prioritize_ranked_moves", lambda ranked, **kwargs: ranked)
    monkeypatch.setattr(bot, "detect_booster_activate", lambda _path: {"active": True, "score": 1.0})
    monkeypatch.setattr(
        bot,
        "choose_high_voltage_target",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("High Voltage target should not run")),
    )
    monkeypatch.setattr(bot, "write_move_debug_report", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        bot,
        "click_booster_activate",
        lambda *args, **kwargs: booster_clicks.append((args, kwargs)),
    )

    result = bot.run_check_best_move_request(
        bot.CheckBestMoveRequest(
            mode=bot.normalize_game_mode(None),
            special_piece_mode=bot.SPECIAL_PIECE_MODE_HIGH_VOLTAGE,
            booster_action_mode=bot.BOOSTER_ACTION_NONE,
            selected_profile="regular",
            allow_square_matches=True,
            specials_explode_immediately=False,
            score_rally_values=None,
            selected_perks=(bot.PERK_NONE, bot.PERK_NONE),
            cursor_return_position=(10, 20),
            pre_scanned_board=board,
            pre_scanned_special_board=special_board,
            debug_enabled=False,
        )
    )

    assert result.best_move_text == "Booster: activate"
    assert len(booster_clicks) == 1


def test_run_check_best_move_request_high_voltage_action_uses_target_flow_with_auto_recognition(monkeypatch, isolated_runtime_bot):
    bot = isolated_runtime_bot
    board = [[1, 2], [3, 4]]
    special_board = [[0, 0], [0, 0]]
    activated = []
    normal = MoveEvaluation(
        candidate=MoveCandidate((0, 0), (0, 1), Direction.RIGHT, [], []),
        score=50.0,
        instant_score=50.0,
        special_bonus=0.0,
        blue_bonus=0.0,
        mode_bonus=0.0,
        extra_move_bonus=0.0,
        disco_move_bonus=0.0,
        extra_moves=0.0,
        disco_moves=0.0,
        cascade_count=0.0,
        board_potential=0.0,
        lookahead_bonus=0.0,
        explanation="normal",
    )
    target = HighVoltageTargetEvaluation(
        target_cell=(1, 1),
        target_color=2,
        score=42.0,
        instant_score=40.0,
        special_bonus=0.0,
        blue_bonus=0.0,
        mode_bonus=0.0,
        extra_move_bonus=0.0,
        cleared_cells=8.0,
        blue_cells=0.0,
        activated_specials=0.0,
        extra_moves=0.0,
        cascade_count=0.0,
        mode_targets=0.0,
        chest_drops=0.0,
        multiplier_mushrooms=0.0,
        board_potential=2.0,
        explanation="instant=40.0",
    )

    monkeypatch.setattr(bot, "rank_moves", lambda *args, **kwargs: [normal])
    monkeypatch.setattr(bot, "prioritize_ranked_moves", lambda ranked, **kwargs: ranked)
    monkeypatch.setattr(bot, "detect_booster_activate", lambda _path: {"active": True, "score": 1.0})
    monkeypatch.setattr(bot, "choose_high_voltage_target", lambda *args, **kwargs: target)
    monkeypatch.setattr(bot, "write_move_debug_report", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        bot,
        "activate_high_voltage_booster",
        lambda detection, target_cell, return_position=None: activated.append(
            (detection, target_cell, return_position)
        ),
    )

    result = bot.run_check_best_move_request(
        bot.CheckBestMoveRequest(
            mode=bot.normalize_game_mode(None),
            special_piece_mode=bot.SPECIAL_PIECE_MODE_AUTO,
            booster_action_mode=bot.BOOSTER_ACTION_HIGH_VOLTAGE,
            selected_profile="regular",
            allow_square_matches=True,
            specials_explode_immediately=False,
            score_rally_values=None,
            selected_perks=(bot.PERK_NONE, bot.PERK_NONE),
            cursor_return_position=(10, 20),
            pre_scanned_board=board,
            pre_scanned_special_board=special_board,
            debug_enabled=False,
        )
    )

    assert result.best_move_text == "High Voltage: (1, 1)"
    assert activated == [({"active": True, "score": 1.0, "latched": False}, (1, 1), (10, 20))]
```

Update `test_write_move_debug_report_copies_board_score_and_candidates` with:

```python
        booster_action_mode=bot.BOOSTER_ACTION_HIGH_VOLTAGE,
```

and assert after `move["special_piece_mode"]`:

```python
    assert move["booster_action_mode"] == bot.BOOSTER_ACTION_HIGH_VOLTAGE
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_move_debug.py -q`

Expected: FAIL because runtime still branches on `recognition.special_piece_mode` for High Voltage and `move.json` does not include `booster_action_mode`.

- [x] **Step 3: Implement production change**

In `run_check_best_move_request(...)`, normalize the action mode after `selected_perks` is resolved:

```python
    booster_action_mode = normalize_booster_action_mode(request.booster_action_mode)
```

Update the console output:

```python
    print("Recognition:", SPECIAL_PIECE_MODE_LABELS[recognition.special_piece_mode])
    print("Booster action:", BOOSTER_ACTION_LABELS[booster_action_mode])
```

Replace the latch call:

```python
            booster_detection = apply_booster_ready_latch(
                booster_detection,
                booster_action_mode,
            )
```

Replace the High Voltage target-selection gate:

```python
            if selected_action == "activate_booster" and booster_action_mode == BOOSTER_ACTION_HIGH_VOLTAGE:
                high_voltage_target = choose_high_voltage_target(
                    game_board,
                    special_game_board,
                    mode=recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    include_future_value=request.include_future_value,
                    explode_created_specials_immediately=specials_explode_immediately,
                )
                if high_voltage_target is None:
                    selected_action = "none"
```

Pass the action mode to the debug writer call:

```python
            booster_action_mode=booster_action_mode,
```

Replace the activation branch:

```python
    if selected_action == "activate_booster":
        if booster_action_mode == BOOSTER_ACTION_HIGH_VOLTAGE:
            print(
                "High Voltage bira:",
                high_voltage_target.target_cell,
                "boja",
                high_voltage_target.target_color,
            )
            print("Detalji:", high_voltage_target.explanation)
            activate_high_voltage_booster(
                booster_detection,
                high_voltage_target.target_cell,
                return_position=cursor_return_position,
            )
            clear_booster_ready_latch()
            log_phase_timings()
            return CheckBestMoveResult(
                best_move_text=f"High Voltage: {high_voltage_target.target_cell}",
                score_text="Score: " + str(round(high_voltage_target.score, 2)),
                auto_signature=request.auto_signature,
            )
        print("Booster je aktivan i nema pravog extra move poteza. Aktiviram booster.")
        click_booster_activate(
            booster_detection,
            return_position=cursor_return_position,
        )
```

Update `write_move_debug_report(...)` signature:

```python
    booster_action_mode=BOOSTER_ACTION_NONE,
```

Add this field to `move_payload` after `special_piece_mode`:

```python
        "booster_action_mode": normalize_booster_action_mode(booster_action_mode),
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_move_debug.py -q`

Expected: PASS.

- [x] **Step 5: Scope check**

Run: `rg -n "SPECIAL_PIECE_MODE_HIGH_VOLTAGE|booster_action_mode|BOOSTER_ACTION_HIGH_VOLTAGE|will_click_high_voltage_target" runtime.py tests/test_move_debug.py`

Expected: High Voltage runtime branching in `runtime.py` uses `booster_action_mode`; old recognition constants remain for recognition compatibility. Do not run git commit in this checkout.

## Task 4: Final Verification and Scope Audit

**Files:**
- Modify: none unless verification exposes a failing assertion from Tasks 1-3
- Test: full test suite

**Security flag:** `none`

**Does NOT cover:** Feature expansion, model retraining, or live BlueStacks gameplay.

- [x] **Step 1: Run focused booster tests**

Run: `python -m pytest tests/test_booster_activation.py -q`

Expected: PASS.

- [x] **Step 2: Run focused GUI/runtime debug tests**

Run: `python -m pytest tests/test_move_debug.py -q`

Expected: PASS.

- [x] **Step 3: Run recognition compatibility tests**

Run: `python -m pytest tests/test_special_detection.py -q`

Expected: PASS. Old `SPECIAL_PIECE_MODE_*` constants and template fallback behavior should still be covered.

- [x] **Step 4: Run full suite**

Run: `python -m pytest -q`

Expected: PASS.

- [x] **Step 5: Compile changed runtime modules**

Run: `python -m py_compile recognition.py runtime.py gui.py test.py`

Expected: PASS with no output.

- [x] **Step 6: Scope audit**

Run:

```powershell
rg -n "SpecialPieceBox|Booster: Srca|Booster: Konji|Booster: Cleo|Booster: Billie" gui.py tests/test_move_debug.py
rg -n "booster_action_mode|BOOSTER_ACTION|normalize_booster_action_mode" runtime.py gui.py tests/test_booster_activation.py tests/test_move_debug.py
rg -n "SPECIAL_PIECE_MODE_OPTIONS|normalize_special_piece_mode|SPECIAL_PIECE_MODE_HIGH_VOLTAGE" recognition.py tests/test_special_detection.py
```

Expected:
- No old figure-family UI strings remain in `gui.py`.
- `booster_action_mode` appears in runtime, GUI state/request tests, and `move.json` debug tests.
- Recognition constants remain in `recognition.py` and recognition tests.

Manual live check after automated verification:
- Run `python test.py`.
- Select `ML only`.
- Confirm the visible booster selector contains only `Bez posebne akcije` and `High Voltage`.
- With `Bez posebne akcije`, a ready booster clicks only Activate.
- With `High Voltage`, a ready booster clicks Activate, waits, then clicks the selected target tile.
- Confirm ordinary moves still use ML-recognized pieces without manual figure-family selection.
