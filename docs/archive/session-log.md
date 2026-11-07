# Session Log

## 2026-05-24 [saved]
Goal: Write implementation plan for Sub-project A recognition dataset builder.
Decisions:
- Plan at `docs/plans/2026-05-24-recognition-dataset-builder.md`: 6 TDD tasks creating 5 new modules + 20 tests; manual UI acceptance at end.
- Scanner writes `classes.json` snapshot on every scan because spec §4 requires it for drift detection; gap found in self-review.
- Subagent-driven execution recommended because 6 tasks ≥ 5 threshold and fresh context per task improves reliability.
Rejected:
- Inline execution — too much shared state risk if subagent fails mid-task.
- Committed fixture files — non-git workspace; tests synthesize under tmp_path.
Open:
- User picks execution mode to start Task 1.

## 2026-05-24 [saved]
Goal: Brainstorm ML recognition revival via offline dataset + labeling tool.
Decisions:
- Decomposed into 3 sequential sub-projects: A (dataset+UI), B (training+ONNX), C (runtime ML path with template fallback). Each gets own spec.
- Sub-project A spec at `docs/specs/2026-05-24-recognition-dataset-builder-design.md`: manifest.json + flat crops (not ImageFolder) for audit trail; PyQt5 by-run UI.
- Mandatory one-click-per-cell review enforced because bot is ~95% accurate, skim-confirm would poison training set.
- Class taxonomy is fixed Python enum (color×special combined) — UI dropdowns only, no free-text — eliminates typo failure mode.
- ML returns to runtime ONLY behind feature flag with template matcher as fallback. Reverses 2026-05-24 ML removal but preserves rollback path.
Rejected:
- ImageFolder storage — loses per-crop audit metadata.
- By-class gallery view as MVP — deferred to future enhancement.
- Single mega-spec for all 3 sub-projects — too large to execute in one session.
Open:
- User review of Sub-project A spec → then `writing-plans`.
- Sub-projects B and C: separate brainstorm sessions later.

## 2026-05-24 11:01 [saved] [superseded by 2026-05-31]
Goal: Implementirati evidence-gated mode policy za MM strategy ranking.
Decisions:
- Multiplier Mushrooms evidence is explicit in debug payloads because raw mode bonus hid why moves ranked higher.
- Final-phase mushroom setup is discounted only without categorical extra because setup value cannot pay off after the turn ends.
- Red/Blue and Laser heuristics remain no-op without observable state because community claims are insufficient for hardcoding.
Rejected:
- Hardcoded Red/Blue penalties.
- Laser column scoring without detected laser state.
Open:
- Local onnxruntime DLL blocks full suite. [superseded by 2026-05-24]
- Live BlueStacks validation still separate.

## 2026-05-31 [saved]
Goal: Add ML Red/Blue dual tile support.
Decisions:
- Red/Blue ML mode_target maps to SPECIAL_RED_BLUE_TILE because the capsule is dual-color.
- Dual tile matches blue or red but blue score applies only on blue matches.
- red_blue_tile is reviewable for future ML training because current ONNX cannot emit unseen classes.
Rejected:
- Template matching path for Red/Blue tile.
Open:
- Retrain/promote ONNX when red_blue_tile crops exist.

## 2026-05-24 [saved]
Goal: Napisati implementation plan za Showdown toggle.
Decisions:
- Plan: `docs/plans/2026-05-24-showdown-toggle-versus-move-dots.md`, 5 taskova, TDD ordering.
- Tasks 1-2: reader (test + impl); Tasks 3-4: GUI widget + persistence; Task 5: manual geometry verification sa real PvP screenshot.
- Subagent-Driven execution preporuceno (5 tasks, fresh context per task).
Rejected:
- Single-task implementation — prevelika dimenzija za jedan PR, gubi se TDD checkpoint.
Open:
- User da odobri execution mode.

