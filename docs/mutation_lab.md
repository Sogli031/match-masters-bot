# Mutation Lab — what is known before the first match

Everything here is read out of the shipped client, not inferred from play:

* `base.apk` → `assets/bin/Data/441a450b6fbce4bf3946b442b35eaacb`, the
  `MutationLabDemoData` asset. It holds the whole catalogue as JSON: three pools
  (`soloMutations` 59, `pvpMutations` 49, `rumbleMutations` 44 entries; **108
  unique mutations**), each with its `type`, `durationType`, `triggerType` and
  `mutationParams`. Extracted verbatim to `data/mutation_lab_catalogue.json`.
* `base.apk` → `assets/bin/Data/012fc2e90b7cc49b6a54a2146c704a45`, the
  localisation table, which carries a `mutation_title_*` / `mutation_desc_*`
  key per mutation id.
* `global-metadata.dat` → the field names on `MatchRulesModel` and the engine's
  own class list (`MutationLabMutation`, `MutationLabMutationType`,
  `MutationLabEffectTrigger`, `MutationLabPieceEffects`).

**The per-match knobs are not shipped.** `isMutationLab`,
`mutationLabAmountToPick`, `mutationLabOptionsPerPick`, `mutationLabMovesRefill`,
`mutationLabPicksPerSoloTarget`, `mutationLabTargetsPerSoloTarget` and
`mutationPvpActivateDelay` exist as fields but their values come from the server,
so they can only be read live. The generic ruleset sweep already dumps them into
`rules.engine_fields` — no agent change was needed for that part.

## The structure

A mutation is `type` + `mutationParams` + a lifetime:

| `durationType` | count | meaning |
| --- | --- | --- |
| `Permanent` | 45 | until the match ends |
| `ThisRound` | 25 | until the round ends |
| `XMoves` | 19 | `durationAmount` moves (mostly 5) |
| `Instant` | 19 | fires once, changes the board, then it is gone |

37 of them carry `triggerType: OnTurnStart` — those top the board up every turn
rather than once. Entries also carry `dontShowAsOptionWith` /
`blockTheseIfActive` (mutually exclusive picks, e.g. the four
`*-charges-energy`), `isStackable`, `isRepeatable` and `baseWeight`.

## What the bot already models

The important structural finding: **most mutation types are the
`MatchRulesModel` flags the bot already implements, only switched on mid-match**,
and most of the rest change the board, which the bot re-reads anyway.

| `MutationLabMutationType` | ids | bot support |
| --- | --- | --- |
| `AddSpecials` | 42 | not needed — the specials are read off the board |
| `ConvertToSpecial` | 4 | not needed — read off the board |
| `Painter` | 1 | not needed — read off the board |
| `RemoveColors` / `DestroyColors` | 2 | not needed — read off the board |
| `ColorsAmount` | 1 | not needed — colours are read off the board |
| `ColorSpawnIncrease` / `BombsSpawnIncrease` | 2 | not needed — refill is unmodelled anyway |
| `BoosterEnergyFill` / `BoosterCostAddition` | 5 | not needed — `energy` / `energy_to_ability` come from memory |
| `GiveMoves` / `PerksRefill` | 2 | not needed — moves and perks come from memory |
| `ColorChargesEnergy` | 4 | **yes** — `energized_colors` (Energized / Shared Energy) |
| `ColorPointsIncrease` | 12 | **yes** — per-colour `score_rally_values` |
| `SpecialsAutoExplode` | 2 | **yes** — `specials_explode_immediately` (Blow Em Up) |
| `DestroyRowOnHorizontalMatch` | 1 | **yes** — `line_destruction(rows=True)` |
| `DestroyColumnOnVerticalMatch` | 1 | **yes** — `line_destruction(columns=True)` |
| `VerticalMatchDestroyColor` | 1 | **yes** — `vertical_matches_destroy_color` |
| `VerticalMatchTempIncreaseMultiplier` | 2 | **yes** — Vertical Rush |
| `MatchesCreateSpecials` | 1 | partly — `every_match_is_special`, but the `odds` string is ignored |
| `ColorMatchCreatesSpecial` | 4 | partly — the same, restricted to one colour |
| `ColorMatchExplodeColor` | 2 | partly — Color Crush is the same shape |
| `ColorMatchExplodeLine` | 4 | partly — Arcade Man is the same shape, but for every colour |
| `CreateExtraMoveTiles` | 3 | partly — Xtra Moves tiles, which the bot already reads |
| `BiggerBombs` | 1 | **no** — `biggerBombArea`, and nothing says how big |
| `MultiplierIncrease`, `SetScoreMultiplyNextMove`, `ColorMatchTempIncreaseMultiplier`, `EveryMatchTempIncreaseMultiplier` | 11 | **no** — score multipliers |

