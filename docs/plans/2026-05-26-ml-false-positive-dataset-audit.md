# ML False-Positive Dataset Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:subagent-driven-development (recommended) or superpowers-optimized:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a review-only ML false-positive audit that lists crops where the current model predicts a selected class, such as `green_horizontal`, but the dataset manifest currently labels the crop as another class.
**Architecture:** Add a pure `dataset_ml_audit.py` module that loads reviewed dataset crops, runs batched ONNX inference through the current model metadata, and returns structured suspect rows. Expose it through `dataset_cli.py ml-audit`, then extend the existing `dataset_review_ui.py` Audit tab with a mode selector so the UI can show either current-class crops or ML-says-class suspects. UI relabel/delete actions stay manual and reuse existing manifest mutation paths.
**Tech Stack:** Python, PyTorch tensor preprocessing already used by `recognition_dataset.py`, ONNX Runtime, PyQt5, pytest.
**Assumptions:**
- Assumes `models/recognition_model.onnx` and `models/recognition_model.metadata.json` are the current model artifacts - will NOT diagnose old generated `label_audit_*.json` files as authoritative.
- Assumes ML output is only a suspicion signal - will NOT auto-relabel or mark crops reviewed.
- Assumes UI inference may take noticeable time - will NOT run ML audit inference on the Qt main thread.

---

## Scope And Constraints

Approved spec: `docs/specs/2026-05-26-ml-false-positive-dataset-audit-design.md`.

In scope:

- Find crops where `predicted_class == <selected class>` and `current_class != <selected class>`.
- Include confidence, label confidence, threshold, model version, crop id, source run, row, col, and current class.
- Add CLI table and optional JSON output.
- Add UI Audit mode for `Current class` versus `ML says class`.

Out of scope:

- Model retraining.
- Threshold edits in `models/recognition_model.metadata.json`.
- Live runtime recognition or move selection.
- Automatic relabeling from ML output.

Stop conditions:

- If ONNX Runtime is unavailable in the active Python environment, stop after the pure/CLI tests and report the environment blocker.
- If the UI worker cannot be made import-safe without broad PyQt refactoring, keep the CLI complete and stop before UI changes.
- If any test shows manifest mutation from `ml-audit`, stop and fix before proceeding.

Expected final behavior:

- `python -m dataset_cli ml-audit --predicted green_horizontal --min-confidence 0.75` lists suspicious crops, including rows similar to `green_bomb -> green_horizontal`.
- Existing Audit tab behavior for current classes is unchanged.
- In the UI, choosing `ML says class` and `green_horizontal` shows only crops currently labeled as another class that the model predicts as `green_horizontal`.

## File Structure

- Create `dataset_ml_audit.py`: pure ML audit engine, dataclasses, formatting, JSON serialization.
- Create `tests/test_dataset_ml_audit.py`: focused unit tests using fake prediction rows and tiny crop fixtures.
- Modify `dataset_cli.py`: add `ml-audit` command.
- Modify `tests/test_dataset_audit.py` or create `tests/test_dataset_cli_ml_audit.py`: CLI behavior and no-manifest-mutation tests.
- Modify `dataset_review_ui.py`: add Audit mode controls, ML audit worker thread, audit grid metadata captions.
- Modify `tests/test_dataset_review_ui.py`: verify UI audit filtering uses ML suspect rows and preserves current-class mode.

No Git commit steps are included because this checkout is documented as not being a Git repository.

---

### Task 1: Pure ML Audit Engine

**Files:**
- Create: `dataset_ml_audit.py`
- Create: `tests/test_dataset_ml_audit.py`

**Security flag:** `none`

**Does NOT cover:** CLI arguments, PyQt UI, model retraining, metadata threshold edits, or manifest mutation.

- [x] **Step 1: Write failing tests**

Create `tests/test_dataset_ml_audit.py` with:

