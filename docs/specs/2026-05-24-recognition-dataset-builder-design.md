# Recognition Dataset Builder & Labeling UI — Design

_Sub-project A of the "ML recognition revival" initiative._

Status: **Draft for user review**
Date: 2026-05-24
Related: Sub-project B (training/ONNX export) and Sub-project C (runtime ML path) will follow as separate specs.

## 1. Goal and Scope

Build an **offline desktop tool** that turns the accumulated `Debug/runs/` snapshots into a labeled, auditable dataset of per-cell tile crops. The dataset is the input to Sub-project B (CNN training).

The tool:
1. Scans `Debug/runs/` for snapshots that contain both `board.png` and `move.json`.
2. Slices each board into per-cell crops using the active board profile (`squareSize`, `boardSize`).
3. Auto-labels each cell from `move.json["board"]` and `move.json["special_board"]` using a fixed class taxonomy.
4. Presents a PyQt5 "by-run" review UI where the user confirms or corrects each cell.
5. Writes incremental updates to a manifest file so a mid-session crash never loses work.
6. Exports the curated dataset (crops + manifest) into `data/recognition_dataset/` ready for Sub-project B.

### Non-goals

- **No ML training.** That is Sub-project B.
- **No runtime changes.** `recognition.py`, `runtime.py`, and `gui.py` are not touched. That is Sub-project C.
- **No `after_board.png` ingestion.** Only `board.png` (the pre-move snapshot referenced by `move.json`) is processed in MVP.
- **No class balancing or augmentation.** Sub-project B handles imbalance via weighted sampling. A only collects.
- **No bulk delete or run pruning.** All scanned runs are kept; if the user wants to discard a run, they delete the folder manually.
- **No multi-user merging.** Single workstation, single manifest.
- **No image augmentation** (rotation, color jitter, mixup). That is a training concern.

## 2. Data Flow

```
Debug/runs/<run_id>/
  ├── board.png             # source crop (pre-move screenshot of the board)
  └── move.json             # contains board[][] and special_board[][]
        ▼
    [Scanner]               # walks Debug/runs/, dedups by (run_id, row, col)
        ▼
    [Slicer]                # slice board.png into N x N crops using squareSize
        ▼
    [Auto-labeler]          # map (color, special) -> ClassName
        ▼
data/recognition_dataset/
  ├── crops/<crop_id>.png   # individual 84x84 (or native squareSize) PNGs
  ├── manifest.json         # one entry per crop with full audit trail
  └── classes.json          # canonical class enum (id, name, color, special, color_agnostic)
        ▼
    [Review UI: PyQt5]      # by-run grid view with click-to-correct
        ▼
data/recognition_dataset/manifest.json  # updated in place with reviewed=True, corrected_class=...
```

## 3. Class Taxonomy

The class taxonomy is a **fixed enum** defined in `dataset_classes.py`. UI dropdowns and auto-labeler are driven from this enum — no free-text class names. This eliminates typo failure mode.

### Naming convention

- **Color-bound special:** `<color>_<special>` (e.g., `red_normal`, `blue_heart`, `green_knight`, `yellow_horizontal`, `purple_bomb`, `orange_lightning`, `white_mode_target`).
- **Color-agnostic special:** `<special>` (e.g., `disco_ball`, `joojoo_skull`, `mode_target` if rendered without a base color).
- **Structural cells:** `blocked`, `empty`.

### Initial class list (MVP)

Derived from `move_strategy.py` constants. Six base colors × normal + per-special enumeration:

| Class id | Meaning | Color-agnostic? |
|---|---|---|
| `red_normal` / `orange_normal` / `yellow_normal` / `green_normal` / `blue_normal` / `purple_normal` | Base gem, no special | No |
| `<color>_horizontal` (×6) | Horizontal arrow | No |
| `<color>_vertical` (×6) | Vertical arrow | No |
| `<color>_bomb` (×6) | Bomb gem | No |
| `<color>_lightning` (×6) | Lightning gem | No |
| `<color>_heart` (×6) | Cupid heart | No |
| `<color>_knight` (×6) | Knight piece | No |
| `<color>_mushroom` (×6) | Multiplier mushroom | No |
| `<color>_color_crystal` (×6) | Color crystal | No |
| `<color>_all_aboard_bandit` (×6) | All-Aboard bandit | No |
| `cleo_bug` | Cleo bug | Yes (always blue/red?) — verified per template |
| `billie_drone` | Billie drone | Yes |
| `disco_ball` | Disco ball | Yes |
| `joojoo_skull` | JooJoo skull | Yes |
| `mode_target` | Mode target | Yes |
| `blocked` | BLOCKED cell | n/a |
| `empty` | `board[i][j] == 0` (recognizer failed) | n/a |

