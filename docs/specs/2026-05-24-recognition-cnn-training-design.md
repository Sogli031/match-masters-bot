# Recognition CNN Training & ONNX Export — Design

_Sub-project B of the "ML recognition revival" initiative._

Status: **Draft for user review**
Date: 2026-05-24
Predecessor: Sub-project A — [docs/specs/2026-05-24-recognition-dataset-builder-design.md](2026-05-24-recognition-dataset-builder-design.md).
Successor: Sub-project C (runtime ML path, feature-flagged) will follow as a separate spec.

## 1. Goal and Scope

Build an **offline training pipeline** that consumes the curated dataset produced by Sub-project A (`data/recognition_dataset/`) and produces a deployable ONNX model plus sidecar metadata at `models/recognition_model.onnx` + `models/recognition_model.metadata.json`.

The pipeline:
1. Reads `manifest.json` and crops, filters to fully reviewed entries.
2. Splits runs into train/validation **at the run level** (not the cell level) to prevent same-board leakage.
3. Trains a small CNN classifier over the fixed class taxonomy from `dataset_classes.py`.
4. Reports validation accuracy, macro F1, per-class accuracy, and confusion matrix.
5. Derives a per-class confidence threshold targeting ~99% precision on the validation set.
6. Exports the model to ONNX and writes the sidecar metadata Sub-project C requires.

### Non-goals

- **No runtime integration.** That is Sub-project C. Touching `recognition.py`, `runtime.py`, `gui.py` is forbidden in this plan.
- **No hyperparameter search.** Fixed defaults baked in; user can override via CLI flags.
- **No GPU-specific code.** Model trains on CPU; uses GPU if available via `torch.cuda.is_available()` but is not required.
- **No pretrained backbone fine-tuning.** Train from scratch (the input is 64×64 game-tile crops, ImageNet weights are a poor match).
- **No checkpoint resume / continual learning.** Each run trains from scratch. Future enhancement.
- **No INT8 quantization.** Future enhancement.
- **No active-learning UI loop.** That is downstream from B and not designed yet.
- **No augmentation beyond ±5% color jitter.** Rotation/flip would break directional classes (`horizontal_arrow` ↔ `vertical_arrow`, `heart` orientation).

## 2. Tech Stack

- Python 3 (existing).
- PyTorch (new dependency, CPU build is fine).
- `onnx`, `onnxruntime` (new dependencies; `onnxruntime` is **optional** at training time — used only for the export-verification check, which is gated by `--verify-export` flag).
- NumPy, PIL (existing).
- pytest (existing).

Add to `requirements-dev.txt`:
```
torch
onnx
onnxruntime ; platform_system != "Linux" or python_version >= "3.10"
```

If `onnxruntime` installation fails on the user's machine (history note: it has blocked the full pytest suite before), training and export still work — only the verification step skips with a warning.

## 3. Data Flow

```
data/recognition_dataset/
  ├── crops/<id>.png
  ├── manifest.json     (reviewed=True entries are eligible)
  └── classes.json
        ▼
  [PyTorch Dataset]     (recognition_dataset.py)
        ▼
  [Per-run train/val split + conservative augment]
        ▼
  [Tiny CNN]            (recognition_model.py)
        ▼
  [Training loop with weighted loss + early stop on val macro-F1]
        ▼
  [Metrics]             (recognition_metrics.py — confusion matrix, per-class accuracy, threshold derivation)
        ▼
  [ONNX export + sidecar metadata]   (recognition_onnx_export.py)
        ▼
models/
  ├── recognition_model.onnx
  └── recognition_model.metadata.json
```

## 4. Components

### 4.1 `recognition_dataset.py`

```python
class RecognitionDataset(torch.utils.data.Dataset): ...

def load_train_val(
    dataset_root: Path,
    val_run_fraction: float = 0.2,
    seed: int = 42,
    augment: bool = True,
) -> tuple[RecognitionDataset, RecognitionDataset, SplitReport]: ...
```

- Reads `manifest.json`, filters `reviewed=True`.
- Groups entries by `source_run`.
- Deterministically assigns ~20% of runs to validation; remaining 80% to train. Stratification target: every class with ≥2 examples in the full dataset must appear ≥1 time in val. If not achievable, `SplitReport` warns.
- Train transform: resize to 64×64, `ColorJitter(brightness=0.05, contrast=0.05, saturation=0.05)`, ToTensor, normalize to [0,1].
- Val transform: resize to 64×64, ToTensor, normalize to [0,1].
- No `RandomHorizontalFlip` or `RandomRotation` — would break directional classes.
- Class indices come from `sorted(ALL_CLASSES)` for deterministic ordering.

### 4.2 `recognition_model.py`

```python
class TinyTileCNN(torch.nn.Module):
    def __init__(self, num_classes: int): ...
    def forward(self, x): ...

def create_model(num_classes: int) -> TinyTileCNN: ...
```