```python
import json
from pathlib import Path

import numpy as np
from PIL import Image

from dataset_ml_audit import (
    MlAuditPrediction,
    audit_ml_false_positives,
    format_ml_audit_table,
)


def _entry(crop_id, run, current, row=0, col=0, reviewed=True):
    return {
        "crop_id": crop_id,
        "source_run": run,
        "row": row,
        "col": col,
        "profile": "regular",
        "original_size": [84, 84],
        "auto_class": current,
        "current_class": current,
        "reviewed": reviewed,
        "corrected": False,
        "first_seen_at": "2026-05-26T10:00:00",
        "last_reviewed_at": "2026-05-26T10:01:00" if reviewed else None,
    }


def _write_manifest(root: Path, entries):
    root.mkdir(parents=True)
    (root / "crops").mkdir()
    (root / "manifest.json").write_text(
        json.dumps({"version": 1, "entries": entries}),
        encoding="utf-8",
    )
    for entry in entries:
        Image.new("RGB", (8, 8), color=(20, 100, 20)).save(
            root / "crops" / f"{entry['crop_id']}.png"
        )


def test_audit_reports_only_requested_predicted_class_with_different_label(tmp_path):
    root = tmp_path / "dataset"
    _write_manifest(
        root,
        [
            _entry("fp_high", "run_b", "green_bomb", row=0, col=3),
            _entry("same_class", "run_a", "green_horizontal", row=0, col=4),
            _entry("other_pred", "run_c", "purple_normal", row=1, col=1),
            _entry("too_low", "run_d", "green_bomb", row=2, col=2),
            _entry("unreviewed", "run_e", "green_bomb", row=3, col=3, reviewed=False),
        ],
    )

    predictions = {
        "fp_high": MlAuditPrediction("green_horizontal", 0.9591, 0.1818, 1.01),
        "same_class": MlAuditPrediction("green_horizontal", 0.99, 0.99, 1.01),
        "other_pred": MlAuditPrediction("purple_horizontal", 0.98, 0.02, 0.8),
        "too_low": MlAuditPrediction("green_horizontal", 0.50, 0.30, 1.01),
        "unreviewed": MlAuditPrediction("green_horizontal", 0.99, 0.01, 1.01),
    }

    report = audit_ml_false_positives(
        root,
        predicted_class="green_horizontal",
        min_confidence=0.75,
        reviewed_only=True,
        prediction_provider=lambda entries, **_kwargs: predictions,
        model_version="test-model",
    )

    assert report.predicted_class == "green_horizontal"
    assert report.model_version == "test-model"
    assert report.total_entries == 5
    assert report.scanned_entries == 4
    assert report.missing_crops == 0
    assert [row.crop_id for row in report.rows] == ["fp_high"]
    row = report.rows[0]
    assert row.current_class == "green_bomb"
    assert row.predicted_class == "green_horizontal"
    assert row.confidence == 0.9591
    assert row.label_confidence == 0.1818
    assert row.threshold == 1.01
    assert row.source_run == "run_b"
    assert row.row == 0
    assert row.col == 3


def test_audit_sorts_by_confidence_and_applies_limit(tmp_path):
    root = tmp_path / "dataset"
    _write_manifest(
        root,
        [
            _entry("mid", "run_b", "green_bomb"),
            _entry("high", "run_a", "green_bomb"),
            _entry("low", "run_c", "green_bomb"),
        ],
    )
    predictions = {
        "mid": MlAuditPrediction("green_horizontal", 0.88, 0.12, 1.01),
        "high": MlAuditPrediction("green_horizontal", 0.99, 0.01, 1.01),
        "low": MlAuditPrediction("green_horizontal", 0.80, 0.20, 1.01),
    }

    report = audit_ml_false_positives(
        root,
        predicted_class="green_horizontal",
        min_confidence=0.75,
        limit=2,
        prediction_provider=lambda entries, **_kwargs: predictions,
        model_version="test-model",
    )

    assert [row.crop_id for row in report.rows] == ["high", "mid"]


def test_audit_rejects_unknown_predicted_class(tmp_path):
    root = tmp_path / "dataset"
    _write_manifest(root, [_entry("c1", "run", "green_bomb")])

    try:
        audit_ml_false_positives(
            root,
            predicted_class="not_a_class",
            prediction_provider=lambda entries, **_kwargs: {},
        )
    except ValueError as exc:
        assert "Unknown predicted class" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_audit_counts_missing_crop_files(tmp_path):
    root = tmp_path / "dataset"
    _write_manifest(root, [_entry("missing", "run", "green_bomb")])
    (root / "crops" / "missing.png").unlink()

    report = audit_ml_false_positives(
        root,
        predicted_class="green_horizontal",
        prediction_provider=lambda entries, **_kwargs: {},
    )

    assert report.missing_crops == 1
    assert report.scanned_entries == 0


def test_format_ml_audit_table_includes_class_transition(tmp_path):
    root = tmp_path / "dataset"
    _write_manifest(root, [_entry("fp", "run", "green_bomb", row=1, col=2)])
    report = audit_ml_false_positives(
        root,
        predicted_class="green_horizontal",
        prediction_provider=lambda entries, **_kwargs: {
            "fp": MlAuditPrediction("green_horizontal", 0.9591, 0.1818, 1.01)
        },
        model_version="test-model",
    )

    text = format_ml_audit_table(report)

    assert "green_bomb -> green_horizontal" in text
    assert "95.91%" in text
    assert "fp" in text
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_dataset_ml_audit.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'dataset_ml_audit'`.