## 2026-05-24 [saved]
Goal: Dodati Showdown toggle za PvP (2-dot) prepoznavanje pored solo (6-dot).
Decisions:
- Approach A: dva detektora (`_read_solo_move_dot_count` + `_read_versus_move_dot_count`), bira se preko `showdown: bool` kwarg.
- Showdown ON = default = 6-dot solo (trenutno ponasanje); OFF = 2-dot versus (broji samo leve plave, ignorise desne ruzicaste).
- GUI `ShowdownCheck` u `StateGroup` pored `AutoStateCheck`; perzistencija u `settings.json` kao `showdown_mode`.
- Spec: `docs/specs/2026-05-24-showdown-toggle-versus-move-dots-design.md`.
Rejected:
- Auto-detekcija bez toggle-a — rizik miss-klasifikacije (user odbio).
- Jedan parametrizovan detektor — previse if-ova jer su ulazi vizuelno razliciti problemi.
Open:
- Geometrija `versus_moves_region_from_board()` ce mozda zahtevati tuning posle prvog debug crop-a.

## 2026-05-24 [saved]
Goal: Ubrzati detekciju poteza (screenshot → potez).
Decisions:
- `recognition_ms` je bottleneck (62% vremena, 643ms mean) — compute je već brz (67ms, 6%).
- Fine-grained instrumentacija odobrena pre optimizacije da se nađe tačan uzrok gap-a (~452ms neidentifikovano).
- `update_board_2` dobija `_diag=None` param; dict se puni tajmerima samo kad se prosledi.
- Plan: `docs/plans/2026-05-24-recognition-timing-instrumentation.md`; spec: `docs/specs/...design.md`.
Rejected:
- Optimizovati compute (move strategy) — već 67ms, nema prostora.
- Preskočiti instrumentaciju i odmah menjati kod — merenje mora biti pre fixa.
Open:
- Pokrenuti plan (Task 1-3) u sledećoj sesiji. [superseded by 2026-05-24]

## 2026-05-24 [saved]
Goal: Implementirati fine-grained timing instrumentaciju u recognition.py i runtime.py.
Decisions:
- Tasks 1+2 završeni: `update_board_2` dobio `_diag=None` param sa 6 checkpoint-a; `runtime.py` gradi `_recognition_breakdown` dict i upisuje ga u `timings.json`.
- Oba fajla kompajliraju (`python -c "import recognition; import runtime; print('OK')`).
- Task 3 čeka korisnika: pokrenuti bot 3-5 poteza sa debug enabled, inspekcija timings.json.
Rejected:
- (nema novih odbijenih pristupa u ovoj sesiji)
Open:
- Task 3 verifikacija na pravom run-u.

## 2026-05-24 12:09 [saved]
Goal: Draft decision-audit and extra-preservation strategy spec.
Decisions:
- Audit-first design chosen because visible JSON evidence should precede ranking weight changes.
- Extra preservation is a tie-breaker only because it must not demote clearly stronger extras.
- Perk value typing is classification only because existing conservative gates must remain intact.
Rejected:
- Opponent-denial scoring without observed state.
- Save-booster/comeback logic without score pressure.
Open:
- User review before implementation plan.

## 2026-05-24 12:21 [saved]
Goal: Write TDD plan for decision-audit and extra-preservation.
Decisions:
- Plan is self-contained because future execution should not depend on chat context.
- Execution defaults to subagent-driven because the plan has seven tasks.
- Preservation tie-breaker remains bounded by comparable-score buckets because stronger extras must stay ahead.
Rejected:
- Git commit steps in this non-Git workspace.
- Broad behavior changes before audit fields.
Open:
- User reply to start execution.

## 2026-05-24 21:04 [saved]
Goal: Implement Sub-project B CNN training/export stack.
Decisions:
- Added root-level training modules because Sub-project C needs ONNX plus metadata contract.
- Export suppresses incidental ORT probe because Windows DLL import is unstable and verify-export is optional.
- Live training remains blocked until all 9849 crops are reviewed.
Rejected:
- Editing runtime recognition files before Sub-project C.
- Training on unreviewed labels.
Open:
- Review recognition dataset.
- Run live training after review.

