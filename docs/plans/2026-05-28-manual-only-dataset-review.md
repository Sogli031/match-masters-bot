# Manual-Only Dataset Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:subagent-driven-development (recommended) or superpowers-optimized:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make recognition dataset review safe for adding only explicitly marked new examples.
**Architecture:** Keep scanner and training unchanged. Restrict the review UI mutation surface so bulk confirmation cannot mark unreviewed entries, while `Mark as fix` can manually accept the selected cell even when the label equals `auto_class`. For `review-existing`, treat unreviewed entries loaded at session start as staging data and delete any still-unreviewed session entries on close.
**Tech Stack:** Python, PyQt5, pytest, JSON manifest files.
**Assumptions:**
- Assumes training eligibility remains `reviewed=True` in `recognition_dataset.py` - will NOT work as a separate incremental-training feature.
- Assumes accidental bulk additions are the main risk - will NOT prevent intentional single-cell mistakes.
- Assumes staging cleanup is only wanted for `python -m dataset_cli review-existing`; ordinary `review` must not auto-delete crops.

---

## File Structure

- Modify `tests/test_dataset_review_ui.py`: regression tests for disabled/no-op bulk confirmation and same-label `Mark as fix`.
- Modify `tests/test_dataset_cli.py`: regression test that `review-existing` enables close-time staging cleanup.
- Modify `dataset_review_ui.py`: make `Confirm all` no-op/disabled, remove the same-label rejection from `_fix_selected()`, and delete unmarked staging entries on close when explicitly enabled.
- Modify `dataset_cli.py`: pass the staging-cleanup flag for `review-existing`.
- Do not modify `recognition_dataset.py`, `train_recognition_model.py`, `dataset_scanner.py`, or manifest schema files.

## Task 1: Lock `Confirm all` As No-Op

**Files:**
- Modify: `tests/test_dataset_review_ui.py`
- Modify: `dataset_review_ui.py`

**Security flag:** `none`

**Does NOT cover:** Single-cell `Confirm` and `Mark as fix`; those remain separate explicit actions.

- [x] **Step 1: Write failing test**

Replace `test_confirm_all_marks_remaining_unreviewed_entries` in `tests/test_dataset_review_ui.py` with:

```python
def test_confirm_all_does_not_mark_unreviewed_entries(monkeypatch):
    first = _entry("new_open", reviewed=False)
    second = _entry("new_mixed", reviewed=False)
    second.current_class = "red_normal"
    already_fixed = _entry("old_done", reviewed=True)
    already_fixed.current_class = "green_normal"
    already_fixed.corrected = True
    already_fixed.last_reviewed_at = "2026-05-25T00:01:00"
    entries = [first, second, already_fixed]
    saved = []
    refreshed = []
    updated = []
    window = SimpleNamespace(
        _entries=entries,
        _manifest_path="manifest.json",
        _refresh_run_labels=lambda: refreshed.append(True),
        _board=SimpleNamespace(update=lambda: updated.append(True)),
    )

    monkeypatch.setattr(
        "dataset_review_ui.save_manifest",
        lambda path, saved_entries: saved.append((path, list(saved_entries))),
    )

    ReviewWindow._confirm_all_unreviewed(window)

    assert first.reviewed is False
    assert first.corrected is False
    assert first.last_reviewed_at is None
    assert second.reviewed is False
    assert second.corrected is False
    assert second.last_reviewed_at is None
    assert already_fixed.reviewed is True
    assert already_fixed.corrected is True
    assert already_fixed.last_reviewed_at == "2026-05-25T00:01:00"
    assert saved == []
    assert refreshed == []
    assert updated == []
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dataset_review_ui.py -q`
Expected: FAIL because `_confirm_all_unreviewed()` still marks unreviewed entries and saves the manifest.

- [x] **Step 3: Implement minimal change**

In `dataset_review_ui.py`, change `_confirm_all_unreviewed()` to:

```python
    def _confirm_all_unreviewed(self) -> None:
        return
```

Also make the UI show that bulk confirmation is unavailable:

```python
self._confirm_all_button = QtWidgets.QPushButton("Confirm all disabled")
self._confirm_all_button.setToolTip(
    "Bulk confirm is disabled. Select a cell and use Mark as fix to add it."
)
self._confirm_all_button.setEnabled(False)
```

In `_set_controls_enabled()`, keep the button disabled:

```python
self._confirm_all_button.setEnabled(False)
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dataset_review_ui.py -q`
Expected: PASS.

## Task 2: Allow `Mark as fix` To Manually Accept Same Label

**Files:**
- Modify: `tests/test_dataset_review_ui.py`
- Modify: `dataset_review_ui.py`