- [x] **Step 3: Implement pure helper**

Create `dataset_ml_audit.py`:

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
from PIL import Image

from dataset_classes import ALL_CLASSES
from dataset_manifest import ManifestEntry, load_manifest
from ml_recognition_runtime import DEFAULT_METADATA_PATH, DEFAULT_MODEL_PATH
from recognition_dataset import IMAGE_SIZE, _to_tensor


@dataclass(frozen=True)
class MlAuditPrediction:
    predicted_class: str
    confidence: float
    label_confidence: float
    threshold: float


@dataclass(frozen=True)
class MlAuditRow:
    crop_id: str
    source_run: str
    row: int
    col: int
    current_class: str
    predicted_class: str
    confidence: float
    label_confidence: float
    threshold: float
    model_version: str | None


@dataclass(frozen=True)
class MlAuditReport:
    predicted_class: str
    min_confidence: float
    model_version: str | None
    total_entries: int
    scanned_entries: int
    missing_crops: int
    rows: list[MlAuditRow]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["rows"] = [asdict(row) for row in self.rows]
        return payload


PredictionProvider = Callable[..., dict[str, MlAuditPrediction]]


def _load_metadata(metadata_path: Path) -> dict:
    return json.loads(Path(metadata_path).read_text(encoding="utf-8"))


def _predict_with_onnx(
    entries: list[ManifestEntry],
    *,
    dataset_root: Path,
    model_path: Path,
    metadata_path: Path,
) -> dict[str, MlAuditPrediction]:
    import onnxruntime as ort  # type: ignore

    metadata = _load_metadata(metadata_path)
    classes = list(metadata["classes"])
    thresholds = metadata.get("thresholds_per_class", {})
    fallback_threshold = float(metadata.get("fallback_threshold_default", 0.9))
    class_to_index = {class_name: index for index, class_name in enumerate(classes)}

    tensors = []
    crop_ids = []
    for entry in entries:
        crop_path = dataset_root / "crops" / f"{entry.crop_id}.png"
        image = Image.open(crop_path).convert("RGB")
        tensors.append(_to_tensor(image, augment=False).numpy())
        crop_ids.append(entry.crop_id)

    if not tensors:
        return {}

    batch = np.stack(tensors).astype(np.float32)
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    logits = np.asarray(session.run(None, {input_name: batch})[0], dtype=np.float32)
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    probs = exp / exp.sum(axis=1, keepdims=True)

    predictions: dict[str, MlAuditPrediction] = {}
    for index, crop_id in enumerate(crop_ids):
        predicted_index = int(np.argmax(probs[index]))
        predicted_class = classes[predicted_index]
        label_class = entries[index].current_class
        label_index = class_to_index.get(label_class)
        label_confidence = float(probs[index, label_index]) if label_index is not None else 0.0
        predictions[crop_id] = MlAuditPrediction(
            predicted_class=predicted_class,
            confidence=float(probs[index, predicted_index]),
            label_confidence=label_confidence,
            threshold=float(thresholds.get(predicted_class, fallback_threshold)),
        )
    return predictions


def audit_ml_false_positives(
    dataset_root: Path,
    *,
    predicted_class: str,
    min_confidence: float = 0.75,
    limit: int = 0,
    reviewed_only: bool = True,
    model_path: Path = DEFAULT_MODEL_PATH,
    metadata_path: Path = DEFAULT_METADATA_PATH,
    prediction_provider: PredictionProvider | None = None,
    model_version: str | None = None,
) -> MlAuditReport:
    if predicted_class not in ALL_CLASSES:
        raise ValueError(f"Unknown predicted class: {predicted_class}")
    dataset_root = Path(dataset_root)
    model_path = Path(model_path)
    metadata_path = Path(metadata_path)
    metadata = _load_metadata(metadata_path) if metadata_path.exists() else {}
    resolved_model_version = model_version if model_version is not None else metadata.get("model_version")

    all_entries = load_manifest(dataset_root / "manifest.json")
    eligible_entries = [
        entry for entry in all_entries
        if not reviewed_only or entry.reviewed
    ]

    present_entries = []
    missing_crops = 0
    for entry in eligible_entries:
        crop_path = dataset_root / "crops" / f"{entry.crop_id}.png"
        if crop_path.is_file():
            present_entries.append(entry)
        else:
            missing_crops += 1

    provider = prediction_provider or _predict_with_onnx
    predictions = provider(
        present_entries,
        dataset_root=dataset_root,
        model_path=model_path,
        metadata_path=metadata_path,
    )

    rows: list[MlAuditRow] = []
    for entry in present_entries:
        prediction = predictions.get(entry.crop_id)
        if prediction is None:
            continue
        if prediction.predicted_class != predicted_class:
            continue
        if entry.current_class == predicted_class:
            continue
        if prediction.confidence < min_confidence:
            continue
        rows.append(
            MlAuditRow(
                crop_id=entry.crop_id,
                source_run=entry.source_run,
                row=entry.row,
                col=entry.col,
                current_class=entry.current_class,
                predicted_class=prediction.predicted_class,
                confidence=round(float(prediction.confidence), 6),
                label_confidence=round(float(prediction.label_confidence), 6),
                threshold=round(float(prediction.threshold), 6),
                model_version=resolved_model_version,
            )
        )

    rows.sort(key=lambda row: (-row.confidence, row.source_run, row.row, row.col, row.crop_id))
    if limit > 0:
        rows = rows[:limit]

    return MlAuditReport(
        predicted_class=predicted_class,
        min_confidence=float(min_confidence),
        model_version=resolved_model_version,
        total_entries=len(all_entries),
        scanned_entries=len(present_entries),
        missing_crops=missing_crops,
        rows=rows,
    )


