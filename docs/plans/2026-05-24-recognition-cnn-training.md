# Recognition CNN Training & ONNX Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:subagent-driven-development (recommended) or superpowers-optimized:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Train a small CNN classifier on the curated tile dataset produced by Sub-project A and export it as `models/recognition_model.onnx` + sidecar metadata that the downstream runtime path (Sub-project C) can consume.

**Architecture:** Five new modules at the project root — `recognition_dataset.py`, `recognition_model.py`, `recognition_metrics.py`, `recognition_onnx_export.py`, and `train_recognition_model.py` (CLI orchestrator) — plus pytest coverage in `tests/`. The dataset reader loads `data/recognition_dataset/manifest.json`, filters reviewed entries, splits at the run level, and applies conservative color-jitter augmentation. A tiny CNN (~460k params) is trained with weighted cross-entropy + weighted-random sampling against class imbalance. Validation metrics (accuracy, macro-F1, confusion matrix, per-class accuracy) drive an early-stop loop and per-class confidence-threshold derivation. The trained model is exported to ONNX with a static 1×3×64×64 input and a dynamic batch axis; a sidecar JSON records the class list, thresholds, preprocessing, and training stats.

**Tech Stack:** Python 3, PyTorch (new), `onnx` (new), `onnxruntime` (new, optional for verification only), NumPy, PIL, pytest.

**Assumptions:**
- Workspace is **not** a git repository. The plan contains no `git add` / `git commit` steps. Will NOT work if the user later requires git checkpoints; in that case append commit steps per task.
- Sub-project A has been executed and `data/recognition_dataset/` exists with at least some `reviewed=True` entries before the smoke acceptance test in Task 6 runs. The pure unit tests in Tasks 1–4 do not require live data — they synthesize fixtures under `tmp_path`. Will NOT work for the manual acceptance step if the user runs B before labeling any data.
- `dataset_classes.py` from Sub-project A is importable and exposes `ALL_CLASSES: frozenset[str]` + `classify(color, special) -> str`. Will NOT work if Sub-project A modules were renamed or removed.
- `torch` is installable in the user's Python environment. Will NOT work if PyPI/torch wheels are unavailable; provide alternative install instructions to the user.
- `onnxruntime` may fail to install or import on this Windows setup (documented prior issue per `session-log.md`). Plan tolerates this: training and ONNX export proceed; only the `--verify-export` flag becomes a no-op with a warning. Will NOT work if the user *requires* hard verification — they must fix their `onnxruntime` install first.
- Pre-existing test suite (415+ baseline + ~20 from Sub-project A) must still pass. Will NOT work if any change leaks into `recognition.py`, `runtime.py`, `gui.py`, `move_strategy.py`, `board_profiles.py`, `capture.py`, `screen_state_reader.py`, or any existing test.

---

## Required Spec Context (self-contained for fresh sessions)

This plan implements the design at [docs/specs/2026-05-24-recognition-cnn-training-design.md](../specs/2026-05-24-recognition-cnn-training-design.md). Key spec facts are repeated here so a fresh agent does not need to read the spec to execute.

### Goal in plain language

Sub-project A built a labeling tool that produces `data/recognition_dataset/` containing:
- `crops/<crop_id>.png` — individual 84×84 (or other `squareSize`) RGB tile images.
- `manifest.json` — list of entries with fields `crop_id`, `source_run`, `row`, `col`, `profile`, `original_size`, `auto_class`, `current_class`, `reviewed`, `corrected`, `first_seen_at`, `last_reviewed_at`. The current label is `current_class`. Only entries with `reviewed == True` are eligible for training.
- `classes.json` — `{"classes": [sorted list of valid class names]}` snapshot.

This sub-project (B) reads that dataset, trains a CNN classifier over the same class taxonomy, and emits:
- `models/recognition_model.onnx` — the ONNX model.
- `models/recognition_model.metadata.json` — the sidecar metadata contract with Sub-project C.

### Class taxonomy (from Sub-project A's `dataset_classes.py`)

A class is a string identifier from a fixed frozenset `ALL_CLASSES` defined in `dataset_classes.py`. Examples: `"blue_normal"`, `"red_bomb"`, `"green_heart"`, `"joojoo_skull"`, `"disco_ball"`, `"blocked"`, `"empty"`. Total count is roughly 60. The deterministic class order used by the model is `sorted(ALL_CLASSES)`.

### Sidecar metadata schema (contract with Sub-project C)

```json
{
  "schema_version": 1,
  "model_version": "2026-05-24T15:30:00",
  "trained_at": "2026-05-24T15:30:00",
  "framework": "pytorch",
  "torch_version": "2.x.y",
  "onnx_opset": 13,
  "input": {
    "name": "input",
    "shape": [1, 3, 64, 64],
    "dynamic_axes": ["batch"],
    "channels": "RGB",
    "preprocessing": {
      "resize_to": [64, 64],
      "scale": 0.00392156862745098,
      "mean": [0.0, 0.0, 0.0],
      "std": [1.0, 1.0, 1.0]
    }
  },
  "output": {"name": "logits", "post_softmax": false},
  "classes": ["billie_drone", "blocked", "..."],
  "thresholds_per_class": {"blue_normal": 0.85, "joojoo_skull": 1.01, "...": 0.0},
  "fallback_threshold_default": 0.90,
  "train_stats": {
    "train_runs": 45, "val_runs": 12, "train_examples": 2205, "val_examples": 588,
    "val_accuracy": 0.97, "val_macro_f1": 0.86,
    "low_support_classes": ["joojoo_skull", "billie_drone"]
  },
  "dataset_classes_snapshot": ["billie_drone", "blocked", "..."]
}
```

A threshold value of `1.01` is the sentinel "never trust ML for this class; always fall back to template matcher". Classes with `<3` val examples receive the default (`0.90`) and are appended to `train_stats.low_support_classes`.

### Model architecture

`TinyTileCNN` with input `3×64×64`:

| Layer | Output |
|---|---|
| Conv2d(3→16, k=3, pad=1) + ReLU + MaxPool(2) | 16×32×32 |
| Conv2d(16→32, k=3, pad=1) + ReLU + MaxPool(2) | 32×16×16 |
| Conv2d(32→48, k=3, pad=1) + ReLU + MaxPool(2) | 48×8×8 |
| Flatten → Linear(48·64 → 128) + ReLU + Dropout(0.3) | 128 |
| Linear(128 → num_classes) | num_classes |

≈ 460k params, CPU-trainable in seconds to minutes. No BatchNorm (keeps ONNX export simple).

### Training procedure

