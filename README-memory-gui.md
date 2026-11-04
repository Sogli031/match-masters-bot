# Memory GUI — Internal Notes

Working directory extracted from the full project backup. Contains only the
memory-reader path (Frida / IL2CPP).

## Running
- `Pokreni Memory GUI.bat` — with terminal (live output)
- `Pokreni Memory GUI (bez terminala).vbs` — silent, output goes to `Debug\memory_gui_last_run.log`
- Panel log (attach, match start/end, agent errors) is always written to `Debug\memory_gui.log`

## Contents
- `memory_gui.py` + import chain: `runtime.py`, `move_strategy.py`,
  `board_source.py`, `board_profiles.py`, `recognition.py`, `gui.py`,
  `perk_detection.py`, `perk_executor.py`, `matchmasters_launcher.py`, etc.
- `tools/` — reader (`matchmasters_board_reader.py`), agent
  (`matchmasters_board_dump.js` + `.ts` source), `build_board_agent.ps1`,
  `node_modules` and `frida_agent` for agent rebuild. Rebuild works without node:
  from `tools` folder `frida-compile .\matchmasters_board_dump.ts -o
  .\matchmasters_board_dump.js -T none -S` (frida-compile is in Python311\Scripts).
  New agent loads after GUI restart.
- `assets/` — overlays, score legend
- `models/` — `recognition_model.onnx` + metadata
- `data/` — `ability_config.json`, `piece_logic_config.json`,
  `mutation_lab_catalogue.json`, `il2cpp_symbols.json`, `charge_value.json`,
  `ability_live.json`
- `docs/` — mode/booster/reader documentation
- `Debug/` — empty at start, logs and snapshots written here
- calibration: `board_config.json`, `board_config_supersize.json`,
  `display_calibration.json`, `gui_state.json`, `swipe_profile.json`

## Not included (in backup folder)
- ML training pipeline, datasets (553 MB), old model candidates
- `gui.py` screen-capture entry point kept (imported for calibration overlay),
  but `prepare_and_run.py`, LAN, benchmarks not included
- PNG templates from `assets/general`, `assets/modes`, `assets/perks` no longer
  exist — reader path does not use them. Only
  `assets/score_legend/digit_templates.npz` remains.

## Tests
`tests/` has 236+ tests. `pytest` not installed — tests run through a shim that
registers a mock `pytest` module (`mark.parametrize`, `approx`, `raises`,
`monkeypatch`, `tmp_path`).

## Migration
`setup_new_pc/` contains a PC setup checklist and restore script.
`payload/` carries offline dependencies (~370 MB).

## Dependencies
`requirements.txt` — runtime packages.

## Flash sync
`Sync Memory GUI na fles.bat` (or `python sync_to_flash.py`) mirrors to
`E:\memory gui`. Full mirror — includes `Debug`, `__pycache__`, `node_modules`.
Custom destination: `python sync_to_flash.py --dest F:\MemoryGUI`, preview:
`--list`, skip deletes: `--no-delete`.