def format_ml_audit_table(report: MlAuditReport) -> str:
    header = (
        f"predicted={report.predicted_class} "
        f"min_confidence={report.min_confidence:.2f} "
        f"model={report.model_version or 'unknown'} "
        f"suspects={len(report.rows)} scanned={report.scanned_entries} "
        f"missing_crops={report.missing_crops}"
    )
    if not report.rows:
        return header + "\nNo suspects found."
    columns = (
        f"{'confidence':>10} {'label_conf':>10} {'transition':<38} "
        f"{'run':<24} {'cell':<7} crop_id"
    )
    lines = [header, columns, "-" * len(columns)]
    for row in report.rows:
        lines.append(
            f"{row.confidence * 100:>9.2f}% "
            f"{row.label_confidence * 100:>9.2f}% "
            f"{row.current_class + ' -> ' + row.predicted_class:<38} "
            f"{row.source_run:<24} r{row.row}c{row.col:<4} {row.crop_id}"
        )
    return "\n".join(lines)
```

- [x] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_dataset_ml_audit.py -q
```

Expected: PASS.

---

### Task 2: CLI Command

**Files:**
- Modify: `dataset_cli.py`
- Create: `tests/test_dataset_cli_ml_audit.py`

**Security flag:** `none`

**Does NOT cover:** PyQt UI, live recognition, model retraining, or manifest writes.

- [x] **Step 1: Write failing CLI tests**

Create `tests/test_dataset_cli_ml_audit.py`:

```python
import json
from types import SimpleNamespace

from dataset_cli import main
from dataset_manifest import load_manifest
from dataset_ml_audit import MlAuditReport, MlAuditRow


def _write_manifest(root):
    (root / "crops").mkdir(parents=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "crop_id": "fp",
                        "source_run": "run",
                        "row": 0,
                        "col": 3,
                        "profile": "regular",
                        "original_size": [84, 84],
                        "auto_class": "green_bomb",
                        "current_class": "green_bomb",
                        "reviewed": True,
                        "corrected": False,
                        "first_seen_at": "2026-05-26T10:00:00",
                        "last_reviewed_at": "2026-05-26T10:01:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _fake_report(**kwargs):
    return MlAuditReport(
        predicted_class=kwargs.get("predicted_class", "green_horizontal"),
        min_confidence=kwargs.get("min_confidence", 0.75),
        model_version="test-model",
        total_entries=1,
        scanned_entries=1,
        missing_crops=0,
        rows=[
            MlAuditRow(
                crop_id="fp",
                source_run="run",
                row=0,
                col=3,
                current_class="green_bomb",
                predicted_class="green_horizontal",
                confidence=0.9591,
                label_confidence=0.1818,
                threshold=1.01,
                model_version="test-model",
            )
        ],
    )


def test_ml_audit_cli_prints_table_and_does_not_mutate_manifest(tmp_path, monkeypatch, capsys):
    root = tmp_path / "dataset"
    _write_manifest(root)
    before = (root / "manifest.json").read_text(encoding="utf-8")
    calls = []

    def fake_audit(dataset_root, **kwargs):
        calls.append((dataset_root, kwargs))
        return _fake_report(**kwargs)

    monkeypatch.setattr("dataset_cli.audit_ml_false_positives", fake_audit)

    code = main([
        "ml-audit",
        "--dataset-root",
        str(root),
        "--predicted",
        "green_horizontal",
        "--min-confidence",
        "0.75",
        "--limit",
        "25",
    ])

    out = capsys.readouterr().out
    assert code == 1
    assert "green_bomb -> green_horizontal" in out
    assert "95.91%" in out
    assert calls[0][1]["predicted_class"] == "green_horizontal"
    assert calls[0][1]["min_confidence"] == 0.75
    assert calls[0][1]["limit"] == 25
    assert (root / "manifest.json").read_text(encoding="utf-8") == before
    assert load_manifest(root / "manifest.json")[0].current_class == "green_bomb"


def test_ml_audit_cli_writes_json_report(tmp_path, monkeypatch):
    root = tmp_path / "dataset"
    _write_manifest(root)
    out_path = tmp_path / "audit.json"
    monkeypatch.setattr(
        "dataset_cli.audit_ml_false_positives",
        lambda dataset_root, **kwargs: _fake_report(**kwargs),
    )

    code = main([
        "ml-audit",
        "--dataset-root",
        str(root),
        "--predicted",
        "green_horizontal",
        "--json-out",
        str(out_path),
    ])

    assert code == 1
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["predicted_class"] == "green_horizontal"
    assert payload["rows"][0]["current_class"] == "green_bomb"
    assert payload["rows"][0]["predicted_class"] == "green_horizontal"
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_dataset_cli_ml_audit.py -q
```

