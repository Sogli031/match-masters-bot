# Game modes: engine rules, bot support, open questions

Where the facts in this document come from — nothing here is inferred from
watching the game:

* `Match-Masters/TextAsset/Constants` → `general.matchRules` (34 rulesets, each
  with its `id` and, where it has one, its `boardModelName`) and
  `general.gameModes` / `general.arenas` (which arena each mode is played in).
* `Debug/network_capture/2026-08-15/.../Match3Engine/` → the decompiled engine:
  `BoardModelName.cs` (the 37 board models), `MatchRulesModel.cs` (every rule as
  a named field), the per-board classes and their compiled constants.
* The live `ShowSettings.matchRules` payloads captured on 2026-08-15, which show
  the id a league match actually reports.

Two structural facts drive everything below:

1. **A mode is a board model plus a set of rule flags.** `MatchRulesModel` has
   ~150 fields; several named modes are nothing but one of them being true.
   Modes are therefore not mutually exclusive, and a mode name alone never
   fully determines behaviour.
2. **A league match reports `<stageId>-master-league`.** Captured:
   `plunder-pirates-master-league` → `boardModelName` 8 (`PlunderPiratesBoard`),
   `dustville-duel-master-league` → 4 (`DustvilleDuelBoard`). The engine names
   each arena's board model after the arena, which is what makes the prefix
   mapping in `memory_gui.RULES_ID_TO_MODE` safe.

**The decompiled sources carry signatures and constants but no method bodies.**
So a board model tells us *that* a mode has, say, a blast area
(`GetAreaOfBoardSpecialEffect`) and how many tiles spawn — never the shape of
the blast. That boundary is why several modes below stay unimplemented instead
of being guessed at.

## Status table

### Supported before this change

| Engine id / arena | Board model | `GameMode` |
| --- | --- | --- |
| `fireworks-festival` | `FireworksFestivalBoard` (9) | `FIREWORKS` |
| `plunder-pirates` | `PlunderPiratesBoard` (8) | `CHEST` |
| `crystal-cave` | `CrystalCaveBoard` (3) | `PURPLE_GEM` |
| `jungle-rumble` | `JungleRumbleBoard` (7) | `GREEN_LEAF` |
| `laser-matches` | `LightsabersBoard` (18) | `LASER` |
| `bulls-eye` / `bullseye-bash` | `BullseyeBoard` (13) | `BOUNTY` |
| `funky-tiles` | `FunkyTilesBoard` (12) | `FUNKY_TILES` |
| `color-crystals` | `ColorBombBoard` (16) | `COLOR_CRYSTALS` |
| `drillin-down` / `drill-down` | `DigDownBoard` (17) | `DRILLIN_DOWN` |
| `crazy-columns` | `CrazyColumnsBoard` (19) | `CRAZY_COLUMNS` |
| `hot-color` | `HotColorBoard` (21) | `HOT_COLOR` |
| `lights-up` | `LightsUpBoard` (37) | `LIGHTS_UP` |
| `color-climb` | `RainbowMultiplierBoard` (35) | `COLOR_CLIMB` (2026-09-13, see below) |
| `extra-moves` | `ExtraMovesBoard` (14) | `XTRA_MOVES` |
| `infinite-moves` | — (`reduceMoveOnValidSwap` = false) | `INFINITE_MOVES` |
| `arcade-man` *(captured 2026-08-21)* | `MatchLineBoard` (27) | `ARCADE_MAN` |
| `color-crush` | `ColorCrushBoard` (28) | `COLOR_CRUSH` |
| *(id not yet captured)* | `VerticalRushBoard` (23) | `VERTICAL_RUSH` |
| `multiplier-mushrooms` | `MultiplierMushroomsBoard` (29) | `MULTIPLIER_MUSHROOMS` |
| `the-floor-is-lava` | `FloorIsLavaBoard` (36) | `FLOOR_IS_LAVA` |
| *(id not yet captured)* | `EnergizedBoard` (26) | `ENERGIZED` |
| *(id not yet captured)* | — | `RED_AND_BLUE`, `SPECIAL_O_RAMA` |

The "id not yet captured" rows work fine when the mode is selected by hand in
the GUI; what is missing is only the automatic `RULES_ID_TO_MODE` entry, which
needs one memory snapshot taken while that mode is on screen.

### Added by this change

