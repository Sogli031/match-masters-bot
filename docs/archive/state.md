# Session State - 2026-06-03

## Current Goal
Enable Sweep SE small broom labeling for recognition dataset review/training.

## Decisions
- `broom` is a colorless dataset class because Sweep SE target color comes from the adjacent swapped tile.
- `SPECIAL_SWEEP_SE_BROOM` uses a stable code after the Vinnie SE dynamic range.
- Broom is excluded from normal-swap and generic-created-special handling until a dedicated Sweep evaluator exists.
- Future Sweep evaluator should omit opponent-board-risk item 8 per user request.

## Plan Status
Implemented and verified for dataset taxonomy, ML overlay handling, debug labeling, and strategy safety guards.

## Evidence
- New tests failed before the implementation because `broom` and `SPECIAL_SWEEP_SE_BROOM` did not exist.
- Focused Sweep tests now pass.
- Relevant scanner/dataset/ML runtime tests pass.

## Open Issues
- `tests/test_dataset_classes.py` currently has unrelated Spray SE taxonomy failures: tests expect colorless `spray_se`, while strategy still treats Spray SE as color-bound.
- Full `python -m pytest -q` remains avoided because prior state records unrelated dataset/Torch/model/ONNX failures.