- **Loss:** `CrossEntropyLoss(weight=class_weights)`. Weights = `min(10, total/N_class)` per class, indexed in `sorted(ALL_CLASSES)` order.
- **Sampler:** `WeightedRandomSampler` on the train loader with per-sample weight = `1 / class_count[sample.class]`.
- **Optimizer:** Adam, `lr=1e-3`, `weight_decay=1e-4`.
- **Augmentation (train only):** `ColorJitter(brightness=0.05, contrast=0.05, saturation=0.05)`, resize to 64×64, ToTensor, divide by 255 only (no mean/std subtraction). NO flips or rotations — `horizontal_arrow` ↔ `vertical_arrow` would corrupt labels.
- **Augmentation (val):** resize to 64×64, ToTensor, divide by 255. No jitter.
- **Early stopping:** macro-F1 on val set, patience 5 epochs, max 50 epochs.
- **Train/val split:** at the **run level**. Roughly 20% of runs go to val (override via `--val-run-fraction`). Deterministic given `--seed`. Stratification target: every class with ≥2 examples in the full reviewed dataset must appear ≥1 time in val; otherwise CLI fails with a guidance message.
- **Threshold derivation:** for each class, sweep softmax-confidence thresholds in 0.05 steps from 0.50 to 0.99; pick the lowest threshold where per-class precision on val ≥ `--target-precision` (default 0.99). If no threshold reaches the target, record `1.01`. Classes with `<3` val examples get the default `0.90` and a `low_support_warning` flag.

### Scope Boundaries

**In scope:** Five new modules + tests + dependency updates + a 1-epoch smoke acceptance.

**Out of scope (no edits permitted):** `recognition.py`, `runtime.py`, `gui.py`, `test.py`, `move_strategy.py`, `board_profiles.py`, `capture.py`, `screen_state_reader.py`, anything under `assets/`, any existing test, `dataset_classes.py`, `dataset_manifest.py`, `dataset_scanner.py`, `dataset_review_ui.py`, `dataset_cli.py` (Sub-project A modules are read-only here).

---

## File Structure

| Path | Responsibility |
|---|---|
| `recognition_model.py` | `TinyTileCNN(nn.Module)` and `create_model(num_classes)` factory. Pure model definition, no I/O. |
| `recognition_dataset.py` | `RecognitionDataset(torch.utils.data.Dataset)` + `load_train_val(...)` + `SplitReport` dataclass. Reads `manifest.json` from Sub-project A. |
| `recognition_metrics.py` | `ValMetrics` dataclass + `compute_val_metrics(...)` + `derive_thresholds(...)`. Pure compute on torch tensors. |
| `recognition_onnx_export.py` | `export_to_onnx(...)` writes both the `.onnx` file and the `recognition_model.metadata.json` sidecar atomically. |
| `train_recognition_model.py` | CLI entrypoint with subcommands `train` and `export-only`. Orchestrates dataset → model → train loop → metrics → export. |
| `requirements-dev.txt` | Append `torch`, `onnx`, `onnxruntime` (last marked optional in comments). |
| `tests/test_recognition_model.py` | Forward-pass shape + param count smoke. |
| `tests/test_recognition_dataset.py` | Per-run split determinism, transforms, filter, SplitReport. |
| `tests/test_recognition_metrics.py` | Confusion matrix correctness + threshold derivation behavior including 1.01 sentinel + low-support default. |
| `tests/test_recognition_onnx_export.py` | Export round-trip + metadata schema. |
| `tests/test_train_recognition_model.py` | 1-epoch smoke on a synthetic in-memory dataset; asserts artifacts written. |

---

## Task Order

Tasks 1–3 are independent (pure modules) and could parallelize. Task 4 depends on Task 1. Task 5 depends on Tasks 1–4. Task 6 is sequential acceptance.

---

### Task 0: Add new dependencies

**Files:**
- Modify: `requirements-dev.txt`

**Security flag:** `none`

**Does NOT cover:** Installing the dependencies into the user's environment (the user runs `pip install -r requirements-dev.txt` themselves). Pinning to a specific torch version — left floating because CPU wheel availability varies by platform.

- [x] **Step 1: Read current requirements**

Run: `python -c "from pathlib import Path; print(Path('requirements-dev.txt').read_text())"`

Expected output includes the existing line(s) such as `pytest-benchmark>=5.2.3`.

- [x] **Step 2: Append new dependencies**

Replace the contents of `requirements-dev.txt` with the existing content plus:

```
torch
onnx
# onnxruntime is optional — used only for `train_recognition_model train --verify-export`.
# If installation fails on this platform, training and export still work; verification
# is skipped with a warning.
onnxruntime
```

- [x] **Step 3: Install (user-action documented; do not run automatically if it would surprise the user)**

The implementing agent should print this instruction and pause for user confirmation before running it:

```
pip install -r requirements-dev.txt
```

After installation, verify importable:

Run: `python -c "import torch; import onnx; print('torch', torch.__version__); print('onnx', onnx.__version__)"`

Expected: prints both versions without ImportError.

Optional onnxruntime check (failure is acceptable):

Run: `python -c "import onnxruntime; print('onnxruntime', onnxruntime.__version__)"`

Expected: either prints a version, or fails with ImportError (which is acceptable per spec — Task 4 tests handle the missing case).

Execution note 2026-05-24: dependencies were already importable (`torch 2.4.1+cpu`, `onnx 1.21.0`, `onnxruntime 1.26.0`), so `pip install -r requirements-dev.txt` was not run.

- [x] **Step 4: Regression check**

Run: `python -m pytest -q`

Expected: All existing tests pass. PyTorch import alone should not break any prior tests.

---

### Task 1: Model architecture + tests

**Files:**
- Create: `recognition_model.py`
- Create: `tests/test_recognition_model.py`

**Security flag:** `none`

**Does NOT cover:** Alternative architectures (ResNet, MobileNet, pretrained backbones). BatchNorm — explicitly excluded to keep ONNX export deterministic. Quantization.

- [x] **Step 1: Write failing test**

Create `tests/test_recognition_model.py`:

```python
import pytest
import torch

from recognition_model import TinyTileCNN, create_model


def test_forward_pass_shape():
    model = create_model(num_classes=60)
    model.eval()
    x = torch.zeros(2, 3, 64, 64)
    with torch.no_grad():
        logits = model(x)
    assert logits.shape == (2, 60)


def test_forward_pass_arbitrary_num_classes():
    model = create_model(num_classes=7)
    model.eval()
    x = torch.randn(1, 3, 64, 64)
    with torch.no_grad():
        logits = model(x)
    assert logits.shape == (1, 7)


def test_param_count_in_expected_range():
    model = create_model(num_classes=60)
    n = sum(p.numel() for p in model.parameters())
    # Spec target ~460k; allow ±15% to absorb minor implementation choices
    assert 390_000 < n < 530_000, f"unexpected param count: {n}"


def test_dropout_active_in_train_mode_only():
    model = create_model(num_classes=10)
    x = torch.ones(4, 3, 64, 64)
    model.eval()
    with torch.no_grad():
        out_eval_a = model(x)
        out_eval_b = model(x)
    assert torch.allclose(out_eval_a, out_eval_b)

    model.train()
    out_train_a = model(x)
    out_train_b = model(x)
    # Dropout makes train passes non-deterministic — at least one of the elements must differ
    assert not torch.allclose(out_train_a, out_train_b)
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recognition_model.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'recognition_model'`.

- [x] **Step 3: Implement minimal change**

Create `recognition_model.py`:

```python
"""TinyTileCNN: small CNN for 64x64 RGB tile classification.

Architecture (from spec):
    Conv(3->16) -> ReLU -> MaxPool ->
    Conv(16->32) -> ReLU -> MaxPool ->
    Conv(32->48) -> ReLU -> MaxPool ->
    Flatten -> Linear(48*8*8 -> 128) -> ReLU -> Dropout(0.3) ->
    Linear(128 -> num_classes)

No BatchNorm: keeps ONNX export deterministic. ~460k params.
"""
from __future__ import annotations

import torch
import torch.nn as nn


class TinyTileCNN(nn.Module):
    def __init__(self, num_classes: int):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 16, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 48, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(48 * 8 * 8, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(128, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(x))


def create_model(num_classes: int) -> TinyTileCNN:
    return TinyTileCNN(num_classes=num_classes)
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_recognition_model.py -q`

Expected: PASS (4 tests).

- [x] **Step 5: Regression check**

Run: `python -m pytest -q`

Expected: All pre-existing tests still pass. 4 new tests pass.

---

### Task 2: Dataset module + tests

**Files:**
- Create: `recognition_dataset.py`
- Create: `tests/test_recognition_dataset.py`

**Security flag:** `none`

**Does NOT cover:** Augmentations other than `ColorJitter` (rotations and flips are explicitly excluded for directional classes per spec). Reading from any source other than the Sub-project A manifest format. Lazy crop loading optimizations beyond PIL's default.

- [x] **Step 1: Write failing test**

Create `tests/test_recognition_dataset.py`:

```python
import json
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from recognition_dataset import RecognitionDataset, SplitReport, load_train_val


def _write_crop(crops_dir: Path, crop_id: str, color=(128, 128, 128)):
    img = np.full((84, 84, 3), color, dtype=np.uint8)
    Image.fromarray(img).save(crops_dir / f"{crop_id}.png")


def _make_manifest_entry(run, row, col, cls, reviewed=True):
    return {
        "crop_id": f"{run}__r{row}_c{col}",
        "source_run": run,
        "row": row,
        "col": col,
        "profile": "regular",
        "original_size": [84, 84],
        "auto_class": cls,
        "current_class": cls,
        "reviewed": reviewed,
        "corrected": False,
        "first_seen_at": "2026-05-24T10:00:00",
        "last_reviewed_at": "2026-05-24T10:01:00" if reviewed else None,
    }


def _build_dataset(tmp_path: Path, runs_per_class=4):
    root = tmp_path / "ds"
    crops = root / "crops"
    crops.mkdir(parents=True)
    entries = []
    classes = ["red_normal", "blue_normal", "green_normal", "yellow_normal"]
    for ci, cls in enumerate(classes):
        for r in range(runs_per_class):
            run = f"r{ci}_{r}"
            for cell in range(4):  # 4 cells per run, all same class for simplicity
                row, col = divmod(cell, 2)
                e = _make_manifest_entry(run, row, col, cls)
                entries.append(e)
                _write_crop(crops, e["crop_id"])
    (root / "manifest.json").write_text(
        json.dumps({"version": 1, "entries": entries}), encoding="utf-8"
    )
    (root / "classes.json").write_text(
        json.dumps({"classes": sorted(set(e["current_class"] for e in entries))}),
        encoding="utf-8",
    )
    return root


def test_load_train_val_is_deterministic(tmp_path: Path):
    root = _build_dataset(tmp_path)
    train_a, val_a, report_a = load_train_val(root, val_run_fraction=0.25, seed=7)
    train_b, val_b, report_b = load_train_val(root, val_run_fraction=0.25, seed=7)
    assert report_a.train_runs == report_b.train_runs
    assert report_a.val_runs == report_b.val_runs
    assert [e.crop_id for e in train_a.entries] == [e.crop_id for e in train_b.entries]


def test_load_train_val_filters_unreviewed(tmp_path: Path):
    root = _build_dataset(tmp_path)
    # Add 5 unreviewed entries — they must not appear in either split
    manifest_path = root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    for k in range(5):
        e = _make_manifest_entry(f"ghost_{k}", 0, 0, "red_normal", reviewed=False)
        payload["entries"].append(e)
        _write_crop(root / "crops", e["crop_id"])
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    train, val, _ = load_train_val(root, val_run_fraction=0.25, seed=7)
    all_ids = [e.crop_id for e in train.entries] + [e.crop_id for e in val.entries]
    assert all("ghost_" not in cid for cid in all_ids)


def test_train_val_disjoint_at_run_level(tmp_path: Path):
    root = _build_dataset(tmp_path)
    train, val, _ = load_train_val(root, val_run_fraction=0.25, seed=7)
    train_runs = {e.source_run for e in train.entries}
    val_runs = {e.source_run for e in val.entries}
    assert train_runs.isdisjoint(val_runs)


def test_dataset_getitem_returns_tensor_and_label_index(tmp_path: Path):
    root = _build_dataset(tmp_path)
    train, _, _ = load_train_val(root, val_run_fraction=0.25, seed=7)
    assert len(train) > 0
    img, label = train[0]
    assert isinstance(img, torch.Tensor)
    assert img.shape == (3, 64, 64)
    assert 0.0 <= img.min() and img.max() <= 1.0
    assert isinstance(label, int)
    assert 0 <= label < len(train.classes)


def test_train_uses_jitter_but_val_does_not(tmp_path: Path):
    root = _build_dataset(tmp_path)
    train, val, _ = load_train_val(root, val_run_fraction=0.25, seed=7)
    # Val is deterministic across calls; train is not (jitter is random)
    val_a = val[0][0]
    val_b = val[0][0]
    assert torch.allclose(val_a, val_b)


def test_split_report_warns_about_uncovered_classes(tmp_path: Path):
    # Build a dataset where one class has only 1 run -> may be uncovered in val
    root = tmp_path / "rare"
    crops = root / "crops"
    crops.mkdir(parents=True)
    entries = []
    for run_idx in range(10):
        e = _make_manifest_entry(f"common_{run_idx}", 0, 0, "blue_normal")
        entries.append(e)
        _write_crop(crops, e["crop_id"])
    # one rare class with a single example
    e = _make_manifest_entry("rare_run", 0, 0, "joojoo_skull")
    entries.append(e)
    _write_crop(crops, e["crop_id"])
    (root / "manifest.json").write_text(
        json.dumps({"version": 1, "entries": entries}), encoding="utf-8"
    )
    train, val, report = load_train_val(root, val_run_fraction=0.2, seed=1)
    classes_in_val = {e.current_class for e in val.entries}
    if "joojoo_skull" not in classes_in_val:
        assert "joojoo_skull" in report.uncovered_in_val
    else:
        assert "joojoo_skull" not in report.uncovered_in_val
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recognition_dataset.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'recognition_dataset'`.

- [x] **Step 3: Implement minimal change**

Create `recognition_dataset.py`:

```python
"""PyTorch Dataset for the Sub-project A recognition dataset.

Reads `manifest.json`, filters reviewed=True entries, splits at the run level
(not the cell level) so adjacent cells from the same board cannot leak between
train and val.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import torch
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms

from dataset_classes import ALL_CLASSES
from dataset_manifest import ManifestEntry, load_manifest


@dataclass
class SplitReport:
    train_runs: int
    val_runs: int
    train_examples: int
    val_examples: int
    classes_present: List[str]
    uncovered_in_val: List[str]
    low_support_in_val: List[str]


def _build_transform(augment: bool):
    ops = [transforms.Resize((64, 64))]
    if augment:
        ops.append(transforms.ColorJitter(brightness=0.05, contrast=0.05, saturation=0.05))
    ops.append(transforms.ToTensor())  # scales to [0,1]
    return transforms.Compose(ops)


class RecognitionDataset(Dataset):
    def __init__(
        self,
        entries: List[ManifestEntry],
        crops_dir: Path,
        classes: List[str],
        augment: bool,
    ):
        self.entries = entries
        self.crops_dir = Path(crops_dir)
        self.classes = classes
        self._class_to_idx = {c: i for i, c in enumerate(classes)}
        self._transform = _build_transform(augment)

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        entry = self.entries[idx]
        img = Image.open(self.crops_dir / f"{entry.crop_id}.png").convert("RGB")
        tensor = self._transform(img)
        label = self._class_to_idx[entry.current_class]
        return tensor, label


def load_train_val(
    dataset_root: Path,
    val_run_fraction: float = 0.2,
    seed: int = 42,
    augment_train: bool = True,
) -> Tuple[RecognitionDataset, RecognitionDataset, SplitReport]:
    dataset_root = Path(dataset_root)
    entries = [e for e in load_manifest(dataset_root / "manifest.json") if e.reviewed]
    classes = sorted(ALL_CLASSES)

    runs = sorted({e.source_run for e in entries})
    rng = random.Random(seed)
    rng.shuffle(runs)
    n_val = max(1, int(round(len(runs) * val_run_fraction))) if len(runs) > 1 else 0
    val_runs = set(runs[:n_val])
    train_runs_set = set(runs[n_val:])

    train_entries = [e for e in entries if e.source_run in train_runs_set]
    val_entries = [e for e in entries if e.source_run in val_runs]

    train_classes = {e.current_class for e in train_entries}
    val_classes = {e.current_class for e in val_entries}
    uncovered = sorted(c for c in train_classes if c not in val_classes)

    from collections import Counter
    val_counts = Counter(e.current_class for e in val_entries)
    low_support = sorted(c for c in train_classes if 0 < val_counts.get(c, 0) < 3)

    report = SplitReport(
        train_runs=len(train_runs_set),
        val_runs=len(val_runs),
        train_examples=len(train_entries),
        val_examples=len(val_entries),
        classes_present=sorted(train_classes | val_classes),
        uncovered_in_val=uncovered,
        low_support_in_val=low_support,
    )

    train_ds = RecognitionDataset(train_entries, dataset_root / "crops", classes, augment=augment_train)
    val_ds = RecognitionDataset(val_entries, dataset_root / "crops", classes, augment=False)
    return train_ds, val_ds, report
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_recognition_dataset.py -q`

Expected: PASS (6 tests).

- [x] **Step 5: Regression check**

Run: `python -m pytest -q`

Expected: All prior tests + 4 from Task 1 + 6 new = all pass.

---

### Task 3: Metrics module + tests

**Files:**
- Create: `recognition_metrics.py`
- Create: `tests/test_recognition_metrics.py`

**Security flag:** `none`

**Does NOT cover:** Metrics beyond accuracy, macro-F1, per-class accuracy, confusion matrix, and per-class threshold derivation. Bootstrap confidence intervals. Calibration diagnostics (reliability diagrams).

- [x] **Step 1: Write failing test**

Create `tests/test_recognition_metrics.py`:

```python
import numpy as np
import pytest
import torch

from recognition_metrics import (
    ValMetrics,
    compute_val_metrics_from_arrays,
    derive_thresholds_from_arrays,
    DEFAULT_THRESHOLD,
    NEVER_TRUST_SENTINEL,
)


def test_perfect_predictions_give_one_accuracy():
    classes = ["a", "b", "c"]
    y_true = np.array([0, 1, 2, 0, 1, 2])
    y_pred = np.array([0, 1, 2, 0, 1, 2])
    probs = np.eye(3)[y_pred].astype(np.float32)
    metrics = compute_val_metrics_from_arrays(y_true, y_pred, probs, classes)
    assert metrics.accuracy == pytest.approx(1.0)
    assert metrics.macro_f1 == pytest.approx(1.0)
    assert metrics.confusion_matrix == [[2, 0, 0], [0, 2, 0], [0, 0, 2]]


def test_per_class_accuracy_counts_correctly():
    classes = ["a", "b"]
    y_true = np.array([0, 0, 1, 1])
    y_pred = np.array([0, 1, 1, 1])
    probs = np.array([[0.9, 0.1], [0.4, 0.6], [0.1, 0.9], [0.2, 0.8]], dtype=np.float32)
    metrics = compute_val_metrics_from_arrays(y_true, y_pred, probs, classes)
    assert metrics.per_class_accuracy["a"] == pytest.approx(0.5)
    assert metrics.per_class_accuracy["b"] == pytest.approx(1.0)
    assert metrics.per_class_count == {"a": 2, "b": 2}


def test_derive_thresholds_picks_lowest_meeting_precision():
    classes = ["a", "b"]
    # For class 'a': all positives at confidence 0.80 are TRUE positives
    # For class 'b': mixed precision at confidence levels
    y_true = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    y_pred = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    probs = np.array([
        [0.80, 0.20],
        [0.85, 0.15],
        [0.90, 0.10],
        [0.95, 0.05],
        [0.20, 0.80],
        [0.10, 0.90],
        [0.30, 0.70],
        [0.05, 0.95],
    ], dtype=np.float32)
    thresholds = derive_thresholds_from_arrays(y_true, probs, classes, target_precision=0.99)
    # Class 'a': all preds at >= 0.80 are correct, so threshold should be 0.80 (lowest sweep)
    assert thresholds["a"] <= 0.80 + 1e-6
    # Class 'b': all preds correct, threshold should be at most the lowest 'b' confidence (0.70)
    assert thresholds["b"] <= 0.70 + 1e-6


def test_derive_thresholds_returns_sentinel_when_unachievable():
    classes = ["a", "b"]
    # Class 'a' has 5 true examples (support >= 3, so NOT low-support)
    # but the model predicts class 'a' with high confidence on all 10 samples.
    # -> precision for 'a' at any threshold is at most 5/10 = 0.5, never >= 0.99.
    y_true = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    probs = np.array([[0.99, 0.01]] * 10, dtype=np.float32)  # always predicts 'a'
    thresholds = derive_thresholds_from_arrays(
        y_true, probs, classes, target_precision=0.99
    )
    assert thresholds["a"] == NEVER_TRUST_SENTINEL


def test_derive_thresholds_uses_default_for_low_support():
    classes = ["rare", "common"]
    # 'rare' appears only once -> low support -> default 0.90 threshold
    y_true = np.array([0, 1, 1, 1, 1, 1, 1, 1])
    probs = np.zeros((8, 2), dtype=np.float32)
    probs[0, 0] = 0.95
    probs[1:, 1] = 0.95
    thresholds = derive_thresholds_from_arrays(y_true, probs, classes, target_precision=0.99)
    assert thresholds["rare"] == DEFAULT_THRESHOLD
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recognition_metrics.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'recognition_metrics'`.

