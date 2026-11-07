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

## Tacan izbor boje (figura, igra 5.817) — 2026-11-04

Ovo vazi umesto „Gde se bot razilazi" i „Predlog" nize, koji opisuju stariji
model. Kod: `engine_cleo_odds.py`, `move_strategy._cleo_color_weights`.

### Procitano iz koda (ARM64, `Debug/reverse/simulator_all`)

| tvrdnja | RVA |
| --- | --- |
| `Chance(p)` je `Next() % 100 <= p`: uspeva (p+1)/100, pa je 15 → **16%**, 40 → 41%, 60 → 61%, a `Chance(0)` → 1% | 0x5af5c4c, poredjenje 0x5af5c78 |
| redosled izvlacenja: pickByCount, pa prevent; oba se uvek izvlace | 0x5ae3464, 0x5ae34f4 |
| kandidat boje: 3,5,6,7,8 i protivnikova; bez boje partnera; **sopstvena boja samo ako nijedna druga nema polje** | 0x5ae2fa8..0x5ae31a0, 0x5ae335c, b__2 0x5ae4b64 |
| obican partner uzima samo obicne plocice; specijal partner uzima i figure sa specijalom, ali nikad board specijale | b__2 0x5ae4d04..0x5ae4d34 |
| `matchesExtraMove`: `isHighRank` (rang 4..8) kombinacija kroz obojeno polje, **pre unistavanja**. Kaskada se ne racuna | 0x5ae3848, b__26_13 0x5ae4754, 0x59cbad8 |
| `leavesExtraMoveOnBoard`: `GetPossibleSpecialMoves` na smirenoj tabli klona | 0x5ae3a34 |
| `deltaToTarget = |polja − kolicina|` | 0x5ae3a8c |
| izbacuju se boje sa manje od 4 polja | b__5 0x5ae4804 |
| prioritet: `!prevent && matches && leaves && d<3`, pa `!prevent && matches && d<3`, pa `leaves && d<2` | b__6 0x5ae5084, b__7 0x5ae50d8, b__8 0x5ae4868 |
| nista od toga, ili pickByCount: najmanji d, sa `prevent` prvo bez boja koje spajaju | b__9 0x5ae5124, b__26_10/11 |
| granica d je 3 (podrazumevana vrednost konstruktora; nema je u konfiguraciji) | 0x5ae0c58 |
| brojac upotreba raste pre `SwapPerformed`, a nula se na pocetku poteza igraca | 0x5951120, 0x5959600 |

Posledica: boje **nisu jednako verovatne**. Kad postoji boja sa direktnim
match-4 blizu kolicine, extra je 84% na prvoj figuri poteza, 59% na drugoj, 39%
od trece; inace je blizu 0% (osim preko kaskade). Stari model je delio 1/N.

### Ispravka posle prve snimljene partije (`20261104_041047_moves-multiplier`)

Tabela 84/59/39 vazi **samo za PvP listu** `15,40,60`. Igra ucitava listu po vrsti
partije, a bot je sada cita iz memorije:

| partija | `chanceToPrevent...` | extra uz direktan match, po figuri |
| --- | --- | --- |
| PvP | 15,40,60 | 84%, 59%, 39% |
| Solo | 10,20,35,50 | 89%, 79%, 64%, 49% |
| Rumble | 10 | 89% stalno |

Procitano iz memorije u toj partiji (`pvpMode` 2): prevent `[10]`, granica 3,
minimum 4, `maxAllowedClonedPieces` 99. Lista `[10]` i `piecesPerActivation`
`[2,2,1]` odgovaraju Rumble konfiguraciji; to da je `pvpMode` 2 bas Rumble je
zakljucak, nije procitano.

Procitano iz koda:

* Figura iz boostera ima logiku pod boosterom (`BoosterPiecesLogic`), a ne u
  `specialPiecesLogics`. Zato je `cleo_piece_logic` bio prazan.
* Omotac `CleoCadabra.BoosterPieceSwapPerformed` 0x5a20f54 za booster figuru
  menja kolicinu listama `...ByActivation` (`Min(ActivatesThisTurn-1, ...)`,
  upis 0x5a21350). U toj partiji je to 9,8,7 umesto 8,7,6.
* `overrideChanceToCreateExtraMove` (0xbc) se samo upisuje; `CleoCadabraPieceLogic`
  ga nigde ne cita.

Izmereno:

* Brojac upotreba u memoriji raste 1..5 i nije se ponistio u tom nizu.
* U toj partiji je 5 od 5 odigranih Cleo poteza zadrzalo potez (model 89-100%).
  Uzorak je mali i ne razlikuje modele.
* Stari snimci su skoro svi `solo_6`: uz direktan match i obicnog partnera
  zadrzano je 32/41, 13/14 i 15/16 po figuri, ukupno 60/71 = 85%. To ne prati
  PvP rast (nesklad opisan nize), a slaze se sa ravnih 89%. Vrsta partije nije u
  starim snimcima, pa je ovo slaganje, a ne dokaz.

### Izmereno na snimcima (`python tools/cleo_odds_audit.py`)

158 odigranih Cleo poteza sa citljivim brojacem (`Debug/runs`, od 2026-09-15),
zadrzano 114. Boja se ne koristi jer se cita sa table posle kaskada i dopune.

| | stari 1/N | novi selektor |
| --- | --- | --- |
| pogodak na pragu 50%, svi | 101/158 (64%) | 107/158 (68%) |
| Brier, svi | 0.223 | 0.228 |
| Brier, obican partner (77) | 0.193 | 0.176 |
| Brier, specijal partner (81) | 0.251 | 0.278 |