Expected: FAIL because `dataset_cli` does not expose `ml-audit` and does not import `audit_ml_false_positives`.

- [x] **Step 3: Implement CLI command**

Modify imports at the top of `dataset_cli.py`:

```python
import json
from dataset_ml_audit import audit_ml_false_positives, format_ml_audit_table
```

Add command handler before `main()`:

```python
def _cmd_ml_audit(args: argparse.Namespace) -> int:
    report = audit_ml_false_positives(
        Path(args.dataset_root),
        predicted_class=args.predicted,
        min_confidence=args.min_confidence,
        limit=args.limit,
        reviewed_only=not args.include_unreviewed,
    )
    print(format_ml_audit_table(report))
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(report.to_dict(), indent=2),
            encoding="utf-8",
        )
        print(f"json={args.json_out}")
    return 1 if report.rows else 0
```

Add parser registration in `main()` after `normal-audit` or before final parse:

```python
    ml_audit_parser = subparsers.add_parser(
        "ml-audit",
        help="Find crops where the current ML model predicts a class but the manifest labels another class.",
    )
    ml_audit_parser.add_argument("--dataset-root", default=str(DEFAULT_DATASET_ROOT))
    ml_audit_parser.add_argument("--predicted", required=True)
    ml_audit_parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.75,
        help="Minimum ML confidence required for a suspect row.",
    )
    ml_audit_parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum rows to print/write. 0 keeps all rows.",
    )
    ml_audit_parser.add_argument(
        "--json-out",
        default=None,
        help="Optional JSON report path.",
    )
    ml_audit_parser.add_argument(
        "--include-unreviewed",
        action="store_true",
        help="Also scan unreviewed crops. Default scans reviewed training candidates.",
    )
    ml_audit_parser.set_defaults(func=_cmd_ml_audit)
```

- [x] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_dataset_cli_ml_audit.py tests/test_dataset_ml_audit.py -q
```

Expected: PASS.

- [x] **Step 5: Manual CLI smoke check on the real dataset**

Run:

```powershell
python -m dataset_cli ml-audit --predicted green_horizontal --min-confidence 0.75 --limit 20
```

Expected: exits `1` if suspects exist, prints a table with transitions such as `green_bomb -> green_horizontal`; exits `0` with `No suspects found.` if the current model no longer has suspects.

---

### Task 3: Dataset Review UI ML Audit Mode

**Files:**
- Modify: `dataset_review_ui.py`
- Modify: `tests/test_dataset_review_ui.py`

**Security flag:** `none`

**Does NOT cover:** manifest writes beyond existing explicit relabel/delete buttons; no auto-review or auto-relabel from ML predictions.

- [x] **Step 1: Write failing UI helper tests**

Append to `tests/test_dataset_review_ui.py`:

```python
from dataset_ml_audit import MlAuditReport, MlAuditRow


