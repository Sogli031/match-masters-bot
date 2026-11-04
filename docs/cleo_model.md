# Cleo Cadabra — kako radi i kako da se mapira

Cleo je buster koji bot igra najgore. Ovaj dokument je popis onoga sto je
procitano iz igre (kod + konfiguracija), sta bot trenutno pretpostavlja, i gde
se to dvoje ne poklapa.

Izvori: `data/ability_config.json` (buster), `data/piece_logic_config.json`
(figura na tabli), disasembler nad `libil2cpp.so`. Postupak:
`docs/il2cpp_reverse.md`.

## Dva odvojena sloja

Cleo ima **dve** klase, i to je prvo sto treba razdvojiti:

| | klasa | kad radi | parametri |
| --- | --- | --- | --- |
| aktivacija | `Match3Engine.CleoCadabra` | kad se buster potrosi (7 energije) | `SpecialAbilityModel.additionalParams` |
| figura | `Match3Engine.CleoCadabraPieceLogic` | kad igrac zameni Cleo figuru na tabli | `SpecialPieceModel.pieceParams` (slotType 32) |

Bot ima model samo za drugi sloj (`_simulate_post_cleo_board`), sto je i
ispravno — prvi sloj se vidi na tabli posle aktivacije.

## Aktivacija (`CleoCadabra`)

```
explodeOnActivate = 16          # PvP; Rumble 18
piecesPerActivation = 2,1       # PvP i Solo; Rumble 2,2,1
activationsWithArrows = 2
hideTargetColor = true
cloneToRandomPieces = true
```

Dakle: aktivacija dize 16 plocica sa table i ostavi **2 Cleo figure** prvi put,
1 svaki sledeci (u Rumble/Party 2, 2, pa 1).

Koliko se klonira po aktivaciji:

```
clonedNormalPiecesAmountByActivation  = 8,7      # Solo 9,8,7 ; Rumble 9,8,7
clonedBluePiecesAmountByActivation    = 8,7,6,5  # Solo 8,7 ; Rumble 8,7,6
clonedSpecialPiecesAmountByActivation = 8,7,6,5
   ...-BroccoBoogiePiece / SweepItSEPiece / ColorCrystalPiece
   ...-MonkeyJoojooPiece / ZanyZapperPiece / CupidHeart = 3,2
clonedBoardSpecialPiecesAmountByActivation = 7,6,5
```

Za sta engine cilja pri kloniranju:

```
attemptsToReachTargetPiecesMatchedOnClone = 100
targetBluePiecesMatchedOnCloneByActivation = 3,99 | 0,99 | 0,99
chanceToCreateExtraMoveOnCloneByActivation = 80,50,10   # Solo 80,50,30
chanceToNeighborBluesByActivation          = 70,30,20   # Solo 70,50,35 ; Rumble 70,30
```

Cita se ovako: pri **prvoj** aktivaciji engine do 100 puta pokusava da nadje
raspored klonova koji spaja **bar 3 plave** (`3,99` = min 3, max 99), i sa
80% sanse takav koji pravi extra potez. Kasnije aktivacije spustaju oba cilja.

## Figura na tabli (`CleoCadabraPieceLogic`, slotType 32)

```
cloneToWholeColor = true
cloneToWholeColorMinimumTargetPieces = 4
chanceToCloneRandomly = 0
chanceToPickColorOnlyByPieceCount = 0
allowRed = true, allowBlue = true
mergeSwapBlockTypes = CleoCadabraPiece, BillieBoomPiece, PirateChestPiece
clonedNormalPiecesAmountByPieceUse  = 8,7,6
clonedBluePiecesAmountByPieceUse    = 7,6,5
clonedSpecialPiecesAmountByPieceUse = 8,7,6,5
   ...-FoxyRoxySEPiece / BroccoBoogiePiece / SweepItSEPiece / MonkeyJoojooPiece = 3
chanceToPreventExtraMoveOnColorBasedClone = 15,40,60   # Solo 10,20,35,50 ; Rumble 10
```

Tri stvari odavde su vaznije od ostalih:

* **`chanceToCloneRandomly = 0`.** Cleo **nikad** ne bira nasumicno.
* **`cloneToWholeColor = true`** uz minimum 4 ciljne plocice — klon ide po
  celoj boji, ne po nasumicnom skupu.
