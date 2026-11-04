# Recognition Dataset Builder & Labeling UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:subagent-driven-development (recommended) or superpowers-optimized:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline PyQt5 tool that turns `Debug/runs/` snapshots into an auditable, hand-reviewed per-cell tile dataset suitable for downstream CNN training.

**Architecture:** Five new modules under the project root (`dataset_classes.py`, `dataset_manifest.py`, `dataset_scanner.py`, `dataset_review_ui.py`, `dataset_cli.py`) plus pytest coverage in `tests/`. The scanner slices each `board.png` into per-cell crops using the board's `boardSize` (derived from `move.json["board"]` shape) and writes them to `data/recognition_dataset/crops/`, with a single `manifest.json` keyed by `crop_id`. A PyQt5 review window walks runs one at a time, displays the board with overlaid grid + labels, and lets the user confirm or correct each cell. Manifest writes are atomic and incremental so a crash never loses work.

**Tech Stack:** Python 3, PyQt5 (already a project dependency), NumPy, OpenCV, PIL, pytest.

**Assumptions:**
- Workspace is **not** a git repository. The plan therefore contains no `git add` / `git commit` steps — verification is purely via running tests and inspecting files. Will NOT work if the user later requires git checkpoints; in that case append commit steps per task.
- Pre-existing test suite (415 tests) must still pass at the end. Will NOT work if any change leaks into `recognition.py`, `runtime.py`, `gui.py`, `move_strategy.py`, `board_profiles.py`, or any other runtime module. This sub-project is strictly additive; runtime code stays frozen.
- `Debug/runs/<run_id>/board.png` is the pre-move board crop and matches `move.json["board"]`. Will NOT work for `after_board.png` — out of scope.
- `boardSize` is reliably derivable from `len(move.json["board"])` (7 for regular, 8 for supersize). Will NOT work if `move.json["board"]` is malformed or non-square; such runs are reported as rejected and skipped.
- PyQt5 is importable in the active Python environment (it is already used by `test.py` and `gui.py`).

---

## Required Spec Context (self-contained for fresh sessions)

This plan implements the design at [docs/specs/2026-05-24-recognition-dataset-builder-design.md](../specs/2026-05-24-recognition-dataset-builder-design.md). Key spec facts repeated here so a fresh agent does not need to read the spec to execute:

### Goal in plain language

The bot saves a debug snapshot per move under `Debug/runs/<timestamp>/`. Each snapshot contains `board.png` (the cropped pre-move board image) and `move.json` (with arrays `board[i][j]` = base color code 1–6 and `special_board[i][j]` = special-piece type code). After many gameplay sessions, ~58+ such snapshots exist. We need a tool that:

1. Slices each `board.png` into N×N per-cell crops (N = 7 or 8 depending on profile).
2. Auto-labels each crop using `move.json` arrays.
3. Lets a human review and correct labels in a PyQt5 UI.
4. Writes a fully audited dataset at `data/recognition_dataset/`.

Sub-projects B (CNN training) and C (feature-flagged runtime ML path) consume the output but are **not** part of this plan.

### Color and special code reference (from `move_strategy.py`)

```
BLOCKED = -1
BLUE = 1, GREEN = 2, YELLOW = 3, PURPLE = 4, RED = 5, ORANGE = 6, WHITE = 7

SPECIAL_HORIZONTAL = 1
SPECIAL_VERTICAL = 2
SPECIAL_BOMB = 3
SPECIAL_LIGHTNING = 4
SPECIAL_MODE_TARGET = 9
SPECIAL_HEART = 11
SPECIAL_KNIGHT = 12
SPECIAL_CLEO_BUG = 13
SPECIAL_BILLIE_DRONE = 14
SPECIAL_COLOR_CRYSTAL = 15
SPECIAL_DISCO_BALL = 16
SPECIAL_MUSHROOM = 17
SPECIAL_ALL_ABOARD_BANDIT = 18
SPECIAL_JOOJOO_SKULL = 19
```

### Class taxonomy

- **Color-agnostic specials** (label uses the special name only, ignoring the color value in `move.json`):
  - `SPECIAL_DISCO_BALL` → `"disco_ball"`
  - `SPECIAL_CLEO_BUG` → `"cleo_bug"` (bot writes `board[i][j] = 1` for these, but graphic is color-agnostic)
  - `SPECIAL_BILLIE_DRONE` → `"billie_drone"`
  - `SPECIAL_MODE_TARGET` → `"mode_target"`
- **Color-bound specials** (label is `"<color>_<suffix>"`):
  - special `0` → suffix `"normal"`
  - `SPECIAL_HORIZONTAL` → `"horizontal"`
  - `SPECIAL_VERTICAL` → `"vertical"`
  - `SPECIAL_BOMB` → `"bomb"`
  - `SPECIAL_LIGHTNING` → `"lightning"`
  - `SPECIAL_HEART` → `"heart"`
  - `SPECIAL_KNIGHT` → `"knight"`
  - `SPECIAL_MUSHROOM` → `"mushroom"`
  - `SPECIAL_COLOR_CRYSTAL` → `"color_crystal"`
  - `SPECIAL_ALL_ABOARD_BANDIT` → `"all_aboard_bandit"`
  - `SPECIAL_JOOJOO_SKULL` → `"joojoo_skull"`
- **Structural classes:**
  - `board[i][j] == BLOCKED` (-1) → `"blocked"`
  - `board[i][j] == 0` (recognizer returned nothing) → `"empty"`

Color name mapping: `1→"blue", 2→"green", 3→"yellow", 4→"purple", 5→"red", 6→"orange", 7→"white"`.

### Storage layout

```
data/recognition_dataset/
  crops/
    <run_id>__r<row>_c<col>.png    # e.g., 2026-05-24_10-12-28_905__r2_c3.png
  manifest.json                    # list of entries, one per crop
  classes.json                     # snapshot of valid class names
```

### Manifest entry schema

```json
{
  "crop_id": "2026-05-24_10-12-28_905__r2_c3",
  "source_run": "2026-05-24_10-12-28_905",
  "row": 2,
  "col": 3,
  "profile": "regular",
  "original_size": [84, 84],
  "auto_class": "red_normal",
  "current_class": "red_normal",
  "reviewed": false,
  "corrected": false,
  "first_seen_at": "2026-05-24T14:30:00",
  "last_reviewed_at": null
}
```

### Mandatory review discipline (critical mitigation)

The bot's auto-labels are ~95% accurate. To prevent the user from skim-confirming and poisoning the training set, every cell starts `reviewed=false` and requires an explicit Confirm or Fix click. The "by-run" view tracks reviewed/total per run. `dataset_cli stats --require-fully-reviewed` exits non-zero if any cell is unreviewed — Sub-project B will gate on this.