def test_refresh_audit_grid_current_class_mode_preserves_existing_filter(monkeypatch):
    green = _entry("run", reviewed=True, current_class="green_horizontal")
    bomb = _entry("run", reviewed=True, row=0, col=1, current_class="green_bomb")
    captured = []
    window = SimpleNamespace(
        _entries=[green, bomb],
        _dataset_root="dataset",
        _audit_mode_combo=SimpleNamespace(currentData=lambda: "current_class"),
        _audit_source_combo=SimpleNamespace(currentText=lambda: "green_horizontal"),
        _audit_confidence_spin=SimpleNamespace(value=lambda: 75),
        _audit_status_label=SimpleNamespace(setText=lambda text: captured.append(("status", text))),
        _audit_grid=SimpleNamespace(set_entries=lambda root, entries, annotations=None: captured.append(("grid", entries, annotations))),
        _refresh_audit_controls=lambda: captured.append(("controls", None)),
        _ml_audit_report=None,
    )

    ReviewWindow._refresh_audit_grid(window)

    grid_call = [item for item in captured if item[0] == "grid"][0]
    assert [entry.crop_id for entry in grid_call[1]] == [green.crop_id]
    assert grid_call[2] is None


def test_refresh_audit_grid_ml_mode_uses_report_rows(monkeypatch):
    bomb = _entry("run", reviewed=True, row=0, col=3, current_class="green_bomb")
    other = _entry("run", reviewed=True, row=0, col=4, current_class="purple_normal")
    report = MlAuditReport(
        predicted_class="green_horizontal",
        min_confidence=0.75,
        model_version="test-model",
        total_entries=2,
        scanned_entries=2,
        missing_crops=0,
        rows=[
            MlAuditRow(
                crop_id=bomb.crop_id,
                source_run=bomb.source_run,
                row=bomb.row,
                col=bomb.col,
                current_class="green_bomb",
                predicted_class="green_horizontal",
                confidence=0.9591,
                label_confidence=0.1818,
                threshold=1.01,
                model_version="test-model",
            )
        ],
    )
    captured = []
    window = SimpleNamespace(
        _entries=[bomb, other],
        _dataset_root="dataset",
        _audit_mode_combo=SimpleNamespace(currentData=lambda: "ml_says_class"),
        _audit_source_combo=SimpleNamespace(currentText=lambda: "green_horizontal"),
        _audit_confidence_spin=SimpleNamespace(value=lambda: 75),
        _audit_status_label=SimpleNamespace(setText=lambda text: captured.append(("status", text))),
        _audit_grid=SimpleNamespace(set_entries=lambda root, entries, annotations=None: captured.append(("grid", entries, annotations))),
        _refresh_audit_controls=lambda: captured.append(("controls", None)),
        _ml_audit_report=report,
    )

    ReviewWindow._refresh_audit_grid(window)

    grid_call = [item for item in captured if item[0] == "grid"][0]
    assert [entry.crop_id for entry in grid_call[1]] == [bomb.crop_id]
    assert grid_call[2][bomb.crop_id] == "green_bomb -> green_horizontal 95.91%"
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_dataset_review_ui.py -q
```

Expected: FAIL because `CropGridWidget.set_entries` does not accept annotations and `ReviewWindow._refresh_audit_grid` does not handle ML mode.

- [x] **Step 3: Extend crop tile annotations**

In `CropCellWidget.__init__`, add optional `annotation: str | None = None`, include it in tooltip and caption:

```python
    def __init__(
        self,
        dataset_root: Path,
        entry: ManifestEntry,
        annotation: Optional[str] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        ...
        tooltip = (
            f"{entry.crop_id}\nrun={entry.source_run} row={entry.row} col={entry.col}\n"
            f"auto={entry.auto_class} current={entry.current_class}"
        )
        if annotation:
            tooltip = f"{tooltip}\n{annotation}"
        self.setToolTip(tooltip)
        ...
        caption_text = f"r{entry.row} c{entry.col}"
        if annotation:
            caption_text = f"{caption_text}\n{annotation}"
        caption = QtWidgets.QLabel(caption_text)
```

In `CropGridWidget.set_entries`, accept annotations:

```python
    def set_entries(
        self,
        dataset_root: Path,
        entries: List[ManifestEntry],
        annotations: Optional[Dict[str, str]] = None,
    ) -> None:
        self._clear_widgets()
        annotations = annotations or {}
        visible_ids = {entry.crop_id for entry in entries}
        self._selected_crop_ids &= visible_ids
        for index, entry in enumerate(entries):
            widget = CropCellWidget(dataset_root, entry, annotations.get(entry.crop_id))
            ...
```

- [x] **Step 4: Add UI controls and ML report worker**

Add imports:

```python
from dataset_ml_audit import MlAuditReport, audit_ml_false_positives
```

Add constants near `_FILTER_ALL`:

```python
_AUDIT_MODE_CURRENT_CLASS = "current_class"
_AUDIT_MODE_ML_SAYS_CLASS = "ml_says_class"
```

Add worker class above `ReviewWindow`:

```python
class MlAuditWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, dataset_root: Path, predicted_class: str, min_confidence: float, limit: int):
        super().__init__()
        self._dataset_root = Path(dataset_root)
        self._predicted_class = predicted_class
        self._min_confidence = min_confidence
        self._limit = limit

    @QtCore.pyqtSlot()
    def run(self) -> None:
        try:
            report = audit_ml_false_positives(
                self._dataset_root,
                predicted_class=self._predicted_class,
                min_confidence=self._min_confidence,
                limit=self._limit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(report)
```

In `ReviewWindow.__init__`, initialize:

```python
        self._ml_audit_report: Optional[MlAuditReport] = None
        self._ml_audit_thread: Optional[QtCore.QThread] = None
        self._ml_audit_worker: Optional[MlAuditWorker] = None
```

In `_build_audit_tab`, add controls before source combo:

```python
        self._audit_mode_combo = QtWidgets.QComboBox()
        self._audit_mode_combo.addItem("Current class", _AUDIT_MODE_CURRENT_CLASS)
        self._audit_mode_combo.addItem("ML says class", _AUDIT_MODE_ML_SAYS_CLASS)
        self._audit_mode_combo.currentIndexChanged.connect(self._refresh_audit_grid)
        self._audit_confidence_spin = QtWidgets.QSpinBox()
        self._audit_confidence_spin.setRange(0, 100)
        self._audit_confidence_spin.setValue(75)
        self._audit_confidence_spin.setSuffix("%")
        self._audit_confidence_spin.valueChanged.connect(self._refresh_audit_grid)
        self._audit_ml_refresh_button = QtWidgets.QPushButton("Run ML audit")
        self._audit_ml_refresh_button.clicked.connect(self._start_ml_audit)
```

Add widgets to the layout:

```python
        controls_layout.addWidget(QtWidgets.QLabel("Mode:"))
        controls_layout.addWidget(self._audit_mode_combo)
        controls_layout.addWidget(QtWidgets.QLabel("Class:"))
        controls_layout.addWidget(self._audit_source_combo, 2)
        controls_layout.addWidget(QtWidgets.QLabel("Min:"))
        controls_layout.addWidget(self._audit_confidence_spin)
        controls_layout.addWidget(self._audit_ml_refresh_button)
```

Add methods:

```python
    def _audit_mode(self) -> str:
        if not hasattr(self, "_audit_mode_combo"):
            return _AUDIT_MODE_CURRENT_CLASS
        return self._audit_mode_combo.currentData() or _AUDIT_MODE_CURRENT_CLASS

    def _start_ml_audit(self) -> None:
        if self._ml_audit_thread is not None:
            return
        predicted_class = self._audit_source_combo.currentText()
        min_confidence = self._audit_confidence_spin.value() / 100.0
        self._audit_status_label.setText("ML audit running...")
        self._audit_ml_refresh_button.setEnabled(False)
        thread = QtCore.QThread(self)
        worker = MlAuditWorker(self._dataset_root, predicted_class, min_confidence, 200)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._finish_ml_audit)
        worker.failed.connect(self._fail_ml_audit)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._clear_ml_audit_worker)
        self._ml_audit_thread = thread
        self._ml_audit_worker = worker
        thread.start()

    def _finish_ml_audit(self, report: object) -> None:
        self._ml_audit_report = report if isinstance(report, MlAuditReport) else None
        self._refresh_audit_grid()

    def _fail_ml_audit(self, message: str) -> None:
        self._ml_audit_report = None
        self._audit_status_label.setText(f"ML audit failed: {message}")
        self._audit_grid.set_entries(self._dataset_root, [])

    def _clear_ml_audit_worker(self) -> None:
        if self._ml_audit_thread is not None:
            self._ml_audit_thread.deleteLater()
        self._ml_audit_thread = None
        self._ml_audit_worker = None
        self._audit_ml_refresh_button.setEnabled(True)