## 2026-05-25 01:59 [saved] [superseded by 2026-05-28]
Goal: Complete Sub-project B live training.
Decisions:
- User accepted unconfirmed labels as automatic; backup was created first to preserve rollback.
- Singleton classes no longer block split because one example cannot appear in train and validation.
- Export-only rejects Windows device checkpoint paths before `torch.load`.
Rejected:
- Training before fully reviewed manifest.
- Treating `nul` as a real checkpoint file.
Open:
- Sub-project C runtime integration.
- Spot-check auto-accepted labels.

## 2026-05-28 20:26 [saved] [superseded by 2026-05-28]
Goal: Prevent accidental bulk dataset review.
Decisions:
- `Confirm all` is disabled because new scanned crops must not be bulk-added.
- `Mark as fix` accepts same-label cells because it is now the manual add path.
- Training stays reviewed-only because no incremental training was requested.
Rejected:
- Future auto-accepting unreviewed labels.
- Train-new-only changes in this slice.
Open:
- Live PyQt smoke.

## 2026-05-28 21:18 [saved]
Goal: Make `review-existing` a staging workflow.
Decisions:
- `review-existing` deletes untouched session crops because the user wants only marked cells retained.
- Cleanup is close-time only because selected `Mark as fix` entries must survive.
- Regular `review` avoids auto-delete because it may be used for normal dataset maintenance.
Rejected:
- Deleting all unreviewed dataset entries automatically.
- Changing training or scanner behavior.
Open:
- Explicit approval before cleaning existing real crops.

## 2026-05-25 02:05 [saved]
Goal: Add append-review workflow and per-class accuracy reports.
Decisions:
- `dataset_cli scan` remains append path; `review --only-unreviewed` limits UI to new cells.
- Training writes per-class accuracy JSON/CSV because runtime decisions need class-level confidence evidence.
- Small random label noise is tolerable, but rare-class or systematic mistakes remain high-risk.
Rejected:
- Manual navigation through old reviewed runs after every game.
- Trusting aggregate accuracy without per-class support.
Open:
- Spot-check low-support classes.
- Integrate reports into Sub-project C.

## 2026-05-26 00:00 [saved]
Goal: Complete move-intent debug audit.
Decisions:
- Intent trace stays audit-only because ranking and gameplay behavior must remain unchanged.
- Debug reports write `intent.txt` and append `intent_audit.md` because post-game review needs readable evidence.
- Perk-only rendering ignores top-level best move because selected action must not misrepresent intent.
Rejected:
- Visual overlays in this slice.
- Claiming refill-dependent cascades as known intent.
Open:
- Live BlueStacks review of new debug files.

## 2026-05-26 22:23 [saved]
Goal: Harden manual recognition against animation frames.
Decisions:
- Manual Check Best Move requires two matching clean frames because one filled frame can still be animated.
- `Cekaj anim.` toggle defaults on because the user needs a quick escape hatch without weakening the safe default.
- Dataset purge must preserve label-integrity crop IDs because tests encode visually confirmed hard labels.
Rejected:
- Blind purge of all unreviewed entries without protected-label restore.
- Ranking moves from unstable manual frames.
Open:
- Live BlueStacks animation smoke.

## 2026-05-27 01:23 [saved]
Goal: Add directional Fireworks tiles.
Decisions:
- Fireworks labels are color-bound because strategy still needs tile color.
- Directional special ids preserve arrow direction because horizontal/vertical collapsed runtime behavior.
- Fireworks rockets keep swap suppression because special-special swaps are not normal Fireworks activations.
Rejected:
- Color-agnostic `firework_up` labels.
- Treating directional rockets as normal row/column arrows.
Open:
- Retrain ONNX model.
- Live BlueStacks smoke.

## 2026-05-31 02:15 [saved]
Goal: Fix Fireworks move ranking.
Decisions:
- Directional fireworks never special-swap because Match Masters does not allow combining two fireworks.
- Zero-blue firework activations are downranked because blue charge should beat empty Fireworks chains.
Rejected:
- Mode-only swap suppression.
- Treating firework activation bonus as equal to blue charge.
Open:
- Live BlueStacks smoke.

