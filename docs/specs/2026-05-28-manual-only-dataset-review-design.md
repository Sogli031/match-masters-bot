# Manual-Only Dataset Review Design

## Status

Approved on 2026-05-28.

## Scope

Change the recognition dataset review flow so a scanned board can be inspected
without accidentally adding every unreviewed crop to the training set or leaving
unmarked staging crops in the dataset. The user will manually select only the
new cells worth adding, choose a class label, and click `Mark as fix`. Only those
explicitly marked cells remain in the dataset as training-eligible examples.

## Requirements

- `Confirm all` must no longer mark all unreviewed manifest entries as reviewed.
- Accidental `Confirm all` activation must not write `manifest.json`.
- `Mark as fix` must mark exactly the selected cell as `reviewed=True`.
- `Mark as fix` must allow the selected class to match `auto_class`; this is a
  deliberate manual acceptance for new good examples, not only a correction path.
- `corrected` remains `True` only when `current_class != auto_class`.
- Existing reviewed entries and labels are preserved.
- `python -m dataset_cli review-existing` must treat the loaded unreviewed
  entries as staging data: on window close, entries captured at session start
  that are still unreviewed are deleted from the manifest and their crop files.
- Regular `review` and `review --only-unreviewed` must not auto-delete entries.
- Training remains bounded by `reviewed=True`; unmarked staging entries are
  ignored while the window is open and removed when the staging window closes.

## Non-Goals

- No training-flow changes.
- No incremental training or "train only new" mode.
- No manifest schema migration.
- No change to scanner behavior: new crops are still appended as unreviewed.
- No change to delete or audit-tab relabel/delete behavior.
- No automatic cleanup for ordinary `review`; physical staging cleanup is only
  for `review-existing`.

## Architecture

`dataset_scanner.py` continues to create unreviewed entries. `dataset_cli.py`
enables staging cleanup only for `review-existing`. `dataset_review_ui.py` owns
the safety behavior:

- The visible board review flow keeps per-cell selection, class dropdown, and
  single-cell actions.
- The `Confirm all` action becomes disabled/no-op. Keeping a no-op method avoids
  older tests or direct calls from reintroducing bulk writes.
- `_fix_selected()` becomes the preferred manual-add action and delegates to the
  existing `_commit_entry()` path even when the selected class equals `auto_class`.
- `ReviewWindow` receives a `delete_unreviewed_on_close` flag. When enabled, it
  snapshots the currently loaded unreviewed crop IDs at session start.
- On window close, only those snapshotted crop IDs that are still unreviewed are
  deleted through the existing dataset-entry deletion path, then the manifest is
  saved.

`recognition_dataset.py` and `train_recognition_model.py` stay unchanged. Their
existing reviewed-only filter is the training boundary.

## Failure-Mode Check

- Critical: `Confirm all` still writes all unreviewed cells to the manifest.
  Mitigation: change the handler to no-op and keep the UI button disabled.
- Critical: `Mark as fix` rejects same-label manual additions, preventing the new
  "add this good example" workflow. Mitigation: remove the same-label rejection.
- Critical: cleanup deletes old good data. Mitigation: cleanup only runs for
  `review-existing`, only for crop IDs loaded at session start, and only while
  those entries are still unreviewed.
- Critical: cleanup removes entries manually accepted during the session.
  Mitigation: close-time cleanup checks current `reviewed` state before deleting.
- Minor: a user can still manually confirm a wrong single selected cell.
  Accepted limitation: single-cell manual mistakes are reversible through the
  existing relabel/delete review tools and are outside the bulk-accident problem.

## Testing Strategy

- Update `tests/test_dataset_review_ui.py` so `Confirm all` is verified as a no-op
  that does not mutate entries or save the manifest.
- Add a test that `Mark as fix` commits the selected cell when the selected class
  equals `auto_class`.
- Add tests that staging cleanup deletes only unreviewed session entries and is
  disabled for regular review windows.
- Add CLI coverage proving `review-existing` enables close-time cleanup.
- Keep training tests unchanged to prove training still uses the existing reviewed
  manifest boundary.

## Manual Acceptance

1. Run `python -m dataset_cli review-existing`.
2. Select a cell, leave or choose its desired class, and click `Mark as fix`.
3. Verify only that cell changes to reviewed.
4. Close the window.
5. Verify unselected staging crops are gone from the dataset review view, while
   the manually marked cell remains available for training.