**Security flag:** `none`

**Does NOT cover:** Bulk accepting all auto labels; this task only changes the selected-cell action.

- [x] **Step 1: Write failing test**

Append to `tests/test_dataset_review_ui.py`:

```python
def test_mark_as_fix_accepts_selected_auto_label_as_manual_example():
    entry = _entry("new_run", reviewed=False, auto_class="blue_normal")
    commits = []
    window = SimpleNamespace(
        _board=SimpleNamespace(selected=lambda: (entry.row, entry.col)),
        _entry_at=lambda row, col: entry if (row, col) == (entry.row, entry.col) else None,
        _class_combo=SimpleNamespace(currentText=lambda: "blue_normal"),
        _commit_entry=lambda selected_entry, chosen_class: commits.append(
            (selected_entry, chosen_class)
        ),
    )

    ReviewWindow._fix_selected(window)

    assert commits == [(entry, "blue_normal")]
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dataset_review_ui.py -q`
Expected: FAIL because `_fix_selected()` currently refuses when `chosen_class == entry.auto_class`.

- [x] **Step 3: Implement minimal change**

In `dataset_review_ui.py`, remove the same-label guard from `_fix_selected()` so the method becomes:

```python
    def _fix_selected(self) -> None:
        row, col = self._board.selected()
        entry = self._entry_at(row, col)
        if entry is None:
            return
        chosen_class = self._class_combo.currentText()
        self._commit_entry(entry, chosen_class)
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dataset_review_ui.py -q`
Expected: PASS.

## Task 3: Verify Training Boundary Remains Unchanged

**Files:**
- Read-only check: `recognition_dataset.py`
- Read-only check: `train_recognition_model.py`

**Security flag:** `none`

**Does NOT cover:** incremental training, checkpoint fine-tuning, or train-new-only behavior.

- [x] **Step 1: Run focused dataset/training tests**

Run:

```powershell
python -m pytest tests/test_dataset_review_ui.py tests/test_recognition_dataset.py tests/test_train_recognition_model.py -q
```

Expected: PASS.

- [x] **Step 2: Compile touched runtime files**

Run:

```powershell
python -m py_compile dataset_review_ui.py dataset_manifest.py recognition_dataset.py train_recognition_model.py
```

Expected: PASS.

- [x] **Step 3: Manual smoke note**

Do not mutate the real dataset during automated verification. Report the manual check:

```powershell
python -m dataset_cli review --only-unreviewed
```

Expected manual behavior: `Confirm all disabled` cannot mark entries; selecting a cell and clicking `Mark as fix` marks only that cell reviewed.

## Stop Conditions

- Stop if any test tries to modify `data/recognition_dataset/manifest.json`.
- Stop if implementation touches training selection logic.
- Stop if a proposed fix requires manifest schema changes.

## Expected Final Behavior

After implementation, scanning new debug runs still appends unreviewed entries. The user can inspect a board and manually add selected cells through `Mark as fix`. Unmarked cells remain unreviewed and are ignored by the existing training command.

## Task 4: Add `review-existing` Staging Cleanup

**Files:**
- Modify: `tests/test_dataset_review_ui.py`
- Modify: `tests/test_dataset_cli.py`
- Modify: `dataset_review_ui.py`
- Modify: `dataset_cli.py`

**Security flag:** `medium` - deletes crop files, but only for crop IDs captured at staging-window startup and still unreviewed at close.

**Does NOT cover:** physical cleanup for ordinary `review` / `review --only-unreviewed`, and does not delete reviewed entries.

- [x] **Step 1: Write failing tests**

Add regression tests proving a staging close deletes only unreviewed session crop IDs, preserves manually reviewed entries, and regular review windows do not auto-delete.

- [x] **Step 2: Verify tests fail before implementation**

Run:

```powershell
python -m pytest tests/test_dataset_review_ui.py tests/test_dataset_cli.py -q
```

Expected before implementation: FAIL because `ReviewWindow` has no staging cleanup method/flag and `review-existing` does not pass one.

- [x] **Step 3: Implement minimal change**

Add `delete_unreviewed_on_close=False` to `run_app()` and `ReviewWindow`. When true, snapshot loaded unreviewed crop IDs for the current run set. In `closeEvent()`, delete only snapshotted crop IDs that are still unreviewed and save the manifest. Pass the flag only from `_cmd_review_existing()`.

- [x] **Step 4: Run focused verification**

Run:

```powershell
python -m pytest tests/test_dataset_review_ui.py tests/test_dataset_cli.py -q
```

Expected after implementation: PASS.