---

## Scope Boundaries

**In scope:** Five new modules + tests + manual UI acceptance.

**Out of scope (no edits permitted):** `recognition.py`, `runtime.py`, `gui.py`, `test.py`, `move_strategy.py`, `board_profiles.py`, `capture.py`, `screen_state_reader.py`, anything under `assets/`, any existing test.

---

## File Structure

| Path | Responsibility |
|---|---|
| `dataset_classes.py` | Canonical class names (`ALL_CLASSES` frozenset) + `classify(color, special) -> str` + color/special code constants imported from `move_strategy`. Pure module, no I/O. |
| `dataset_manifest.py` | `ManifestEntry` dataclass + `load_manifest(path)` + `save_manifest(path, entries)` with atomic `.tmp` + replace. Pure I/O wrapper, no business logic. |
| `dataset_scanner.py` | `scan_debug_runs(debug_root, dataset_root) -> ScanReport` — walks Debug/runs/, slices `board.png`, auto-labels via `dataset_classes.classify`, writes crops + updates manifest. Idempotent. |
| `dataset_review_ui.py` | PyQt5 `MainWindow` showing one run at a time with overlaid grid, click-to-select, class dropdown, Confirm/Fix actions, keyboard shortcuts. Writes manifest on every user action. |
| `dataset_cli.py` | Three subcommands: `scan`, `stats`, `review`. Entrypoint via `python -m dataset_cli`. |
| `tests/test_dataset_classes.py` | Unit tests for `classify()` covering every color×special branch, BLOCKED, empty, unknown codes. |
| `tests/test_dataset_manifest.py` | Tests for load/save, atomic write, corrupt `.tmp` recovery, dedup-by-crop_id. |
| `tests/test_dataset_scanner.py` | Integration test: fixture run on disk, scanner produces expected crops + manifest entries. |
| `tests/fixtures/dataset/fake_run_001/board.png` | 588×588 synthetic 7×7 board (84-px cells) for scanner test. |
| `tests/fixtures/dataset/fake_run_001/move.json` | Hand-crafted `move.json` matching the fixture. |

---

## Task Order

Tasks 1–2 are foundational and independent. Tasks 3–6 depend on the chain: scanner → CLI scan/stats → UI → CLI review.

---

### Task 1: Class taxonomy module + tests

**Files:**
- Create: `dataset_classes.py`
- Create: `tests/test_dataset_classes.py`

**Security flag:** `none`

**Does NOT cover:** Future class additions for hypothetical new specials. Only the special codes currently defined in `move_strategy.py` are mapped. Adding a new special there without updating `dataset_classes.py` will raise `ValueError` from `classify()` — that's intentional, so the dataset never silently swallows unknown labels.

- [x] **Step 1: Write failing test**

Create `tests/test_dataset_classes.py`:

```python
import pytest
from dataset_classes import classify, ALL_CLASSES


def test_normal_color_classes():
    assert classify(1, 0) == "blue_normal"
    assert classify(2, 0) == "green_normal"
    assert classify(3, 0) == "yellow_normal"
    assert classify(4, 0) == "purple_normal"
    assert classify(5, 0) == "red_normal"
    assert classify(6, 0) == "orange_normal"


def test_color_bound_specials():
    assert classify(1, 1) == "blue_horizontal"
    assert classify(5, 3) == "red_bomb"
    assert classify(2, 11) == "green_heart"
    assert classify(6, 12) == "orange_knight"
    assert classify(4, 17) == "purple_mushroom"
    assert classify(3, 15) == "yellow_color_crystal"
    assert classify(6, 18) == "orange_all_aboard_bandit"
    assert classify(5, 19) == "red_joojoo_skull"


def test_color_agnostic_specials_ignore_color():
    # disco ball, cleo bug, billie drone, mode target are color-agnostic;
    # whatever color the bot wrote is ignored
    assert classify(1, 16) == "disco_ball"
    assert classify(5, 16) == "disco_ball"
    assert classify(1, 13) == "cleo_bug"
    assert classify(0, 13) == "cleo_bug"
    assert classify(1, 14) == "billie_drone"
    assert classify(7, 9) == "mode_target"


def test_structural_classes():
    assert classify(-1, 0) == "blocked"
    assert classify(-1, 5) == "blocked"  # BLOCKED beats any special
    assert classify(0, 0) == "empty"


def test_unknown_codes_raise():
    with pytest.raises(ValueError):
        classify(99, 0)  # unknown color
    with pytest.raises(ValueError):
        classify(1, 7)  # unknown special code (7 is not defined)


def test_all_classes_includes_expected_members():
    expected_members = {
        "blue_normal", "red_bomb", "orange_horizontal", "purple_lightning",
        "green_heart", "yellow_knight", "blue_mushroom", "red_color_crystal",
        "blue_all_aboard_bandit", "red_joojoo_skull",
        "disco_ball", "cleo_bug", "billie_drone", "mode_target",
        "blocked", "empty",
    }
    missing = expected_members - ALL_CLASSES
    assert missing == set(), f"missing classes: {missing}"


def test_all_classes_is_frozenset():
    assert isinstance(ALL_CLASSES, frozenset)
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dataset_classes.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'dataset_classes'`.

- [x] **Step 3: Implement minimal change**

Create `dataset_classes.py`:

```python
"""Canonical class taxonomy for the recognition dataset.

A class identifier is a string. The full set of valid identifiers is exposed as
ALL_CLASSES (frozenset). The classify() function maps a (color, special) pair
as written into move.json by the bot into the canonical class name.
"""
from move_strategy import (
    BLOCKED,
    BLUE,
    GREEN,
    YELLOW,
    PURPLE,
    RED,
    ORANGE,
    WHITE,
    SPECIAL_HORIZONTAL,
    SPECIAL_VERTICAL,
    SPECIAL_BOMB,
    SPECIAL_LIGHTNING,
    SPECIAL_MODE_TARGET,
    SPECIAL_HEART,
    SPECIAL_KNIGHT,
    SPECIAL_CLEO_BUG,
    SPECIAL_BILLIE_DRONE,
    SPECIAL_COLOR_CRYSTAL,
    SPECIAL_DISCO_BALL,
    SPECIAL_MUSHROOM,
    SPECIAL_ALL_ABOARD_BANDIT,
    SPECIAL_JOOJOO_SKULL,
)

_COLOR_NAMES = {
    BLUE: "blue",
    GREEN: "green",
    YELLOW: "yellow",
    PURPLE: "purple",
    RED: "red",
    ORANGE: "orange",
    WHITE: "white",
}

_COLOR_AGNOSTIC_SPECIALS = {
    SPECIAL_DISCO_BALL: "disco_ball",
    SPECIAL_CLEO_BUG: "cleo_bug",
    SPECIAL_BILLIE_DRONE: "billie_drone",
    SPECIAL_MODE_TARGET: "mode_target",
}

_COLOR_BOUND_SUFFIX = {
    0: "normal",
    SPECIAL_HORIZONTAL: "horizontal",
    SPECIAL_VERTICAL: "vertical",
    SPECIAL_BOMB: "bomb",
    SPECIAL_LIGHTNING: "lightning",
    SPECIAL_HEART: "heart",
    SPECIAL_KNIGHT: "knight",
    SPECIAL_MUSHROOM: "mushroom",
    SPECIAL_COLOR_CRYSTAL: "color_crystal",
    SPECIAL_ALL_ABOARD_BANDIT: "all_aboard_bandit",
    SPECIAL_JOOJOO_SKULL: "joojoo_skull",
}


def _build_all_classes() -> frozenset:
    classes = {"blocked", "empty"}
    classes.update(_COLOR_AGNOSTIC_SPECIALS.values())
    for color_name in _COLOR_NAMES.values():
        for suffix in _COLOR_BOUND_SUFFIX.values():
            classes.add(f"{color_name}_{suffix}")
    return frozenset(classes)


ALL_CLASSES: frozenset = _build_all_classes()


def classify(color: int, special: int) -> str:
    """Map (color, special) from move.json to a canonical class name."""
    if color == BLOCKED:
        return "blocked"
    if color == 0 and special == 0:
        return "empty"
    if special in _COLOR_AGNOSTIC_SPECIALS:
        return _COLOR_AGNOSTIC_SPECIALS[special]
    suffix = _COLOR_BOUND_SUFFIX.get(special)
    if suffix is None:
        raise ValueError(f"Unknown special code: {special}")
    color_name = _COLOR_NAMES.get(color)
    if color_name is None:
        raise ValueError(f"Unknown color code: {color}")
    return f"{color_name}_{suffix}"
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dataset_classes.py -q`

Expected: PASS (7 tests).

- [x] **Step 5: Regression check**

Run: `python -m pytest -q`

Expected: All 415 existing tests + 7 new tests pass (422 total).

---

### Task 2: Manifest module + tests

**Files:**
- Create: `dataset_manifest.py`
- Create: `tests/test_dataset_manifest.py`

**Security flag:** `none`

**Does NOT cover:** Multi-process safety (only one writer assumed). Migration of older manifest versions to newer schemas — `version` field is recorded but `load_manifest` raises on mismatch. The unsupported-version path is exercised in the test for `test_load_rejects_unknown_version`.

- [x] **Step 1: Write failing test**

Create `tests/test_dataset_manifest.py`:

```python
import json
from pathlib import Path

import pytest

from dataset_manifest import (
    ManifestEntry,
    MANIFEST_VERSION,
    load_manifest,
    save_manifest,
)


def _sample_entry(crop_id="r1__r0_c0", auto="blue_normal"):
    return ManifestEntry(
        crop_id=crop_id,
        source_run="r1",
        row=0,
        col=0,
        profile="regular",
        original_size=(84, 84),
        auto_class=auto,
        current_class=auto,
        reviewed=False,
        corrected=False,
        first_seen_at="2026-05-24T10:00:00",
        last_reviewed_at=None,
    )


def test_save_and_load_roundtrip(tmp_path: Path):
    path = tmp_path / "manifest.json"
    save_manifest(path, [_sample_entry("a"), _sample_entry("b")])
    loaded = load_manifest(path)
    assert len(loaded) == 2
    assert loaded[0].crop_id == "a"
    assert loaded[1].crop_id == "b"
    assert loaded[0].profile == "regular"
    assert loaded[0].original_size == (84, 84)


def test_load_missing_file_returns_empty(tmp_path: Path):
    assert load_manifest(tmp_path / "does_not_exist.json") == []


def test_save_writes_atomically(tmp_path: Path, monkeypatch):
    """If write to .tmp fails midway, manifest.json must remain untouched."""
    path = tmp_path / "manifest.json"
    save_manifest(path, [_sample_entry("first")])
    original_contents = path.read_text(encoding="utf-8")

    # Simulate failure during the tmp-file write
    real_open = open

    def boom(file, *args, **kwargs):
        if str(file).endswith(".tmp"):
            raise IOError("disk full")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", boom)
    with pytest.raises(IOError):
        save_manifest(path, [_sample_entry("second")])

    monkeypatch.setattr("builtins.open", real_open)
    assert path.read_text(encoding="utf-8") == original_contents
    assert load_manifest(path)[0].crop_id == "first"


def test_orphan_tmp_does_not_block_load(tmp_path: Path):
    path = tmp_path / "manifest.json"
    save_manifest(path, [_sample_entry("ok")])
    (tmp_path / "manifest.json.tmp").write_text("garbage{", encoding="utf-8")
    loaded = load_manifest(path)
    assert len(loaded) == 1
    assert loaded[0].crop_id == "ok"


def test_load_rejects_unknown_version(tmp_path: Path):
    path = tmp_path / "manifest.json"
    payload = {"version": MANIFEST_VERSION + 99, "entries": []}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(path)


def test_dedup_by_crop_id_during_save(tmp_path: Path):
    """Two entries with the same crop_id collapse to one (last wins)."""
    path = tmp_path / "manifest.json"
    entries = [
        _sample_entry("dup", auto="blue_normal"),
        _sample_entry("dup", auto="red_normal"),
    ]
    save_manifest(path, entries)
    loaded = load_manifest(path)
    assert len(loaded) == 1
    assert loaded[0].auto_class == "red_normal"
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dataset_manifest.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'dataset_manifest'`.

- [x] **Step 3: Implement minimal change**

Create `dataset_manifest.py`:

```python
"""Manifest I/O for the recognition dataset.

The manifest is a single JSON file at <dataset_root>/manifest.json containing a
list of ManifestEntry records keyed by crop_id. Writes use a .tmp + os.replace
pattern so a crash mid-write never corrupts the existing manifest.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

MANIFEST_VERSION = 1


@dataclass
class ManifestEntry:
    crop_id: str
    source_run: str
    row: int
    col: int
    profile: str
    original_size: Tuple[int, int]
    auto_class: str
    current_class: str
    reviewed: bool
    corrected: bool
    first_seen_at: str
    last_reviewed_at: Optional[str]


def _entry_from_dict(d: dict) -> ManifestEntry:
    size = d["original_size"]
    return ManifestEntry(
        crop_id=d["crop_id"],
        source_run=d["source_run"],
        row=d["row"],
        col=d["col"],
        profile=d["profile"],
        original_size=(int(size[0]), int(size[1])),
        auto_class=d["auto_class"],
        current_class=d["current_class"],
        reviewed=d["reviewed"],
        corrected=d["corrected"],
        first_seen_at=d["first_seen_at"],
        last_reviewed_at=d.get("last_reviewed_at"),
    )


def load_manifest(path: Path) -> List[ManifestEntry]:
    path = Path(path)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != MANIFEST_VERSION:
        raise ValueError(
            f"Unsupported manifest version: {payload.get('version')!r} "
            f"(expected {MANIFEST_VERSION})"
        )
    return [_entry_from_dict(d) for d in payload.get("entries", [])]


def save_manifest(path: Path, entries: Iterable[ManifestEntry]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Dedup by crop_id, last-wins
    by_id: dict[str, ManifestEntry] = {}
    for entry in entries:
        by_id[entry.crop_id] = entry
    payload = {
        "version": MANIFEST_VERSION,
        "entries": [asdict(e) for e in by_id.values()],
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dataset_manifest.py -q`

Expected: PASS (6 tests).

- [x] **Step 5: Regression check**

Run: `python -m pytest -q`

Expected: All 415 existing + 7 from Task 1 + 6 new = 428 tests pass.

---

### Task 3: Scanner module + tests

**Files:**
- Create: `dataset_scanner.py`
- Create: `tests/test_dataset_scanner.py`
- (No physical fixture files committed; the test synthesizes them under `tmp_path`.)

**Security flag:** `none`

**Does NOT cover:** Modifying or reading `after_board.png`. Detecting when a run's `board.png` was captured under a different `squareSize` than the current `board_config.json` — the scanner trusts `board.png`'s pixel dimensions and `move.json["board"]`'s shape only.

- [x] **Step 1: Write failing test**

The fixture is a synthetic 588×588 board image with seven 84-px-wide rows of distinct solid-color cells. The matching `move.json` declares each cell's color and `special=0`. The test creates fixture files inside `tmp_path` at runtime, so no binary asset is committed and no directory pre-creation is needed.

Create `tests/test_dataset_scanner.py`:

```python
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from dataset_manifest import load_manifest
from dataset_scanner import scan_debug_runs

# Solid RGB colors used in the synthetic fixture (the scanner does not need to
# match these visually — it just slices the image into cells).
_RGB_PER_CODE = {
    1: (50, 50, 250),     # BLUE
    2: (50, 220, 50),     # GREEN
    3: (240, 230, 50),    # YELLOW
    4: (160, 50, 200),    # PURPLE
    5: (230, 40, 40),     # RED
    6: (240, 150, 40),    # ORANGE
}


def _build_fake_run(run_dir: Path, board_codes, square_size: int = 84) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    n = len(board_codes)
    img = np.zeros((n * square_size, n * square_size, 3), dtype=np.uint8)
    for i, row in enumerate(board_codes):
        for j, code in enumerate(row):
            color = _RGB_PER_CODE[code]
            img[
                i * square_size:(i + 1) * square_size,
                j * square_size:(j + 1) * square_size,
            ] = color
    Image.fromarray(img).save(run_dir / "board.png")

    special_board = [[0 for _ in range(n)] for _ in range(n)]
    move = {
        "board": board_codes,
        "special_board": special_board,
        "best_move": None,
    }
    (run_dir / "move.json").write_text(json.dumps(move), encoding="utf-8")


def test_scanner_creates_crops_and_manifest(tmp_path: Path):
    debug = tmp_path / "Debug" / "runs"
    dataset = tmp_path / "data" / "recognition_dataset"

    codes = [
        [1, 2, 3, 4, 5, 6, 1],
        [2, 3, 4, 5, 6, 1, 2],
        [3, 4, 5, 6, 1, 2, 3],
        [4, 5, 6, 1, 2, 3, 4],
        [5, 6, 1, 2, 3, 4, 5],
        [6, 1, 2, 3, 4, 5, 6],
        [1, 2, 3, 4, 5, 6, 1],
    ]
    _build_fake_run(debug / "fake_run_001", codes)

    report = scan_debug_runs(debug, dataset)

    assert report.runs_scanned == 1
    assert report.runs_rejected == []
    assert report.crops_added == 49
    assert (dataset / "crops" / "fake_run_001__r0_c0.png").exists()
    assert (dataset / "crops" / "fake_run_001__r6_c6.png").exists()
    assert (dataset / "classes.json").exists()
    snapshot = json.loads((dataset / "classes.json").read_text(encoding="utf-8"))
    assert "blue_normal" in snapshot["classes"]

    entries = load_manifest(dataset / "manifest.json")
    assert len(entries) == 49
    e00 = next(e for e in entries if e.crop_id == "fake_run_001__r0_c0")
    assert e00.auto_class == "blue_normal"
    assert e00.current_class == "blue_normal"
    assert e00.profile == "regular"
    assert e00.original_size == (84, 84)
    assert e00.reviewed is False
    assert e00.corrected is False


def test_scanner_is_idempotent(tmp_path: Path):
    debug = tmp_path / "Debug" / "runs"
    dataset = tmp_path / "data" / "recognition_dataset"
    _build_fake_run(debug / "fake_run_001", [[1, 2], [3, 4]])

    first = scan_debug_runs(debug, dataset)
    assert first.crops_added == 4

    # Mark one entry reviewed so we can confirm it survives a re-scan
    entries = load_manifest(dataset / "manifest.json")
    entries[0].reviewed = True
    entries[0].current_class = "red_bomb"
    entries[0].corrected = True
    from dataset_manifest import save_manifest
    save_manifest(dataset / "manifest.json", entries)

    second = scan_debug_runs(debug, dataset)
    assert second.crops_added == 0  # nothing new

    after = load_manifest(dataset / "manifest.json")
    preserved = next(e for e in after if e.crop_id == entries[0].crop_id)
    assert preserved.reviewed is True
    assert preserved.current_class == "red_bomb"
    assert preserved.corrected is True


def test_scanner_skips_run_missing_files(tmp_path: Path):
    debug = tmp_path / "Debug" / "runs"
    dataset = tmp_path / "data" / "recognition_dataset"

    (debug / "no_board").mkdir(parents=True)
    (debug / "no_board" / "move.json").write_text("{}", encoding="utf-8")

    (debug / "no_move").mkdir(parents=True)
    Image.fromarray(np.zeros((84, 84, 3), dtype=np.uint8)).save(
        debug / "no_move" / "board.png"
    )

    report = scan_debug_runs(debug, dataset)
    assert report.runs_scanned == 0
    assert {r["run_id"] for r in report.runs_rejected} == {"no_board", "no_move"}


def test_scanner_detects_supersize(tmp_path: Path):
    debug = tmp_path / "Debug" / "runs"
    dataset = tmp_path / "data" / "recognition_dataset"
    codes = [[1] * 8 for _ in range(8)]
    _build_fake_run(debug / "ss_run", codes, square_size=84)

    report = scan_debug_runs(debug, dataset)
    assert report.crops_added == 64
    entries = load_manifest(dataset / "manifest.json")
    profiles = {e.profile for e in entries}
    assert profiles == {"supersize"}
```