Architecture (input 3×64×64):

| Layer | Output |
|---|---|
| Conv2d(3→16, k=3, pad=1) + ReLU + MaxPool(2) | 16×32×32 |
| Conv2d(16→32, k=3, pad=1) + ReLU + MaxPool(2) | 32×16×16 |
| Conv2d(32→48, k=3, pad=1) + ReLU + MaxPool(2) | 48×8×8 |
| Flatten → Linear(48·64 → 128) + ReLU + Dropout(0.3) | 128 |
| Linear(128 → num_classes) | num_classes |

≈ 460k params. Trains in seconds to minutes on CPU. No batch normalization (keeps ONNX export simple and stable; dropout already regularizes).

### 4.3 `recognition_metrics.py`

```python
@dataclass
class ValMetrics:
    accuracy: float
    macro_f1: float
    per_class_accuracy: dict[str, float]
    per_class_count: dict[str, int]
    confusion_matrix: list[list[int]]
    class_order: list[str]

def compute_val_metrics(model, val_loader, classes) -> ValMetrics: ...

def derive_thresholds(
    model, val_loader, classes, target_precision: float = 0.99,
) -> dict[str, float]: ...
```

`derive_thresholds()`:
- For each class, sweep softmax-confidence thresholds in 0.05 steps from 0.50 to 0.99.
- Pick the lowest threshold where per-class precision ≥ `target_precision` on val set.
- If no threshold reaches 99% precision (rare or noisy class), record `1.01` — meaning "never trust ML for this class, always fallback to template matcher".
- Classes with `<3` val examples get the global default (0.9) and a `low_support_warning` flag in metadata.

### 4.4 `recognition_onnx_export.py`

```python
def export_to_onnx(
    model: torch.nn.Module,
    out_path: Path,
    metadata_out: Path,
    classes: list[str],
    thresholds_per_class: dict[str, float],
    train_stats: dict,
    verify: bool = False,
) -> None: ...
```

- Calls `torch.onnx.export()` with `opset=13`, `input_names=["input"]`, `output_names=["logits"]`, `dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}}` — fixed spatial dims (64×64) for predictable inference cost.
- Writes `models/recognition_model.metadata.json` (schema in §6).
- If `verify=True` and `onnxruntime` is importable: runs both torch and onnxruntime on the same 8-sample batch, asserts `np.max(abs(torch_logits - ort_logits)) < 1e-4`. Otherwise prints `skipped — onnxruntime unavailable`.

### 4.5 `train_recognition_model.py`

CLI entrypoint. Subcommands:

```
python -m train_recognition_model train [options]
python -m train_recognition_model export-only [options]   # re-export from a checkpoint without retraining
```

Default options (override via flags):

| Flag | Default | Purpose |
|---|---|---|
| `--dataset-root` | `data/recognition_dataset` | Input |
| `--out-dir` | `models` | Output |
| `--val-run-fraction` | `0.2` | Per-run split |
| `--seed` | `42` | Reproducibility |
| `--batch-size` | `32` | Training |
| `--learning-rate` | `1e-3` | Adam |
| `--max-epochs` | `50` | Cap |
| `--early-stop-patience` | `5` | Epochs without macro-F1 improvement |
| `--target-precision` | `0.99` | For threshold derivation |
| `--verify-export` | flag | Run onnxruntime verification |
| `--no-class-weights` | flag | Disable inverse-frequency class weights |
| `--no-augment` | flag | Disable color jitter |

Pipeline:
1. Load dataset → train/val split → log SplitReport.
2. Sanity check: refuse if val set has 0 examples of any class that exists in train; refuse if `--require-fully-reviewed` is violated on the manifest.
3. Build model + Adam optimizer + CrossEntropyLoss with class weights (inverse frequency, capped at 10×).
4. WeightedRandomSampler for train loader (further mitigates imbalance).
5. Train loop with per-epoch val pass; track val macro-F1; early stop after `--early-stop-patience` no-improvement epochs.
6. After training: `compute_val_metrics()` final report.
7. `derive_thresholds()` against val set.
8. `export_to_onnx()` to `out-dir`.
9. Print summary including path of artifacts.

## 5. Training Specifics

- **Loss:** `CrossEntropyLoss(weight=class_weights)`. Weights = `min(10, total/N_class)`.
- **Optimizer:** Adam, weight_decay=1e-4.
- **Sampler:** `WeightedRandomSampler` on train so minority classes appear in most batches.
- **Early stopping:** macro-F1 on val set, patience 5 epochs, max 50 epochs.
- **Determinism:** seeds for `random`, `numpy`, `torch`. `torch.use_deterministic_algorithms(False)` for performance — accept small non-determinism.
- **Logging:** Per-epoch print of train_loss, val_loss, val_acc, val_macroF1. No external logging deps.

