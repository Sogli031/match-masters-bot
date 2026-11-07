# Recognition SQLite Dataset Index - Design

_Storage Option C for the recognition dataset. This is separate from the future runtime ML path that earlier specs called "Sub-project C"._

Status: **Draft for user review**
Date: 2026-05-24
Predecessor: [Recognition Dataset Builder & Labeling UI](2026-05-24-recognition-dataset-builder-design.md)
Parallel work: [Recognition CNN Training & ONNX Export](2026-05-24-recognition-cnn-training-design.md)

## 1. Goal and Scope

Add a SQLite metadata store for the existing recognition dataset while keeping the current flat crop files under `data/recognition_dataset/crops/`.

The target layout becomes:

```text
data/recognition_dataset/
  crops/
    <crop_id>.png
  recognition_dataset.sqlite3
  manifest.json
  classes.json
```

SQLite becomes the authoritative metadata store after migration. `manifest.json` remains as a compatibility export so the in-progress training pipeline can continue reading the format it already expects until it is deliberately moved to SQLite.

The SQLite layer must support:

1. Idempotent migration from the current `manifest.json` + `crops/`.
2. Queryable metadata by class, run, row, col, review state, correction state, profile, and timestamp.
3. Atomic label/review metadata updates via SQLite transactions.
4. A full label event history so corrections can be audited later.
5. Manifest export that preserves the existing schema for Sub-project B compatibility.
6. Reconciliation checks for missing crop files, orphan crop files, unknown classes, and manifest/DB drift.

### Non-goals

- No crop reorganization into `ImageFolder` class directories.
- No storing image bytes as SQLite BLOBs. Crops stay as normal PNG files.
- No runtime ML integration in `recognition.py`, `runtime.py`, or `gui.py`.
- No training behavior changes unless the later implementation plan explicitly adds an optional SQLite loader.
- No multi-user or network database. This remains a single-workstation local dataset.
- No SQL editor UI. Existing `dataset_review_ui.py` remains the review surface.
- No deletion of `manifest.json` while Sub-project B is in progress.

## 2. Chosen Approach

### Recommended variant: SQLite metadata source of truth + flat crop files + manifest export

The DB owns metadata after migration. Crops remain files because the training code and visual review UI naturally consume PNGs. `manifest.json` is generated from the DB after mutations or on demand.

Trade-offs:

| Variant | Pros | Cons | Decision |
|---|---|---|---|
| SQLite sidecar only, manifest remains source of truth | Lowest risk for B | SQLite queries can become stale and updates are still JSON-first | Reject |
| SQLite source of truth + manifest export | Atomic metadata updates, queryable, preserves B compatibility | More code than manifest-only | Choose |
| SQLite BLOB storage for crops | One physical file, easier backup semantics | Slower visual inspection, harder manual recovery, unnecessary for small PNGs | Reject |

This gives the useful parts of Option C without breaking the already completed Option A or the in-progress training pipeline.

## 3. Data Flow

### Migration flow

```text
manifest.json + classes.json + crops/
        |
        v
  dataset_sqlite.migrate_from_manifest()
        |
        v
recognition_dataset.sqlite3
        |
        v
dataset_cli db-check
```

Migration is idempotent. Re-running it updates existing rows only when the manifest row is identical or compatible. Conflicting rows stop with a clear error instead of silently overwriting labels.

### Ongoing write flow

```text
Debug/runs/<run_id>/board.png + move.json
        |
        v
dataset_scanner.py
        |
        v
crop PNG written to crops/<crop_id>.png
        |
        v
SQLite transaction inserts run + crop metadata
        |
        v
manifest.json export for compatibility
```

Review UI updates follow the same rule: update SQLite inside one transaction, append a label event, then export `manifest.json`.

### Training compatibility flow

Until B is moved intentionally:

```text
SQLite DB
  -> export_manifest()
  -> manifest.json
  -> RecognitionDataset / training pipeline
```

