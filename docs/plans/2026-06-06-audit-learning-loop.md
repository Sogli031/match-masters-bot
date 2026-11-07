# Audit Learning Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:test-driven-development before production code edits.

**Goal:** Add an offline audit-learning script that turns Stage D flagged games into concrete improvement recommendations.
**Architecture:** `learn_from_audit.py` is pure and import-safe, with a thin CLI. It reads `Debug/calibration_report.json`, resolves flagged run folders, compares selected moves against `candidates.json`, checks ML health, and writes markdown/JSON reports.
**Tech Stack:** Python stdlib, pytest.
**Assumptions:** Assumes `calibrate_from_audit.py` already generated Stage D JSON — will NOT infer flagged runs from screenshots alone.

---

## Files

- Create: `learn_from_audit.py` — pure analysis engine and CLI.
- Create: `tests/test_learn_from_audit.py` — unit and CLI serialization tests.
- Modify: `calibrate_from_audit.py` only if Stage D JSON lacks enough flagged examples for the learning script.

## Tasks

### Task 1: Add Learning Analysis Module

**Files:**
- Create: `learn_from_audit.py`
- Test: `tests/test_learn_from_audit.py`

**Does NOT cover:** Live move selection, automatic weight updates, model training.

- [x] Write failing tests for ranking classification, recognition classification, positive undervalued learning, and report writing.
- [x] Implement helpers to load report cases and run artifacts.
- [x] Implement candidate empirical scoring from turn-sequence coefficients.
- [x] Implement markdown and JSON serialization.
- [x] Verify with `python -m pytest tests/test_learn_from_audit.py -q`.

### Task 2: Ensure Stage D Exposes Examples

**Files:**
- Modify: `calibrate_from_audit.py`
- Test: `tests/test_calibrate_from_audit.py`

**Does NOT cover:** Changing Stage D scoring thresholds.

- [x] Add `overvalued_examples` and `undervalued_examples` to `quality` JSON.
- [x] Verify with `python -m pytest tests/test_calibrate_from_audit.py -q`.

### Task 3: Generate Real Reports

**Files:**
- Generate: `Debug/improvement_learning_report.md`
- Generate: `Debug/improvement_learning_report.json`

**Does NOT cover:** Editing strategy weights.

- [x] Run `python calibrate_from_audit.py`.
- [x] Run `python learn_from_audit.py`.
- [x] Verify report includes diagnosis counts, component summary, and concrete flagged folders.
