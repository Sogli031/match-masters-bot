# Audit Learning Loop Design

## Scope

Add an offline learning report that reads existing `Debug/runs` audit artifacts and explains how the bot can improve after Stage D flags weak turns.

The tool must:
- read `Debug/calibration_report.json`;
- inspect flagged run folders under `Debug/runs`;
- load `move.json`, `candidates.json`, `intent.txt`, and `ml_recognition.json` when present;
- classify each flagged case as likely `ranking`, `underweighted`, `recognition`, `candidate_tie`, or `data_needed`;
- identify the score component most likely being over-credited;
- compare the selected move against candidate moves using the fitted turn-sequence coefficients when available;
- write `Debug/improvement_learning_report.md` and `Debug/improvement_learning_report.json`.

## Non-goals

- Do not edit `move_strategy.py`.
- Do not auto-change live weights.
- Do not train a neural model.
- Do not treat one noisy game as proof of a ranking rule.

## Architecture

Create a pure import-safe module `learn_from_audit.py` with a CLI wrapper.

Data flow:
1. `calibrate_from_audit.py` produces a Stage D report.
2. `learn_from_audit.py` reads the report's quality watchlist and flagged examples.
3. The tool resolves each flagged `game/run` folder.
4. The tool extracts selected move details, candidate alternatives, intent text, and ML confidence signals.
5. The tool writes a human-readable markdown report plus structured JSON.

## Classification Rules

- `recognition`: ML was unavailable, blocked, rejected cells, or had weak accepted confidence.
- `ranking`: recognition looks clean and the selected move is overvalued or a fitted empirical candidate would have been preferred.
- `underweighted`: recognition looks clean and Stage D says a low-rated selected turn charged well, so this is a positive signal for a component or pattern that may deserve more weight.
- `candidate_tie`: recognition looks clean and the best empirical alternative is too close to the selected candidate to call a strong ranking error.
- `data_needed`: required artifacts are missing.

## Error Handling

Missing optional files must not crash the report. Missing `move.json` or missing selected move data marks the case as `data_needed`.

## Testing

Use deterministic temp `Debug/runs` fixtures:
- ranking case with a high selected score but a better fitted candidate;
- recognition-suspect case with rejected ML cells;
- CLI/report serialization check.
