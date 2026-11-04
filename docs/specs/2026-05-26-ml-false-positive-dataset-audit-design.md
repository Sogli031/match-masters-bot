# ML False-Positive Dataset Audit Design

## Scope

Add a focused audit path for finding dataset crops where the current ML model predicts one class, but the manifest label says another class.

Primary use case:

- User selects or requests `green_horizontal`.
- Tool finds crops where `predicted_class == green_horizontal` and `current_class != green_horizontal`.
- Tool shows enough context to manually decide whether the manifest label or the model is wrong.

This is a review aid only. It must not auto-relabel crops.

## Non-Goals

- No automatic dataset relabeling from ML output.
- No threshold changes in `models/recognition_model.metadata.json`.
- No model retraining.
- No changes to live board recognition or move selection.
- No replacement for human review in `dataset_review_ui.py`.

## Architecture

Create a pure helper module, `dataset_ml_audit.py`, that can run independently of PyQt.

Inputs:

- `data/recognition_dataset/manifest.json`
- `data/recognition_dataset/crops/*.png`
- `models/recognition_model.onnx`
- `models/recognition_model.metadata.json`
- requested predicted class
- minimum confidence
- optional limit
- reviewed-only flag

Output:

- structured audit rows containing:
  - `crop_id`
  - `source_run`
  - `row`
  - `col`
  - `current_class`
  - `predicted_class`
  - `confidence`
  - `label_confidence`
  - `threshold`
  - `model_version`

Rows are sorted by confidence descending, then source run, row, and col.

## CLI

Add a `dataset_cli.py` command:

```powershell
python -m dataset_cli ml-audit --predicted green_horizontal --min-confidence 0.75
```

The CLI prints a compact table and can optionally write JSON:

```powershell
python -m dataset_cli ml-audit --predicted green_horizontal --min-confidence 0.75 --json-out label_audit_green_horizontal.json
```

Dry-run behavior is implicit: the command never modifies the manifest or crop files.

## UI

Extend the existing Audit tab in `dataset_review_ui.py`.

Add an audit mode selector:

- `Current class`
- `ML says class`

When mode is `Current class`, preserve current behavior: show crops whose `current_class` matches the selected class.

When mode is `ML says class`, show crops returned by `dataset_ml_audit.py` where:

- ML predicted the selected source class
- manifest `current_class` is different
- confidence is above the selected minimum

Each crop tile should display:

- row/col
- current class
- predicted class
- confidence percentage

Existing manual actions stay the same:

- select crop
- relabel selected
- delete selected
- clear selection

The UI must not relabel anything until the user explicitly selects crops and clicks `Relabel selected`.

## Error Handling

If ONNX Runtime, model, metadata, or a crop image is unavailable, the CLI returns a clear non-zero error.

In the UI, unavailable ML audit shows a status message instead of freezing or crashing the window.

Invalid class names are rejected before inference.

Missing crop files are skipped and counted in the report.

## Performance

Inference should run batched over crop images.

The UI must not do long inference on the main Qt event loop. The first implementation may use the CLI/helper path and display cached/generated results, or run the helper through a worker thread.

Default UI limit should be conservative, for example 200 rows, so one audit class does not flood the grid.

## Testing

Add focused tests for `dataset_ml_audit.py`:

- returns only rows where predicted class matches requested class and current class differs
- sorts by confidence descending
- includes label confidence and model version
- skips or reports missing crop files predictably
- rejects unknown predicted class

Add CLI tests for:

- table output
- JSON output
- no manifest mutation

Add UI-level tests only around filtering/selection behavior, not full ONNX inference.

## Failure-Mode Check

1. Model predictions can be wrong.
   - Severity: minor if the tool is review-only.
   - Mitigation: label all results as suspects and keep manual relabel explicit.

2. Audit results can become stale after model retraining.
   - Severity: minor.
   - Mitigation: include `model_version` in every report and regenerate results from the current model.

3. Running inference from the UI can freeze PyQt.
   - Severity: critical if implemented directly on the main thread.
   - Mitigation: keep inference in a pure helper and run UI inference through a worker or cached report path.

## Acceptance Criteria

- `green_horizontal` false-positive suspects can be listed without editing the manifest.
- The known pattern `current_class != green_horizontal` and `predicted_class == green_horizontal` is visible in CLI output.
- Existing Audit tab current-class behavior remains unchanged.
- Manual relabel/delete behavior remains explicit and unchanged.
- Tests cover the pure audit logic and CLI output.