So the work Mutation Lab needs is not 108 new mechanics. It is:

1. **Read which mutations are active.** They live on `PlayerModel`; the agent now
   sweeps that object down to its mutation-named fields only (`mutation_fields`
   on each player). PlayerModel is also where the account identifiers live, which
   is why the filter is applied inside the process rather than in the host.
2. **Route the ~10 supported types into the flags that already exist**, the same
   way `memory_gui` already routes the ruleset flags.
3. **Decide the picks.** `mutationLabOptionsPerPick` options are offered and
   `mutationLabAmountToPick` are taken; picking well is a separate problem from
   playing well, and needs the live offer list (`AllMutationOptions`).

## Concrete numbers worth having on hand

* `booster-fill-instantly` = `amount 999`; `booster-fill-2` = 2.
* `booster-cost-1-less` = permanent −1 to the booster denominator;
  `booster-cost-4-less-for-x-moves` = −4 for 4 moves.
* `*-points-increase` = +2 permanent, `*-points-increase-moves-limited` = +10 for
  5 moves, `*-points-increase-this-round` = +10 for the round.
* `painter-blue` = paints 8 pieces blue, once.
* `blue-spawn-increase` = `amount 200` (a spawn weight, not a count), permanent.
* `next-move-multiplier-10` = `amount 5`, one move — the title says 10, the
  parameter says 5. **Trust the parameter over the title.**
* `matches-creates-specials` = 100 % chance for 10 moves, odds
  `Bomb,2|Row,3|Column,3|Fireworks,1|Crosshair,1`.
* `give-moves-3` = +3 moves, instant.
* `add-*-once` entries are `ThisRound` + `OnTurnStart`, i.e. not literally once.

## Where the live state is (2026-08-19)

* **`GameLogic.mutationsActivatedList`** — the picked mutations, one
  `MutationLabMutation` each. `PlayerModel` carries only `mutationLabTargetInd`;
  the mutation itself is not there. The agent reads the list through `_items` /
  `_size` rather than `get_Count` / `get_Item`, because calling a game method
  from a sweep crashed Match Masters on attach once already.
* Each entry carries `type` (the enum below), `addedScore` / `addedMoves` /
  `addedMultiplyer` running totals, and a `config` model with `color`,
  `durationType`, `durationAmount`, `durationAmountLeft` and **`isActivated`**.
  The instant picks stay in the list once spent, with `isActivated` false — so
  that flag, not membership, is what says a mutation is still in force.
* `config.id` and `config.title` read as null in the live capture, which is why
  the routing goes through the numeric type.
* `MutationLabMutationDuration`: `Instant` 0, `Permanent` 1, `XMoves` 2,
  `ThisRound` 3.

### `MutationLabMutationType`

Recovered from the shipped `global-metadata.dat`, whose enum member names are
stored in declaration order, and pinned by three values observed live:

| # | name | | # | name |
| --- | --- | --- | --- | --- |
| 1 | ColorChargesEnergy | | 17 | RemoveColors **(anchor)** |
| 2 | ColorComboChargesEnergy | | 18 | MultiplierIncrease |
| 3 | ColorMatchCreatesSpecial | | 19 | ConvertToSpecial |
| 4 | ColorMatchExplodeLine | | 20 | GiveMoves |
| 5 | ColorPointsIncrease **(anchor)** | | 21 | DestroyRowOnHorizontalMatch |
| 6 | SpecialsAutoExplode | | 22 | DestroyColumnOnVerticalMatch |
| 7 | MatchesCreateSpecials | | 23 | SetScoreMultiplyNextMove |
| 8 | BiggerBombs | | 24 | ColorMatchExplodeColor |
| 9 | PerksRefill | | 25 | ColorMatchTempIncreaseMultiplier |
| 10 | AddSpecials | | 26 | BoosterEnergyFill |
| 11 | GiveScore | | 27 | VerticalMatchTempIncreaseMultiplier |
| 12 | BombsSpawnIncrease | | 28 | DestroyColors |
| 13 | ColorSpawnIncrease | | 29 | *(unnamed — probably `Painter`)* |
| 14 | CreateExtraMoveTiles | | 30 | VerticalMatchDestroyColor **(anchor)** |
| 15 | ColorsAmount | | 31 | EveryMatchTempIncreaseMultiplier |
| 16 | BoosterCostAddition | | | |