This keeps the split and training work stable while storage migration happens independently.

## 4. SQLite Schema

### `dataset_meta`

Key/value table for schema and reproducibility metadata.

```sql
CREATE TABLE dataset_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

Required keys:

- `schema_version`: starts at `1`.
- `created_at`: ISO timestamp.
- `classes_snapshot_hash`: hash of sorted `classes.json` / `dataset_classes.ALL_CLASSES`.
- `source_manifest_version`: current manifest version at migration time.

### `classes`

```sql
CREATE TABLE classes (
  class_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  active INTEGER NOT NULL DEFAULT 1
);
```

Class names come from `dataset_classes.ALL_CLASSES`. Unknown class names in an imported manifest are fatal.

### `runs`

```sql
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  profile TEXT NOT NULL,
  board_size INTEGER NOT NULL,
  debug_run_path TEXT,
  board_png_path TEXT,
  move_json_path TEXT,
  first_seen_at TEXT NOT NULL,
  last_scanned_at TEXT NOT NULL,
  rejected_reason TEXT
);
```

Rejected runs may be recorded with `rejected_reason`, but they must not create crop rows.

### `crops`

```sql
CREATE TABLE crops (
  crop_id TEXT PRIMARY KEY,
  source_run TEXT NOT NULL REFERENCES runs(run_id) ON DELETE RESTRICT,
  row INTEGER NOT NULL,
  col INTEGER NOT NULL,
  crop_path TEXT NOT NULL,
  profile TEXT NOT NULL,
  original_width INTEGER NOT NULL,
  original_height INTEGER NOT NULL,
  auto_class_id INTEGER NOT NULL REFERENCES classes(class_id),
  current_class_id INTEGER NOT NULL REFERENCES classes(class_id),
  reviewed INTEGER NOT NULL DEFAULT 0,
  corrected INTEGER NOT NULL DEFAULT 0,
  label_origin TEXT NOT NULL CHECK (label_origin IN ('auto', 'confirmed', 'corrected')),
  first_seen_at TEXT NOT NULL,
  last_reviewed_at TEXT,
  UNIQUE(source_run, row, col)
);
```

Field mapping to the current manifest:

| Manifest field | SQLite field |
|---|---|
| `crop_id` | `crops.crop_id` |
| `source_run` | `crops.source_run` |
| `row`, `col` | `crops.row`, `crops.col` |
| `profile` | `crops.profile`, `runs.profile` |
| `original_size` | `original_width`, `original_height` |
| `auto_class` | `classes.name` via `auto_class_id` |
| `current_class` | `classes.name` via `current_class_id` |
| `reviewed` | `crops.reviewed` |
| `corrected` / `was_corrected` | `crops.corrected` |
| `first_seen_at`, `last_reviewed_at` | same meaning |

`label_origin` semantics:

- `auto`: label is the unreviewed auto-label.
- `confirmed`: user reviewed the cell and accepted the auto-label.
- `corrected`: user changed the label.

This is more precise than a single `was_auto` boolean. A compatibility view or manifest export can derive:

- `was_auto = label_origin IN ('auto', 'confirmed')`
- `was_corrected = corrected`

### `label_events`

```sql
CREATE TABLE label_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  crop_id TEXT NOT NULL REFERENCES crops(crop_id) ON DELETE CASCADE,
  old_class_id INTEGER REFERENCES classes(class_id),
  new_class_id INTEGER NOT NULL REFERENCES classes(class_id),
  action TEXT NOT NULL CHECK (action IN ('auto_imported', 'confirmed', 'corrected', 'reverted')),
  created_at TEXT NOT NULL,
  note TEXT
);
```

Every imported crop gets one `auto_imported` event. Every UI confirm/correction gets a new event. The current label lives in `crops`; the history lives in `label_events`.

### Indexes

```sql
CREATE INDEX idx_crops_class ON crops(current_class_id);
CREATE INDEX idx_crops_run ON crops(source_run);
CREATE INDEX idx_crops_reviewed ON crops(reviewed);
CREATE INDEX idx_crops_corrected ON crops(corrected);
CREATE INDEX idx_crops_position ON crops(source_run, row, col);
CREATE INDEX idx_label_events_crop ON label_events(crop_id);
```

## 5. Interfaces

### `dataset_store.py`

Introduce a narrow storage interface so scanner, CLI, UI, and training code do not know whether metadata came from JSON or SQLite.

```python
class DatasetStore:
    def list_entries(self) -> list[ManifestEntry]: ...
    def get_entry(self, crop_id: str) -> ManifestEntry | None: ...
    def upsert_scanned_entry(self, entry: ManifestEntry) -> None: ...
    def mark_reviewed(self, crop_id: str, current_class: str, reviewed_at: str) -> None: ...
    def stats(self) -> DatasetStats: ...
    def export_manifest(self, manifest_path: Path) -> None: ...