```

Replace `_refresh_audit_grid` with mode-aware logic:

```python
    def _refresh_audit_grid(self, *args) -> None:
        del args
        selected_class = self._audit_source_combo.currentText()
        if self._audit_mode() == _AUDIT_MODE_ML_SAYS_CLASS:
            report = self._ml_audit_report
            if report is None or report.predicted_class != selected_class:
                self._audit_grid.set_entries(self._dataset_root, [])
                self._audit_status_label.setText("Run ML audit for this class")
                self._refresh_audit_controls()
                return
            entries_by_id = {entry.crop_id: entry for entry in self._entries}
            rows = [
                row for row in report.rows
                if row.predicted_class == selected_class
            ]
            entries = [
                entries_by_id[row.crop_id]
                for row in rows
                if row.crop_id in entries_by_id
            ]
            annotations = {
                row.crop_id: (
                    f"{row.current_class} -> {row.predicted_class} "
                    f"{row.confidence * 100:.2f}%"
                )
                for row in rows
            }
            self._audit_grid.set_entries(self._dataset_root, entries, annotations)
            self._audit_status_label.setText(
                f"{len(entries)} ML suspects | scanned={report.scanned_entries} "
                f"missing={report.missing_crops}"
            )
            self._refresh_audit_controls()
            return

        entries = sorted(
            (entry for entry in self._entries if entry.current_class == selected_class),
            key=lambda entry: (entry.source_run, entry.row, entry.col),
        )
        self._audit_grid.set_entries(self._dataset_root, entries)
        self._refresh_audit_controls()