Najvazniji pojedinacni rezultat: gde novi model kaze 84% (opseg 80-100%),
zadrzano je 72/88 = **82%**, a na obicnom partneru 48/57 = 84%. Bot je ove
poteze birao po starom modelu, pa uzorak nije nasumican.

`tools/cleo_audit.py` posle izmene daje 34 pogotka, 5 promasaja i 116 nepoznatih
(pre: 48, 11, 92). Te brojke se **ne porede**: alat boju pogadja samo medju
bojama koje model smatra mogucim, a taj skup je sada manji.

Otvoreno, merenje se ne slaze sa kodom:

* **Druga i kasnija figura poteza.** Kod kaze 59% / 39%, a uz obican partner je
  zadrzano 15/16 i 8/10 (prva figura: 34/43). Moguce objasnjenje je kaskada u
  granama „prevent", ali to nije dokazano. Upotrebe su u alatu zakljucene iz
  redosleda poteza, jer stari snimci nemaju brojac.
* **Specijal partner.** Novi model je tu losiji po Brier-u (0.278 prema 0.251):
  iz niskih procenata je zadrzano 9/22. Lanac aktivacija specijala nije prenet.

Nije izmereno: tacna tabla + specijali + ceo RNG. `tools/verify_cleo.py` daje
0 pogodaka i 0 promasaja. Nova partija ima polja, ali booster figura
(`specialAbilityType` 53) i `moves-multiplier` u tacnom prolazu nisu preneti, pa
je taj prolaz odbija.

### Ciljno polje se unistava u prvom sloju

Procitano iz koda: na cilju je merge komad, a `ValidSwapPerformed` 0x5950dcc pravi
prisilnu kombinaciju ranga 9. Komad ostaje samo ako original ima vise od 1 HP
(`GetSurvivingPieceIndex` 0x59320c0), pa obican partner nestaje i bez matcha. Bot
ga je ostavljao na tabli, sto je pravilo lazne kaskade.

Izmereno na 10 poteza snimljenih partija, gde je boja izabrana po slaganju sa
tablom posle poteza (poznata polja, bez dopune):

| | polje ostaje | polje se unistava |
| --- | --- | --- |
| prosecno slaganje table | 0.712 | 0.774 |
| izgubljeni 04:38:25 i 04:38:47 | 0.80, 0.87 | **1.00, 1.00** |
| extra pogodjen | 9/10 | 10/10 |

Na 173 poteza (lista `[10]`, obican partner) Brier ide sa 0.158 na 0.150. Ostaje
razlika: kad je P>=80%, obecano je 0.905, a zadrzano 0.839. U 04:38:34 i 04:11:13
najbolje se slaze druga boja od one koju je model dao, sto ide na `leaves` bez
dopune. Da li unistenje polja daje i energiju i poene nije provereno.

### Figura se ne ostecuje, a dopuna radi i kad je Cleo na tabli

Izmereno na `moves-multiplier` partijama: kad eksplozija kolone predje preko Cleo,
ostaje figura i jedna rupa manje (+63 izvlacenja = 3 + 6 rupa), a u memoriji je
`damageable: False`. Nije trazeno mesto u kodu igre koje to proverava. Sirova boja
figure ulazi u brojanje boja za dopunu u svakom modu, ne samo u Match & Hatch.
Ukupan nalaz za mod: `docs/refill_engine.md`.

### Sta bot radi

* Sansa za extra je ogranicena na 100% minus sansa za sprecavanje, odluka igraca
  2026-11-04. Izuzetak je kad sve dostupne boje daju direktan match: tada `b__9`
  nema gde da skrene pa je extra siguran (procitano iz koda). Razlog je merenje:
  potezi sa P~100% zadrzali su potez 43/49 (88%), a u partiji 04:22-04:24 su
  izgubljena 2 od 6. Bez tog izuzetka takvi potezi vise nisu „siguran extra".
* Prag za Cleo potez (`CLEO_PLAY_MIN_CHANCE`) je 55%, odluka igraca 2026-11-04:
  druga figura poteza (59%) se igra, treca (39%) samo na poslednjem potezu. Isti
  prag vazi i za najvredniju boju pre spremnog bustera. Proveriti kad snimci
  donesu pravi brojac upotreba.
* Kad `engine_cleo_simulation.simulate_swipe` podrzava granu, koristi se tacan
  prolaz. To je uzak podskup: samo obicne plocice, i svaki probni raspored mora
  da unisti merge polje u pocetnoj trojci.
* Inace ide obicno rangiranje sa `_cleo_color_weights`: tezine po pravilu iznad,
  `leaves` je procena bez dopune, a kaskade su iz obicne simulacije. To je
  **model, nije tacna simulacija**, i takav potez nikad ne ide u
  `ExactRefillSession` kao tacan (`cleo_scenario_count` prekida liniju).
* Polja, brojac i kolicina se citaju iz memorije za svaku figuru posebno
  (`engine_cleo_odds.figure_params`), i **ne zavise od prekidaca za dopunu**:
  `square_solo_live.cleo_odds_profile` ih cita cim je Cleo na mirnoj tabli. Bez
  figure nema dodatnog citanja. Ako tabla nije mirna ili citanje ne uspe, koristi
  se konfiguracija PvP i prva upotreba, a GUI to ispise. U dubljem pretrazivanju
  se brojac ne prati, nego ostaje vrednost sa pocetne table.
* Tacna tabla posle poteza i dalje trazi dopunu. Bez dopune je procenat iz pravih
  vrednosti, ali kaskade ne vide novu dopunu.
* `Chance` izvlacenja se u obicnom rangiranju ne citaju iz RNG-a, iako je RNG
  poznat. `engine_cleo_odds.distribution(draws=...)` je spreman, ali nije
  ukljucen dok stroga provera ne potvrdi da pre njih nema drugih izvlacenja.

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