- [x] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_dataset_scanner.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'dataset_scanner'`.

- [x] **Step 4: Implement minimal change**

Create `dataset_scanner.py`:

```python
"""Scan Debug/runs/ and produce per-cell crops + manifest entries."""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import numpy as np
from PIL import Image

from dataset_classes import ALL_CLASSES, classify
from dataset_manifest import ManifestEntry, load_manifest, save_manifest


def _write_classes_snapshot(dataset_root: Path) -> None:
    """Snapshot the current ALL_CLASSES set into classes.json. Idempotent."""
    payload = {"classes": sorted(ALL_CLASSES)}
    out = dataset_root / "classes.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@dataclass
class ScanReport:
    runs_scanned: int = 0
    crops_added: int = 0
    crops_skipped_existing: int = 0
    runs_rejected: list = field(default_factory=list)


def _now_iso() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _profile_for_size(n: int) -> str:
    if n == 7:
        return "regular"
    if n == 8:
        return "supersize"
    return f"unknown_{n}"


def scan_debug_runs(debug_root: Path, dataset_root: Path) -> ScanReport:
    debug_root = Path(debug_root)
    dataset_root = Path(dataset_root)
    crops_dir = dataset_root / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_root / "manifest.json"

    _write_classes_snapshot(dataset_root)

    existing = {e.crop_id: e for e in load_manifest(manifest_path)}
    report = ScanReport()

    if not debug_root.exists():
        save_manifest(manifest_path, existing.values())
        return report

    for run_dir in sorted(p for p in debug_root.iterdir() if p.is_dir()):
        board_png = run_dir / "board.png"
        move_json = run_dir / "move.json"
        if not board_png.exists() or not move_json.exists():
            report.runs_rejected.append({
                "run_id": run_dir.name,
                "reason": "missing board.png or move.json",
            })
            continue

        try:
            move = json.loads(move_json.read_text(encoding="utf-8"))
            board = move.get("board")
            special = move.get("special_board")
            if not board or not isinstance(board, list):
                raise ValueError("missing board[][]")
            n = len(board)
            if n == 0 or any(len(row) != n for row in board):
                raise ValueError(f"non-square board: {n}")
            if special is None or len(special) != n or any(len(r) != n for r in special):
                raise ValueError("special_board shape mismatch")
        except Exception as exc:
            report.runs_rejected.append({"run_id": run_dir.name, "reason": str(exc)})
            continue

        img = Image.open(board_png).convert("RGB")
        w, h = img.size
        if w % n != 0 or h % n != 0 or w != h:
            report.runs_rejected.append({
                "run_id": run_dir.name,
                "reason": f"board.png {w}x{h} not divisible by {n}",
            })
            continue

        square = w // n
        arr = np.array(img)
        profile = _profile_for_size(n)
        report.runs_scanned += 1

        for i in range(n):
            for j in range(n):
                crop_id = f"{run_dir.name}__r{i}_c{j}"
                if crop_id in existing:
                    report.crops_skipped_existing += 1
                    continue
                cell = arr[i * square:(i + 1) * square, j * square:(j + 1) * square]
                crop_path = crops_dir / f"{crop_id}.png"
                Image.fromarray(cell).save(crop_path)

                color = int(board[i][j])
                spc = int(special[i][j])
                auto_class = classify(color, spc)
                entry = ManifestEntry(
                    crop_id=crop_id,
                    source_run=run_dir.name,
                    row=i,
                    col=j,
                    profile=profile,
                    original_size=(square, square),
                    auto_class=auto_class,
                    current_class=auto_class,
                    reviewed=False,
                    corrected=False,
                    first_seen_at=_now_iso(),
                    last_reviewed_at=None,
                )
                existing[crop_id] = entry
                report.crops_added += 1

    save_manifest(manifest_path, existing.values())
    return report
```

- [x] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_dataset_scanner.py -q`

Expected: PASS (4 tests).

- [x] **Step 6: Regression check**

Run: `python -m pytest -q`

Expected: 415 existing + 7 + 6 + 4 = 432 tests pass.

---

### Task 4: CLI module — `scan` and `stats` subcommands

**Files:**
- Create: `dataset_cli.py`
- Create: `tests/test_dataset_cli.py`

**Security flag:** `none`

**Does NOT cover:** The `review` subcommand (added in Task 6). Auto-running scan before stats. Network or remote dataset sources.

- [x] **Step 1: Write failing test**

Create `tests/test_dataset_cli.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from dataset_manifest import load_manifest


def _make_run(debug: Path, name: str, codes):
    run = debug / name
    run.mkdir(parents=True)
    n = len(codes)
    img = np.zeros((84 * n, 84 * n, 3), dtype=np.uint8)
    Image.fromarray(img).save(run / "board.png")
    (run / "move.json").write_text(
        json.dumps({"board": codes, "special_board": [[0] * n for _ in range(n)]}),
        encoding="utf-8",
    )


def _run_cli(args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "dataset_cli", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_cli_scan_subcommand(tmp_path: Path):
    debug = tmp_path / "Debug" / "runs"
    _make_run(debug, "r1", [[1, 2], [3, 4]])
    dataset = tmp_path / "data" / "recognition_dataset"

    result = _run_cli(
        ["scan", "--debug-root", str(debug), "--dataset-root", str(dataset)],
        cwd=Path(__file__).resolve().parents[1],
    )

    assert result.returncode == 0, result.stderr
    assert "crops_added=4" in result.stdout
    assert (dataset / "manifest.json").exists()


def test_cli_stats_subcommand(tmp_path: Path):
    debug = tmp_path / "Debug" / "runs"
    _make_run(debug, "r1", [[1, 2], [3, 4]])
    dataset = tmp_path / "data" / "recognition_dataset"

    _run_cli(
        ["scan", "--debug-root", str(debug), "--dataset-root", str(dataset)],
        cwd=Path(__file__).resolve().parents[1],
    )
    result = _run_cli(
        ["stats", "--dataset-root", str(dataset)],
        cwd=Path(__file__).resolve().parents[1],
    )

    assert result.returncode == 0, result.stderr
    assert "total=4" in result.stdout
    assert "reviewed=0" in result.stdout
    assert "blue_normal=1" in result.stdout


def test_cli_stats_require_fully_reviewed_exits_nonzero(tmp_path: Path):
    debug = tmp_path / "Debug" / "runs"
    _make_run(debug, "r1", [[1]])
    dataset = tmp_path / "data" / "recognition_dataset"

    _run_cli(
        ["scan", "--debug-root", str(debug), "--dataset-root", str(dataset)],
        cwd=Path(__file__).resolve().parents[1],
    )
    result = _run_cli(
        ["stats", "--dataset-root", str(dataset), "--require-fully-reviewed"],
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode != 0
    assert "unreviewed" in (result.stdout + result.stderr).lower()
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dataset_cli.py -q`

