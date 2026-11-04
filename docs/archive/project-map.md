# Project Map
_Generated: 2026-05-31 06:31 | Staleness: timestamps | Git: none detected_

## Directory Structure
assets/ - Curated template images actually loaded by the bot for base colors, specials, and game modes.
Debug/ - Runtime screenshots captured by `test.py` during board scans; generated/debug data, not source.
docs/ - Superpowers design and implementation plan for the strategic move evaluator.
images/ - README illustration images for original project documentation.
Match-Masters/ - Large extracted game asset dump used as source material for curated templates.
temp_repo/ - Temporary/source reference checkout; do not treat as the active runtime path.
tests/ - Pytest regression tests for board profiles, chest templates, and pure move strategy.
__pycache__/ and .pytest_cache/ - Generated Python/test caches.

## Key Files
README.md - Original project overview: Python bot using PyAutoGUI, NumPy, and OpenCV to recognize a Match Masters board and choose a move.
test.py - Main live bot UI/runtime: PyQt5 window, BlueStacks screenshot capture, OpenCV template recognition, mode handling, and PyAutoGUI swipes.
move_strategy.py - Pure import-safe move engine: candidate generation, match grouping, board/special simulation, heuristic scoring, and shallow lookahead.
board_profiles.py - Profile loader for regular 7x7 and supersize 8x8 board calibration files.
board_config.json - Current regular board crop; lacks `boardSize`, so `board_profiles.py` defaults it to 7.
board_config_supersize.json - Current supersize 8x8 board crop with explicit `boardSize: 8`.
setup_assets.py - Copies selected template assets from `Match-Masters/` into `assets/`; paths are hardcoded to this desktop copy.
calibrate.py - Manual calibration helper that asks the user to click board corners and writes `board_config.json`.
auto_calibrate.py - BlueStacks/OpenCV calibration experiment using a live window screenshot.
find_scale.py, find_grid.py, find_board_y.py - One-off OpenCV calibration/debug scripts around screenshots and template scale.
check_colors.py, check_gem_colors.py - Asset color inspection helpers for template/color tuning.
tests/test_move_strategy.py - Main regression suite for pure board logic, scoring, legality, stale-match filtering, special swaps, and lookahead.
tests/test_board_profiles.py - Regression coverage for profile defaults, 8x8 config calculation/loading, and unknown profile rejection.
tests/test_chest_template.py - Checks chest templates are loaded at full tile scale and match the live fixture.
docs/superpowers/specs/2026-05-05-strategic-move-evaluator-design.md - Design rationale for extracting and weighting the strategic evaluator.
docs/superpowers/plans/2026-05-05-strategic-move-evaluator.md - Historical implementation plan; useful for expected architecture and test intent.

## Critical Constraints
- This directory is not a Git repository; use timestamp freshness unless the user explicitly wants `git init`.
- Keep `C:\Users\PC\Desktop\mm` and this playable bot repo distinct: `mm` is advisor/assets work, this repo is the runnable BlueStacks bot.
- `test.py` must stay import-safe: BlueStacks lookup, config reads, and template setup belong behind `initialize_runtime()` and the `__main__` path.
- Pure move logic belongs in `move_strategy.py`; tests should not need PyQt5, BlueStacks, screenshots, or live windows.
- `choose_best_move()` is the UI entrypoint for current move selection; old scoring helpers in `test.py` remain legacy helpers and are not the main button path.
- The evaluator is heuristic, not a proof of globally optimal Match Masters play; logged boards can tie, and "best" may mean one of several equal top scores.
- Preserve `board` and `special_board` alignment during drops/cascades; previous strategy work specifically fixed detached special-piece state.
- Treat `SPECIAL_XTRA_MOVE_TILE` as a board-position marker: do not swap/drop it with gems; score it only when the marked cell clears.
- Directional fireworks cannot be direct special-swap activations; they score by color-match/chain effects and zero-blue activations are downranked.
- Zany Zappers cannot be direct special-swap activations; they only activate when matched or cleared by another effect.
- The strategic explanation labels `instant=`, `special=`, `blue=`, `mode=`, and `potential=` are deliberate debug output.
- `lookahead_candidates=None` in `choose_best_move()` means refine all legal candidates, not zero candidates.
- Template filenames include existing misspellings such as `horizonal_purple_arrow.png`; update references consistently if renaming.
- Live verification still requires BlueStacks open, `python test.py`, selecting mode/profile, clicking `Check Best Move`, and checking console/swipe behavior.

## Hot Files
test.py, move_strategy.py, tests/test_move_strategy.py, board_profiles.py, tests/test_board_profiles.py, tests/test_chest_template.py, board_config.json, board_config_supersize.json, setup_assets.py