## 6. Sidecar Metadata Schema (`recognition_model.metadata.json`)

This file is the **contract** between Sub-project B and Sub-project C. C must read it to know how to preprocess input and how to interpret logits.

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
  "output": {
    "name": "logits",
    "post_softmax": false
  },
  "classes": ["billie_drone", "blocked", "blue_all_aboard_bandit", "..."],
  "thresholds_per_class": {
    "blue_normal": 0.85,
    "red_bomb": 0.90,
    "joojoo_skull": 1.01,
    "...": 0.0
  },
  "fallback_threshold_default": 0.90,
  "train_stats": {
    "train_runs": 45,
    "val_runs": 12,
    "train_examples": 2205,
    "val_examples": 588,
    "val_accuracy": 0.97,
    "val_macro_f1": 0.86,
    "low_support_classes": ["joojoo_skull", "billie_drone"]
  },
  "dataset_classes_snapshot": ["billie_drone", "blocked", "..."]
}
```

Notes:
- `thresholds_per_class[class] = 1.01` means "never use ML for this class — always fall back to template matcher".
- `dataset_classes_snapshot` mirrors the `classes.json` written by Sub-project A. If it drifts from C's local `dataset_classes.py`, C refuses to load the model.

## 7. Error Handling

| Failure | Behavior |
|---|---|
| `manifest.json` missing or empty | CLI exits 2 with `ERROR: dataset not built or empty`. |
| No `reviewed=True` entries | CLI exits 2 with guidance pointing at `dataset_cli review`. |
| Any class in train has 0 val examples (after split) | CLI exits 2; suggests collecting more data or different `--val-run-fraction`. |
| `torch` not importable | CLI exits 1 with install instruction. |
| ONNX export fails | CLI exits 3 with the underlying torch error. |
| ONNX verification mismatch (>1e-4) | CLI exits 4. Artifacts are NOT moved to final paths (atomic). |
| `onnxruntime` not importable AND `--verify-export` was passed | Warning, verification skipped, training succeeds. |
| Crash mid-training | Partial files in temp dir cleaned up via `try/finally`. No partial `recognition_model.onnx`. |

## 8. Failure Modes Considered

1. **Class imbalance dominates** — *Critical*. Mitigation: inverse-frequency class weights (capped 10×) + `WeightedRandomSampler` + macro-F1 early stopping (not accuracy).
2. **Per-run split leaves classes uncovered in val** — *Critical*. Mitigation: pre-train assertion that every train class appears ≥1× in val; fail loudly with collect-more-data message. Classes with `<3` val examples get the default threshold and a warning flag.
3. **ONNX export silently loses behavior** — *Critical*. Mitigation: `--verify-export` flag runs onnxruntime + torch back-to-back on a held-out batch, fails on logit divergence >1e-4. Documented to be optional only because `onnxruntime` has been brittle on this Windows setup (see session-log 2026-05-24 11:01).
4. **Threshold derivation overfits to val set** — *Minor*. The val set is reused both for early-stop and for threshold derivation. Documented limitation; refining with a separate calibration split is future work.
5. **Color jitter blurs heart/arrow distinctions** — *Minor*. Locked at ±5%; can be disabled via `--no-augment`.
6. **`onnxruntime` install breaks the user's env** — *Minor*. Listed as optional dep; training/export work without it; verification just skips.

## 9. Testing Strategy

- **`recognition_dataset.py`:** unit tests for per-run split determinism, transform shape, class index mapping, reviewed-filter, SplitReport warnings on uncovered classes.
- **`recognition_model.py`:** forward-pass shape test (batch=2 → logits batch=2); param count smoke check (within 10% of expected ~460k).
- **`recognition_metrics.py`:** confusion matrix test on a hand-crafted dataset; `derive_thresholds()` test using synthetic logits with known precision curves.
- **`recognition_onnx_export.py`:** export round-trip test (export → load with `onnx.load` → check graph has expected input/output names); metadata.json schema match against expected keys.
- **`train_recognition_model.py`:** smoke test running 1 epoch on a 4-class synthetic dataset; asserts artifacts written and metadata parsed.
- **No live training in CI.** The 1-epoch smoke test is the integration check; full training is a manual user step.

## 10. Rollout

B produces files in `models/`. Sub-project C consumes those files at runtime. There is no migration. If the user does not run B, Sub-project C falls back to template matching unconditionally — the runtime is robust to a missing model file.

## 11. Open Questions Deferred

- **Calibration split** for threshold derivation (currently reuses val set).
- **INT8 quantization** for faster runtime inference.
- **Per-cell context window** (passing 3×3 neighborhood instead of single cell). Currently single-cell only.
- **Active learning loop** that asks the user to label the lowest-confidence cells next. Out of scope for B; could be a Sub-project D.
- **Model card** documenting limitations and biases. Documentation task, not engineering.