```

Adjust `_refresh_audit_controls` so total reflects current grid mode:

```python
        if self._audit_mode() == _AUDIT_MODE_ML_SAYS_CLASS and self._ml_audit_report:
            total = len(self._ml_audit_report.rows)
        else:
            total = sum(1 for entry in self._entries if entry.current_class == source_class)
```

- [x] **Step 5: Run UI tests**

Run:

```powershell
python -m pytest tests/test_dataset_review_ui.py -q
```

Expected: PASS.

---

### Task 4: Integrated Verification And Real Green-Horizontal Smoke Test

**Files:**
- Modify only if prior task tests reveal scoped defects.

**Security flag:** `none`

**Does NOT cover:** new features beyond the approved ML false-positive audit.

- [x] **Step 1: Run focused test set**

Run:

```powershell
python -m pytest tests/test_dataset_ml_audit.py tests/test_dataset_cli_ml_audit.py tests/test_dataset_review_ui.py -q
```

Expected: PASS.

- [x] **Step 2: Run adjacent recognition tests**

Run:

```powershell
python -m pytest tests/test_ml_recognition_runtime.py tests/test_recognition_metrics.py -q
```

Expected: PASS.

- [x] **Step 3: Run real CLI smoke test**

Run:

```powershell
python -m dataset_cli ml-audit --predicted green_horizontal --min-confidence 0.75 --limit 20
```

Expected:

- Exit code `1` if suspects exist, `0` if none exist.
- Output includes header fields `predicted=green_horizontal`, `suspects=`, `scanned=`, and `missing_crops=`.
- If the current model still has the known false-positive pattern, output includes a transition like `green_bomb -> green_horizontal`.
- The command does not modify `data/recognition_dataset/manifest.json`.

- [ ] **Step 4: Optional manual UI smoke check**

Not run in the automated verification pass; the UI behavior is covered by focused unit tests and code review.

Run:

```powershell
python -m dataset_cli review
```

Expected manual checks:

- Audit tab opens normally.
- `Current class` + `green_horizontal` shows current `green_horizontal` crops as before.
- `ML says class` + `green_horizontal` shows an empty grid until `Run ML audit` is clicked.
- After `Run ML audit`, suspects appear with captions like `green_bomb -> green_horizontal 95.91%`.
- Selecting a suspect does not mutate the manifest until `Relabel selected` or `Delete selected` is clicked.

- [ ] **Step 5: Final full regression gate**

Ran `python -m pytest -q --tb=short`: 632 passed, 14 failed. Failures were captured as pre-existing/unrelated groups (`tests/test_dataset_normal_audit.py`, dataset label-integrity fixture drift, and full-suite-only PyTorch import failures). Focused feature tests and adjacent recognition tests were rerun afterward and passed.

Run:

```powershell
python -m pytest -q
```

Expected: PASS. If unrelated failures appear, capture the failing test names and rerun the focused tests from Steps 1 and 2 to prove this feature remains green.

---

## Self-Review

Spec coverage:

- Pure helper covers the approved ML false-positive detection and structured output.
- CLI covers the requested script path and JSON export.
- UI task covers the Audit tab mode switch and preserves current-class behavior.
- Verification covers real `green_horizontal` smoke behavior and no manifest mutation.

Placeholder scan:

- No `TBD`, `TODO`, `implement later`, or unspecified test commands remain.

Type consistency:

- `MlAuditPrediction`, `MlAuditRow`, and `MlAuditReport` are introduced in Task 1 and reused consistently in Tasks 2 and 3.
- UI annotation keys are `crop_id` strings, matching `CropGridWidget` selection state.

Scope-reduction scan:

- The only optional step is manual UI smoke verification; automated CLI and unit tests are required.
- No "basic", "for now", or "minimal" scope downgrades are used.

Fresh-chat handoff check:

- This plan includes the goal, architecture, scope, non-goals, constraints, relevant files, task order, exact commands, stop conditions, and expected final behavior.
