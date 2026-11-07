# Recognition ML First Mode - Design

Status: Approved
Date: 2026-05-25

## Goal

Add a fourth runtime ML recognition option named `ML first`.

`ML first` makes the model the primary per-cell recognizer. For each cell, the
runtime uses the ML prediction only when confidence, metadata, class decoding, and
safety gates pass. Every rejected or unavailable ML prediction falls back to the
existing template/color result for that same cell.

## Scope

In scope:

- Add a new mode constant: `ML_RECOGNITION_FIRST = "first"`.
- Expose the mode in the GUI as `ML first`.
- Preserve existing `off`, `shadow`, and `hybrid` behavior.
- Reuse the existing ML inference runtime and debug payload.
- Keep per-cell debug comparison: template result, ML result, and final result.
- Keep the training/debug flow compatible with recognized overlays and debug runs.

Out of scope:

- Retraining changes.
- Dataset manifest mutation.
- Template asset changes.
- Move strategy changes.
- Making ML the default mode.

## Runtime Behavior

Existing modes remain:

- `off`: template/color recognition only.
- `shadow`: run ML diagnostics, return template/color output unchanged.
- `hybrid`: template/color baseline, ML overlays only safe cells.

New mode:

- `first`: ML is evaluated first per cell; accepted cells become final output, rejected
  cells keep the template/color fallback.

The implementation still runs template recognition first because the current runtime
needs the template board for fallback, debug comparison, and recognized overlay output.
The observable behavior is ML-primary per cell.

## Acceptance Gates

`first` accepts an ML cell only when all of these are true:

- ML result is available.
- Prediction class is known and already decoded by metadata validation.
- Prediction is not `empty`.
- Confidence and threshold are finite.
- Threshold is not greater than `1.0`; threshold `1.01` remains a disabled class.
- Confidence is greater than or equal to threshold.
- For `disco_ball`, `cleo_bug`, `billie_drone`, and `mode_target`, both confidence and
  threshold must be at least `0.90`.

When any gate fails, final output for that cell remains the template/color result.

Unlike `hybrid`, `first` is allowed to replace an existing template special when the ML
prediction passes the gates. That is the practical difference: `hybrid` protects the
template baseline, while `first` trusts ML first and uses template only as fallback.

## Debug Contract

When ML runs, `ml_recognition.json` must include for every predicted cell:

- template board/special values
- ML class, board, special, confidence, threshold
- accepted flag and reason
- final board/special values after merge

The existing `recognized.png`, `move.json`, `candidates.json`, and `timings.json` flow
continues to use the final board after recognition. This keeps debug useful for training
and review: template vs ML vs final remains visible.

## Failure Modes

- Model missing, metadata bad, `onnxruntime` unavailable, or inference exception:
  template/color output is returned for the whole board.
- Bad class threshold over `1.0`: that class is disabled and falls back per cell.
- Risky special below `0.90`: falls back per cell.
- Debug disabled: no disk debug file is written, but recognition behavior remains the same.