Expected: FAIL — module not found.

- [x] **Step 3: Implement minimal change**

Create `dataset_cli.py`:

```python
"""Command-line entry points for the recognition dataset tool.

Usage:
    python -m dataset_cli scan [--debug-root PATH] [--dataset-root PATH]
    python -m dataset_cli stats [--dataset-root PATH] [--require-fully-reviewed]
    python -m dataset_cli review [--dataset-root PATH]   # added in Task 6
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

from dataset_manifest import load_manifest
from dataset_scanner import scan_debug_runs

DEFAULT_DEBUG_ROOT = Path("Debug") / "runs"
DEFAULT_DATASET_ROOT = Path("data") / "recognition_dataset"


def _cmd_scan(args: argparse.Namespace) -> int:
    report = scan_debug_runs(Path(args.debug_root), Path(args.dataset_root))
    print(
        f"runs_scanned={report.runs_scanned} "
        f"crops_added={report.crops_added} "
        f"crops_skipped_existing={report.crops_skipped_existing} "
        f"runs_rejected={len(report.runs_rejected)}"
    )
    for r in report.runs_rejected:
        print(f"  REJECTED {r['run_id']}: {r['reason']}", file=sys.stderr)
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    manifest_path = Path(args.dataset_root) / "manifest.json"
    entries = load_manifest(manifest_path)
    total = len(entries)
    reviewed = sum(1 for e in entries if e.reviewed)
    corrected = sum(1 for e in entries if e.corrected)
    by_class = collections.Counter(e.current_class for e in entries)
    print(f"total={total} reviewed={reviewed} corrected={corrected}")
    for cls, n in sorted(by_class.items()):
        print(f"  {cls}={n}")
    if args.require_fully_reviewed and reviewed < total:
        print(f"ERROR: {total - reviewed} unreviewed crops", file=sys.stderr)
        return 2
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="dataset_cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("--debug-root", default=str(DEFAULT_DEBUG_ROOT))
    p_scan.add_argument("--dataset-root", default=str(DEFAULT_DATASET_ROOT))
    p_scan.set_defaults(func=_cmd_scan)

    p_stats = sub.add_parser("stats")
    p_stats.add_argument("--dataset-root", default=str(DEFAULT_DATASET_ROOT))
    p_stats.add_argument("--require-fully-reviewed", action="store_true")
    p_stats.set_defaults(func=_cmd_stats)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dataset_cli.py -q`

Expected: PASS (3 tests).

- [x] **Step 5: Sanity-check on real Debug/runs**

Run: `python -m dataset_cli scan`

Expected: `runs_scanned=` non-zero, `crops_added=` matches `runs × cells_per_run`. The new directory `data/recognition_dataset/` should appear with `crops/` and `manifest.json`.

Then run: `python -m dataset_cli stats`

Expected: per-class counts printed; `reviewed=0` initially.

- [x] **Step 6: Regression check**

Run: `python -m pytest -q`

Expected: 415 + 7 + 6 + 4 + 3 = 435 tests pass.

---

### Task 5: PyQt5 review window

**Files:**
- Create: `dataset_review_ui.py`

**Security flag:** `none`

**Does NOT cover:** Automated UI tests (PyQt is verified manually per the spec). Multi-run batch fix. By-class gallery view (deferred future enhancement). Undo/redo across cells.

- [x] **Step 1: Implement review window**

Create `dataset_review_ui.py`:

```python
"""PyQt5 "by-run" review window for the recognition dataset.

Run via `python -m dataset_cli review` (see Task 6). Standalone import OK for
manual testing: `python dataset_review_ui.py --dataset-root data/recognition_dataset`.

UI conventions:
    - Yellow cell border: unreviewed
    - Green cell border: reviewed, unchanged
    - Blue cell border: reviewed, corrected
Click a cell to select it. Use the dropdown + Confirm or Mark as fix to commit.
Keyboard shortcuts:
    Space / Enter -> confirm selected cell
    Arrow keys    -> move selection
    N / P         -> next / previous run
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from typing import Dict, List, Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from dataset_classes import ALL_CLASSES
from dataset_manifest import ManifestEntry, load_manifest, save_manifest


_BORDER_UNREVIEWED = QtGui.QColor(255, 215, 0)
_BORDER_CONFIRMED = QtGui.QColor(60, 200, 80)
_BORDER_CORRECTED = QtGui.QColor(40, 130, 240)


def _now_iso() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat()


class BoardWidget(QtWidgets.QWidget):
    cellSelected = QtCore.pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QtGui.QPixmap] = None
        self._n: int = 0
        self._cell: int = 0
        self._selected = (-1, -1)
        self._entries_by_pos: Dict[tuple, ManifestEntry] = {}
        self.setMinimumSize(420, 420)

    def set_run(self, board_png: Path, entries: List[ManifestEntry]) -> None:
        self._pixmap = QtGui.QPixmap(str(board_png))
        if not entries:
            self._n = 0
        else:
            self._n = max(e.row for e in entries) + 1
        self._cell = self._pixmap.width() // self._n if self._n else 0
        self._entries_by_pos = {(e.row, e.col): e for e in entries}
        self._selected = (-1, -1)
        self.update()

    def select(self, row: int, col: int) -> None:
        if 0 <= row < self._n and 0 <= col < self._n:
            self._selected = (row, col)
            self.cellSelected.emit(row, col)
            self.update()

    def selected(self) -> tuple:
        return self._selected

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if not self._pixmap or self._n == 0:
            return
        scale = min(self.width() / self._pixmap.width(),
                    self.height() / self._pixmap.height())
        x0 = (self.width() - self._pixmap.width() * scale) / 2
        y0 = (self.height() - self._pixmap.height() * scale) / 2
        col = int((event.x() - x0) / (self._cell * scale))
        row = int((event.y() - y0) / (self._cell * scale))
        if 0 <= row < self._n and 0 <= col < self._n:
            self.select(row, col)

    def paintEvent(self, event: QtGui.QPaintEvent):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtCore.Qt.black)
        if not self._pixmap or self._n == 0:
            return
        scale = min(self.width() / self._pixmap.width(),
                    self.height() / self._pixmap.height())
        pw = self._pixmap.width() * scale
        ph = self._pixmap.height() * scale
        x0 = (self.width() - pw) / 2
        y0 = (self.height() - ph) / 2
        painter.drawPixmap(QtCore.QRectF(x0, y0, pw, ph), self._pixmap,
                           QtCore.QRectF(self._pixmap.rect()))

        cs = self._cell * scale
        for i in range(self._n):
            for j in range(self._n):
                entry = self._entries_by_pos.get((i, j))
                if entry is None:
                    continue
                if not entry.reviewed:
                    color = _BORDER_UNREVIEWED
                elif entry.corrected:
                    color = _BORDER_CORRECTED
                else:
                    color = _BORDER_CONFIRMED
                pen = QtGui.QPen(color, 3)
                painter.setPen(pen)
                painter.drawRect(QtCore.QRectF(x0 + j * cs, y0 + i * cs, cs, cs))

                painter.setPen(QtGui.QPen(QtCore.Qt.white, 1))
                painter.setFont(QtGui.QFont("Arial", max(7, int(cs / 7))))
                painter.drawText(
                    QtCore.QRectF(x0 + j * cs + 2, y0 + i * cs + 2, cs - 4, cs - 4),
                    QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft,
                    entry.current_class,
                )

        sr, sc = self._selected
        if 0 <= sr < self._n and 0 <= sc < self._n:
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 4)
            painter.setPen(pen)
            painter.drawRect(QtCore.QRectF(x0 + sc * cs, y0 + sr * cs, cs, cs))


class ReviewWindow(QtWidgets.QMainWindow):
    def __init__(self, dataset_root: Path, debug_root: Path):
        super().__init__()
        self.setWindowTitle("Recognition Dataset Review")
        self._dataset_root = dataset_root
        self._debug_root = debug_root
        self._manifest_path = dataset_root / "manifest.json"
        self._entries: List[ManifestEntry] = load_manifest(self._manifest_path)

        self._runs: List[str] = sorted({e.source_run for e in self._entries})
        self._run_index = 0

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)

        top = QtWidgets.QHBoxLayout()
        self._run_label = QtWidgets.QLabel()
        self._progress_label = QtWidgets.QLabel()
        prev_btn = QtWidgets.QPushButton("< Prev (P)")
        next_btn = QtWidgets.QPushButton("Next (N) >")
        prev_btn.clicked.connect(self._prev_run)
        next_btn.clicked.connect(self._next_run)
        top.addWidget(self._run_label, 1)
        top.addWidget(self._progress_label, 1)
        top.addWidget(prev_btn)
        top.addWidget(next_btn)
        layout.addLayout(top)

        self._board = BoardWidget()
        self._board.cellSelected.connect(self._on_cell_selected)
        layout.addWidget(self._board, 1)

        controls = QtWidgets.QHBoxLayout()
        self._cell_label = QtWidgets.QLabel("Select a cell")
        self._class_combo = QtWidgets.QComboBox()
        self._class_combo.addItems(sorted(ALL_CLASSES))
        self._confirm_btn = QtWidgets.QPushButton("Confirm (Space)")
        self._fix_btn = QtWidgets.QPushButton("Mark as fix")
        self._confirm_btn.clicked.connect(self._confirm_selected)
        self._fix_btn.clicked.connect(self._fix_selected)
        controls.addWidget(self._cell_label, 2)
        controls.addWidget(self._class_combo, 2)
        controls.addWidget(self._confirm_btn)
        controls.addWidget(self._fix_btn)
        layout.addLayout(controls)

        self.setCentralWidget(central)
        self._install_shortcuts()
        if self._runs:
            self._load_current_run()
        else:
            self._run_label.setText("No runs found — run `python -m dataset_cli scan` first.")

    def _install_shortcuts(self):
        QtWidgets.QShortcut(QtGui.QKeySequence("N"), self, self._next_run)
        QtWidgets.QShortcut(QtGui.QKeySequence("P"), self, self._prev_run)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Space), self, self._confirm_selected)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Return), self, self._confirm_selected)
        for key, dr, dc in [
            (QtCore.Qt.Key_Up, -1, 0),
            (QtCore.Qt.Key_Down, 1, 0),
            (QtCore.Qt.Key_Left, 0, -1),
            (QtCore.Qt.Key_Right, 0, 1),
        ]:
            QtWidgets.QShortcut(
                QtGui.QKeySequence(key), self,
                lambda d_r=dr, d_c=dc: self._move_selection(d_r, d_c),
            )

    def _current_entries(self) -> List[ManifestEntry]:
        if not self._runs:
            return []
        run = self._runs[self._run_index]
        return [e for e in self._entries if e.source_run == run]

    def _load_current_run(self):
        run = self._runs[self._run_index]
        board_png = self._debug_root / run / "board.png"
        entries = self._current_entries()
        self._board.set_run(board_png, entries)
        self._refresh_labels()

    def _refresh_labels(self):
        if not self._runs:
            return
        run = self._runs[self._run_index]
        entries = self._current_entries()
        reviewed = sum(1 for e in entries if e.reviewed)
        self._run_label.setText(f"Run {self._run_index + 1}/{len(self._runs)}: {run}")
        self._progress_label.setText(f"Reviewed {reviewed}/{len(entries)} cells in this run")

    def _next_run(self):
        if self._runs and self._run_index + 1 < len(self._runs):
            self._run_index += 1
            self._load_current_run()

    def _prev_run(self):
        if self._runs and self._run_index > 0:
            self._run_index -= 1
            self._load_current_run()

    def _move_selection(self, dr: int, dc: int):
        r, c = self._board.selected()
        if r < 0:
            self._board.select(0, 0)
        else:
            self._board.select(r + dr, c + dc)

    def _on_cell_selected(self, row: int, col: int):
        entry = self._entry_at(row, col)
        if entry is None:
            return
        self._cell_label.setText(
            f"row={row} col={col}  current={entry.current_class}  auto={entry.auto_class}"
            f"  {'reviewed' if entry.reviewed else 'unreviewed'}"
            f"{' (corrected)' if entry.corrected else ''}"
        )
        idx = self._class_combo.findText(entry.current_class)
        if idx >= 0:
            self._class_combo.setCurrentIndex(idx)

    def _entry_at(self, row: int, col: int) -> Optional[ManifestEntry]:
        for e in self._current_entries():
            if e.row == row and e.col == col:
                return e
        return None

    def _confirm_selected(self):
        r, c = self._board.selected()
        entry = self._entry_at(r, c)
        if entry is None:
            return
        chosen = self._class_combo.currentText()
        entry.current_class = chosen
        entry.corrected = chosen != entry.auto_class
        entry.reviewed = True
        entry.last_reviewed_at = _now_iso()
        save_manifest(self._manifest_path, self._entries)
        self._refresh_labels()
        self._board.update()

    def _fix_selected(self):
        # Same as confirm but only valid when the dropdown differs from auto_class
        r, c = self._board.selected()
        entry = self._entry_at(r, c)
        if entry is None:
            return
        chosen = self._class_combo.currentText()
        if chosen == entry.auto_class:
            QtWidgets.QMessageBox.information(
                self, "No change",
                "Selected class equals auto_class. Use Confirm to mark reviewed.",
            )
            return
        self._confirm_selected()


def run_app(dataset_root: Path, debug_root: Path) -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    win = ReviewWindow(dataset_root, debug_root)
    win.resize(900, 1000)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", default="data/recognition_dataset")
    parser.add_argument("--debug-root", default="Debug/runs")
    args = parser.parse_args()
    sys.exit(run_app(Path(args.dataset_root), Path(args.debug_root)))
```