## 2026-05-28 20:57 [saved]
Goal: Add Zany Zappers labels.
Decisions:
- Zapper labels are color-bound and counter-bound because ML must read both color and visible number.
- Special ids 25/26 map to counters 1/2 because Vinnie SE starts at 30.
- Counter 2 decrements; counter 1 zaps row and column.
Rejected:
- Single generic `zapper` label.
- Treating counter ids as created bombs.
Open:
- Retrain after reviewed Zany crops.

## 2026-05-29 06:39 [saved] [superseded by 2026-05-31]
Goal: Force extra moves before all other choices.
Decisions:
- Extra preempts Mixy, Froggy, perks, booster activation, and raw score because turn preservation wins unconditionally.
- Booster-immediate waits behind extras because the user explicitly requested every-case extra priority.
- `choose_best_move()` uses fast extra-only preemption because full runtime prioritization broke the benchmark.
Rejected:
- Letting mode-specific branches override an available extra.
Open:
- Full-suite dataset/Torch failures remain unrelated.

## 2026-05-31 01:59 [saved]
Goal: Fix xtra marker scoring.
Decisions:
- Xtra markers stay on board coordinates because observed runs keep `special_board` unchanged after swaps.
- False extras lose priority because only clearing the original xtra cell grants marker extra.
Rejected:
- Moving `SPECIAL_XTRA_MOVE_TILE` with swapped or dropped gems.
Open:
- Full suite not rerun.


## 2026-05-29 20:49 [saved]
Goal: Prefer blue-purpose perk usage.
Decisions:
- Perk blue clears reuse booster-aware blue priority because perks should help fill blue charge.
- Follow-up blue moves use reduced priority because they need a later move after activation.
- Existing hard gates stay first because boosters and must-play normal moves still override perks.
Rejected:
- Boosting score-only perk actions.
Open:
- Live BlueStacks play not run.

## 2026-05-29 21:07 [saved]
Goal: Use perks before matches pass.
Decisions:
- Perk gating now allows setup windows because score-only and special-only moves should not consume whole games without perks.
- Active booster, extra/must-play moves, and already-fillable blue plans still block perks because those are stronger immediate priorities.
- Energy Boost can convert a non-blue follow-up because its practical role is blue charge.
Rejected:
- Treating every special/score move as too good for perks.
Open:
- Live BlueStacks play not run.

## 2026-05-29 21:18 [saved]
Goal: Let auto use remaining perks after the first one without rapid double activation.
Decisions:
- The last observed run showed Star Maker stayed detected/available, but GUI sent `allow_perk_activation=false` after Mini Cleo.
- Replaced the one-per-auto-run perk guard with a short post-perk cooldown via `AUTO_POST_PERK_COOLDOWN_SECONDS`.
- During that cooldown auto keeps the remaining perk selected but passes `allow_perk_activation=false`; after cooldown it can activate the remaining perk.
Rejected:
- Keeping `_auto_perk_used_this_run` as a hard block for the rest of the match.
Open:
- Live BlueStacks play not run.
## 2026-05-29 06:50 [saved]
Goal: Keep extras through live lookahead.
Decisions:
- Limited live lookahead retains guaranteed/direct extras because raw top-score windows can hide blue squares.
- The 06:44 run proved candidate truncation, not recognition or square-mode failure.
Rejected:
- Treating `candidates.json` top five as the full legal move set.
Open:
- Full-suite dataset/Torch failures remain unrelated.

## 2026-05-29 08:25 [saved]
Goal: Replace manual perk selection.
Decisions:
- Perk slot state comes from screenshot templates because manual dropdowns drift from game truth.
- Used and unknown slots resolve to `none` because runtime must not click unavailable perks.
- GUI shows detected status only because manual Perk 1/2 controls are no longer authoritative.
Rejected:
- Persisting selected perk dropdown state.
Open:
- Add templates when new perk screenshots exist.