* **`chanceToPreventExtraMoveOnColorBasedClone`** je sansa da se extra potez
  **sprijeci**. U PvP-u je 15 na prvoj upotrebi figure u potezu, dakle **85%
  da NIJE sprecen**.

### Kako se ta sansa racuna — procitano iz koda

`CleoCadabraPieceLogic::SwapPerformed` (rva 0x58cb9c0):

```
index = Min(PieceUsesThisTurn - 1, chanceToPreventExtraMoveOnColorBasedClone.Count - 1)
preventExtraMove = RandomWrapper.Chance(chanceToPreventExtraMoveOnColorBasedClone[index])
```

Provereno na instrukcijama: `get_PieceUsesThisTurn` → `Math.Min` → `List.get_Item`
nad poljem na ofsetu **0x78**, a 0x78 je bas
`chanceToPreventExtraMoveOnColorBasedClone` u dumpu simbola. Indeksira se
**brojem upotreba figure u tom potezu**, ne brojem aktivacija bustera.

### Sta jos radi `SwapPerformed`

Poziva redom: `GameLogic::Clone`, `ConvertSlots`, `BoardAnalyzer::GetAllCombos`,
`DestroyMatches`, `BoardAnalyzer::GetPossibleSpecialMoves`.

Engine dakle **klonira celu partiju i simulira** kandidat-rasporede klonova, pa
bira. To nije lutrija — to je pretraga sa ciljem, isto ono sto bot radi za svoj
potez.

## Gde se bot razilazi

> **2026-08-28:** tri stavke iz ove tabele su mapirane u `move_strategy.py`.
> Scenariji vise nisu uniformna lutrija: posle bodovanja svake boje tezine se
> preusmere softmax-om ka najboljim ishodima (`CLEO_GOAL_SHARPNESS`, najbolja
> boja ~20x verovatnija od najgore) — aproksimacija engine-ove pretrage bez
> pretpostavke da mu znamo tacan cilj. Boje sa manje od
> `cloneToWholeColorMinimumTargetPieces = 4` plocica ispadaju iz scenarija
> (`CLEO_MIN_TARGET_PIECES`), a kredit konverzija je ogranicen na first-use
> brojke klonova (`CLEO_CLONED_NORMAL_CAP = 8`, `CLEO_CLONED_BLUE_CAP = 7`).
> Deep lookahead za Cleo potez vise nije blokiran: racuna se ponderisano preko
> top-`CLEO_LOOKAHEAD_SCENARIOS` scenario tabli (`_cleo_expected_future_score`)
> — ocekivana buduca vrednost umesto fantomskog uzorka ili nule.
> `CLEO_EXTRA_MOVE_CHANCE` ostaje 0.0: `tools/measure_cleo_swaps.py` na 16
> zivih swap-ova (5 sa pouzdanim brojacem van lag prozora) daje 0/5 za citanje
> "swap odmah vraca potez", dok citanje "ostavi match-4 priliku" (6/16) vec
> ulazi kroz scenario skorove i goal tezine.

| | engine | bot |
| --- | --- | --- |
| izbor klonova | pretraga do 100 pokusaja ka cilju | goal-softmax preko scenario skorova (`CLEO_GOAL_SHARPNESS`) |
| nasumicnost | `chanceToCloneRandomly = 0` | tezine skewovane ka najboljim ishodima, ne uniformni RNG |
| extra potez | 85% da nije sprecen (PvP, prva upotreba) | `CLEO_EXTRA_MOVE_CHANCE = 0.0` (izmereno 0/5, vidi iznad) |
| plave | cilja min 3 plave na prvoj aktivaciji | `CLEO_BLUE_POTENTIAL_WEIGHT = 0.25` (diskont) + goal tezine indirektno |
| broj klonova | 8,7,6 normalnih po upotrebi | kredit ogranicen na first-use kap (8/7); transformacija table ostaje cela boja |

Bitna ograda oko extra poteza: bot je **izmerio** dva ziva Cleo swap-a koja su
oba isla `remaining_moves 2 -> 1`, dakle sam swap ne vraca potez. To se ne kosi
sa 85% ako „create extra move" znaci da klon **ostavi match-4 priliku na tabli
za sledeci potez**, a ne da odmah vrati potez. Ta dva citanja se razlikuju u
tome gde bot treba da knjizi vrednost, i **nisu razdvojena merenjem**.