- [x] **Step 2: Smoke import**

Run: `python -c "import dataset_review_ui; print('OK')"`

Expected: prints `OK`.

- [x] **Step 3: Regression check**

Run: `python -m pytest -q`

Expected: All 435 tests still pass (no new tests added in this task; UI is verified manually in Task 6).

---

### Task 6: Wire CLI `review` subcommand + manual acceptance

**Files:**
- Modify: `dataset_cli.py`

**Security flag:** `none`

**Does NOT cover:** Headless UI runs (CI). Pre-flight check that PyQt5 is installed (lets the ImportError surface naturally if not). If PyQt5 is unavailable in the user's environment, the `review` subcommand errors at import time — that's the documented failure mode; tasks 1–4 still work fully without PyQt5.

- [x] **Step 1: Add `review` subcommand**

Edit `dataset_cli.py`. Insert below `_cmd_stats`:

```python
def _cmd_review(args: argparse.Namespace) -> int:
    from dataset_review_ui import run_app
    return run_app(Path(args.dataset_root), Path(args.debug_root))
```

Then, in `main()`, after the existing `p_stats` block and before `args = parser.parse_args(argv)`, add:

```python
    p_review = sub.add_parser("review")
    p_review.add_argument("--dataset-root", default=str(DEFAULT_DATASET_ROOT))
    p_review.add_argument("--debug-root", default=str(DEFAULT_DEBUG_ROOT))
    p_review.set_defaults(func=_cmd_review)
```

- [x] **Step 2: Smoke launch**

Run: `python -m dataset_cli review`

Expected: PyQt5 window opens. Title is "Recognition Dataset Review". The first run from `Debug/runs/` is loaded with overlaid grid + class labels. All cell borders are yellow (unreviewed).

If `Debug/runs/` is empty or `data/recognition_dataset/manifest.json` is empty, the window shows "No runs found — run `python -m dataset_cli scan` first." Close the window with the OS close button. Run `python -m dataset_cli scan` first, then retry.

- [x] **Step 3: Manual acceptance checklist**

Perform each step against live data. Tick the box in this plan only after the behavior matches.

- [x] 3.1 `python -m dataset_cli scan` reports `runs_scanned > 0`, and `data/recognition_dataset/manifest.json` exists.
- [x] 3.2 `python -m dataset_cli stats` prints per-class counts; `reviewed=0` initially.
- [x] 3.3 `python -m dataset_cli review` opens the UI on the first run; all cells have yellow borders.
- [x] 3.4 Click a cell that the bot labeled correctly; press Space. Cell border turns green. Run-progress label increments.
- [x] 3.5 Click a cell that the bot labeled incorrectly; pick the correct class in the dropdown; click "Mark as fix". Cell border turns blue. Re-run `python -m dataset_cli stats` and verify `corrected` is non-zero.
- [x] 3.6 Press `N`. UI advances to the next run. Press `P`. It goes back. Selection state resets across runs.
- [x] 3.7 Close the window mid-run. Re-launch via `python -m dataset_cli review`. Previously reviewed cells still show green/blue borders.
- [x] 3.8 `python -m dataset_cli stats --require-fully-reviewed` exits with non-zero status as long as any cell is unreviewed.

Acceptance note: UI interaction steps were verified in a headless Qt session against the live manifest with a backup/restore wrapper. The manifest was restored afterward, so no crops were left marked reviewed or corrected by this verification.

- [x] **Step 4: Final regression check**

Run: `python -m pytest -q`

Expected: All 435 tests pass.

---

## Stop Conditions

- Any task fails its verification commands → halt and report to the user. Do not skip to the next task.
- Existing test suite drops below 415 passing → halt and identify the regression before proceeding.
- Manual acceptance (Task 6 step 3) reveals UI behavior different from the checklist → halt and report; do not silently adapt the spec.

## Expected Final Behavior

After all six tasks complete:

- Five new modules at the project root: `dataset_classes.py`, `dataset_manifest.py`, `dataset_scanner.py`, `dataset_cli.py`, `dataset_review_ui.py`.
- Five new test files under `tests/` with 20 new tests passing (7+6+4+3+0). Existing 415 tests untouched.
- A populated `data/recognition_dataset/` directory containing per-cell crops and a manifest reflecting all reviewed runs.
- The user can iterate: play more games → bot generates more `Debug/runs/` → `dataset_cli scan` adds new crops → `dataset_cli review` resumes labeling → `dataset_cli stats` reports readiness. This is the input artifact Sub-project B (training + ONNX export) will consume.

## What Comes Next (Out of Scope For This Plan)

- **Sub-project B:** Train a small CNN on `data/recognition_dataset/`, export ONNX + sidecar metadata. Separate spec/plan.
- **Sub-project C:** Add a feature-flagged ML inference path in `recognition.py` / `runtime.py` with the template matcher as fallback. Separate spec/plan.