## 2026-05-29 08:39 [saved]
Goal: Add Chest and Green Leaf templates.
Decisions:
- Chest templates override ML-primary lotus predictions because active Chest mode defines those cells as targets.
- Green Leaf uses a live `+3` template because the clean leaf asset misses glowing board pieces.
- The overlay is mode-scoped because other ML-primary fast paths must stay template-free.

## 2026-05-29 08:46 [saved]
Goal: Fix grey perk status.
Decisions:
- Perk identity keeps grayscale shape score because it recognizes the icon reliably.
- Available/used status uses RGB distance within the matched perk because grayscale cannot separate blue from grey.
Rejected:
- Trusting the grayscale template winner for status.
Open:
- Add templates when new perk screenshots exist.
Rejected:
- Running these templates in `None` mode.
Open:
- Full-suite dataset/Torch failures remain unrelated.

## 2026-05-31 03:28 [saved]
Goal: Make Froggy Lotus override extra priority.
Decisions:
- Lotus-trigger moves preempt extra moves because the user wants Lotus played whenever legal.
- Lotus colors sort yellow, purple, orange, green, blue, red because fixed color priority now beats raw bonus.
Rejected:
- Letting red/blue win Lotus solely by larger board count.
Open:
- Full-suite dataset/Torch failures remain unrelated.

## 2026-05-31 03:45 [saved]
Goal: Stop live lookahead hiding Lotus triggers.
Decisions:
- `choose_best_move()` ignores positive live candidate limits when Lotus exists because truncated ranking hid legal yellow triggers.
Rejected:
- Trusting `LIVE_LOOKAHEAD_CANDIDATES=5` to contain every Lotus option.
Open:
- Restart the running GUI so Python reloads `move_strategy.py`.

## 2026-05-31 04:13 [saved]
Goal: Stop ML Cleo appearing as blue.
Decisions:
- `cleo_bug` decodes to `DISCO_BALL` because Cleo must stay movable but not color-matchable.
- Cleo overlay labels omit color because the board value is only a sentinel.
Rejected:
- Mapping Cleo to blue, which creates false four-blue matches.
Open:
- Restart the running GUI so Python reloads recognition/runtime modules.

## 2026-05-31 03:57 [saved]
Goal: Fix weak Cleo live moves.
Decisions:
- Cleo blue color preference is a tie-breaker because score already prices blue value.
- Guaranteed extras remain categorical because deterministic turn preservation beats RNG Cleo value.
- Live Cleo sorting uses score before color because tier ordering hid Cleo+special swaps.
Rejected:
- Letting blue Cleo swaps outrank stronger probabilistic Cleo scores.
Open:
- Restart the running GUI so Python reloads `move_strategy.py`.

## 2026-05-31 04:44 [saved]
Goal: Stop booster activate auto stalls.
Decisions:
- Same-board booster attempts count through motion/visual noise because glowing frames can hide the fallback path.
- Fallback still requires matching board signature because changed boards must use normal stability.
Rejected:
- Counting only `wait_reason=change` after booster clicks.
Open:
- Restart the running GUI so Python reloads `gui.py`.

## 2026-05-31 06:31 [saved]
Goal: Block Zany direct special swaps.
Decisions:
- The direct special-swap gate rejects Zany participants because the game only activates them through clears.
- Zany remains activatable through match/chain resolution because counter-one still zaps row and column.
Rejected:
- Removing Zany from all activatable logic.
Open:
- Restart the running GUI so Python reloads `move_strategy.py`.

## 2026-06-03 09:18 [saved]
Goal: Enable Sweep SE broom labeling.
Decisions:
- `broom` is colorless because target color comes from the adjacent swapped tile.
- Broom is excluded from normal-swap handling until a dedicated Sweep evaluator exists.
Rejected:
- Including opponent-board-risk item 8 in Sweep evaluation.
Open:
- Resolve existing Spray SE taxonomy mismatch separately.