## Predlog kako da se mapira

Redom, od najjeftinijeg ka najskupljem:

1. **Razdvojiti dva pitanja merenjem.** Alat je napravljen:
   `tools/measure_cleo_swaps.py`. Vidi „Kako se meri" nize. Bez tog merenja se
   `CLEO_EXTRA_MOVE_CHANCE` ne sme dirati — bas zato sto je 0.0 postavljena na
   osnovu merenja, a ne osecaja.

2. **Zameniti lutriju ciljem.** Ako se potvrdi da je klon strukturiran
   (`chanceToCloneRandomly = 0`, `cloneToWholeColor`), onda ceo `CLEO_RISK_*`
   aparat modeluje pogresnu stvar. Umesto uzorkovanja scenarija, bot bi trebalo
   da uradi istu pretragu kao engine: za svaku kandidat-boju izracunati klon po
   celoj boji sa `clonedNormalPiecesAmountByPieceUse[uses]` plocica i oceniti
   rezultat. To je deterministicno i mnogo blize onome sto igra stvarno radi.

3. **Uvesti broj klonova kao ulaz.** `8,7,6` po upotrebi figure i `8,7` po
   aktivaciji su tacne brojke; sada se nigde ne koriste. Indeks je
   `PieceUsesThisTurn` odnosno broj aktivacije, oba se citaju iz memorije.

4. **Plavi cilj.** `targetBluePiecesMatchedOnCloneByActivation = 3,99` znaci da
   prva aktivacija gotovo sigurno spaja bar 3 plave. To je jaci signal od
   trenutnog diskonta 0.25 na `blue_potential`.

## Sto se ne moze procitati iz konfiguracije

Koja se boja bira (`hideTargetColor = true` znaci da je igracu sakrivena) i
kako se rangiraju kandidat-rasporedi. Za to treba disasemblovati
`CleoCadabra::CreatingPieces` (0x58084e0) i `ChooseNeighbor` (0x580a44c), ili
meriti na snimcima.


## Kako se meri

```bash
python .\tools\measure_cleo_swaps.py
```

Pokrene se pre partije, igra se normalno, prekida se sa Ctrl-C. Alat samo cita —
ne salje nijedan potez i ne igra umesto tebe.

Za svaki Cleo swap ispise jedan red i zapise ga u
`Debug\cleo_swaps\measurements.jsonl`:

```
#1   boja=narandzasta prebojano= 8 potezi 3->2 potez_vracen=ne  match4_posle=DA  (2 takvih poteza)
```

Dve kolone su ceo smisao merenja:

* `potez_vracen` — da li je brojac poteza ostao isti, tj. da li se potez vratio
  odmah. Za ovo vec postoji odgovor iz dva ranija swap-a (ne), pa je ovde samo
  provera na vecem uzorku.
* `match4_posle` — da li na smirenoj tabli posle klona postoji potez koji daje
  extra. **To niko nikad nije izmerio**, a od toga zavisi da li se 85% iz
  konfiguracije uopste odnosi na ono sto bot racuna.

Sirovi tok snapshot-a ide u `Debug\cleo_swaps\snapshots.jsonl`, pa se ista
partija moze ponovo analizirati bez igre:

```bash
python .\tools\measure_cleo_swaps.py --from-log Debug\cleo_swaps\snapshots.jsonl
```

Detekcija swap-a: izmedju dva **settled** kadra broj Cleo figura na tabli je
opao i najmanje 3 polja su promenila boju. Nestabilni kadrovi usred kaskade se
preskacu jer u njima pola table menja boju iz drugog razloga.

Svaki zapis nosi i `moves_delta`. Ako je manji od -1, izmedju dva settled kadra
je odigran jos jedan potez i taj red nije cisto merenje — sazetak to izdvojeno
prijavljuje umesto da ga tiho ubroji.

Koliko swap-ova treba: pri 15% sanse da je extra sprecen, deset swap-ova
razlikuje „85%" od „0%" bez ikakve statistike — ako je nula od deset ostavilo
match-4, model iz konfiguracije ne vazi za ono sto bot meri.