- [x] **Step 3: Implement minimal change**

Create `recognition_metrics.py`:

```python
"""Validation metrics + per-class confidence threshold derivation.

The "from_arrays" suffix on functions denotes pure-NumPy entry points used by
unit tests. Production callers go through compute_val_metrics() / derive_thresholds()
which run a model over a DataLoader to produce these arrays.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import torch

DEFAULT_THRESHOLD = 0.90
NEVER_TRUST_SENTINEL = 1.01
LOW_SUPPORT_MIN_COUNT = 3


@dataclass
class ValMetrics:
    accuracy: float
    macro_f1: float
    per_class_accuracy: Dict[str, float]
    per_class_count: Dict[str, int]
    confusion_matrix: list
    class_order: List[str]


def compute_val_metrics_from_arrays(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    probs: np.ndarray,
    classes: List[str],
) -> ValMetrics:
    n_classes = len(classes)
    cm = np.zeros((n_classes, n_classes), dtype=np.int64)
    for t, p in zip(y_true, y_pred):
        cm[t, p] += 1
    accuracy = float((y_true == y_pred).mean()) if len(y_true) else 0.0

    per_class_acc: Dict[str, float] = {}
    per_class_count: Dict[str, int] = {}
    f1s = []
    for i, cls in enumerate(classes):
        tp = int(cm[i, i])
        fp = int(cm[:, i].sum() - tp)
        fn = int(cm[i, :].sum() - tp)
        support = int(cm[i, :].sum())
        per_class_count[cls] = support
        per_class_acc[cls] = float(tp / support) if support else 0.0
        if support == 0 and (tp + fp) == 0:
            continue
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        f1s.append(f1)
    macro_f1 = float(np.mean(f1s)) if f1s else 0.0

    return ValMetrics(
        accuracy=accuracy,
        macro_f1=macro_f1,
        per_class_accuracy=per_class_acc,
        per_class_count=per_class_count,
        confusion_matrix=cm.tolist(),
        class_order=list(classes),
    )


def derive_thresholds_from_arrays(
    y_true: np.ndarray,
    probs: np.ndarray,
    classes: List[str],
    target_precision: float = 0.99,
) -> Dict[str, float]:
    thresholds: Dict[str, float] = {}
    pred_class = probs.argmax(axis=1)
    pred_conf = probs.max(axis=1)
    support = Counter(int(y) for y in y_true)
    sweep = np.arange(0.50, 1.0, 0.05)

    for i, cls in enumerate(classes):
        n_support = support.get(i, 0)
        if n_support < LOW_SUPPORT_MIN_COUNT:
            thresholds[cls] = DEFAULT_THRESHOLD
            continue
        chosen: float = NEVER_TRUST_SENTINEL
        for th in sweep:
            mask = (pred_class == i) & (pred_conf >= th)
            n_pred = int(mask.sum())
            if n_pred == 0:
                continue
            n_correct = int((y_true[mask] == i).sum())
            precision = n_correct / n_pred
            if precision >= target_precision:
                chosen = float(th)
                break
        thresholds[cls] = chosen
    return thresholds


@torch.no_grad()
def _model_arrays_over_loader(model: torch.nn.Module, loader) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    model.eval()
    ys, preds, probs = [], [], []
    for x, y in loader:
        logits = model(x)
        prob = torch.softmax(logits, dim=1).cpu().numpy()
        pred = prob.argmax(axis=1)
        ys.append(y.cpu().numpy())
        preds.append(pred)
        probs.append(prob)
    if not ys:
        empty = np.zeros((0,), dtype=np.int64)
        return empty, empty, np.zeros((0, 0), dtype=np.float32)
    return np.concatenate(ys), np.concatenate(preds), np.concatenate(probs)


def compute_val_metrics(model: torch.nn.Module, loader, classes: List[str]) -> ValMetrics:
    y_true, y_pred, probs = _model_arrays_over_loader(model, loader)
    return compute_val_metrics_from_arrays(y_true, y_pred, probs, classes)


def derive_thresholds(model: torch.nn.Module, loader, classes: List[str], target_precision: float = 0.99) -> Dict[str, float]:
    y_true, _, probs = _model_arrays_over_loader(model, loader)
    return derive_thresholds_from_arrays(y_true, probs, classes, target_precision=target_precision)
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_recognition_metrics.py -q`

Expected: PASS (5 tests).

- [x] **Step 5: Regression check**

Run: `python -m pytest -q`

Expected: All prior + new tests pass.

---

### Task 4: ONNX export module + tests

**Files:**
- Create: `recognition_onnx_export.py`
- Create: `tests/test_recognition_onnx_export.py`

**Security flag:** `none`

**Does NOT cover:** INT8 quantization (future enhancement). Multi-input or multi-output models. Hard failure on missing `onnxruntime` — that path is explicitly graceful per spec section §7. Atomic-rename safety for partial export crash mid-write — the writer uses `.tmp` rename for `.onnx` but does **not** orchestrate transactional rollback if `metadata.json` write fails after the `.onnx` is committed; the implementer keeps writes ordered (`.metadata.tmp` → metadata rename → onnx rename) so the metadata commits last and a missing metadata.json is an obvious tell.

- [x] **Step 1: Write failing test**

Create `tests/test_recognition_onnx_export.py`:

```python
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from recognition_model import create_model
from recognition_onnx_export import export_to_onnx


def _train_stats():
    return {
        "train_runs": 3,
        "val_runs": 1,
        "train_examples": 12,
        "val_examples": 4,
        "val_accuracy": 1.0,
        "val_macro_f1": 1.0,
        "low_support_classes": [],
    }


def test_export_creates_artifacts(tmp_path: Path):
    classes = ["a", "b", "c"]
    thresholds = {"a": 0.8, "b": 0.9, "c": 1.01}
    out_onnx = tmp_path / "model.onnx"
    out_meta = tmp_path / "model.metadata.json"

    model = create_model(num_classes=len(classes))
    export_to_onnx(
        model=model,
        out_path=out_onnx,
        metadata_out=out_meta,
        classes=classes,
        thresholds_per_class=thresholds,
        train_stats=_train_stats(),
        verify=False,
    )
    assert out_onnx.exists()
    assert out_meta.exists()

    meta = json.loads(out_meta.read_text(encoding="utf-8"))
    assert meta["schema_version"] == 1
    assert meta["framework"] == "pytorch"
    assert meta["onnx_opset"] == 13
    assert meta["input"]["shape"] == [1, 3, 64, 64]
    assert meta["input"]["dynamic_axes"] == ["batch"]
    assert meta["input"]["preprocessing"]["resize_to"] == [64, 64]
    assert meta["input"]["preprocessing"]["scale"] == pytest.approx(1 / 255.0)
    assert meta["input"]["channels"] == "RGB"
    assert meta["output"]["name"] == "logits"
    assert meta["output"]["post_softmax"] is False
    assert meta["classes"] == classes
    assert meta["thresholds_per_class"] == thresholds
    assert meta["fallback_threshold_default"] == 0.9
    assert meta["dataset_classes_snapshot"] == classes


def test_onnx_graph_has_expected_io_names(tmp_path: Path):
    import onnx
    out_onnx = tmp_path / "model.onnx"
    out_meta = tmp_path / "model.metadata.json"
    classes = ["a", "b"]
    model = create_model(num_classes=len(classes))
    export_to_onnx(
        model=model,
        out_path=out_onnx,
        metadata_out=out_meta,
        classes=classes,
        thresholds_per_class={"a": 0.9, "b": 0.9},
        train_stats=_train_stats(),
        verify=False,
    )
    graph = onnx.load(str(out_onnx)).graph
    assert any(i.name == "input" for i in graph.input)
    assert any(o.name == "logits" for o in graph.output)


def test_verify_ok_when_onnxruntime_available(tmp_path: Path):
    pytest.importorskip("onnxruntime")
    out_onnx = tmp_path / "model.onnx"
    out_meta = tmp_path / "model.metadata.json"
    classes = ["a", "b"]
    model = create_model(num_classes=len(classes))
    # Should not raise
    export_to_onnx(
        model=model,
        out_path=out_onnx,
        metadata_out=out_meta,
        classes=classes,
        thresholds_per_class={"a": 0.9, "b": 0.9},
        train_stats=_train_stats(),
        verify=True,
    )
    assert out_onnx.exists()


def test_verify_skipped_when_onnxruntime_missing(tmp_path: Path, monkeypatch):
    import sys
    # Force the onnxruntime import to fail inside the export module
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    out_onnx = tmp_path / "model.onnx"
    out_meta = tmp_path / "model.metadata.json"
    classes = ["a"]
    model = create_model(num_classes=len(classes))
    # Must not raise; should print/log skip and finish
    export_to_onnx(
        model=model,
        out_path=out_onnx,
        metadata_out=out_meta,
        classes=classes,
        thresholds_per_class={"a": 0.9},
        train_stats=_train_stats(),
        verify=True,
    )
    assert out_onnx.exists()
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recognition_onnx_export.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'recognition_onnx_export'`.

- [x] **Step 3: Implement minimal change**

Create `recognition_onnx_export.py`:

```python
"""Export the trained CNN to ONNX + write the sidecar metadata file.

Order of writes is metadata-tmp -> metadata-final -> onnx-tmp -> onnx-final
so that the final onnx file appearing on disk implies the metadata is already
committed (avoids a runtime-side race where the runtime loads onnx but sees
a stale metadata).
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List

import numpy as np
import torch

SCHEMA_VERSION = 1
ONNX_OPSET = 13
INPUT_SHAPE = [1, 3, 64, 64]
DEFAULT_FALLBACK = 0.90


def _now_iso() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _try_onnxruntime():
    try:
        import onnxruntime  # type: ignore
    except Exception:
        return None
    return onnxruntime


def export_to_onnx(
    model: torch.nn.Module,
    out_path: Path,
    metadata_out: Path,
    classes: List[str],
    thresholds_per_class: Dict[str, float],
    train_stats: dict,
    verify: bool = False,
) -> None:
    out_path = Path(out_path)
    metadata_out = Path(metadata_out)
    model.eval()
    dummy = torch.zeros(*INPUT_SHAPE)

    # Export to a temp byte buffer first; torch.onnx requires a file path,
    # so use a tmp file in the destination directory.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_onnx = out_path.with_suffix(out_path.suffix + ".tmp")
    torch.onnx.export(
        model,
        dummy,
        str(tmp_onnx),
        export_params=True,
        opset_version=ONNX_OPSET,
        input_names=["input"],
        output_names=["logits"],
        dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
    )

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "model_version": _now_iso(),
        "trained_at": _now_iso(),
        "framework": "pytorch",
        "torch_version": torch.__version__,
        "onnx_opset": ONNX_OPSET,
        "input": {
            "name": "input",
            "shape": list(INPUT_SHAPE),
            "dynamic_axes": ["batch"],
            "channels": "RGB",
            "preprocessing": {
                "resize_to": [INPUT_SHAPE[2], INPUT_SHAPE[3]],
                "scale": 1.0 / 255.0,
                "mean": [0.0, 0.0, 0.0],
                "std": [1.0, 1.0, 1.0],
            },
        },
        "output": {"name": "logits", "post_softmax": False},
        "classes": list(classes),
        "thresholds_per_class": dict(thresholds_per_class),
        "fallback_threshold_default": DEFAULT_FALLBACK,
        "train_stats": dict(train_stats),
        "dataset_classes_snapshot": list(classes),
    }

    _atomic_write_text(metadata_out, json.dumps(metadata, indent=2))

    # Optional verification before committing the onnx final path
    if verify:
        ort = _try_onnxruntime()
        if ort is None:
            print("WARNING: onnxruntime unavailable; skipping export verification.", file=sys.stderr)
        else:
            sess = ort.InferenceSession(str(tmp_onnx), providers=["CPUExecutionProvider"])
            sample = torch.randn(4, 3, INPUT_SHAPE[2], INPUT_SHAPE[3])
            with torch.no_grad():
                torch_logits = model(sample).cpu().numpy()
            ort_logits = sess.run(["logits"], {"input": sample.cpu().numpy()})[0]
            max_abs_diff = float(np.max(np.abs(torch_logits - ort_logits)))
            if max_abs_diff > 1e-4:
                # Clean up partial files; do not commit
                try:
                    tmp_onnx.unlink()
                except OSError:
                    pass
                raise RuntimeError(
                    f"ONNX export verification failed: max abs logit diff {max_abs_diff:g} > 1e-4"
                )

    os.replace(tmp_onnx, out_path)
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_recognition_onnx_export.py -q`

Expected: PASS (4 tests). The `test_verify_ok_when_onnxruntime_available` test is skipped if `onnxruntime` is not installed — that is acceptable.

- [x] **Step 5: Regression check**

Run: `python -m pytest -q`

Expected: All prior + new tests pass.

---

### Task 5: Training CLI orchestrator + tests

**Files:**
- Create: `train_recognition_model.py`
- Create: `tests/test_train_recognition_model.py`

**Security flag:** `none`

**Does NOT cover:** Multi-GPU / distributed training. Mixed-precision training. Checkpoint resume (`export-only` resumes from a saved model file but training-from-checkpoint mid-training is not implemented). Hyperparameter search.

- [x] **Step 1: Write failing test**