```

The first implementation can be small and pragmatic:

- `JsonManifestStore` wraps current `dataset_manifest.py`.
- `SQLiteDatasetStore` wraps `recognition_dataset.sqlite3`.

### `dataset_sqlite.py`

Owns all SQLite-specific code:

- connect with `PRAGMA foreign_keys=ON`.
- initialize schema.
- migrate from manifest.
- insert/update crops and label events transactionally.
- export manifest.
- run integrity checks.

No UI code should write SQL directly.

### `dataset_cli.py`

Add DB commands:

```text
python -m dataset_cli db-init
python -m dataset_cli db-migrate
python -m dataset_cli db-check
python -m dataset_cli export-manifest
```

Existing commands stay:

```text
python -m dataset_cli scan
python -m dataset_cli review
python -m dataset_cli stats
```

Once SQLite is ready, these commands should default to SQLite when `recognition_dataset.sqlite3` exists. A `--store json|sqlite` flag can force either mode during rollout.

### `dataset_review_ui.py`

The UI should switch from loading a list of manifest entries directly to using `DatasetStore`.

Required behavior is unchanged:

- show runs one at a time.
- show current/auto label per cell.
- confirm unchanged labels.
- correct wrong labels.
- persist after every confirm/correction.

The visible UI is not redesigned in this storage spec.

## 6. Atomicity and Consistency

SQLite provides atomic metadata updates. It does not make the DB row and external PNG file a single physical atomic unit.

The implementation must be explicit about this:

1. Label/review changes are fully atomic because they only touch SQLite rows.
2. Scanner ingestion writes the PNG first, then inserts metadata in a transaction.
3. If a scan crashes between file write and DB insert, the next `db-check` reports an orphan crop file.
4. If a DB row exists but the crop file is missing, `db-check` reports a missing crop and training must refuse to use that row.
5. `manifest.json` is exported from SQLite after metadata mutations with the existing temp-file + replace pattern.

Use WAL mode for normal operation after the DB exists at its final path:

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
```

Single writer is assumed. If the UI and scanner try to write at the same time, the second writer should fail with a clear "database is busy; close the other dataset tool or retry" message.

## 7. Migration Rules

`db-migrate` from the current dataset must:

1. Refuse if `manifest.json` is missing.
2. Refuse if `classes.json` or `dataset_classes.ALL_CLASSES` does not contain every class referenced by the manifest.
3. Refuse if any manifest entry is missing its crop file.
4. Create `recognition_dataset.sqlite3.tmp` for the initial migration with default rollback journaling, then rename to `recognition_dataset.sqlite3` after all checks pass.
5. Insert all classes, runs, crops, and initial `auto_imported` label events.
6. Preserve `reviewed`, `corrected`, `current_class`, and `last_reviewed_at` exactly.
7. Open the final DB path and enable WAL mode only after the rename.
8. Write no partial DB if migration fails before the rename.

If the DB already exists, migration becomes an idempotent sync:

- identical rows are skipped.
- new manifest rows are inserted.
- conflicting rows stop with an error that names the `crop_id` and differing fields.