**Open verification at implementation time:** for `cleo_bug`, `billie_drone`, `joojoo_skull` we will check `recognition.py` to confirm whether they are truly color-agnostic or color-bound in the current detector. If color-bound, expand to per-color variants.

### Class enum file

`dataset_classes.py` exposes:

```python
class TileClass(Enum):
    RED_NORMAL = "red_normal"
    BLUE_HEART = "blue_heart"
    # ... etc
    BLOCKED = "blocked"
    EMPTY = "empty"

def classify(color_code: int, special_code: int) -> TileClass: ...
```

The `classify()` function is the **single source of truth** for the (color, special) → class mapping. Both the auto-labeler and any future runtime decoder use it. UI dropdowns enumerate `TileClass`.

## 4. Storage Format

### Directory layout

```
data/recognition_dataset/
  crops/
    <crop_id>.png             # e.g., 2026-05-24_10-12-28_905__r2_c3.png
  manifest.json               # full audit log of every crop
  classes.json                # snapshot of dataset_classes.py at last build (for reproducibility)
```

### Crop id format

`<run_id>__r<row>_c<col>.png`

- Deterministic: same source cell always produces the same id.
- Re-scanning the same run does not duplicate work — manifest is keyed by crop_id.

### Manifest schema

`manifest.json` is a single JSON file containing a list of entries. Atomic writes use a `manifest.json.tmp` + rename pattern.

```json
{
  "version": 1,
  "generated_at": "2026-05-24T14:30:00",
  "entries": [
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
  ]
}
```

Field semantics:
- `auto_class` — what the bot's `move.json` said (immutable after first scan).
- `current_class` — the active label; equals `auto_class` until corrected.
- `reviewed` — set to `true` the first time the user opens this cell in the UI and confirms or fixes it.
- `corrected` — `true` iff `current_class != auto_class`.

### Incremental write strategy

The manifest is rewritten **on every UI state change** (every confirm or fix). Crash recovery is automatic: reopening the tool reads the manifest as-is.

For 58 runs × 49 cells = ~2,842 entries, the JSON file is small enough (<500 KB) that full-file rewrite per change is acceptable. If the dataset grows past ~50k entries, switch to append-only JSONL (deferred).

## 5. Components

### 5.1 `dataset_classes.py`

Canonical taxonomy and `classify()` function. Pure module, no I/O.

### 5.2 `dataset_scanner.py`

```python
def scan_debug_runs(debug_root: Path, dataset_root: Path) -> ScanReport:
    """Walk Debug/runs/, find runs with board.png + move.json, slice into crops,
    auto-label, write missing entries to manifest.json. Idempotent."""
```

Reads `board_config.json` (or `board_config_supersize.json`) to determine `squareSize`. Slices `board.png` via `numpy` slicing. Writes individual crops to `crops/`. Updates manifest.

`ScanReport` summarizes: runs scanned, new crops added, crops skipped (already in manifest), runs rejected (missing files, profile mismatch).

### 5.3 `dataset_manifest.py`

Loader/writer for `manifest.json`. Provides typed access (dataclass `ManifestEntry`) and atomic write.

### 5.4 `dataset_review_ui.py` (PyQt5)

Single-window application. Layout:

```
+--------------------------------------------------+
| Run: [2026-05-24_10-12-28_905 ▼]  Next > Prev <  |
| Progress: 12/58 runs reviewed                    |
+--------------------------------------------------+
| [board image with overlay grid + class labels]   |
|                                                  |
| Each cell is clickable. Hovered cell shows       |
| current class + "auto" or "corrected" badge.     |
|                                                  |
| Color coding:                                    |
|   green border  = reviewed, unchanged            |
|   blue border   = reviewed, corrected            |
|   yellow border = unreviewed                     |
+--------------------------------------------------+
| Selected cell: row=2 col=3                       |
| Current: red_normal  Auto: red_normal            |
| [Class dropdown: ▼]  [Confirm]  [Mark as fix]    |
+--------------------------------------------------+
| Footer: Save state (auto) | Quit                 |
+--------------------------------------------------+
```