The anchors: type 5 was live while the boosted colour was purple and the score
legend read purple 3; type 17 was the pick described in play as "destroy two
colours this move"; type 30 was Vertical Matches Destroy Color. Slot 29 has no
name in that run of the string table — the table de-duplicates, and `Painter` is
the one catalogue type missing from the run — which is why the numbers above 28
rest on the type-30 anchor rather than on counting through it.

### Correction, 2026-08-20: the table above is one too low near the top end

A live match showed four permanent picks — "3 specials every turn", "Yellow
matches charge booster", "Horizontal match explodes row", "2 Multiplier
Mushrooms every turn" — reported as types `[10, 1, 22, 10]`. Both mushroom and
special picks are `AddSpecials` (a mushroom is a board special, SlotValue 19,
so it needs no type of its own) and 1 is the yellow charge, which leaves **22
for the horizontal pick** while no vertical mutation appeared in the match at
all. So `DestroyRowOnHorizontalMatch` is 22, not 21, and the declaration order
gains a member somewhere between 15 and 21 — most likely one shipped after the
`MutationLabDemoData` dump, since the catalogue has no mushroom entry either.

Consequences, applied in `memory_gui`:

* `MUTATION_DESTROY_ROW_ON_HORIZONTAL_MATCH = 22`. Before this it was 21, so 22
  was routed onto the *vertical* half of `line_destruction` and the whole match
  was simulated destroying columns while the game destroyed rows.
* `MUTATION_DESTROY_COLUMN_ON_VERTICAL_MATCH = None`. Its number is now unknown
  and a wrong axis is worse than none, so a vertical pick goes unrouted until
  one is seen live.
* Everything in 17..21 and 23..29 is suspect by the same argument. The
  "Mutacije" line in the memory GUI prints those as `tip N (?)`, so an
  unrecognised pick is visible on screen instead of silently ignored.

A second live match (2026-08-19 23:02-23:07, `mutation-lab-pvp-mode`) narrows
this down and settles the routing question:

* Type 22 was picked at 23:02:52 and the engine's own
  `MatchRulesModel.destroyRowOnHorizontalMatch` flipped to true in the same
  frame, with the column flag staying false. That is the engine confirming 22 is
  the *row* member, independently of the on-screen wording. It also means these
  mutations are picked up through the plain rule fields anyway, so the type pin
  is a second path rather than the only one.
* Type 16 dropped `energyToAbility` from 7 to 3 for both players and restored it
  when the round ended: `BoosterCostAddition`, exactly as the string table says.
  So 16 is *not* shifted, and the insertion sits between 16 and 22.
* Type 15 arrived with `config.color` 6 (orange) and `rules.colorsCount` went
  6 -> 5, with orange vanishing from the board two frames later: `ColorsAmount`,
  with the colour field naming the colour that leaves. Nothing to route -- the
  board is read from memory and refilled tiles are simulated as unknown.

* Type 23 was picked at 23:10:01 and `destroyColumnOnVerticalMatch` flipped true
  in the same frame: the pair is **22/23**, both engine-confirmed. Routing is
  restored for both axes.
* Type 31 is `EveryMatchTempIncreaseMultiplier` -- its ThisRound duration,
  baseWeight 8 and 3800-trophy floor match exactly one pvp catalogue entry, the
  player read "all matches increase multiplier" off the screen, and
  `scoreMultiplier` climbed one per match while it was live and reset to 0 when
  the round ended. Unrouted: the simulator has no multiplier term. It nudges
  toward multi-match moves, which cascade scoring already prefers.

* Type 26 arrived with `config.color` 7 (purple) and read "purple matches
  increase multiplier" on screen: `ColorMatchTempIncreaseMultiplier`, whose
  permanent pvp entries all carry baseWeight 8 and a 3800-trophy floor. The
  table puts that member at 25.

### The reconciled numbering

Five live pins -- 16 and 31 on their table slots, 22, 23 and 26 one above theirs
-- admit exactly one model: **one real member was added somewhere in 17..21, and
the "unnamed slot 29" is not a member at all**. The +1 therefore runs over
21..28 and cancels before 30, where `VerticalMatchDestroyColor` keeps its own
live anchor. Reading the corrected table off that: 24 SetScoreMultiplyNextMove,
25 ColorMatchExplodeColor, 26 ColorMatchTempIncreaseMultiplier, 27
BoosterEnergyFill, 28 VerticalMatchTempIncreaseMultiplier, 29 DestroyColors.
None of those is routed, so they appear in the readout as derived names and
nothing more; 17..21 stay unknown, since the added member is in there somewhere.