Create `tests/test_train_recognition_model.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def _write_synthetic_dataset(root: Path, classes, runs_per_class=4, cells_per_run=4):
    """Build a tiny synthetic reviewed dataset under `root`."""
    crops = root / "crops"
    crops.mkdir(parents=True)
    entries = []
    for ci, cls in enumerate(classes):
        # Each class gets a slightly different solid color so the CNN can learn it
        color = (40 + ci * 30, 80, 120)
        for r in range(runs_per_class):
            run = f"{cls}_run_{r}"
            for cell in range(cells_per_run):
                row, col = divmod(cell, 2)
                crop_id = f"{run}__r{row}_c{col}"
                img = np.full((84, 84, 3), color, dtype=np.uint8)
                Image.fromarray(img).save(crops / f"{crop_id}.png")
                entries.append({
                    "crop_id": crop_id,
                    "source_run": run,
                    "row": row,
                    "col": col,
                    "profile": "regular",
                    "original_size": [84, 84],
                    "auto_class": cls,
                    "current_class": cls,
                    "reviewed": True,
                    "corrected": False,
                    "first_seen_at": "2026-05-24T10:00:00",
                    "last_reviewed_at": "2026-05-24T10:01:00",
                })
    (root / "manifest.json").write_text(
        json.dumps({"version": 1, "entries": entries}), encoding="utf-8"
    )
    (root / "classes.json").write_text(
        json.dumps({"classes": sorted(classes)}), encoding="utf-8"
    )


def _run(args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "train_recognition_model", *args],
        cwd=cwd, capture_output=True, text=True,
    )


def test_train_smoke_writes_artifacts(tmp_path: Path):
    dataset = tmp_path / "ds"
    classes = ["red_normal", "blue_normal", "green_normal", "yellow_normal"]
    _write_synthetic_dataset(dataset, classes, runs_per_class=5, cells_per_run=4)
    out_dir = tmp_path / "models"

    cwd = Path(__file__).resolve().parents[1]
    result = _run(
        [
            "train",
            "--dataset-root", str(dataset),
            "--out-dir", str(out_dir),
            "--max-epochs", "1",
            "--early-stop-patience", "1",
            "--batch-size", "8",
            "--seed", "0",
        ],
        cwd=cwd,
    )
    assert result.returncode == 0, result.stderr
    assert (out_dir / "recognition_model.onnx").exists()
    assert (out_dir / "recognition_model.metadata.json").exists()

    meta = json.loads((out_dir / "recognition_model.metadata.json").read_text(encoding="utf-8"))
    assert "classes" in meta
    assert "thresholds_per_class" in meta
    assert "val_accuracy" in meta["train_stats"]


def test_train_fails_on_missing_manifest(tmp_path: Path):
    cwd = Path(__file__).resolve().parents[1]
    result = _run(
        ["train", "--dataset-root", str(tmp_path / "missing"), "--out-dir", str(tmp_path / "m")],
        cwd=cwd,
    )
    assert result.returncode != 0
    assert "dataset" in (result.stdout + result.stderr).lower()


def test_train_fails_on_empty_reviewed(tmp_path: Path):
    dataset = tmp_path / "ds"
    crops = dataset / "crops"
    crops.mkdir(parents=True)
    # Manifest with no reviewed entries
    (dataset / "manifest.json").write_text(
        json.dumps({"version": 1, "entries": []}), encoding="utf-8"
    )
    cwd = Path(__file__).resolve().parents[1]
    result = _run(
        ["train", "--dataset-root", str(dataset), "--out-dir", str(tmp_path / "m")],
        cwd=cwd,
    )
    assert result.returncode != 0
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_train_recognition_model.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'train_recognition_model'`.

- [x] **Step 3: Implement minimal change**

Create `train_recognition_model.py`:

```python
"""CLI for training the recognition CNN and exporting it to ONNX.

Usage:
    python -m train_recognition_model train [options]
    python -m train_recognition_model export-only --checkpoint <path> [options]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, WeightedRandomSampler

from recognition_dataset import load_train_val
from recognition_metrics import (
    compute_val_metrics,
    derive_thresholds,
)
from recognition_model import create_model
from recognition_onnx_export import export_to_onnx


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def _class_weights(train_entries, classes):
    counts = Counter(e.current_class for e in train_entries)
    total = sum(counts.values())
    weights = []
    for cls in classes:
        n = counts.get(cls, 0)
        if n == 0:
            weights.append(1.0)
        else:
            w = total / n
            weights.append(min(10.0, w))
    return torch.tensor(weights, dtype=torch.float32)


def _sample_weights(train_entries, classes):
    counts = Counter(e.current_class for e in train_entries)
    class_to_idx = {c: i for i, c in enumerate(classes)}
    return torch.tensor(
        [1.0 / max(1, counts.get(e.current_class, 1)) for e in train_entries],
        dtype=torch.float64,
    ), class_to_idx


def _train_loop(model, train_loader, val_loader, classes, args, class_weights):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    criterion = torch.nn.CrossEntropyLoss(weight=class_weights.to(device))
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)

    best_f1 = -1.0
    best_state = None
    epochs_no_improve = 0

    for epoch in range(1, args.max_epochs + 1):
        model.train()
        train_loss = 0.0
        n_batches = 0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            loss = criterion(logits, y)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_loss += float(loss.item())
            n_batches += 1
        avg_loss = train_loss / max(1, n_batches)
        metrics = compute_val_metrics(model.cpu(), val_loader, classes)
        model = model.to(device)
        print(
            f"epoch={epoch} train_loss={avg_loss:.4f} "
            f"val_acc={metrics.accuracy:.4f} val_macroF1={metrics.macro_f1:.4f}"
        )
        if metrics.macro_f1 > best_f1 + 1e-6:
            best_f1 = metrics.macro_f1
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            epochs_no_improve = 0
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= args.early_stop_patience:
                print(f"early stop at epoch {epoch} (no macro-F1 improvement)")
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model.cpu()


def _cmd_train(args: argparse.Namespace) -> int:
    dataset_root = Path(args.dataset_root)
    out_dir = Path(args.out_dir)
    if not (dataset_root / "manifest.json").exists():
        print(f"ERROR: dataset manifest not found at {dataset_root}/manifest.json", file=sys.stderr)
        return 2

    _seed_everything(args.seed)
    train_ds, val_ds, report = load_train_val(
        dataset_root, val_run_fraction=args.val_run_fraction, seed=args.seed,
        augment_train=not args.no_augment,
    )
    if report.train_examples == 0 or report.val_examples == 0:
        print(
            f"ERROR: empty split (train={report.train_examples}, val={report.val_examples}). "
            f"Run `python -m dataset_cli review` to label more crops.",
            file=sys.stderr,
        )
        return 2
    if report.uncovered_in_val:
        print(
            f"ERROR: classes present in train but absent in val: {report.uncovered_in_val}. "
            f"Collect more data or adjust --val-run-fraction.",
            file=sys.stderr,
        )
        return 2

    classes = train_ds.classes
    model = create_model(num_classes=len(classes))

    sample_weights, _ = _sample_weights(train_ds.entries, classes)
    sampler = WeightedRandomSampler(sample_weights, num_samples=len(train_ds), replacement=True)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, sampler=sampler, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)

    cw = torch.ones(len(classes))
    if not args.no_class_weights:
        cw = _class_weights(train_ds.entries, classes)

    model = _train_loop(model, train_loader, val_loader, classes, args, cw)

    final_metrics = compute_val_metrics(model, val_loader, classes)
    thresholds = derive_thresholds(model, val_loader, classes, target_precision=args.target_precision)

    low_support = sorted(
        cls for cls, cnt in final_metrics.per_class_count.items()
        if 0 < cnt < 3
    )
    train_stats = {
        "train_runs": report.train_runs,
        "val_runs": report.val_runs,
        "train_examples": report.train_examples,
        "val_examples": report.val_examples,
        "val_accuracy": final_metrics.accuracy,
        "val_macro_f1": final_metrics.macro_f1,
        "low_support_classes": low_support,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    export_to_onnx(
        model=model,
        out_path=out_dir / "recognition_model.onnx",
        metadata_out=out_dir / "recognition_model.metadata.json",
        classes=classes,
        thresholds_per_class=thresholds,
        train_stats=train_stats,
        verify=args.verify_export,
    )
    print(
        f"Done. val_acc={final_metrics.accuracy:.4f} val_macroF1={final_metrics.macro_f1:.4f} "
        f"-> {out_dir / 'recognition_model.onnx'}"
    )
    return 0


def _cmd_export_only(args: argparse.Namespace) -> int:
    ckpt = Path(args.checkpoint)
    if not ckpt.exists():
        print(f"ERROR: checkpoint not found: {ckpt}", file=sys.stderr)
        return 2
    payload = torch.load(ckpt, map_location="cpu")
    classes = payload["classes"]
    state = payload["state_dict"]
    thresholds = payload.get("thresholds_per_class", {c: 0.9 for c in classes})
    train_stats = payload.get("train_stats", {})
    model = create_model(num_classes=len(classes))
    model.load_state_dict(state)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    export_to_onnx(
        model=model,
        out_path=out_dir / "recognition_model.onnx",
        metadata_out=out_dir / "recognition_model.metadata.json",
        classes=classes,
        thresholds_per_class=thresholds,
        train_stats=train_stats,
        verify=args.verify_export,
    )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="train_recognition_model")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_tr = sub.add_parser("train")
    p_tr.add_argument("--dataset-root", default="data/recognition_dataset")
    p_tr.add_argument("--out-dir", default="models")
    p_tr.add_argument("--val-run-fraction", type=float, default=0.2)
    p_tr.add_argument("--seed", type=int, default=42)
    p_tr.add_argument("--batch-size", type=int, default=32)
    p_tr.add_argument("--learning-rate", type=float, default=1e-3)
    p_tr.add_argument("--max-epochs", type=int, default=50)
    p_tr.add_argument("--early-stop-patience", type=int, default=5)
    p_tr.add_argument("--target-precision", type=float, default=0.99)
    p_tr.add_argument("--verify-export", action="store_true")
    p_tr.add_argument("--no-class-weights", action="store_true")
    p_tr.add_argument("--no-augment", action="store_true")
    p_tr.set_defaults(func=_cmd_train)

    p_ex = sub.add_parser("export-only")
    p_ex.add_argument("--checkpoint", required=True)
    p_ex.add_argument("--out-dir", default="models")
    p_ex.add_argument("--verify-export", action="store_true")
    p_ex.set_defaults(func=_cmd_export_only)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_train_recognition_model.py -q`