## 8. Error Handling

| Case | Behavior |
|---|---|
| Unknown class in manifest | Refuse migration; list class names. |
| Missing crop PNG for a manifest entry | Refuse migration and `db-check`; training must not proceed. |
| Orphan crop PNG without DB row | `db-check` warns; optional cleanup can be a later command. |
| DB schema version mismatch | Refuse writes and tell the user the expected/current versions. |
| DB locked | Fail fast with a clear single-writer message. |
| Manifest export fails | Leave DB committed; report export failure; B should not run until export succeeds. |
| Corrupt DB | Refuse to open; user can continue from `manifest.json` and crops if those are still valid. |

## 9. Testing Strategy

Add focused tests before implementation:

1. Migration creates SQLite rows from a fixture `manifest.json` + crops folder.
2. Migration refuses unknown classes.
3. Migration refuses missing crop files.
4. Migration is idempotent for identical manifest data.
5. Migration detects conflicting manifest data for the same `crop_id`.
6. `mark_reviewed()` updates `crops` and appends `label_events` in one transaction.
7. `export_manifest()` round-trips DB rows back into the current manifest schema.
8. `db-check` detects orphan crop files and missing crop files.
9. `dataset_cli stats` returns the same totals from JSON and SQLite stores.
10. Existing A tests keep passing in JSON mode during rollout.

Verification commands:

```text
python -m pytest tests/test_dataset_manifest.py tests/test_dataset_scanner.py -q
python -m pytest tests/test_dataset_sqlite.py tests/test_dataset_cli.py -q
python -m dataset_cli db-migrate
python -m dataset_cli db-check
python -m dataset_cli export-manifest
python -m dataset_cli stats --require-fully-reviewed
```

The final full gate remains:

```text
python -m pytest -q
```

## 10. Rollout Plan

Implementation should be staged so B is not broken mid-work:

1. Add SQLite module and tests without changing existing scanner/UI defaults.
2. Add `db-migrate`, `db-check`, and `export-manifest`.
3. Run migration against the current dataset and verify row counts match `manifest.json`.
4. Add `DatasetStore` abstraction and keep JSON as the default store.
5. Switch CLI/UI/scanner to SQLite only when `recognition_dataset.sqlite3` exists, with `--store json|sqlite` override.
6. Export `manifest.json` after each SQLite mutation until B is deliberately moved.
7. Later, if desired, add an optional training loader that reads SQLite directly and compares its split input to the manifest-based loader.

No step deletes existing crop files or removes the manifest path.

## 11. Failure-Mode Check

### Failure mode 1: "Atomic DB" is mistaken for atomic DB + image files

Severity: Critical if undocumented.

SQLite cannot make an external PNG write and a DB transaction one indivisible operation. The design avoids overpromising by limiting atomicity claims to metadata and requiring `db-check` reconciliation for file/row drift.

### Failure mode 2: SQLite and manifest drift while B is still reading manifest

Severity: Critical.

If B trains from stale `manifest.json`, the DB can be correct while the model trains on old labels. The design mitigates this by exporting manifest after every SQLite mutation and by requiring a DB-vs-manifest count/content check in `db-check`.

### Failure mode 3: Schema overhead slows down current work for a small dataset

Severity: Minor if rollout stays staged.

The dataset is currently small enough that JSON works. SQLite is justified only if it is introduced as an optional/staged storage layer, with JSON compatibility preserved until training no longer depends on it.

## 12. Acceptance Criteria

SQLite storage is ready when:

1. `recognition_dataset.sqlite3` can be created from the existing manifest without re-extracting crops.
2. DB crop count equals manifest crop count and every DB crop path exists.
3. `db-check` reports no missing crop files and no DB/manifest drift after export.
4. A reviewed/corrected label update writes one DB transaction and one label event.
5. Exported `manifest.json` is compatible with the current B training spec.
6. Existing dataset builder tests and new SQLite tests pass.