The 2026-08-19 anchor at 17 (`RemoveColors`) is an instant board edit that needs
no routing, so it was never load-bearing; 5 and 30 sit below/at their own live
observations and stand.

### The "Mutacije" readout

`Stanje iz memorije` carries a `Mutacije:` line listing every mutation with
`config.isActivated` true, as `type name [colour] (duration)`. It exists to be
compared against the game's own mutation list: a name that contradicts the
screen means the number is pinned wrong, and `tip N (?)` means the member is
unknown here.

Two members are in the enum but in no catalogue entry:
`ColorComboChargesEnergy` and `GiveScore`.

## Routed into the simulator

`memory_gui` ORs these onto the rule flags of the same name, so a mutation and a
ruleset that say the same thing are handled by one code path:

| type | flag |
| --- | --- |
| 1 `ColorChargesEnergy` | `energized_colors` (its `config.color`) |
| 6 `SpecialsAutoExplode` | `specials_explode_immediately` |
| 7 `MatchesCreateSpecials` | `every_match_is_special` |
| 22 / 23 `DestroyRow/ColumnOn*Match` | `line_destruction` (renumbered; see correction) |
| 30 `VerticalMatchDestroyColor` | `vertical_matches_destroy_color` |

`ColorPointsIncrease` (5) needs no routing: the engine writes the boosted value
into `SlotModel.score`, and the score legend already reads it — a live purple
pick showed up as `{purple: 3.0}` with no code change at all.

## Open

* The mutation the client picks is applied by `MutationLabMutation.ApplyEffect`,
  whose body is not in any shipped text — the parameters above are what it is
  given, not what it does with them.
* `BiggerBombs` has no parameters at all, so the blast size has to be measured.
* Whether `soloMutations` / `pvpMutations` / `rumbleMutations` are the live pools
  or only demo data: the asset is named `MutationLabDemoData`, and the real pool
  may be server-side. The ids and types are engine-side either way.

## Coverage, checked 2026-08-20

Of the 152 catalogue entries **17 carry `isDisabled: true`** and never reach a
pick screen -- among them all four `ColorMatchExplodeLine` ("Yellow matches
explode line"), which the player confirms never having been offered. That is not
a gap; it is a member that does not ship. 135 entries are live.

Two entries had their meaning read wrong from the id alone, corrected by the
player and by `mutationParams`:

* `ColorMatchExplodeColor` is **not** per-colour. `color` is `None` and the
  description is "Every match you make explodes all pieces of the same color" --
  it is `VerticalMatchDestroyColor` without the vertical restriction, which is
  why the catalogue lists them as mutually blocking (`blockTheseIfActive`).
* `ColorMatchExplodeLine` would have been the per-colour line-destroyer, but see
  above: it is disabled. Line destruction that does ship is the horizontal/
  vertical pair, types 22 and 23.

Type 25 was then seen live (2026-08-19 23:23:05, permanent, `config.color`
None, matching `color-match-explode-color-permanent` exactly), with whole
colours vanishing from the board on later moves and no rules field mirroring it.
The derived number is now a live pin.

`ColorMatchExplodeColor` (25) is now routed: `matches_destroy_color` runs the
same whole-colour wipe as the vertical rule with the vertical run condition
dropped (`_destroy_color_cells(..., vertical_only=False)`). The two stay separate
switches, matching the two separate mutations the game offers -- "vertical match
explodes color" and "matches explode color" -- and separate again from the
line destroyers at 22/23, which only sweep the row or column.

Scope, confirmed in play: the wipe follows the **direct** match only, never the
cascades after it -- so the `cascade_number == 1` guard the vertical rule
already used is right here too. A swap whose two ends each complete a match of
their own wipes *both* of those colours, which falls out of collecting the
colours of every match in that first cascade.

Remaining live gaps, in impact order:

| what | entries | why it matters |
| --- | --- | --- |
| `ColorMatchCreatesSpecial` (3) | 4 | every match in one colour creates a *random* special (equal odds over Bomb/Row/Column/Fireworks/Crosshair) -- random, so it also affects extra-move gating |
| multipliers (26, 28, 31, 18, 24) | 19 | no multiplier term in the simulator; the global ones scale all moves equally and cannot reorder them, but the per-colour and per-vertical ones can |
| `BiggerBombs` | 1 | 5x5 instead of 3x3 blast |