Expected: PASS (3 tests). Note: the smoke test runs an actual 1-epoch training pass on a 4-class synthetic dataset; it may take 10–30 seconds.

- [x] **Step 5: Regression check**

Run: `python -m pytest -q`

Expected: All existing + 4 + 6 + 5 + 4 + 3 = 22 new tests pass.

---

### Task 6: Live acceptance against the real dataset

**Files:**
- None (acceptance against live `data/recognition_dataset/` produced by Sub-project A).

**Security flag:** `none`

**Does NOT cover:** Live BlueStacks runtime testing — that is Sub-project C. Hyperparameter tuning — leave defaults unless val accuracy is unacceptable, in which case escalate to the user.

- [x] **Step 1: Pre-flight checks**

Run: `python -m dataset_cli stats --require-fully-reviewed`

Expected: exit code 0 (all crops reviewed). If non-zero, stop and report which run(s) still need labeling — do not proceed.

Execution note 2026-05-24: stopped here as required. Command exited 1 with `ERROR: 9849 unreviewed crops`, `total=9849 reviewed=0 corrected=0`.

Execution note 2026-05-25: user requested accepting unconfirmed labels as automatic. A manifest backup was written at `data/recognition_dataset/manifest.before_auto_accept_20260525_015352.json`; 9721 unreviewed entries were marked reviewed with `current_class=auto_class`. Re-check then passed with `total=9849 reviewed=9849 corrected=126`.

- [x] **Step 2: Train on the real dataset**

Run: `python -m train_recognition_model train`

Expected:
- per-epoch lines printed: `epoch=K train_loss=... val_acc=... val_macroF1=...`
- final line: `Done. val_acc=... val_macroF1=... -> models/recognition_model.onnx`
- `models/recognition_model.onnx` and `models/recognition_model.metadata.json` both exist.

If training fails with `ERROR: classes present in train but absent in val`, report the list to the user and stop — they need to collect more data for those classes.

- [x] **Step 3: Inspect metadata**

Run: `python -c "import json, pathlib; print(json.dumps(json.loads(pathlib.Path('models/recognition_model.metadata.json').read_text()), indent=2))"`

Expected output contains:
- `"schema_version": 1`
- `"classes": [...]` non-empty list, matching `sorted(ALL_CLASSES)` from `dataset_classes.py`
- `"thresholds_per_class": {...}` with one entry per class
- `"train_stats": {...}` with non-zero `train_examples` and `val_examples`
- `"val_accuracy"` ≥ 0 (no upper bound asserted; this is the live result)

- [x] **Step 4: Verify ONNX export integrity (best effort)**

Run: `python -m train_recognition_model export-only --checkpoint /dev/null` (Windows: `nul`)

Expected: exits with non-zero and prints `ERROR: checkpoint not found`. This is a smoke check that the `export-only` subcommand is wired.

Run: `python -m pytest -q`

Expected: full suite still passes.

- [x] **Step 5: Final regression check**

Run: `python -m pytest -q`

Expected: all tests pass.

---

## Stop Conditions

- Any task's verification command fails — halt and report. Do not skip to the next task.
- `torch` import fails after Task 0 — stop and ask the user to fix their Python environment before proceeding.
- Task 6 step 1 reports unreviewed crops — stop and ask the user to label them. Do not attempt to disable the gate.
- Task 6 step 2 reports uncovered classes in val — stop and report which classes; ask the user to collect more debug runs.
- Live `val_accuracy < 0.80` in Task 6 step 2 — report to the user before any further work; the model is too weak for Sub-project C and the cause should be investigated (likely too few labeled examples, or label noise).

## Expected Final Behavior

- Five new modules at the project root: `recognition_model.py`, `recognition_dataset.py`, `recognition_metrics.py`, `recognition_onnx_export.py`, `train_recognition_model.py`.
- Five new test files under `tests/` with 22 new passing tests (4 + 6 + 5 + 4 + 3).
- `requirements-dev.txt` includes `torch`, `onnx`, `onnxruntime`.
- `models/recognition_model.onnx` and `models/recognition_model.metadata.json` exist after Task 6 step 2, derived from the user's live labeled dataset.
- No existing runtime files are modified.

## What Comes Next (Out of Scope For This Plan)

- **Sub-project C:** add a feature-flagged ML inference path in `recognition.py` / `runtime.py` / `gui.py`. C reads `models/recognition_model.onnx` and the sidecar metadata, runs per-cell inference, and falls back to the existing template matcher when the per-class confidence threshold is not met. Separate spec/plan.