Keyboard shortcuts:
- `Space` / `Enter` — confirm selected cell
- `Arrow keys` — move selection across grid
- `1`-`9`, letters — quick-pick top classes (configurable)
- `N` / `P` — next / previous run

UI imports `dataset_classes.py` for dropdown options.

### 5.5 `dataset_cli.py`

Thin CLI entry points:
- `python -m dataset_cli scan` — runs the scanner without UI
- `python -m dataset_cli review` — opens the PyQt5 UI
- `python -m dataset_cli stats` — prints class distribution + review progress

## 6. Mandatory Review Discipline

To mitigate the "blind trust in auto-labels" failure mode:

- Every cell starts as `reviewed=false`.
- The UI surfaces an explicit `Confirm` action even when the user agrees with the auto-label. **One click per cell minimum.**
- The "by-run" view tracks reviewed/total per run; a run is not marked "complete" until all cells are reviewed.
- An export-readiness check (CLI `dataset_cli stats`) reports unreviewed counts and refuses to proceed if any exist when called with `--require-fully-reviewed`.

This is friction by design: bot accuracy is ~95%, which means slipped 5% errors poison the training set if the user is allowed to skim.

## 7. Edge Cases

| Case | Behavior |
|---|---|
| `move.json` is missing | Run skipped; logged in `ScanReport.rejected`. |
| `board.png` is missing | Run skipped; logged. |
| `move.json["board"]` shape ≠ board profile | Run skipped; logged. We do not auto-detect profile changes. |
| `BLOCKED` cell | Auto-label = `blocked`. Crop still saved. |
| `board[i][j] == 0` (recognizer returned nothing) | Auto-label = `empty`. User likely corrects to a real class. |
| Supersize 8×8 run | Detected from `move.json["board"]` shape; manifest records `profile: "supersize"`. Crops sized by the run's `squareSize`. |
| Re-scan same Debug/runs/ | Manifest dedupes by `crop_id`. Existing review state preserved. |
| User edits `dataset_classes.py` mid-project | `classes.json` snapshot in dataset root flags drift. Tool refuses to start if `classes.json` references classes no longer in the enum, until user explicitly migrates. |
| Crash during write | Atomic rename pattern prevents partial manifest. |
| Very large manifest | Acceptable up to ~50k entries with full-file JSON rewrite. Migrate to JSONL if exceeded. |

## 8. Testing Strategy

- **Pure modules first.** `dataset_classes.classify()` and `dataset_manifest.*` are pure and trivially unit-testable. Aim for >90% branch coverage.
- **Scanner integration test.** Fixture: a hand-crafted `Debug/runs/fake_run_001/` with known `board.png` and `move.json`. Test asserts manifest has expected entries with correct auto_class.
- **Profile dispatch test.** Two fixtures: one 7×7, one 8×8. Scanner picks the right profile.
- **Manifest crash recovery test.** Write a manifest, corrupt the `.tmp` partial, ensure load still reads the previous committed state.
- **UI tests.** Out of scope for MVP. PyQt5 tests are slow and brittle; verify manually following an explicit acceptance checklist (below).

### Manual acceptance checklist

1. Launch `python -m dataset_cli scan` against the live `Debug/runs/`. Confirm `manifest.json` is created and crop count matches expected (`runs × cells_per_run`).
2. Launch `python -m dataset_cli review`. UI opens to first run. All cells are yellow (unreviewed).
3. Click on a correctly-labeled cell, press `Space`. Cell turns green.
4. Click on a mislabeled cell (find one deliberately), pick a different class, click `Mark as fix`. Cell turns blue. Manifest entry's `current_class` and `corrected` updated.
5. Close UI mid-run. Re-launch. Review state preserved.
6. Run `python -m dataset_cli stats`. Reports per-class counts, review progress, corrected ratio.

## 9. Rollout

A is a new offline tool. There is no migration. Sub-projects B and C consume A's output (`data/recognition_dataset/`).

## 10. Open Questions Deferred to Future Specs

- **Confidence-based pre-flagging** of likely-wrong cells (would need confidence field in `move.json`, which currently does not exist). Future enhancement; the bot would have to log `special_confidence` to `move.json`.
- **By-class gallery view** for second-pass QA. Skipped from MVP per user direction (workflow α only).
- **Augmentation strategy** for training. Sub-project B.
- **Color-agnostic vs color-bound** for `cleo_bug`, `billie_drone`, `joojoo_skull` — needs verification against `recognition.py` at implementation time.