| Engine id | Rule field | `GameMode` | What the bot now does |
| --- | --- | --- | --- |
| `blow-em-up` | `specialsAutoExplode` | `BLOW_EM_UP` | A special created by a match fires in the same step instead of staying on the board, so its clear, its blue and its cascades are all part of this move's value. |
| `lightning-strike` | `allSpecialsLightning` | `LIGHTNING_STRIKE` | Every created special is a Lightning regardless of the shape that made it, so the simulator resolves its effect instead of carrying an unknown `CREATED_SPECIAL`. |
| `energy` / `shared-energy` | `bothColorsChargeEnergy` | `SHARED_ENERGY` | Red charges the booster meter alongside blue (the game's own text: "Both Red & Blue pieces charge your booster"), so red counts everywhere blue does. |
| — | `destroyRowOnHorizontalMatch` / `destroyColumnOnVerticalMatch` | *(flags, not a mode)* | The two halves of `MatchLineBoard` are now separately selectable. Arcade Man does the same thing from its board model, with both flags off — see below. |
| `candy-world` | `CandyWorldBoard` (2) | `CANDY_WORLD` | A candy is a two-colour (blue/red) piece: matched blue it charges the booster, matched red it does not. See below. |
| `dustville-duel` | `DustvilleDuelBoard` (4) | `DUSTVILLE_DUEL` | Three replenishing "wanted" tiles are paid a collect bonus worth two blue pieces each — the guaranteed `minBluesToPick`. See below. |
| `mighty-mushrooms` | `MightyMushroomsBoard` (30) | `MULTIPLIER_MUSHROOMS` | The same mushrooms as board 29 in a different arena, confirmed in play. |
| `bombs-away`, `match-and-hatch`, `multiplier-madness` | 0 / 0 / 22 | *(no strategy of their own)* | See "Known rulesets that need no strategy of their own". |

#### The 2026-08-19 captures (`Debug/unmapped_modes/`, 420 frames)

Six rulesets were recorded while being played. What each one actually put on
the board, read out of the snapshots rather than guessed:

| id | board model | mode-specific board content | live scalar |
| --- | --- | --- | --- |
| `dustville-duel-master-league` | 4 | exactly 3 `SlotValue` 16 tiles, one colour, topped straight back up to 3 | — |
| `mighty-mushrooms` | 30 | `SlotValue` 19 mushrooms, `origin` 2 (board-spawned) | `scoreMultiplier` 1 → 46 |
| `match-and-hatch` | 0 | `SlotValue` 19 — the hatch *animation*, not a piece of its own | `scoreMultiplier` 0 → 8 |
| `bombs-away` | 0 | `SlotValue` 6 Bombs the board seeds and replenishes (no combo, no owning player) | — |
| `column-mania` | 32 | none found on the slots — the mode state is per *cell* (`scoreMultiplier`) plus the board's own `colsToIncrease` | per-column x1 → live |
| `multiplier-madness` | 22 | none at all — every non-plain slot is a player-created special | `scoreMultiplier` 1 → 7 |

Two traps that cost time and are worth writing down:

* **`scoreModifierOrigin` / `scoreModifierBonus` are not mode evidence.** Eight
  to eleven pieces of one colour get a bonus, gather into a 3x3 block and
  vanish — that is the equipped booster's `asTempSpecials` animation, and it
  shows up identically in three unrelated modes.
* **`SlotValue` 19 is not always a mushroom.** Match & Hatch uses the same value
  for its egg, which is only the animation a special hatches out of. The adapter
  cannot tell them apart from the slot alone; it is harmless today because the
  mushroom bonus is gated on `GameMode.MULTIPLIER_MUSHROOMS`, which Match & Hatch
  never selects.

#### The 2026-08-22 captures (`Debug/unmapped_modes/`, 654 frames)

Four more rulesets recorded while being played. Only one of them turned out to
be a gap:

| id | board model | what it actually is | verdict |
| --- | --- | --- | --- |
| `score-market` | 20 (`StockMarketBoard`) | `board_fields` names the mechanic: `newScoreOverrides` (`Dictionary<SlotColor,int>`) rewritten every move, capped by `MAX_SCORE` / `ENERGY_COLORS_MAX_SCORE` | no strategy of its own — the rewritten per-colour points reach the bot through the live score legend each move |
| `square-match` | 0 | `isSquareMatch` and nothing else; every non-plain slot is a player-created special | no strategy of its own |
| `mutation-lab-pvp-mode` | 0 | `isMutationLab`; the rules are the picked mutations, read from `GameLogic.mutationsActivatedList` | handled outside the mode entry |
| `mutation-lab-solo-mode` | 0 | same, plus `soloRefillMode` | handled outside the mode entry |

Three things worth keeping:

* **An arena id is not a board model.** `score-market` is the same
  `StockMarketBoard` as the already-known `stock-market`, so the one entry did
  not cover the other and 180 frames were recorded for a board the bot already
  played correctly. The board model number is the stronger identifier; the id
  table is only a shortcut.
* **Score Market's only real gap is planning ahead.** The bot reads the legend
  live, so it prices the *current* move right; what it cannot do is anticipate
  the next rewrite — which is not recoverable from a settled board anyway.
  `specialsAutoExplode` was on in 60 of the 180 frames and reaches the
  simulator straight from the rules, so it needs no mode entry.
* **Mutation Lab must not be filed under "no special rules".** Its rules are
  real, they just arrive one mutation at a time. It gets its own label
  (`RULES_ID_HANDLED_OUTSIDE_MODE`) so the readout says where they come from
  instead of claiming the match changes nothing. Still unnamed: mutation
  **type 19** (live with `config.color` 4 = purple, Instant, repeatable). The
  catalogue's declaration order puts `Painter` there, but the catalogue ships
  Painter in blue only while `ConvertToSpecial` has a purple Instant repeatable
  variant — two candidates is a guess, so it prints as "tip 19 (?)".

#### Arcade Man (`arcade-man`, `MatchLineBoard` = 27)

Captured live 2026-08-21 (`Debug/unmapped_modes/arcade-man/`, 4 frames):
`MatchRulesModel.id` = `arcade-man`, `title` "Arcade Man", `boardModelName` 27,
solo (`pvpMode` 1), 7x7, six colours, five moves, one turn, 25 min timer, solo
targets 200 / 625 / 3375.

**The two line-destruction rule flags are false.** `destroyRowOnHorizontalMatch`
and `destroyColumnOnVerticalMatch` are both off on the live ruleset, and so are
`explosionOnMatch`, `verticalMatchDestroyColor` and `colorMatchExplodeColor`.
The sweep is `MatchLineBoard`'s own behaviour, which is why the id had to be
mapped: with the id unmapped the mode resolved to `GameMode.NONE` and the bot
priced every match as a plain three or four. The earlier note in this document
that "Arcade Man is the ruleset with both flags on" was wrong; the simulator was
right anyway, because `_arcade_man_cells` is gated on the mode entry rather than
on the flags.

The same capture measures the rule. The move at 10:28:25 swapped (3,4) so that
column 4 read `3 4 3 3 3 3 4` with the match at rows 2..5, and
`accumulatedTurnScore` came out **33**:

| model | arithmetic | total |
| --- | --- | --- |
| plain match-4 | 4 x 5 | 20 |
| whole column | 5 + 4 + 5 + 5 + 5 + 5 + 4 | **33** |

Per-colour points are `SlotModel.score` from the same frame (the matched colour
is worth 5, the two other tiles in the column 4 each). The tiles that came back
are refill: none of the untouched positions survived, which a match-only clear
would have left in place.

The match-4's created special is a Column piece and it appears at **(6, 4)** —
placed on the swapped cell as usual, then dropped to the bottom of the emptied
column by gravity. Nothing else on the board moved, so the sweep is limited to
the matched line.

Direct matches only, and that is not a guess: `MatchLineBoard` hooks
`AfterPerformedSwap` alone (`docs/game_mode_logic_from_code.md`), which is the
`cascade_number == 1` gate the simulator already applies. The old note that it
"fires on every cascade" is wrong. This capture holds a single chain-free move,
so it neither adds to nor contradicts that.

#### Color Crush (`color-crush`, `ColorCrushBoard` = 28)

Captured live 2026-08-21 (`Debug/unmapped_modes/color-crush/`, 4 frames):
`MatchRulesModel.id` = `color-crush`, `title` "Color Crush", `boardModelName`
28, solo (`pvpMode` 1), 7x7, six colours, eight moves, one turn, 25 min timer,
solo targets 6000 / 12500 / 28000. No flag on the ruleset carries the mode: the
whole-colour explosion lives in the board model, which is exactly why the id has
to be mapped rather than inferred.

The snapshots also confirm the rule the simulator already implements. The move
at 09:14:20 matched green and the board went from 8 green tiles to 4 — a plain
match clears 3 and cannot remove tiles that are nowhere near it — while
`accumulatedTurnScore` jumped by 16, i.e. all 8 green cells at the 2 points the
score legend prints for green. The four tiles that came back are refill.

`GameMode.COLOR_CRUSH` needed no new code: `runtime` turns `color_crush` on from
the mode alone, and the whole-colour wipe is `_color_crush_cells` on the first
cascade. The live score legend from memory keeps precedence over
`COLOR_CRUSH_DEFAULT_SCORE_VALUES`.

**Red is excluded only on a versus board** (settled from the engine code on
2026-09-15, `Debug/reverse/colorcrush`). `ColorCrushBoard` holds two lists and
`<AfterPerformedSwap>b__0` picks by `GameLogic.IsSingleplayerBoard`:
`BOARD_SPECIAL_COLORS` = [Blue, Red] in versus and
`BOARD_SINGLE_PLAYER_SPECIAL_COLORS` = [Blue] solo. The simulator follows it via
`color_crush_active(single_player=...)` / `color_crush_inert_colors()`. Both
older readings below were right for their own board: 2026-08-21 was solo, and
the 2026-08-28 "red stays" measurement was not. On 2026-09-15 06:30:33 (solo) the
red-inert model promised a cascade extra behind a red three; the game wiped 8
of the 9 reds and the turn was lost.

The 2026-08-21 solo measurements (11 memory-read moves):

| Run | direct match | what the board actually lost |
| --- | --- | --- |
| `2026-08-21_11-24-10_204` | red three, 8 reds on the board | all 8, spread over all seven columns; the reds in the next frame all sit in the top rows (refill) |
| `2026-08-21_11-23-40_527` | red four, 10 reds | 9-10 of them, nothing else touched, +98 points |
| `2026-08-21_11-20-05_909` | blue three, 10 blues | exactly its own 3 |
| `2026-08-21_11-20-26_205` | blue three, 8 blues | 3 (the rest of the move's clears came from a Vinnie heart) |

On a solo board blue is the only inert colour (`COLOR_CRUSH_SINGLE_PLAYER_INERT_COLORS`):
it is the colour that charges your own meter. The cost of the red-inert model
there was a red match priced at three or four cells when the game was about to
clear ten, plus phantom cascades behind it.

Measuring this needs no extra tooling: `memory_frames.jsonl` in every run holds
the boards mid-move, and a per-column bottom-up alignment of two consecutive
frames says which tiles vanished and which are refill.

**Open:** whether the wipe also fires on a *cascade* match (the simulator says
no, first cascade only). The frames caught after a wipe are seconds apart and
already past a random refill, so they neither confirm nor refute it -- and the
simulator stops at that refill boundary anyway, which is why the move totals it
reports in this mode are a floor (22 predicted vs 33 measured on
`2026-08-21_11-20-18_220`, where the extra clears all came after the refill).

#### Dustville Duel (`dustville-duel`, `DustvilleDuelBoard` = 4)

60 live frames, 2026-08-19: three wanted tiles, all the same colour, ordinary
matchable and movable pieces carrying `SlotValue` 16 with no second colour — so
the adapter already reads them as `SPECIAL_MODE_TARGET` and always has. What was
missing was only a reason to go and get them.

The live config (2026-08-15) is `wantedTilesCount` 3, `wantedShoots` 4,
`minBluesToPick` 2, `scoreBonusPerHit` 1, `replenishRate` 3. Four shots of which
at least two pick blue is the All Aboard bandit's shape with different counts,
and the bot already models that. What is still missing is what the other two
shots hit, so `MODE_WEIGHTS[DUSTVILLE_DUEL]["mode_target"]` is set to the
guaranteed floor — 2.0, i.e. two blue pieces per collected tile — and nothing
more. **Open:** confirm the shot count and whether the shots destroy as well as
recolour; then the weight can stop being a floor.


Implementation: module flags plus context managers in `move_strategy.py`
(`all_specials_lightning_active`, `both_colors_charge_energy_active`,
`line_destruction_active`), matching the existing `color_crush_active` /
`energized_charge_colors_active` pattern. `runtime.CheckBestMoveRequest` gained
`all_specials_lightning` and `line_destruction`; the memory GUI fills both from
the engine's own rules, and `bothColorsChargeEnergy` is folded into the charge
colours it already passes. Picking the mode in the GUI turns the same rule on,
so the screen path and the memory path agree.

Tests: `tests/test_engine_rule_flags.py`.

#### Candy World (`candy-world`, `CandyWorldBoard` = 2)

Captured live 2026-08-17: `MatchRulesModel.id` = `candy-world-master-league`,
`boardModelName` 2, six colours, 7x7, six moves, one turn, solo refill. The raw
snapshots are in `Debug/unmapped_modes/candy-world-master-league/`.

The candy is a **two-colour piece**, and the snapshot says so outright: each of
the three candies carries `SlotValue` 16 (`BoardSpecial`) with `SlotColor` blue
*and* `SlotColor2` red, where every ordinary piece has `SlotColor2` = None. It
plays as whichever of the two it is matched with — matched blue it is a blue
piece and charges the booster, matched red it is a red piece and charges
nothing (confirmed in play).

That is exactly the Red and Blue tile the engine layer already models, so no new
rule was needed:

* `board_source` reads a `BoardSpecial` whose two colours are the blue/red pair
  as `SPECIAL_RED_BLUE_TILE`; a `BoardSpecial` without a second colour stays the
  plain `SPECIAL_MODE_TARGET` other board models use it for. The colour pair
  decides, not the board model — the adapter never sees the board model.
* the flexible-colour matcher (`_color_match_mask`) then lets a candy complete
  either a blue three or a red three, so those moves are generated at all;
* `_red_blue_tile_cleared_color` credits the cleared candy to the colour it was
  matched as, which is what puts it in — or keeps it out of — the `blue_cells`
  counter the booster scoring reads.

`MODE_WEIGHTS[CANDY_WORLD]` therefore pays no collect bonus (`mode_target` 0): a
candy is a coloured piece, not a collectible, and a synthetic bonus would pay
for candy the bot only matched as red.

Board source: the memory reader. The screen path has no candy template, so on
the ML source a candy reads as a plain piece of one colour — the red half of it
is simply invisible there.

Left open: what a candy counts as when it is blown up by a special instead of
matched (it falls back to its primary colour, i.e. blue), and whether the pair
is always blue/red. `GetEnergyGivenPositions` is overridden by this board model,
which is consistent with "the blue half charges", but the method body is not in
the dump.

### Known rulesets that need no strategy of their own

`classic`, `academy-room`, `spotlight-stars`, `tribal-trouble`, `blitz`,
`hammer-time`, `teleport`, `shuffle`, `three-moves`, `five-colors`,
`mini-master`, `super-sized`, `yin-yang`, `ice-cream`, `rainbow`,
`stock-market`, `score-market`, `square-match`, `bombs-away`,
`match-and-hatch`, `multiplier-madness`.

The last three were added from the 2026-08-19 captures. `bombs-away` seeds
ordinary Bombs on the board (`biggerBombArea` false, so the 3x3 blast the
simulator already resolves) and adds nothing else; `match-and-hatch`'s egg is an
animation, not a piece; `multiplier-madness` has no board content whatsoever and
its `scoreMultiplier` scales every candidate move by the same factor, so it
cannot reorder them. **Open for `multiplier-madness`:** what raises the
multiplier. It climbed 1 → 7 in a 110 s match with no obvious per-move or
per-second cadence, and if it turns out to be raised by a *particular kind* of
move, that would be a real strategy change.

`score-market` and `square-match` were added from the 2026-08-22 captures; see
"The 2026-08-22 captures" above.

Their entire content is board size, colour count, blocked cells, timing,
available perks or per-colour point values — all of which the memory snapshot
already carries (blocked cells come from the cells themselves, per-colour points
from `SlotModel.score` through the score legend). They are listed in
`memory_gui.RULES_ID_NO_STRATEGY_CHANGE` so the UI shows "bez posebnih pravila"
instead of "nemapiran", which keeps a genuinely unknown id visible.

Caveat: `super-sized` is 9x9 and `mini-master` 6x6. The memory GUI already warns
that its board geometry profile is 7x7 and refuses to pretend otherwise.

### Not implemented — mechanic is not recoverable from the sources

Each of these is a real board model with no bot support. The decompilation gives
the class, its overridden hooks and its compiled default constants, but not the
method bodies, so the actual geometry is unknown.

| Arena / id | Board model | What is known | What is missing |
| --- | --- | --- | --- |
| `frozen-feud` | `FrozenFeudBoard` (6) | 3 frozen tiles, replenish chance 0, own `GetAreaOfBoardSpecialEffect`. | The blast area, and how many matches it takes to thaw a tile. |
| `vegas-views` | `VegasViewsBoard` (10) | 1 tile, replenish rate 1, chance 1, `SCORE_MULTIPLIER` 2, hooks `BeforeCombosDestroy`. | Whether the x2 applies to the whole move, the combo containing the tile, or only that tile. |
| `buried-treasure` | `BuriedTreasureBoard` (15) | Max 5 tiles, replenish rate 5, `SCORE` 10, `CHANCE_FOR_SCORE` 50; has `GetAreaOfBoardSpecialCellEffect`. | What the other 50% gives, and the area. |
| `rocket-riot` | `RocketRiotBoard` (5) | `ConvertTargetOnMoveStart`, `FireOnLastMoveEnd`, a single `Position`. | What the rocket destroys when it fires. |
| `stock-market` (board) | `StockMarketBoard` (20) | `MAX_SCORE` 10, `ENERGY_COLORS_MAX_SCORE` 1, rewrites `NewScoreOverrides` on `onMoveEnd`. | The rule that moves the prices. Note the *scoring* is already handled: the memory GUI reads the live per-colour values off `SlotModel.score`. |
| `nuclear`, `zany-zappers`, `switcheroo`, `multiplier-by-round`, `rainbow-multiplier`, `every-move-increase-score-multiplier` | 24, 25, 31–35 | Class names, hook lists and a few constants (e.g. `ZanyZappersBoard`: `REQ_PIECE_COUNT` 7, `MAX_ROW_FILL` 4). | The multiplier amounts and the geometry. |

### Column Mania (`ColumnManiaBoard`, 32)

Mapped 2026-08-22 from the compiled methods and the 60 captured frames in
`Debug/unmapped_modes/column-mania`.

* **The rule.** Every column has a score multiplier. `onGameStart`
  (rva 0x5778ba8) writes 1 into every cell. `AfterPerformedSwap`
  (rva 0x5778c3c) walks the slots of `combosToDestroy`, takes their distinct
  columns and appends the ones it does not already hold to `colsToIncrease`.
  `onMoveEnd` (rva 0x577935c) then walks the columns and raises every one in
  that list — the *whole* column — to `min(current + 1, MaxMultiplier)`,
  finally clearing the list. `MaxMultiplier` (rva 0x5778acc) is read off the
  board's `extraData` and falls back to 99, so the x10 the mode shows in game
  is a UI cap at most, not an engine one; the captured board carried no
  `extraData` at all.
* **Not Crazy Columns.** `CrazyColumnsBoard` (19) has no fields and only
  `onGameStart`: its x1..x7 ramp is baked in at the start and never moves.
  Column Mania starts flat and earns its ramp, so the two cannot share a
  scoring rule. Before this they did.
* **What the capture shows.** `colsToIncrease` is empty between moves and holds
  the move's columns while it resolves — in first-seen order, e.g.
  `[2, 1, 0, 3]`, and constant across every cascade frame of that move (six
  straight frames of `[4, 3, 5, 6]` at 07:05:15–07:05:19). The 12 moves in
  the capture raised 3.0 columns each on average, which is why aiming at a
  column is worth little: they all climb anyway.
* **Where the bot reads it.** The multipliers are on `CellModel`, not
  `SlotModel`, which is why 60 frames of slots showed nothing — every piece
  scores 1 in all of them. The agent now reads `CellModel.scoreMultiplier`
  through `BoardModel.GetCell` into `snapshot.cell_multipliers` (one value per
  column), and `board_source.column_mania_state()` hands it to the scorer.
  `colsToIncrease` alone is not enough: it is the pending delta for the move in
  flight and never says what the columns already stand at.
* **How it scores.** A cleared cell is worth its column's live multiplier, put
  back into cleared-cell units by dividing by the live mean — the same
  normalisation Crazy Columns uses, for the same reason. The columns the swap's
  own matches touch also earn +1 each for the rest of the match; that is priced
  at `column_mania_growth` (a third of a move for the whole board), split
  across the raised columns and tapered by each one's current multiplier. It is
  deliberately a tiebreaker: unmeasured against live scores, and a weight so it
  can be turned down without touching the model.
* **Unread.** Whether a *cascade* also adds to `colsToIncrease`. The hook is
  named for the swap and the captured list never grew after it was first seen,
  but the frames are 1–2s apart and cannot prove it, so only the swap's own
  matches are counted — the conservative half, as in Lights Up.

### Lights Up (`LightsUpBoard`, 37)

Mapped 2026-08-21 from the compiled methods, two live matches
(`Debug/memory_board`) and thirteen logged decisions (`Debug/runs`).

* **The rule.** One column is lit (`CurrentActiveColumn`, board field 0x7c).
  A *combo* with at least one cell in that column raises
  `PlayerControl.ScoreMultiplier` by 1 -- once per combo, not per cell: the
  predicate is `p => p.x == CurrentActiveColumn`, tested with an `Exists`. The
  cap is `MatchRulesModel.maxScoreMultiplier` (9999 in this arena), and
  `onGameStart` sets the multiplier to 1.
* **Only the swap's own matches count.** The engine has two paths and
  `HasEngineFix(5)` chooses: `BeforeCombosDestroy`, which runs on every destroy
  pass and would count cascades, or `ApplyMultiplierForSwap`, reached from
  `AfterPerformedSwap` / `OnAfterPerformedSwap`, which only ever sees the
  combos of the performed swap. The second is what the game does, reported from
  play and consistent with the prediction check below: a cascade that happens
  to fall through the lit column pays nothing. The bot counts
  `cascade_matches[0]` only, the same rule Vertical Rush uses.
* **A merged special earns nothing by sitting there.** A `MergeSwap` combo
  (type 9) needs its target position *in* the lit column **and**
  `IsExplosiveMerge`; anything else is skipped. So combining two specials in
  the lit column without a match there is worth no multiplier -- which is why
  the simulator, whose merges produce no `MatchGroup`, is right to score them
  at zero.
* **The column then moves.** `onMoveEnd` re-rolls `RandomWrapper::Range` until
  it differs from the current column while `RandomColumnChange` is true (true
  in every frame captured so far), and otherwise steps +1 with wrap. It does
  not move at all on a move that used a booster or a board ability.
* **Boosters do earn it**, even though both compiled paths read
  `IsAbilityUsedThisMove` and return early. Live: 11:16:14 x17->18 and 11:30:47
  x37->38 both land ~100ms after energy drops 7->0, with no move consumed, and
  three more do the same. The measurement is what the bot follows; the code
  reading is recorded here because the two disagree.
* **What a point is worth.** In full theory it multiplies everything still to
  be scored, and priced that way it took the match over: a 3-cell move with one
  point outscored a 16-cell move with a special and an extra move (Debug/runs
  13:53:25 and 13:53:29, bonus 90-108 against an instant score of 3). It is not
  worth that in practice -- the multiplier climbs **1.2-1.7 points a move on
  its own** (x1->x45 in 26 moves, x1->x42 in 35, both played before this weight
  existed), so aiming at the column mostly buys points the bot would have got
  anyway, for a worse board. A point is therefore priced as **one move's worth
  of base points divided by the multiplier already standing**: on par with an
  extra move at x1, a tiebreaker by x9, never enough on its own to give up a
  cascade, a booster charge or an extra move. See
  `_lights_up_multiplier_point_value` and `MODE_WEIGHTS[LIGHTS_UP_MODE]`.
* **Why the price stays low.** The bot's own predictions were checked against
  the engine over 13 logged moves on 2026-08-21: a move predicted at +1 gained
  nothing, and moves predicted at 0 gained +1 and +3. Whatever else feeds the
  multiplier (special blasts, refills, the parts of a cascade the simulator
  does not model as matches), the per-move predictor is wrong in both
  directions, so the term is deliberately small enough that being wrong costs a
  tiebreak rather than a move.
* **Still open.** The direct-only rule is not proven frame by frame:
  `memory_frames.jsonl` does not carry `score_multiplier`, so there is no
  record of *when* inside a cascade the multiplier moves. Adding that field
  would settle it. The GUI already logs every multiplier step with its column.

### Color Climb (`color-climb`, `RainbowMultiplierBoard` = 35)

Mapped 2026-09-13 from the compiled methods (`Debug/reverse/rainbow/*.asm`)
and the 420 frames recorded on 2026-08-25 (`Debug/unmapped_modes/color-climb`,
four matches, two of them versus).

* **The rule.** `onGameStart` (rva `0x57950d0`) sets every player's
  `ScoreMultiplier` to 1, fills the board's only field `availableColors`
  (offset 0x80) with the four non-charge colours in a fresh random order, and
  deals **player 0 the first two, player 1 the last two**
  (`SetBoardUniquePlayerColors(index, list.GetRange(...))`). The recording
  shows the list reorder exactly once, on the frame where the multipliers go
  0 → 1, and never again: the pair is fixed for the match.
  `get_MultiplierColors` is `GetBoardUniquePlayerColors(CurrentPlayer.Index)`.
* **What raises it.** `BeforeCombosDestroy` (rva `0x5795358`) walks every
  combo on every destroy pass -- cascades included, like Multiplier Madness --
  and for each ordinary combo (types 2..8, at least three cells) whose colour
  is in the current player's pair it raises `ScoreMultiplier` by one, capped at
  `MatchRulesModel.maxScoreMultiplier` (offset 0x2bc). With
  `linkedScoreMultiplier` (0x2c0) set, the opponent drops one if above 1.
  Measured: x1 → x10 in 20 moves (solo), x1 → x8 in 16.
* **The booster move.** The hook returns early when
  `PlayerControl.IsAbilityUsedThisMove` is set, so on the compiled reading the
  activation move itself earns nothing. Lights Up's identical check was
  measured *not* to hold in play (boosters did earn it), so the bot does not
  rely on it either way: repaints by Jelly, Mixy and Sweep are paid as *setup*
  (surviving tiles in a dealt colour, discounted like Madness) and a lotus
  triggered on a later ordinary move is paid in full.
* **How the bot plays it.** `GameMode.COLOR_CLIMB`, recognised by the id and
  by board model 35. Memory delivers the pair through
  `board_source.color_climb_state` → `MoveRequest.color_climb_state` →
  `move_strategy.multiplier_colors_active`; without it the mode scores like a
  plain board (nothing is guessed). Everything Multiplier Madness does for
  purple is done for the pair: `_multiplier_madness_points` per combo across
  cascades at `MODE_WEIGHTS[COLOR_CLIMB]["score_multiplier"]` (18, the same
  price as Madness), the Jelly/Mixy/Sweep setup bonus, Mixy's code-colour
  choice, and the lotus trigger colour. An extra move in a dealt colour wins
  over an extra in another colour by that combo point.
* **Mandatory, not merely preferred (user rule, 2026-09-13).** Two things in
  this mode are played over anything else that competes with them, through
  `color_climb_priority_colors`:
  * a **lotus collect in a dealt colour** -- `_best_lotus_trigger_for_zone`
    tiers the trigger colour (a three-tile yellow beats an eight-tile green),
    and `rank_froggy_lotus_moves` tiers whole moves the same way, so the
    lotus gate's first pick is a dealt-colour collect whenever one exists;
  * a **Mixy code match in a dealt colour** -- `rank_mixy_code_moves` offers
    only such moves when any exist (best score among them, so with both code
    colours dealt the better one wins), and the runtime plays it
    (`color_climb_mixy_code_gate`) right after the lotus gate, ahead of the
    booster whether ready or not and ahead of the ordinary extra hunt.
* **"Booster immediately" and an extra.** `select_booster_action_with_gate`
  gets the pair (`multiplier_extra_colors`): a move whose *own* matches make a
  four-plus or square in a dealt colour is played before an immediate
  activation (`multiplier_color_extra_before_booster_gate`), because it keeps
  the turn and raises the multiplier while the activation move would not.
  Extras in other colours keep the toggle's old behaviour.
* **Dealt colours before any booster (user rule, 2026-10-08).**
  `color_climb_dealt_combos` counts the dealt-colour combos a move is *sure*
  to make -- its own match plus every cascade before a random refill. Two
  uses:
  * `color_climb_extra_before_booster`: with a lotus on the board, a ready
    meter or a dealt-colour Mixy code, a sure extra with at least one such
    combo (in any colour of extra, e.g. a green four whose cascade drops a
    yellow three) is played first -- runtime
    `color_climb_extra_before_booster_gate`, ahead of the lotus and Mixy
    gates; the booster gate (`multiplier_color_extra_before_booster_gate`)
    uses the same test. With a lotus, an extra that leaves it standing wins.
  * `color_climb_dealt_first_order` (last step of `prioritize_ranked_moves`):
    among sure extras, and among swaps that fire a special (Billie Boom's
    bombs etc.), the ones with more dealt combos take the group's earliest
    slots. Permutation only -- a plain move never jumps a bomb or vice versa.
* **Still open.** Whether the activation move really earns nothing (the
  Lights Up precedent says the code and the game disagree), and the
  `linkedScoreMultiplier` value in the arenas that run this mode -- the
  recording's `engine_fields` sweep did not include it.

### Clear from the sources but deliberately left out

* **`anti-gravity`** (`gravity: 1` = `Gravity.Up`). The rule is unambiguous:
  pieces fall upward. Not implemented because gravity direction is baked into
  the drop routines *and* into every mode geometry that says "below"
  (Drillin' Down, chest drops, column sweeps). Doing it half-way would be worse
  than not doing it; it needs its own change.
* **`win-by-rounds` (`winByRounds`) and `best-turn-wins` (`winByBestRound`)**.
  Both are match objectives, not board rules: the score that counts is per round
  / the best single round, so booster charge does not carry the way it normally
  does. The rule is clear, the *strategy* consequence is a scoring-horizon
  change that deserves its own change and its own validation, next to the
  existing rounds handling.
* **`biggerBombArea`**, **`explosionOnMatch`**, **`everyMatchIsSpecial`**,
  **`matchCreatesSpecialChance`**. Named fields whose effect size is not in the
  sources: nothing says whether a bigger bomb is 5x5 or 4x4, or what
  `explosionOnMatch` explodes.

## Mutation Lab

Its whole catalogue — 108 mutations with their types, lifetimes and parameters —
is shipped inside the client and was extracted before the mode was ever played.
See `docs/mutation_lab.md`; the raw asset is `data/mutation_lab_catalogue.json`.

## Catching an unknown mode while it is being played

The evidence a new mode needs can only be collected while its match is open, so
the memory GUI does it by itself. On every snapshot it compares the ruleset id
against `RULES_ID_TO_MODE` and `RULES_ID_NO_STRATEGY_CHANGE`; if the id is in
neither, the match is being played without the rules that mode actually has, and
that is treated as a finding rather than silence:

* a non-modal warning box (auto-play keeps running behind it), naming the
  ruleset and what the engine reports about it — `board_model_name`, the rule
  flags that are on, moves per turn, colour count, board size;
* the same line in the log, plus the folder it is recording into;
* the raw snapshots written to `Debug/unmapped_modes/<rules-id>/`, one file per
  distinct board state, up to `UNMAPPED_MODE_MAX_SNAPSHOTS` (60) per session.

Warning and folder are per ruleset id, so one match produces one popup and a
sequence of board states, which is what reconstructing the mechanic needs. A
mode listed in `RULES_ID_NO_STRATEGY_CHANGE` never warns — playing it as
`GameMode.NONE` is correct, not a gap.

Hand the resulting folder over together with the mode's name; the id and
`boardModelName` in those files are what turns it into a `RULES_ID_TO_MODE`
entry.

## The Floor Is Lava (`the-floor-is-lava`, `FloorIsLavaBoard` = 36)

In-game description: *match twice on the same column to destroy it*. Captured
live on 2026-08-19 (19 moves, solo timed run, `Debug/memory_board`), which is
the source for everything below.

The board model carries the whole mode; the pieces carry nothing (every
`SlotModel` on it is an ordinary piece):

| Field | What it is |
| --- | --- |
| `ColumnsEruptionDictionary` | `Dictionary<int,int>`: engine column x -> how many matches that column has taken. This is the mark the description talks about. |
| `distinctXValues` | Scratch list: the distinct columns of the match being processed, i.e. how one match is turned into per-column marks. |
| `OnBreak` / `OnEruption` / `OnReset` | `Action<int>` per column — the ground breaking, the column going up, and the reset. |
| `resetGroundOnTurnEnd` = `true` | The marks do not survive the turn. |
| `combosToAddToDestroy` | Specials queued into the destruction the eruption performs. |

What the bot implements:

* Every column a **swipe's own** match occupies takes one mark — a horizontal
  match marks each column it spans (which is what `distinctXValues` computes),
  a vertical match marks only its own.
* A column that was already marked **erupts**: every piece standing in it is
  cleared, and the mark is spent. The cleared pieces score, charge the booster
  and cascade like any other clear (`_floor_lava_eruption_cells`), so the mode
  needs no artificial bonus for the eruption — only `lava_check`, the value of
  leaving a column one match from erupting.
* Cascade matches neither mark nor erupt.

Measured against the capture: the move whose four-in-a-row spanned four marked
columns scored 28 = 4 x 7 cells, and a later three-column eruption scored
21 = 3 x 7. Both are whole columns of a 7x7 board, refilled from the top over
the following frames.

Where the marks come from: the memory path reads
`ColumnsEruptionDictionary` itself (`board_source.floor_lava_column_counts`)
and hands it to the ranking, so the bot never has to infer the state. The
screen path has no such source and keeps its own move-by-move tally
(`runtime.floor_lava_state`).

Confirmed by the player who played the mode (2026-08-19):

* The counter is a plain toggle. It reads 1 after one match, and the second
  match erupts the column and resets it, so it never reaches 2. The reader
  still logs a count above one, as a canary for a model that has gone wrong.
* Every special standing in an erupting column goes off, which is what the
  ordinary clear path already does with it.

### Froggy Fu (the lotus) in this mode

Measured on three memory traces from the 2026-08-19 18:52-18:57 match
(`Debug/runs/2026-08-19_18-53-15_176`, `_18-53-40_205`, `_18-54-11_445`): a
fired lotus does **not** blow up the collected pieces where they stand. It
gathers them into the 3x3 block centred on itself -- in the frame before the
explosion all nine of those cells are the trigger colour -- and detonates them
there.

For lava that decides which columns the collect touches: the lotus's own three
columns, not the columns the pieces came from. Each of them takes a mark, and
one that was already marked erupts. The bot applies this in
`_froggy_lotus_lava_effect`, which also keeps the running mark tally correct
for every following move, and prices only the part of an erupted column
*outside* the blast (the pieces inside it are already in the lotus bonus).

Still unverified about the lotus itself: whether pieces beyond the nine that
fit in the blast die in place too. `collected` was 10 with a 3x3 of nine on two
of the three traces, so the bot's "every tile of that colour" count may be
slightly high; the boards refill too fast in those frames to tell.

Open on this mode:

* **The engine's own counter is not usable.** `ColumnsEruptionDictionary` read
  empty in all 188 polls of that 19-move match -- settled boards included --
  while the columns visibly kept their heat and the bot's toggle predicted the
  next board's heated columns move after move (five consecutive moves matched
  exactly). It is either a per-move scratch the engine clears or not the store
  at all. The reader still reports it, and a non-empty read would be news.
* **`removeLastRowEveryMove` = `true`** in this ruleset (and in no other
  captured one). The 19-move capture shows no per-move bottom-row removal, so
  the flag is either about the ground strip drawn under the 7x7 board or is
  conditional on something the capture did not hit. Not implemented; a mode
  played until the ground actually collapses would settle it.

## Open questions — need one live match each

For every item, the evidence needed is the same: open the mode, take a memory
snapshot, and save `ShowSettings.matchRules` (id, `boardModelName`,
`additionalData`, `extraData`) plus the board before and after one activation.

1. **The rules id for the modes the bot supports but cannot auto-detect**:
   Arcade Man, Color Crush, Vertical Rush, Multiplier Mushrooms,
   Energized, Red and Blue, Special O'Rama. One snapshot each fills in
   `RULES_ID_TO_MODE`; until then those modes must be selected by hand.
2. **Any mode that is not in the 2021 `Constants` snapshot at all.** That file
   ships with the client and predates several current modes, so a mode seen in
   the live game today (for example one shown in the client as "Color Climb")
   has no id or board model in it. Its `MatchRulesModel.id` and
   `boardModelName` have to be read out of memory while the match is open;
   guessing which of the unmapped board models it is would be exactly the kind
   of confident-but-wrong support this document exists to avoid.
3. **The two remaining unsupported league arenas** — frozen-feud, vegas-views.
   These rotate through Master League, so they are the highest-value gap. What
   is needed per arena is listed in the table above. Candy World and Dustville
   Duel are now mapped; Dustville's open item is only the size of the reward,
   not whether to chase it.
4. **`bothColorsChargeEnergy` cross-check.** The implementation assumes the
   second colour is red, which is what the game's own mode description says.
   Confirm on a live Shared Energy match that `PlayerControl.energyColors`
   contains red, and that no ruleset uses this field with a different colour.

#### Swap Freely (`anySwapValid` + `reduceMoveOnMatchOnly`, 2026-11-06)

Mod sa kartice "Square Match: Swap freely, no match required, each color has a
different score". Nema svoj board model: ceo mod su tri polja
`MatchRulesModel` koja agent vec cita u `engine_fields`:

| polje | znacenje |
| --- | --- |
| `anySwapValid` | zamena bez meca je prihvacena, plocice ostaju zamenjene |
| `reduceMoveOnMatchOnly` | potez se trosi samo kad zamena napravi mec |
| `isSquareMatch`, `_colorScoreOverride` | kvadrati i poeni po boji (vec podrzano) |

Kad su prva dva ukljucena, svaka zamena bez meca je besplatna. `free_swap.py`
pre placenog poteza trazi niz besplatnih zamena dve obicne plocice (specijal se
nikad ne pomera, jer ga prevlacenje aktivira) koji gradi sto vredniji potez
koji se racuna: poeni boja iz `SlotModel.score` (sve boje, ne samo legenda) plus
oblik (cetvorka, kvadrat, L/T, petica) i extra potez. Duga pretraga gradi
peticu `c c _ c c` + `c` pored rupe (petica ne moze da se slaze plocicu po
plocicu, treca u nizu je vec mec) i ide kroz table koje same nista ne vrede;
kratka pretraga hvata bilo koji oblik na par zamena.

Plan se pamti (`FreeSwapGuard`) i igra zamenu po zamenu dok tabla odgovara
planu; na kraju se planirani placeni potez gura na prvo mesto
(`engine_plan_move`). Zastite: najvise 40 besplatnih zamena po potezu, broj
zamena ogranicen satom poteza (1.3 s po zameni), a ako igra odbije zamenu ili
zamena potrosi potez, besplatne zamene se gase do kraja partije.
`_unlimited_moves` vise ne proglasava ovaj mod za Infinite Moves ako je
`reduceMoveOnValidSwap` false. Monitor dopune prepoznaje besplatnu zamenu
(dve susedne plocice zamenjene, isti RNG) i ne prijavljuje je kao promasaj.

Jos nije igrano uzivo: nijedan snimak nema `anySwapValid=true`. Prva partija
treba da potvrdi da RNG ostaje isti posle zamene bez meca i da igra prihvata
prevlacenje bez meca odmah (bez animacije vracanja).
