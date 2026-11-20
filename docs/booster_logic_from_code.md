# Logika bustera procitana iz koda

Nalazi dobijeni disasemblovanjem `libil2cpp.so` (postupak: `docs/il2cpp_reverse.md`).
Ovde ide samo ono sto je procitano iz koda, ne ono sto je zakljuceno iz igranja.

Adrese vaze za APK verziju iz `data/il2cpp_symbols.json` (`runtime.version`).

---

## UFO Beam — boja oka nije nasumicna (ali samo u powerup varijanti)

`Match3Engine.UFOBeamSEPowerUpVariant1`

> **Opseg:** sve u ovom odeljku vazi za **powerup varijantu** bustera
> (`powerupId = UFOBeamSE-powerup1`). Bez kupljenog powerup-a ova klasa se ne
> instancira uopste — `SpecialAbility.ActiveVariant` je `null` i radi bazna
> `Match3Engine.UFOBeamSE` (vidi nize). To je izmereno na zivoj partiji, nije
> pretpostavka.

Bot je do sada tretirao izbor boje kao lutriju i resavao ga uzorkovanjem
(16 uzoraka sa deljenim seedom, [[project_high_voltage_target_sampling]]).
Kod kaze da je izbor **tezinsko izvlacenje po strategijama**, a tezine su
serverska konfiguracija.

### `PickPrefilledColor(ability, logic)` — rva 0x58a5640

```
activation = Max(0, ability.ActivatesThisTurn - 1)

w_energyNoMatch = GetIntByActivation(_chanceForEnergyEyeColorIfNoEnergyMatch, activation, 0)
w_energyMatch   = GetIntByActivation(_chanceForEnergyEyeColorIfEnergyMatch,   activation, 0)
w_noMatch       = GetIntByActivation(_chanceForNoMatchEyeColor,               activation, 0)
w_extraMove     = GetIntByActivation(_chanceForExtraMoveEyeColor,             activation, 0)
w_mushroom      = GetIntByActivation(_chanceForMushroomEyeColor,              activation, 0)
w_highScore     = GetIntByActivation(_chanceForHighScoreEyeColor,             activation, 0)

weights = {}
AddStrategyWeights(weights, <energy boje BEZ poteza za mec>, w_energyNoMatch)
AddStrategyWeights(weights, <energy boje SA potezom za mec>,  w_energyMatch)
AddStrategyWeights(weights, <boje bez ijednog poteza>,        w_noMatch)
AddStrategyWeights(weights, <boje iz BuildExtraMovePositions>, w_extraMove)
AddStrategyWeights(weights, <boje pecuraka>,                   w_mushroom)
AddStrategyWeights(weights, GetHighScoreComboColors(logic),    w_highScore)

color = WeightedPickColor(weights, random)
if (color is Empty|None|All) color = PickPrefilledColorFallback(logic)
return color
```

Ulazni skupovi se grade iz `GetColorsWithOneMoveMatch(logic)`,
`GameLogic.CurrentEnergyChargingColors`, `BoardAnalyzer.GetPossibleMoves(1)` →
`BuildExtraMovePositions`, i `BoardModel.ForEach` (pecurke).

Sigurnost nalaza: **redosled poziva i uparivanje tezina sa parametrima je
procitano direktno** (sest uzastopnih `bl AddStrategyWeights` sa tezinama sa
steka). Tacna skupovna algebra za prva tri skupa (presek/razlika energy boja i
boja sa potezom) je zakljucak iz imena parametara i redosleda operacija —
genericke `Except`/`Intersect` metode nisu u indeksu pa im se imena ne vide.

### `AddStrategyWeights(weights, colors, w)` — rva 0x58a87c4

```
if (colors == null || w < 1 || colors.Count == 0) return;
foreach (c in colors) {
    if (c == Empty || c == None || c == All) continue;   // maska 0x1003
    weights[c] = weights.GetValueOrDefault(c) + w;       // SABIRA SE
}
```

Tezine se **sabiraju**. Boja koja je istovremeno energy boja sa potezom i
high-score boja nosi zbir obe tezine, ne vecu od njih.

### `WeightedPickColor(weights, random)` — rva 0x58a89a4

```
total = suma svih tezina
if (total <= 0) return SlotColor.None       // = 1
r = random.Next(total)
running = 0
foreach (kv in weights) { running += kv.Value; if (r < running) return kv.Key; }
return weights.Last().Key
```

Obican tezinski izbor. Klasican `Next(total)` iz `Match3Engine.RandomWrapper`.

### `GetIntByActivation(list, activationIndex, defaultValue)` — rva 0x58a53a0

```
if (list == null || list.Count == 0) return defaultValue;
return list[Max(0, Min(activationIndex, list.Count - 1))];
```

Parametri su liste **po broju aktivacije u potezu**, sa klampovanjem na
poslednji element. Druga i svaka sledeca aktivacija u istom potezu mogu imati
druge tezine, a kad se lista potrosi vazi poslednja vrednost.

### Procitane vrednosti (`data/ability_config.json`, UFO SE = type 49)

Osnovni `additionalParams`:

| param | vrednost |
| --- | --- |
| `allowPickingBlues` | `false` |
| `allowPickingSpecials` | `false` |
| `colorsToPickByActivation` | `2,2,1` |
| `maxPassiveActivates` | `2` |
| `specialPieceScoreValue` | `4` |

Segment za `powerupId = UFOBeamSE-powerup1` (varijanta koja se stvarno igra):

| tezina | vrednost |
| --- | --- |
| `chanceForNoMatchEyeColor` | **60** |
| `chanceForExtraMoveEyeColor` | 40 |
| `chanceForMushroomEyeColor` | 40 |
| `chanceForHighScoreEyeColor` | 40 |
| `chanceForEnergyEyeColorIfNoEnergyMatch` | 5 |
| `chanceForEnergyEyeColorIfEnergyMatch` | 5 |

uz `colorsToPickByActivation = 3,2` (dakle 3 boje na prvoj aktivaciji, 2 na
svakoj sledecoj) i `specialPiecesCountAfterActivation = 2,1`.

Isti buster, drugi mod:

| tezina | Rumble/Party | Solo |
| --- | --- | --- |
| `chanceForEnergyEyeColorIfNoEnergyMatch` | 15 | **0** |
| `chanceForEnergyEyeColorIfEnergyMatch` | **30,10** | **0** |
| `chanceForNoMatchEyeColor` | — | 40 |

Dve stvari koje se odavde vide odmah:

* **Sa powerup-om, u Solo modu UFO nikad ne bira plavu** — obe energy tezine
  su 0. U Rumble/Party prva aktivacija ima tezinu 30 za plavu-sa-potezom, a
  svaka sledeca 10 (`GetIntByActivation` klampuje).
* Sa powerup-om u normalnom PvP-u plava je prakticno zanemarena (5 naspram 60
  za boju bez poteza).

Sva tri segmenta traze `powerupId = UFOBeamSE-powerup1`, pa **bez powerup-a
nijedna od ovih brojki ne vazi**.

### Kako se override segmenti primenjuju

`SpecialAbilityModelParamsManager` nije imao veze sa ovim — to je samo JSON
deserializacija (koji naziv parametra se cita kao int, koji kao lista).

Pravo mesto je nadjeno pretragom svih `bl` poziva ka
`SpecialAbilityOverrideSegment::Includes` (0x57d1c68). **Jedini pozivalac je
`SpecialAbility::.ctor`** (0x58c6394). Dakle:

* izbor segmenata se radi **jednom, pri kreiranju bustera za partiju**, ne pri
  svakoj upotrebi;
* segmenti koji prodju `Includes(...)` se `AddRange`-uju u listu parametara
  (`segment.overrides`, offset 0x30);
* `ReadIntListParam` posle toga cita **iskljucivo** `Config.additionalParams`
  (offset 0xe0) i uzima **prvi** unos sa trazenim kljucem
  (`FirstOrDefault`), pa vrednost deli po zarezu.

Ono sto i dalje nije dokazano je **redosled u toj listi**, a on odlucuje ko
pobedjuje na duplom kljucu, jer je pretraga `FirstOrDefault`.

Zivo merenje koje je ovo raspetljalo u praksi: u Solo partiji sa UFO SE bez
powerup-a, instanca ima tacno bazne parametre i `ActiveVariant = null`. Sva tri
UFO segmenta nose `powerupId = UFOBeamSE-powerup1`, pa nijedan nije prosao —
sto se poklapa.

### Sta ovo znaci za bota

Vrednosti tih sest lista dolaze iz `SpecialAbilityModelParam`, dakle
**citaju se iz memorije** — nisu u kodu. Kad se procitaju, raspodela boje oka se
racuna tacno, umesto da se pogadja uzorkovanjem.

### Bazni UFO SE (bez powerup-a) — koliko boja

`Match3Engine.UFOBeamSE::CalculateColorsToPick` — rva 0x58891b0, 192 bajta:

```
colorsToPick = colorsToPickByActivation[Min(ActivatesThisTurn - 1, Count - 1)];
```

Sa procitanim `colorsToPickByActivation = "2,2,1"` to znaci **2 boje na prvoj
aktivaciji u potezu, 2 na drugoj, 1 na svakoj sledecoj**. To je broj boja koje
se skidaju sa table, tj. broj ociju.

(Sa powerup-om je `colorsToPickByActivation = "3,2"`, dakle 3 pa 2.)

---

## Metla (Sweep It SE) — sta se prebojava

`Match3Engine.SweepItSEPieceLogic::isPiecePaintable(SlotModel, SlotColor)`
— rva 0x58d8a2c, 28 bajtova:

```
return slot.value == 0;      // SlotValueType.Normal
```

Prebojava se **samo obicna plocica**, nijedan specijal, i prosledjena boja se u
toj proveri uopste ne gleda.

Vazno za opseg: ovo je odgovor o **prebojavanju**, ne o **pomeranju**. Za
pomeranje je merodavan `MakeSwaps` — vidi nize, odgovor je da metla **pomera**
klasicne specijale ciljne boje.

Parametri klase: `chanceToRemoveBlues`, `chanceToRemoveMaxScore`,
`minPiecesToPaint`, `maxPiecesToPaint`, `paintBehavior` (string) — vrednosti iz
`SpecialPieceModelParam`, citljive iz memorije.

### Koliko se plocica prebojava (procitano iz memorije 2026-08-21)

`python tools\dump_il2cpp_symbols.py --piece-logics` -> `data\piece_logic_config.json`,
unos `slot_type: 38` (`SlotValueType.SweepItSEPiece`). Vrednosti su reprodukovane
dva puta, nezavisnim dumpovima (13:02 i 15:06):

| param | default (PvP) | pvpMode Solo | pvpMode Rumble/Party |
| --- | --- | --- | --- |
| `paintBehavior` | `PickColor` | **`None`** | `PickColor` |
| `minPiecesToPaint` | 0 | — | 2 |
| `maxPiecesToPaint` | 2 | — | 4 |
| `chanceToRemoveBlues` | 15 | — | — |
| `chanceToRemoveMaxScore` | 15 | — | — |
| `allowRed` / `allowBlue` | `true` / `true` | — | — |
| `mergeSwapBlockTypes` | `SweepItSEPiece` | — | — |

`SwapPerformed` (0x58d8a48) izvlaci broj sa
`RandomWrapper::Range(minPiecesToPaint, maxPiecesToPaint)` (0x58d951c:
`ldp w2, w1, [x19, #0x88]`, dakle w1=min, w2=max). `RandomWrapper::Range`
(0x58db398) racuna `min + Next() % (min - max)`, sto je **max-eksluzivno**.
Ocekivan broj prebojanih plocica je zato:

| mod | opseg | ocekivano |
| --- | --- | --- |
| PvP | 0..1 | **0.5** |
| Solo | nema prebojavanja | **0.0** |
| Rumble/Party | 2..3 | **2.5** |

Odmah pre toga stoje dva `RandomWrapper::Chance` poziva (0x58d948c i 0x58d94ac,
polja `+0x80` i `+0x84`): sa 15% se **plava** izbacuje iz izbora, i sa 15%
boja sa najvecim skorom (`MatchRulesModel::GetMaxScoreColor`). Boja u koju se
prebojava je ista ona koju metla mete — `ConvertSlotModel` na 0x58d9f0c uzima
boju iz `[x20, #0x40]`, a to je rezultat izbora ciljne boje sa pocetka metode.

### Sta `MakeSwaps` zaista pomera (0x587e7dc, `SweepIt::MakeSwaps`)

Potpis: `MakeSwaps(logic, colorsGroup, isSimulate, sourceToTargetRef, conversionsRef, directions)`.
Petlja ide po `colorsGroup`, a za i-tu boju uzima `directions[i]` (ako lista
nije dovoljno duga — poslednji element). Za svaku liniju paralelnu smeru:

1. **Skupljanje** — prolazak kroz liniju, `BoardModel::get_Item(point)`, pa
   provera `SlotModel.movable` (`+0x25`, 0x587eb88). Neprenosive celije
   (sanduci, blokade) se **preskacu u potpunosti** — ne ulaze u listu pozicija,
   pa ostaju tacno gde su i ne pomeraju indekse ostalih.
2. **Dva prolaza (stabilna particija)** — 0x587ee70: `SlotModel::MatchesWithColor`
   po svakoj skupljenoj celiji; prvi prolaz upisuje one koje **ne** odgovaraju
   boji, drugi one koje odgovaraju. Rezultat: ciljna boja se pakuje uz ivicu
   swipe-a, ostale zadrzavaju relativni redosled — isti model koji bot vec ima.

`MatchesWithColor` -> `SlotModel::IsPieceWithColor` (0x57cfadc), a to je
`IsNormalOrClassicSpecial(value)` (`value == 0` ili `4 <= value <= 8`) ili
`IsClassicSpecialMerge` (`11 <= value <= 13`). Dakle **ciljnu boju nose i
klasicni specijali** — `Column 4`, `Row 5`, `Bomb 6`, `Fireworks 7`,
`Crosshair 8`, plus spojevi `Cross 11`, `Star 12`, `FourthOfJuly 13`.

**Time je zatvorena stavka „da li metla pomera obojene specijale": pomera ih.**
Ranija indicija sa snimka (plavi ROW specijal (4,4) -> (6,4)) se poklapa.
Bezbojni board-specijali (pecurka, kristal, lotos...) nemaju boju, pa za njih
`IsPieceWithColor` vraca false i oni ostaju na mestu.

### Segment ispred metle — sta kod kaze

U `MakeSwaps` **nema nikakvog izuzetka za liniju metle**. Nista se u toj petlji
ne unistava: postoje samo `ConvertSlotModel` i `BoardModel::set_Item`. Hipoteza
B iz ranije validacije („metla unistava ne-ciljne plocice ispred sebe") tako
nema podrsku u kodu — ostaje hipoteza A, da je posmatran kadar usred animacije.

Ono sto kod objasnjava je rupa: ako je metla u trenutku skupljanja vec
potrosena / oznacena kao `movable == false`, njena celija se preskace u koraku 1,
pa rupa ostaje tacno na njoj — sto je upravo ono sto je merenje na snimku
pokazalo. Ali kod ne poznaje botov rez „samo deo linije od ivice do metle":
particija ide preko **cele** linije bez te celije. Kako je botov rez empirijski
podigao tacnost linije metle sa 19% na 54%, a `Debug
uns` vise nema nijedan
odigran sweep za ponovnu proveru, geometrija nije menjana — to je prvi kandidat
za sledeci snimak.

### Procitane vrednosti (Sweep It SE = type 61)

| param | vrednost |
| --- | --- |
| `useDirections` | `Right,Left` |
| `colorsAmount` | `2` |
| `pickBehavior` | `closest` |
| `minPiecesToMove` | `4` |
| `piecesPerActivation` | `2,1` |
| `allowRed` / `allowBlue` | `true` / `true` |
| `chanceToAllowBlueAsTargetPosition` | `50` |
| `chanceToBroomWithExtraMoveByActivation` | `100` |
| `minExtraMoveOptions` / `maxExtraMoveOptions` | `1` / `1` |
| `scoreTarget` | `15` |

U normalnom PvP-u je `chanceToBroomWithExtraMoveByActivation = 100`, dakle metla
se **uvek** postavlja tako da napravi extra potez. U Solo modu je
`piecesPerActivation = 1` i `minExtraMoveOptions = 0`; u super-size arenama
(`rulesId`/`modeId` = `super-sized` / `super-size`) sanse za extra padaju na 0.
U Rumble/Party je `maxExtraMoveOptions = 3` uz `chanceForBlueWithExtraMove = 20`.

Za razliku od UFO-a, metlini segmenti **nemaju** `powerupId` — biraju se samo po
`pvpMode` / `rulesId` / `modeId`, pa vaze i bez kupljenog powerup-a.

Napomena o `useDirections = Right,Left`: to je polje `SweepItSE.directions`
(+0xb8 na `SweepIt`), i tice se metli koje **buster postavlja**. Odigran sweep
UP sa snimka 2026-08-08 je tacno reprodukovan (48/49), pa smer koji igrac
prevuce ocito nije ogranicen na horizontalu. Nije menjano nista na osnovu ovog
polja.

### Poredjenje sa botom (2026-08-21)

| sta bot pretpostavlja | sta memorija/kod kaze | poklapa se |
| --- | --- | --- |
| `SWEEP_RECOLOUR_EXPECTED_TILES = 3.0` (mereno sa ekrana) | PvP 0.5, Solo 0.0, Rumble 2.5 | ne — **popravljeno** |
| ciljna boja prebojanih plocica = boja sweep-a | isto (`ConvertSlotModel` uzima boju sweep-a) | da |
| prebojavaju se sve vrste plocica (bot samo skalarno kreditira) | samo `value == 0` | nebitno — bot ne boji u simulaciji |
| specijali ciljne boje **ostaju** na mestu | klasicni obojeni specijali se **pomeraju** | ne — **popravljeno** |
| bezbojni board-specijali ostaju na mestu | isto (`IsPieceWithColor` false) | da |
| po liniji: ciljna boja uz ivicu, ostalo zadrzava redosled | isto (dva prolaza) | da |
| BLOCKED celije ucestvuju u preslaganju | samo lotos je `movable == false` | delimicno — **popravljeno** (skip po lotosu, ne po BLOCKED) |
| rupe (`EMPTY`) putuju na kraj linije | `Empty` je `movable == false`, ostaje na mestu | ne — **nije menjano**, vidi nize |
| rez linije metle na deo „ivica -> metla" | kod nema takav rez | nepoznato — empirijski bolji, ostavljeno |
| `SWEEP_RECOLOUR_BLUE_BONUS`, `SWEEP_RECOLOUR_TILE_BONUS`, `SWEEP_SETUP_*` | engine ne daje broj | nema broja — nije dirano |

### `movable` — koje celije uopste ucestvuju (mereno na 7096 snimaka)

`movable` (+0x25) je vec u dumpu agenta (`tools/matchmasters_board_dump.ts`), pa
se ne mora citati iz koda. Prebrojano po `Debug/memory_board/board_snapshots.jsonl`:

| `SlotValue` | `movable` |
| --- | --- |
| 1 `Empty` | **False** 150/150 |
| 40 lotos (Froggy) | **False** 557/557 |
| 0 `Normal` | True 316369, False 5 (usred animacije) |
| 25 „immovable" Billie | **True** 41/41 |
| sve ostalo (4..8, 16..33) | True |
| 20 `PirateChestPiece` (sanduk) | **nema nijednog uzorka** |

Dakle: neprenosiv je **samo lotos**. Sve ostalo sto bot mapira u `BLOCKED` je
`movable == true` — ukljucujuci Billijev dron (`SlotValue 25`, 41/41), koji je
BLOCKED samo zato sto je `canBeMatched == false`. Zato je skip u
`_sweep_se_packed_board` vezan za `SWEEP_IMMOVABLE_SPECIALS = {lotos}`, a ne za
boju `BLOCKED`; dron se i dalje preslaze sa ostalim ne-ciljnim plocicama.

`board_source` je razdvojen: `value == 40` i `value == 25` vise ne dele granu
„immovable Billie/Lotus". Boja ostaje `BLOCKED` u oba slucaja (za dron zato sto
`canBeMatched == false`, sto je i ono sto ekranska putanja radi — `recognition`
mu takodje daje `BLOCKED`), ali komentar vise ne tvrdi da je dron neprenosiv.

Dve stvari koje **nisu** menjane, jer bi bilo nagadjanje:

* **Sanduci nisu `BLOCKED` u botu** — `board_source` ih mapira u boju `CHEST = 8`,
  ne u `BLOCKED`, pa ih metla i dalje preslaze kao obicnu ne-ciljnu plocicu. U
  memoriji nema nijednog snimka sa `SlotValue 20` da se `movable` proveri, a
  validacija sa snimka 2026-08-08 je bila bas Chest Mode (2 sanduka) i dala je
  48/49 sa modelom koji ih pomera. Za promenu treba snimak Chest Mode partije.
* **Rupe** — `Empty` je `movable == false`, sto znaci da rupa ostaje tacno gde
  jeste, a bot je i dalje gura na kraj linije. To se poklapa sa empirijskim
  nalazom da rupa od potrosene metle ostaje na svojoj celiji (samo sto kod kaze
  da to vazi za *svaku* rupu, ne samo za metlinu). Na smirenoj tabli pre poteza
  je jedina rupa bas metlina i nju bot vec drzi na mestu, pa je razlika vidljiva
  tek na tabli sa vise rupa — nema podataka, nije dirano.

Izmene u kodu: `move_strategy.sweep_recolour_expected_tiles()` +
`sweep_paint_pvp_mode_active(...)` (pvpMode stize iz memorijske putanje kroz
`CheckBestMoveRequest.sweep_paint_pvp_mode`), `SWEEP_MOVABLE_SPECIALS` i
`SWEEP_IMMOVABLE_SPECIALS` u `_sweep_se_packed_board`, plus razdvajanje
`SlotValue` 25 i 40 u `board_source`.

---

---

## Froggy Fu (lotus) — vrednost po boji

`Froggy Fu = type 63`, 32 parametra, najvise od svih bustera. Kljucni je
`rainbowScoreByColor`:

```
Yellow:4 | Purple:3 | Orange:2 | Green:1 | White:1 | Blue:0 | Red:0
```

Bot je vec imao svoju tabelu (`FROGGY_LOTUS_SCORE_VALUES`) sastavljenu iz
igranja. Poredjenje:

| boja | config | config + 1 | bot | |
| --- | --- | --- | --- | --- |
| Yellow | 4 | 5 | 5.0 | poklapa se |
| Purple | 3 | 4 | 4.0 | poklapa se |
| Orange | 2 | 3 | 3.0 | poklapa se |
| Green | 1 | 2 | 2.0 | poklapa se |
| Red | 0 | 1 | 1.0 | poklapa se |
| White | 1 | 2 | — | **nedostajala** |
| Blue | 0 | 1 | 2.0 | **namerno vise** |

Sest od sedam boja se poklapa sa `DEFAULT_CELL_SCORE + config`, sto je jaka
potvrda da je skala tacna i da je `rainbowScoreByColor` bas vrednost po
skupljenoj plocici. Ostaju dva odstupanja:

* **Bela je nedostajala.** `_froggy_lotus_color_value` je za belu vracao `None`,
  pa beli mec u lotus zoni **uopste nije palio lotus** u simulaciji. Config joj
  daje istu vrednost kao zelenoj. Popravljeno: `WHITE: 2.0`, i bela je dodata u
  `FROGGY_LOTUS_COLOR_PRIORITY` pored zelene.
* **Plava ostaje na 2.0 namerno.** Config joj daje 0 poena, ali plavi collect
  pokupi svu plavu sa table i napuni buster, a na lotus putanji to niko drugi ne
  broji — `rank_froggy_lotus_moves` bonus ulaze samo u `score`/`instant_score`.
  Ta razlika je sad imenovana (`FROGGY_LOTUS_BLUE_CHARGE_CREDIT`) da se vidi da
  je kredit za punjenje bustera, a ne tvrdnja o poenima.

### Ostalo iz Froggy config-a

| param | PvP | Solo | Rumble/Party |
| --- | --- | --- | --- |
| `lotusCountByActivation` | 2 | 2,2,1 | 2 |
| `entranceDestroyCountRangeByActivation` | 8–12 | 15–20 | 8–12 |
| `highScorePieceRatioByActivation` | 20,10 | 70,40 | 20,10 |
| `entranceMushroomCountRangeByActivation` | 0–1 | 1–2 | 0–1 |
| `chanceToPlaceNextToEnergyMatchByActivation` | 5 | 70,35 | 10 |

Plus, isto u svim modovima: `gatherShape = square`, `gatherRadius = 7`,
`minLotusSeparation = 5`, `chanceToPlaceNextToDominantColor = 100`,
`chanceToSkipSameColorMatch = 100`, `scoreTarget = 30`.

`gatherRadius 7` u kvadratu pokriva celu 7x7 tablu, pa je botov
`_board_color_count` nad celom tablom tacan — ali na vecim tablama ne bi bio.

`placementWeightByColorByActivation` ima `Blue:0` u svakom modu: lotus se nikad
ne postavlja uz plavu. To ne trazi izmenu jer bot lotuse cita sa table.

---

---

## Provera svih bustera (2026-08-21)

49 bustera u `data/ability_config.json`, 40 sa parametrima. Devet ih nema
nijedan: Magic Wand, Detonator, Crazy Rocket, Laser Beam, Mystery Hat, Quack
Attack, Lil Dragon, High Voltage, All Aboard — za njih se iz konfiguracije nema
sta uporediti.

### Sta je uopste uporedivo

Vecina parametara opisuje **postavljanje** (`chanceToPickMatchablePiece`,
`chanceToBlockNeighbors`, `chanceToNeighborBlues`, `maxTries`...), tj. kako igra
bira gde da spusti figure. Bot te figure cita sa table posle poteza, pa tu nema
sta da se razidje.

Uporedivo je troje, i to je proslo kroz proveru u celosti:

1. tabele vrednosti po boji,
2. `allow*` zastavice po boji,
3. brojevi koje bot mora da predvidi **pre** nego sto ih vidi (broj ociju,
  broj boja u kodu).

### Nadjeno

| buster | config | bot | ishod |
| --- | --- | --- | --- |
| UFO (19) | `allowPickingBlues = **True**` | zakucan skup bez plave | **razilazilo se** |
| UFO SE (49) | `allowPickingBlues = False` | isto | poklapa se |
| UFO SE (49) | `colorsToPickByActivation = 2,2,1` | cita se uzivo | poklapa se |
| Froggy Fu (63) | `rainbowScoreByColor` | tabela + 1 | **bela nedostajala** |
| Mixy Meow (59) | `colorsToPickByActivation = 3,2` | `2 <= len(components) <= 3` | poklapa se |
| Sweep It SE (61) | `useDirections = Right,Left`, `colorsAmount = 2` | horizontalno, 2 boje | poklapa se |

**Obican UFO (type 19) sme da uzme plavu, UFO SE ne sme.** Bot mapira oba na
istu `ufo` akciju, pa je stari zakucani skup boja bio tacan za jedan a pogresan
za drugi. To vise nije problem otkad `allowPickingBlues` stize uzivo iz
`special_ability_params` — ali je konkretna potvrda da je ta izmena bila
potrebna, ne kozmeticka.

### Otvoreno, vredi provere na snimku

* **Cleo (53)** `chanceToCreateExtraMoveOnCloneByActivation = 80,50,10`. Bot ima
  `CLEO_EXTRA_MOVE_CHANCE = 0.0`, ali to je o drugoj stvari — izmereno je da sam
  Cleo *swap* ne vraca potez, dok config govori o tome da klonirane figure sa
  80% sanse **ostave** match-4 priliku na tabli za sledeci potez. Nije protivrecno,
  ali 80% je previse da bi se ignorisalo.
* **Brocco Boogie (44)** `numOfPiecesToDestroy = 15`, `piecesPerActivation = 3,2`.
  Bot disko lopticu (`DISCO_BALL = 99`) vodi kao neuparivu prepreku i ne
  simulira sta ona rusi.
* **Sweep It (39)** ima `minPiecesToMove = 7`, a Sweep It SE (61) `4`. Dve
  verzije istog bustera sa razlicitim pragom.
* **`WOOLLY_WORKOUT_TARGET_COLORS`** iskljucuje plavu, crvenu i belu bez ijednog
  parametra koji to trazi — isti oblik kao dve greske nadjene danas (UFO skup i
  Froggy bela). Woolly (35) nema nijedan parametar boje, pa se ovo iz
  konfiguracije ne moze proveriti; trazi merenje.

---

## Referentne vrednosti enum-a

Citaju se iz `value__`, ne iz redosleda deklaracije:

| `SlotColor` | | | |
| --- | --- | --- | --- |
| Empty 0 | None 1 | Red 2 | Green 3 |
| Blue 4 | Yellow 5 | Orange 6 | Purple 7 |
| White 8 | All 12 | | |

Maska `0x1003` = `Empty | None | All`, tj. „nije prava boja". Pojavljuje se u
svakom filteru boja u UFO kodu.

`SlotValueType` je 0..41 redom, `Normal = 0`, `BroccoBoogiePiece = 28`
(poklapa se sa onim sto je bot ranije utvrdio posmatranjem).

---

## Provera 2026-10-14: poeni, extra potez, UFO oci, disko, Cleo figura

Isti `libil2cpp.so` (APK 2026-08-16). Sta je procitano i sta je promenjeno.

### Poeni — `GameLogic::CalculateDestructionScoreAndMeter` (0x5750ad8)

```
po polju:  slot.hitPoints == 0 ? 0 : slot.score * cell.scoreMultiplier
           * (polje u Special/MergeSwap kombinaciji ? rules.specialComboScoreMultiplier : 1)
ukupno:    suma; x2 za passive DoubleScore, doubleScoreForLoserThisMove, doubleScoreThisMove;
           0 za zeroScoreThisMove; x PlayerControl.ScoreMultiplier ako >= 2; pa HandleAddScore
```

Bot to vec ima. `specialComboScoreMultiplier` se ne cita (podrazumevano 1).

### Extra potez — `GameLogic::DestroyMatches` (0x574b178, oko 0x574d28c..0x574d848)

* `IsAbilityUsedThisMove` (samo buster, `PlayerModel.isAbilityUsedThisMove`) -> nema extra uopste.
* `gotExtraTurnDuringMove` vec postavljen -> nema drugog: **najvise jedan extra po potezu**.
* `extraMoveEnabled && Moves < movesPerTurn` -> prva kombinacija tipa Five/RShape/FourRow/
  FourColumn/Square (`<GetExtraMoveCombo>b__365_0`: tip 4..8), inace Xtra polja table.
  Kaskade se racunaju.

**Promenjeno:** `SimulationResult.extra_moves/direct_extra_moves/ufo_predicted_extra_moves`
su ograniceni na 1 (`_AtMostOneExtraMove`; 339/6000 kandidata je imalo 2). Simulacije meta
bustera (laser, High Voltage, Magic Wand, Woolly) vise ne daju extra
(`_without_booster_extra_moves`). Perkovi i dalje smeju.

### UFO SE oci — `PlayerControl::BeforeCombosDestroy` (0x57e22c0) i `UFOBeamSE::AfterDestroyWithPassiveAbility` (0x5889348)

* Lista boja (`PlayerControl.colorsExplodedThisMove`) se puni samo ako buster NIJE upotrebljen u
  potezu, ako oko jos nije opalilo u tom potezu i ako je `ColorsPicked < colorsToPick`.
* Redosled: kombinacije sa swap-om napred (`MoveCombosWithSwapToFront`), razlicite boje redom;
  Cleo figura (value 32) se preskace.
* Okidanje: jednom po potezu (`preventAfterDestroyWithPassiveAbilityThisMove = 1`),
  `n = min(boje, colorsToPick - ColorsPicked)`, `Take(n)`, pa `ConvertAndDestroy` (obicne figure,
  specijali ostaju).
* Filter plave u ovom putu **ne postoji** — `allowPickingBlues` vazi za aktivni zrak
  (`UFOBeam.Use`). Dopuna 2026-10-28 ispod ispravlja raniju pretpostavku da je
  plava poslednji izbor pasivnog oka.

**Promenjeno:** `_ufo_eyes_this_move()` vraca 0 kad je buster upotrebljen u potezu
(`booster_used_this_move` iz memorije, bez besplatnih perkova).

#### Dopuna 2026-10-28: redosled boja jednog i dva oka

Pregledan sacuvani ARM64 `libil2cpp.so` lokalnim `tools/il2cpp_disasm.py`.
Listinzi su u `Debug/reverse/ufo/`; staticki nalaz nije nova proba uzivo.

* `GameLogic.ValidSwapPerformed` na `0x574a730` prvo dodaje position2
  (odrediste prevlacenja), zatim position1. `BoardAnalyzer.GetAllCombos` i
  `GetCombosFromTestList` obilaze tu listu po redu. `MoveCombosWithSwapToFront`
  daje prednost kombinacijama sa swap podatkom, bez izbora po boji.
* `PlayerControl.BeforeCombosDestroy`, `0x57e2634..0x57e278c`, skuplja
  razlicite normalne boje redom i preskace Cleo figuru. Nema plave preferencije.
* `UFOBeamSE.AfterDestroyWithPassiveAbility`, `0x5889a58..0x5889aa0`, uzima
  `n = min(colorsExplodedThisMove.Count, colorsToPick - ColorsPicked)` i
  `Take(n)`. `PassiveActivates` raste jednom po pasivnom okidanju; `ColorsPicked`
  raste za n, pa dva oka mogu otici u istom potezu.
* Default variant za broj ociju koristi `max(0, colorsToPick - ColorsPicked)`.
  `Use` resetuje oba brojaca i racuna cilj iz tabele aktivacija.

Uklonjena je heuristika "plava poslednja" iz `_ufo_abduction_colors`, i plava
je ukljucena u proveru nedvosmislenosti izbora. Snimci
`2026-10-11_21-15-14_260` (Blow Em Up) i
`2026-10-26_02-27-45_120` (Hot Color): jedno oko, odredisni plavi spoj i
drugi spoj, metar 0 -> 7. Stara heuristika je predvidjala 3 plave; ispravljen
redosled skida plavu i predvidja pun metar. To podupire staticki nalaz;
same krajnje table nisu dokaz da su poznate sve nasumicne dopune.

Testovi proveravaju oba smera istog dvobojnog poteza, jedno i dva oka, plavu
kao prvi ili drugi spoj, ponovljenu istu boju i oba sacuvana slucaja punjenja.
Nepoznate nove figure i efekti nesigurnih specijala ostaju procene; ova
izmena ne pretvara sve post-UFO kaskade u garantovani extra potez. Powerup
varijanta sa prepunjenom bojom i moguca tri oka nije standardni model 1/2 oka.

#### Dopuna posle zivog debuga 2026-10-28 07:18--07:19: drugo oko iz kaskade

`BeforeCombosDestroy` nema uslov da je u pitanju samo direktan spoj. Boje se
skupljaju tokom rusenja sve do prvog pasivnog okidanja, dok su
`isAbilityUsedThisMove`, `isRunningAsPassive` i
`preventAfterDestroyWithPassiveAbilityThisMove` iskljuceni. Ranije ogranicenje
simulatora na prvu kaskadu bilo je pogresno.

U snimcima `2026-10-28_07-18-46_377` i `2026-10-28_07-19-04_682`
direktni spoj je plav, a sledeca modelovana kaskada dodaje novu boju.
Simulator je predvidjao samo jednu potrosenu boju, dok manualni engine dump
na 06:19:05.174Z eksplicitno cita `colors_picked=2`, `passive_activates=1`,
`remaining_hud_eyes=0`. Izmenjeni obican i special-swap put skupljaju nove
razlicite boje pre okidanja i zatvaraju skupljanje kad abdukcija pocne.
Kaskada izazvana samom abdukcijom ne sme potrositi preostalo oko.

Replay oba snimka sada predvidja dve potrosene boje. Kod 07:18:46 vise boja
konkurise za poslednje oko u istoj kaskadi, pa je njihov redosled i dalje
oznacen kao nesiguran; broj potrosenih ociju ne dokazuje tacnu drugu boju.
Testovi imaju i primer bez specijala u kome prirodan pad hrani drugo oko,
kao i negativan primer gde tek post-abdukcijski pad daje drugu boju.

Agent na manualnim snimcima sada dodatno cita
`PlayerControl.colorsExplodedThisMove` kao
`ufo_colors_exploded_this_move` (izvorni `SlotColor` enum brojevi, do 16 stavki).
To je citanje polja, bez promene igre. Omogucava sledecu proveru pravih boja
bez pogadjanja iz nasumicno dopunjene table; stari snimci nemaju tu listu.

#### Laser + UFO SE: boje prolaznih figura, 2026-10-28 07:51

`LightsabersBoard.AfterPerformedSwap` na `0x578aaa0` pravi `ComboType.Manual`
za svaku prihvacenu putanju. Putanja je uredjena lista od prve figure posle
izvora do odgovarajuceg kraja zraka, a pravci su native `(0,+1)`, `(0,-1)`,
`(+1,0)`, `(-1,0)` (u simulatoru: dole, gore, desno, levo). Direktni swap
spojevi idu ispred ovih Manual kombinacija. Kada kombinacija nema jednu
normalnu boju, `BeforeCombosDestroy` obilazi njene figure redom, pa prolazne
figure lasera mogu dati drugu boju oku pre gravitacione kaskade.

`2026-10-28_07-51-39_716`: crveni spoj, laserski zrak prelazi preko
narandzaste, aktivira se i vertikalni specijal. Raniji simulator je laser
svodio na neuredjen skup ociscenih polja i tek iz sledece kaskade birao plavu
za drugo oko. Nova native lista u debugu daje `[2,6]` (crvena, narandzasta),
`colors_picked=2`, `remaining_hud_eyes=0`; punjenje je +4, ne predvidjenih +7.

`_laser_effect_paths` sada cuva uredjene putanje, `_laser_effect_cells` i
dalje koristi njihovu uniju za rusenje, a `_ufo_laser_colors` hrani oci
bojama sa tih putanja pre kaskada. Cleo figure su iskljucene kao u native
kolektoru. Replay svih sedam UFO poteza sa dostupnom native listom iz te
partije daje iste izabrane boje, potrosnju ociju i ograniceno punjenje metra
kao igra. Test fixture cuva i izvorne enum vrednosti i timestamp uzorka.

### Disko kugla — `BroccoBoogiePieceLogic::GetAreaOfPieceExplode` (0x58c9d94)

`GetAreaOfColorEffect(pos, partner, isInclude, destructibleOnly, shouldMatchColor2)` — sve
unistive figure boje partnera, ukljucujuci `color2`. Bot se poklapa (osim `color2`).

### Cleo figura — `CleoCadabraPieceLogic::SwapPerformed` (0x58cb9c0) — procitano, NIJE primenjeno

Lambde nad `CleoCloneToColorResult` (positions, leavesExtraMoveOnBoard, matchesExtraMove,
deltaToTarget): boje sa < `cloneToWholeColorMinimumTargetPieces` ispadaju; kad extra nije
sprecen (`chanceToPreventExtraMoveOnColorBasedClone`) bira se rezultat sa extra mecom /
extra potezom na tabli uz `deltaToTarget < maxAllowedDifferenceFromDeltaForExtraMoveMatch`;
kad je sprecen, extra boje se izbacuju; inace redosled po kljucu (verovatno delta).

Provera na 96 snimljenih Cleo poteza: igra je birala boju koju botova simulacija vidi kao
extra u 52/96 (sigurno ocitane 18/32), uniformni model ocekuje 48 (16.3), pravilo "85%"
~80. Dakle ili `deltaToTarget` uslov retko prolazi, ili engine klonira podskup (ne celu boju)
pa njegova "extra boja" nije botova. Uniformne tezine ostaju (CLEO_GOAL_SHARPNESS = 0).
Usput: 16 poteza je zadrzalo potez iako botova simulacija za tu boju ne vidi extra —
model klona je tu slabiji od izbora boje.

### Opsta pravila motora (druga runda, 2026-10-14)

**Punjenje bustera** — `GameLogic::CalculateEnergyCharge` (0x5754afc) i `get_IsCanChargeAbility` (0x573f16c):

```
IsCanChargeAbility = !rules[0xa0] && !noEnergyThisMove
                     && !(IsAbilityUsedThisMove && !allowEnergyEvenIfAbilityUsedThisMove)
                     && !(IsAbilityUsedThisTurn && LogicModel.limitBoosterCollectEnergyAfterUse)
po polju (boja ili color2 u energy bojama, iz BoardModel.GetEnergyGivenPositions):
    energy += rules.energyMult * slot.energy, staje kad je merac pun
plus rules.colorComboEnergy: origin kombinacija zadate boje
```

`allowEnergyEvenIfAbilityUsedThisMove` upisuje samo Pirate Chest logika (pretraga `strb [x,#0x119]`
po celom kodu), a `ProcessTurnFlowStep` ga brise svakog poteza zajedno sa
`gotExtraTurnDuringMove`. Dakle blast bustera ne puni merac. **Promenjeno:**
`_without_booster_extra_moves` plavu iz blasta (osim `_chest_blue`) knjizi kao `wasted_blue_cells`
— Laser, Magic Wand, Woolly (HV je vec bio izmeren tako). Snimci: Woolly sa predvidjenom plavom
-> merac 0 u 64/71. `energyMult` je u svim snimljenim modovima 1.

**Oblik -> tip** — `ComboModel::GetComboType` (0x579fb58):

```
IsFiveShapeFast (bilo koja petica u redu/koloni)  -> Five
broj >= 5, >= 3 razlicita reda i >= 3 kolone       -> RShape (L/T)
IsCrosshairShapeFast                               -> Square
broj >= 4 i 4 u jednoj osi                         -> FourRow / FourColumn
inace                                              -> ComboRow / ComboColumn
```

**Promenjeno:** `classify_cells` — L/T sa krakom od 5 je sada "five" (Lightning), ne "l".

**extraMoveEnabled** — DestroyMatches ga proverava pre trazenja extra kombinacije. Iskljucen je
u "Lightning Strike" (snimak 2026-10-12). **Promenjeno:** `extra_moves_enabled_active`
(memory_gui -> request.extra_move_enabled -> runtime mode_rules); van memorije ostaje ukljucen.

`LogicModel.chainReactionChance` nema vidljivog citaoca.

### Dometi specijala (treca runda, 2026-10-14)

Ispravka: nizovi pravaca NISU u global-metadata. `Point[]` je niz struktura, pa ga C# puni
instrukcijama u `BoardModel..cctor` (0x576d40c, `Point::.ctor(x, y)` sa konstantama). Izvuceni
emulatorom (19 nizova): bomb = 3x3 + 4 polja na rastojanju 2 (13 sa centrom), star = 5x5 bez
uglova (21), bigBomb 24, bigStar 36, shortRow/shortColumn +-3, itd.

Dispecer `BoardAnalyzer::GetAreaOfEffectByPiece` (0x5723d5c), po `SlotValueType`:

| vrednost | specijal | domet | bot |
| --- | --- | --- | --- |
| 4 Column / 5 Row | linija | cela kolona / ceo red | isto |
| 6 Bomb | bomba | `GetBomb` (13) | isto |
| 7 Fireworks | botov Lightning | `GetFireworks(12)`: 12 zauzetih damageable polja, i ona koja se vec ruse (ignore vazi samo za dopunu) | bilo 13 -> **12**; sa tacnom dopunom iz koda |
| 8 Crosshair | crosshair | `GetCrosshair`: `additionalData.gemPickThreshold` (Square Match: 7 meta, prvo do 3 u boji energije) | sa tacnom dopunom iz koda (`EngineRefill.crosshair_targets`), inace 6 nasumicnih |
| 11 Cross | linija+linija | red + kolona | isto |
| 12 Star | bomba+bomba | `GetStar` (21) | isto |
| 13 FourthOfJuly | lightning+lightning | `GetFireworks(24)` | isto |

Xref alat vidi samo `bl`; dispecer zove repnim `b`, pa ga je nasla tek pretraga i po `b`.

### specialComboScoreMultiplier — sada se cita

Tip `ComboType.Special` pravi samo `BoardAnalyzer::GetAreaOfEffectDestructionSlots` (pretraga
konstruktora ComboModel sa `w1 = 1`), dakle mnozilac vazi za svako polje koje unisti eksplozija
specijala, i za MergeSwap. Dodato: agent (`special_combo_score_multiplier`, agent ponovo
izgradjen, stari `.js.pre-2026-10-14`), allowlist citaca, ispis `special_mult=` u logu citaca,
memory_gui -> request -> `special_combo_score_multiplier_active`. U simulaciji polja koja je
dohvatio samo blast (`cleared - initial_cells`) dobijaju visak `(mult - 1)` pod kljucem
`1000 + boja` u `cleared_color_counts`, koji cita samo bodovanje. Vrednost u zivim
partijama jos nije vidjena (agent je tek dopunjen).

## Provera 2026-10-14 (cetvrta runda): oblik -> specijal, tajmer, solo ciljevi

Isti `libil2cpp.so`. Redosled prema listi otvorenih tacaka (1, 5, 6).

### 1. Koji specijal nastaje iz kog oblika — `BoardAnalyzer::MakeSpecialSlotCreated` (0x5726da4)

Zove ga samo `GetCombosFromTestList` (0x5726648 + 0x620). Po `CreateSpecialReason`
(NoSpecial 0, ComboSpecial 1, EveryMatchSpecial 2, ColorMatchSpecial 3, MatchChanceSpecial 4):

```
rules[0x134] (allSpecialsLightning)         -> uvek Fireworks (7), boja = GetComboColor
ComboSpecial: tabela po ComboType, 0x57270f0..0x5727100 (bajtovi 07 06 05 04 08)
    Five(4) -> 7 Fireworks (Lightning)     RShape(5)      -> 6 Bomb
    FourRow(6) -> 5 Row                    FourColumn(7)  -> 4 Column
    Square(8) -> 8 Crosshair
EveryMatchSpecial (2): GetSpecialPiecesLogic(...) pa boja iz GetComboColor (nije razradjeno)
ColorMatchSpecial (3): GetComboColor -> mapa u rules.extraData (nije razradjeno)
MatchChanceSpecial (4): izbor iz liste po GetRandomSpecialPiece (nije razradjeno)
```

Orijentacija linije: cetvorka u REDU pravi Row (cisti ceo red), cetvorka u KOLONI pravi Column.

**Provera na snimcima** (Debug/runs, intent `special_creation` u cascade 1 + novi specijal na
`special_board_after`, bez aktivacije u potezu): cetvorka u koloni -> Column 677 / bomba 0,
cetvorka u redu -> Row 377 / bomba 0, L -> Bomb 138, T/plus -> Bomb 51, kvadrat -> Crosshair 233,
petica -> Lightning 80. Poklapa se u svim grupama.

**Sta je bot radio:** i cetvorka i L/T su bili nerazreseni `CREATED_SPECIAL` sa dometom bombe
(`_special_effect_cells`). Cetvorka koja se aktivira u istom potezu je zato citila 3x3+ umesto
celog reda/kolone. U 1262 od 18362 snimljenih poteza (6.9%) predvidjanje je sadrzalo takvu
aktivaciju.

**Promenjeno:** `_created_special_type` — cetvorka u redu -> `SPECIAL_HORIZONTAL`, u koloni ->
`SPECIAL_VERTICAL`, L/T -> `SPECIAL_BOMB`. Test: `tests/test_created_special_shape_2026_10_14.py`.
Vracanje: obrisati dva `if` bloka u `_created_special_type`.

### 5. Tajmer — `GameLogic::AddExtraTime` (0x574eec0) i `DestroyMatches`

```
AddExtraTime(t): MoveAddedTime[2 floata na 0x140] += t / GeneralModel.inGameTimeScale;
                 ako je timer aktivan i (pauseTimerForAnimations || pauseTimerForBoosters)
                 isto vreme se prosledjuje i turnTimer-u (IGameTimer, interfejs poziv)
po DestroyMatches (0x574d238..0x574d270):  AddExtraTime(1.0 + LogicModel.timeAddedOnDestroy)
          (samo ako neki combo nije explodeImidiate; inace 1.0)
extra potez (0x574d7a8): ako isTimer:
          conditionalTimeBonus && timeLeft < LogicModel.lastSecondsThreshold
              -> AddExtraTime(timeAddedExtraMoveLastSeconds - timeLeft)
          inace AddExtraTime(timeAddedExtraMove)
rules.extraMoveBonusTime / oneBonusTimePerMove (0x574d2b8): dodatno vreme po potezu
```

U svim snimljenim modovima `extraMoveBonusTime = 0`, `conditionalTimeBonus = true`,
`colorMatchBonusTime` je mapa (vrednosti agent ne cita). Vrednosti `LogicModel.timeAdded*` nisu u
snimku, pa je mereno: promena `time_left_seconds` izmedju uzastopnih poteza + proteklo vreme,
10.2k poteza (solo_6):

| | mediana | n |
| --- | --- | --- |
| potez bez extra | 0.7 s | 3183 |
| potez sa extra | 0.8 s | 6983 |
| 1 kaskada | 0.7 s | 9283 |
| 2 kaskade | 1.0-1.4 s | 4873 |
| 3 kaskade | 1.4-2.2 s | 1008 |
| 4+ kaskade | 2.8-4.2 s | 176 |

Dakle: extra potez NE dodaje merljivo vreme (razlika 0.1 s), a svaka kaskada vraca oko 0.7-1 s
(`1 + timeAddedOnDestroy`). Bot ne modelira ni jedno ni drugo — za sada ispravno za extra;
kaskade su sitnica (< 1 s po potezu). **Nista nije menjano.**

### 6. Solo ciljevi — `GameLogic::HandleAddScore` (0x57551d0)

Vazi kad je `rules.pvpMode == 1` (solo) i postoji `soloTargets`:

```
reachedTargetThisMove (GameLogic 0x11e) vec postavljen i !soloOverflowPastTarget
    -> amount = 0   (osim na poslednjem cilju kad je soloContinueAfterLastTarget)
dok score + amount >= soloTargets[ind]:  ind++, reachedTargetThisMove = 1
posle petlje, ako !soloOverflowPastTarget i (ind < count ILI !soloContinueAfterLastTarget):
    amount = soloTargets[ind-1] - score        // visak preko cilja se brise
```

Dakle bez `soloOverflowPastTarget` poeni koji prelaze NEZAVRSNI cilj u istom potezu se brisu
(skor staje tacno na cilju, dalje kaskade tog poteza daju 0); poslednji cilj sa
`soloContinueAfterLastTarget` ne seče. Sa `soloOverflowPastTarget = true` nema secenja.

**Provera na snimcima** (lights-up, dve konfiguracije u istom jsonl-u):

| konfiguracija | prelaz | skor posle |
| --- | --- | --- |
| `[16000]`, overflow true | 1150 (9 prelaza, kontrolno) | 1158..1297 (bez secenja) |
| `[1150, 12000, 37500]`, overflow false, continue true | 1150 (3x) | tacno 1150 |
| isto | 12000 (2x) | tacno 12000 |
| isto | 37500 (poslednji, 1x) | 38367 (bez secenja) |

Predvidjanje se poklapa u 15/15.

**Primenjeno 2026-10-16:** `solo_challenge.SoloGoalState` prenosi ciljeve, trenutni skor,
refill poteza, overflow, continue i energiju za neiskoriscene poteze iz memorijskog
snapshot-a kroz Memory GUI do runtime rangiranja. Sledeci cilj je prvi veci od skora.
Kad je overflow iskljucen, poeni preko praga ne dobijaju dodatnu vrednost; poslednji
cilj sa continue zadrzava pravilo motora.

Sigurno dostizanje poslednjeg cilja ima `solo_target_finish_gate`, pre boostera/perka.
Siguran prelaz koji dopunjava poteze ima `solo_target_refill_gate` kad ostaju najvise
tri poteza, ili kad pravila pretvaraju ustedjene poteze u energiju. Za garanciju se
koriste poznata unistenja i stvarni mnozilac; random refill, Cleo scenariji i
ocekivani dodatni poeni ne predstavljaju siguran prolaz. Za modove gde sam broj
obicnih plocica nije pouzdan model poena nema ove garancije.

Kandidat koji sigurno dopunjava poteze ili daje pouzdan extra ima sopstveni nastavak
i kad brojac trenutno pokazuje 1. Poznat extra lanac cuva se odvojeno od opste
buduce vrednosti, kako ga nauceni popust za nepoznat refill ne bi obrisao. Obican
poslednji potez i potez koji zavrsava ceo challenge nemaju izmisljeni nastavak.

Pouzdano pripremljen sledeci extra u Solo Challenge cuva se kao
`verified_extra_setup_bonus`: trenutni potez mora ostaviti poznatu tablu, a extra
sledeceg poteza mora nastati pre granice nepoznatog refilla. Kredit je ogranicen
na vrednost jednog dodatnog poteza i nestaje na obicnom poslednjem potezu.
Nauceni rezidual pri efektivno 2–3 preostala poteza ogranicen je na +/-25%
heuristickog prioriteta; pri jednom je nula. Pouzdan extra i poznata dopuna
prethodno prosiruju efektivni horizont. Debug cuva sirov `learned_residual` i
stvarno primenjen `applied_learned_residual` odvojeno.

Dustville Duel (snimak Froggy Fu, 2026-10-16 02:04): `wantedShoots=4`,
`minBluesToPick=2`, `scoreBonusPerHit=1`. `_dustville_wanted_charge` vrednuje
minimalno punjenje od dve plave po prikupljenoj figuri preko postojece cene
punjenja boostera, ograniceno brojem preostalih plavih. Ne izmislja lokacije
pogodaka, dodatne kaskade ni replenishment. Nepoznate kaskade i Cleo scenariji
ne dobijaju ovaj garantovani kredit. Istorijski nauceni rezidual iskljucen je
za ovaj mod jer stara predikcija nije sadrzala ishode pucanja. Pet sacuvanih
tabli sada bira dve wanted figure; siguran extra i dalje ima prednost.

Posle provere partija 02:05–03:27 dodato je:

- Dustville `mode_target_collect` oznacava kaskadu aktiviranja figure.
  `dustville_random_shots` je tvrda granica pouzdanosti: sledeca predvidjena
  cetvorka nije garantovani extra. Minimalno punjenje od figura aktiviranih
  pre granice ostaje vrednovano; ne placaju se kasnije spekulativne figure.
- Lotus u vremenski ogranicenim solo trkama postepeno priblizava ocenu
  neposrednim poenima kada ostaje manje od sest odluka po procenjenom tempu.
  Sa najmanje sest odluka, nepoznatim satom i u Solo Challenge nema promene.
  Na tabli 02:44:56, x16 i 24.13 s bira 54 umesto 36 neposrednih poena;
  obe kombinacije cuvaju potez. Sa 110 s zadrzava staru kombinaciju.
- Mixy zastita od izostalog povracaja sada priznaje i pouzdan extra iz
  poznate kaskade, nakon oduzimanja samog refund kredita. Nasumicna kaskada
  ne dobija tu prednost. Ako alternativa nema sopstveni extra, prvi izostali
  povracaj i dalje nije moguce unapred garantovano predvideti.

### Mixy Meow: novi kod posle prve upotrebe (2026-11-12)

`MixyMeow.AfterCombosDestroy` -> `RandomizeActiveColors` (0x5a7788c), u
`engine_mixy.redeal`. Ide posle svih dopuna poteza, kao poslednje RNG izvlacenje:

1. Cetiri `Chance`: plava bez spoja (`...NoBlueMatchAvailable`), plava sa
   spojem (`...BlueMatchAvailable`), oba po `NumOfPassiveUsesThisTurn` (vec
   uvecan ovim potezom); zatim izbaci i uzmi boju sa najvise poena (po
   aktivaciji). Indeksi su `min(i, Count-1)`.
2. Lista boja u redosledu (6,3,5,7,4,2), samo boje koje se dopunjuju, izmesana
   (`Shuffle`, jedan `Next` po boji). Zatim po jedan `Chance` za svaki unos
   `chanceToPreventColors`.
3. Boja igraca (`slotType`): ide prva ako ima legalan potez i prodje drugi
   `Chance`, ili nema potez i prodje prvi. Uvek se izbacuje iz liste.
4. Sa `colorScoreOverride`: najveci poen (strogo vise od 1, prvi u izmesanoj
   listi) se izbacuje / uzima po trecem / cetvrtom `Chance`.
5. Redom izmesane liste: boja sa bar jednim legalnim potezom koji je spaja,
   dok se ne skupi `colorsToPickByActivation` boja; ostatak iz liste redom.

Specijali iz spojeva svakog poteza koji pogodi kod (i poslednje upotrebe, bez
novog koda) nastaju na mestu konverzije (prva x-pa-y celija spoja), ne na swap
celiji: Color Climb 02:49:10 i 02:49:48; od 155 sacuvanih promasaja sa
upotrebom koda tacno je 65 umesto 20, nijedan raniji tacan nije pokvaren. Redosled boja i "boja igraca = slotType" su
izvuceni iz snimaka: jedini redosled koji odgovara svima. Snimci
`Debug/refill_unsupported/mixy_redeal` + trag 20261112_020924: 20 od 20
poteza koji se ponavljaju tacni (tabla, ceo RNG, boje koda); ostali parovi
nisu jedan cist potez ni pre ove izmene.

### Ostalo otvoreno
2, 3, 4, 7, 8, 9 sa liste nisu dirane; 10: UFO plava, Cleo klon i `GetCrosshair` ostaju.

---

## Billie Boom (41) — sta se desi na aktivaciju (procitano 2026-11-20)

Listinzi: `Debug/reverse/billie_boom/`. Snimci: `Debug/research/20261120_112013_super-sized`
(Solo, pvpMode 1, Super Sized, tabla 8x8, 14 aktivacija), fixtures u `tests/fixtures/billie_boom/`.

### Redosled poziva

`BillieBoom::Use` (0x5a12fd0) — `Ability::Use`, `SetPassiveAbility`, pa
`ConvertBillieBoomPiece` (0x5a13268), a tek onda `GameLogic::ConvertSlots(41)`.
Posle konverzije ide `SuckAndConvertByScoreTarget` (0x5a1345c).

Potpis je `Use(GameLogic logic)` — **nista se ne bira dodirom**: polje, boje i sve
ostalo bira kod. Zato zapis `{"action":"activate_booster","booster_mode":"none"}`
(bez `booster_target`/`booster_color`) jeste dovoljan za replay.

### Pozicija drona — `DronePiecePosition` (0x5a127f8) nema nijedno izvlacenje

```
find = BoardModel.Find(<dron na tabli>)
if (find != Point.Null) return find          // postoji dron: ista pozicija
p = Point(x = Rows / 2, y = Columns - 1)     // (red = visina-1, kolona = sirina/2)
if (slot[p].<flag> == 0 && slot[p].IsLiveEventPieceWorthPoints) return p
// inace: BoardModel.ForEach skuplja kandidate, List.Sort, prvi
```

U `ConvertBillieBoomPiece` se zatim `Board[pos].Clone().ToSpecial(25)` (25 =
`SlotValueType.BillieBoomPiece`), `canBeMatched = 0`, `movable = 0`, i
`ConvertSlots(ConversionModel(..., 41))`. Field `this[0x44] = 3` (za Solo 3 =
`initialCreate`).

**Izmereno na snimku:** dron je na (red 7, kol 4) u 13 od 14 aktivacija; 14. je
(7,5) — tada (7,4) nije bio pogodno polje, pa je pao fallback. `billie_slots` posle
aktivacije ima tacno jedan dron, `color 6` / `color2 1` u svih 14 (dron ne menja
boju; to nije par usisanih boja).

### Koje dve boje se usisaju — `SuckAndConvertByScoreTarget` (0x5a1345c)

```
groups  = GetColorGroups(logic)            // grupe boja; colorsToSuck = 2
sorted  = groups.OrderBy(|simScore(group) - scoreTarget|)
first   = sorted.First()
rng     = new RandomWrapper(<seed iz GameLogic>)
if (rng.Chance(this[0x6c])) ...            // grana sa dodatnim izborom
SuckAndConvert(logic, colors, ...)         // simulacija ide na GameLogic klonu
```

`scoreTarget` se cita kroz `Ability::GetScoreTarget`; u Solo Super Sized je 24.
Usisane boje se pretvaraju (`convertValues`, `suckSpecials = false`, `SuckAndConvert`
0x5a13d20 i dalje `ConvertSlots(41)`), pa ide dopuna i kaskada.

**Izmereno:** poena po aktivaciji 19-26, prosek 22.4 — blizu `scoreTarget` 24, sto
potvrdjuje da izbor boja ide na poene.

**Jos nije procitano (blokira tacan port):**

1. `GetColorGroups` (0x5a12bfc, 261 bajt koda bez ijednog poziva) — tacan redosled
grupa i da li je grupa uopste par boja ili nesto drugo.
2. `SuckAndConvert` (0x5a13d20) — u sta se usisane boje pretvaraju i da li se
unistavaju ili prebojavaju (`convertValues` je lista `SlotValueType`).
3. Field `this[0x6c]` u `Chance` — koja je to `additionalParams` vrednost
(`chanceToPickMatchablePiece` 70 ili `chanceToPickRandomColors` -1).
4. `dnr`: `SuckAndConvertByScoreTarget` skoruje svaku grupu na `GameLogic` klonu
(preko `add_onDestroyed`), pa koje se izvlacenje (ako ikakvo) trosi na pravom RNG-u.

### Sta ovo znaci

Aktivacija ima dva dela: (a) postavljanje drona, koje je deterministicko i vec
potvrdjeno na snimku; (b) izbor dve boje po `scoreTarget`, koji trazi gore navedene
cetiri stavke. Do tada se Billie ne ukljucuje u `EXACT_PLAN_BOOSTERS`.

---

## Billie Boom — sta je izmereno 2026-11-20 (`tools/billie_boom_check.py`)

Engine: `engine_billie_boom.py`; veza u `strategy_lab/simulation.py`
(`billie_activate`, grana za `BILLIE_BOOM`). Alati: `tools/billie_boom_check.py`
(14 aktivacija, TACNO/najblizi promasaj), `Debug/billie_pairs.py` (terajuci
svaki par), `Debug/billie_truth.py` (koji par igra odigrala).
Rezultat: **3 od 14 aktivacija tacno** — zato je port iza prekidaca
`simulation.BILLIE_BOOM_PORTED = False` i bot/planer ga za sada odbijaju.

### Potvrdjeno merenjem

1. **Dron sam po sebi je tacan.** Pozicija (red = visina-1, kolona = sirina/2),
   ponovna upotreba postojeceg drona, i `color 6 / color2 1` se poklapaju sa
   snimkom (13/14 + fallback na (7,5)).
2. **"Usisaj sve obicne plocice dve boje" je tacan model.** Kad se par koji je
   igra odigrala forsira, tabla je **0 razlika u 14 od 14** aktivacija (RNG tacan
   u 10 od 14). `suckSpecials` je false, pa specijali ostaju.
3. **Kandidat-boje NISU [6,3,5,7,8].** 006->007 je Red+Blue i 017->018 je
   Red+Orange, oba tacno; sa listom ogranicenom na Orange/Green/Yellow/Purple/
   White nijedna aktivacija nije pogodjena. Literali u `GetColorGroups` zato
   nisu lista kandidata — trenutno se uzima svih sedam pravih `SlotColor`
   vrednosti (2..8) prisutnih na tabli.
4. `chanceToPickRandomColors` (offset 0x6c) = **-1**, pa `Chance` grana u
   `SuckAndConvertByScoreTarget` ne prolazi i izbor ne trosi izvlacenje.

### Sta jos nije portovano

1. **Izbor para.** Kod sortira grupe po `|skor klona - GetScoreTarget|`
   (`OrderBy` + `ThenBy` + `First`), ali sa mojim skorovanjem (kaskada na klonu)
   istinit par je prvi u 8/14, drugi u 5/14, cetvrti u 1/14. Ostaje da se
   procita tacan kljuc i sekundarni kljuc (`0x542bd74` / `0x542c3b4` /
   `0x542c134` komparatori); `scoreTarget` u Solu je 24 (Solo override).
   Ni varijante sa RNG izborom (`shuffled[0]`, `range`, `chance`+`range`) ne
   pogadjaju bolje od 3/14, pa izbor nije slucajan.
2. **Pasiva posle aktivacije.** U 6 aktivacija gde je par tacan ostaje
   2-4 specijala razlike i RNG odstupanje od -32 do +10: `EndMoveWithPassiveAbility`
   -> `ConvertToCrosses` (engine_billie) se sada poziva i za `kind == "booster"`,
   ali izbor bombi ne odgovara (isti put kao za zamene treba vezati za fazu).
3. **Faza.** `CurrPhase` ide 0 -> 2 samo na prvoj aktivaciji partije
   (`firstCreation`), ostale ostaju na 2; pretpostavka je da je put isti, ali
   to nije potvrdjeno na prvoj aktivaciji.

### Da bi se zatvorilo

- Tacan skor kandidata u klonu (vidi "Izbor para" nize).
- Porediti izbor na vise partija (drugi mod), da se razlikuje "pogresan kljuc"
  od "pogresno skorovanje u jednom modu".

---

## Billie Boom — izbor para procitan iz dekompiliranog koda (2026-11-20)

### Kako je dekompilacija uspela (vazno za sledeci put)

Listinzi u `Debug/reverse/billie_boom` NISU iz `Debug/reverse/libil2cpp.so`
*kao fajla*: njihove adrese su RVA iz `data/il2cpp_method_index.json`
(modul zive igre, `module_base 0x771026fba000`). U tom `.so` vazi
`file_offset = rva - 0x4000` za kodni segment (`p_offset 0x2999620`,
`p_vaddr 0x299d620`), pa je prvi bajt `SuckAndConvertByScoreTarget` na
fajl-ofsetu `0x5a0f45c` (`ff c3 02 d1` = `sub sp, sp, #0xb0`), a ne na
`0x5a1345c`.

Ghidra projekat mora biti importovan iz istog builda; `foxy_slice/foxyfull`
je stariji, a adrese u njemu su **fajl-ofseti**. Nov projekat:

```
Debug/reverse/billie_slice/billie.gpr   (import libil2cpp_5817.so, -noanalysis)
DecompileAt.java <out.c> 5a0f45c:5a0fd20 ...
```

### Tacno pravilo (0x5a1345c)

```
for group in GetColorGroups():                     # 0x5a136a4
    clone = logic.Clone()                          # 0x5956368
    clone.add_onDestroyed(collect)                 # DisplayClass56_0 b__1
    this.SuckAndConvert(clone, group, useChance, automatic)   # 0x5a13d20
    w28 = virtual(this, clone)                     # this[0x218]
    value = clone.CurrentPlayer.Score + w28 - logic.CurrentPlayer.Score   # 0x5a1385c
    dict[group] = value
candidates = dict.OrderBy(|value - GetScoreTarget()|)      # DisplayClass56_1 b__6
                     .ThenBy(|value - GetScoreTarget()|)   # DisplayClass56_1 b__4
chosen = candidates.First()                        # 0x3d50d40 / 0x4fbd620
if (RandomWrapper(rng).Chance(this[0x6c])) chosen = candidates.ElementAt(...)
```

- Obe lambde su **istog oblika**: `0x5a15b94` i `0x5a15c0c` rade
  `subs w8, w19, w20; cneg w8, w8, pl; scvtf s0, w8` = `(float)Math.Abs(x - captured)`,
  gde je `captured` polje `+0x10` DisplayClass56_1, upisano na `0x5a13934` iz
  `Ability::GetScoreTarget` (0x59033c4). Dakle kljuc je **odstupanje od cilja**,
  a ne najveci skor.
- `this[0x6c]` = `chanceToPickRandomColors` = -1, pa `Chance` ne prolazi.
- `SuckAndConvert` koristi `BoardModel.Where`, `SlotModel.Clone`,
  `GameLogic.ConvertSlots` — **samo konvertuje** plocice izabranih boja; u
  klonu nema kaskade (`IsCloneLogic`, flag `[this+0x90]`), pa je skor kandidata
  vrednost unistenih plocica, ne cela kaskada.
- `GetColorGroups` sadi listu `[6,3,5,7,8]` i drzi samo boje sa table;
  `OrderBy` je stabilan, pa taj redosled odlucuje izjednacene.

### Sta jos ne stima

Sa tim pravilom (redosled `[6,3,5,7,8]` pa ostale boje) rezultat je **3/14**
tacnih, a par je pogodjen u 5/14 (003, 008, 027, 029, 033). Offline nad
izmerenom tabelom najbolja varijanta (`|kaskada-24|`, redosled sa 6 napred)
daje 8/14. Preostalo je tacno skorovanje kandidata u klonu (`w28` i vrednost
plocica u tom modu) — bez njega izbor para ostaje nepouzdan.

## Monkey JooJoo (booster 40): aktivacija (`Use`)

Stanje 2026-11-20: mehanika je procitana i portovana (`engine_monkey.py`, kuka u
`strategy_lab.simulation.step_move`, grana `booster_type == MONKEY_JOOJOO`), ali
se **cvor aktivacije jos ne poklapa**: na Super Sized Solo snimku
`Debug/research/20261120_111530_super-sized` (12 aktivacija) 0 je tacnih.
Zato booster 40 ostaje van `square_solo_live.EXACT_PLAN_BOOSTERS`.

Listinzi: `Debug/reverse/monkey/` (64 fajla). `Use` 0x5a7b09c, `ChoosePositions`
0x5a7b6b0, `ConvertToSpecialsAndAutoExplode` 0x5a7c074, `ConvertToSpecials`
0x5a7c148, `RefillExplodedSpecials` 0x5a7c610, lambda izbora `Use>b__0`
0x5a7d148.

### Sta `Use` radi

1. `Ability::Use`, pa `SetPassiveAbility(this)`, pa `WasJustActivated` (0x78) = 1.
2. `maxTries` (Solo 5) puta `ChoosePositions(logic, false)`, svaki rezultat u
   listu kandidata (kapacitet `piecesAmount`).
3. Ako je lista prazna -> `ConvertToSpecialsAndAutoExplode` sa praznom listom.
   Ako ima jedan kandidat -> `List.get_Item(0)` i dalje.
   Inace, za svakog kandidata: `GameLogic::Clone` (0x5956368), `onDestroyed`,
   `ConvertToSpecialsAndAutoExplode`, pa skor = `(skor klona + vrednost virtuelne
   metode na vtable+0x218) - skor igraca`; sve u `Dictionary<positions, score>`.
4. Klon nosi **svoju kopiju RNG-a** (`EngineRefill.clone` radi isto), pa
   izvlacenja tokom ocenjivanja kandidata ne pomeraju pravi brojac. Merenje to
   potvrdjuje: prva aktivacija u igri trosi 531 izvlacenje, a ocenjivanje 5
   kandidata u simulatoru ne ulazi u brojac.
5. Lambda `Use>b__0` vraca `-abs(skor - GetScoreTarget)`; petlja prekida kad
   kandidat pogodi `scoreTarget` (Solo 35). Konkretan selektor (0x3c1199c) i
   sekundarni kljuc nisu razreseni -- port uzima prvi najblizi.

### `ChoosePositions(logic, useChance)`

Polja: 0x50 (grana; 0 u snimcima), 0x78 `WasJustActivated`, 0x7c, 0x80
`maxPieces` = 99, 0x84 `autoExplodeAmount`, 0x88 `piecesAmount`, 0x8c
`chanceToPickMatchablePiece`, 0x90 `skullsPerActivation`, 0x24 `scoreTarget`.

- `WasJustActivated` -> `count = skullsPerActivation[min(ActivatesThisTurn - 1,
  n - 1)]` (grana 0x5a7b9b4), **bez** oduzimanja lobanja koje su vec na tabli.
- inace (pasiva) -> `target = min(zbir skullsPerActivation po bacanjima,
  maxPieces)`, `count = target - lobanje na tabli`; 0 izvlacenja kad je 0.
- `count < 1` -> prazna lista, bez izvlacenja.
- `useChance` true (samo pasiva): `GetPossibleMoves(board, true)` -> matchable,
  `count` puta `Chance(chanceToPickMatchablePiece)`, pa tri
  `GetSlotPrioritize` (prioritet uvek false: x-major, promesano, jedno
  izvlacenje po kandidatu). To je `EngineRefill.joojoo_end_move`.
- `useChance` false (aktivacija): jedan `GetSlotPrioritize` sa `count`, isti
  redosled (x-major `Where`, `shuffled`, prvih `count`).

### `ConvertToSpecialsAndAutoExplode`

`ConvertToSpecials(..., callback, unconvertExisting = false)` pretvara svako
polje iz liste u lobanju (`SlotModel.ToSpecial`, SlotValue 24, bez izvlacenja),
pa callback (b__0):

1. prva lista = prvih `min(len(positions), autoExplodeAmount)` polja **u redu
   kojim ih je `ChoosePositions` vratio**;
2. `board.Where(SlotValue == 24)` (x-major) bez vec uzetih, do ukupno
   `autoExplodeAmount`;
3. ako lista nije prazna: `ComboModel(type 10, 0x28)` + `GameLogic::DestroyMatches`
   (kaskada, dopuna, dalje eksplozije lobanja); ako je prazna:
   `WasJustActivated = 0` + `EndMove`.

Lobanje koje nisu unistene ostaju na tabli; posle poteza
`RefillExplodedSpecials` / `EndMoveWithPassiveAbility` dopunjava do cilja.

### Merenja na snimku (Super Sized Solo, 20261120_111530)

| bacanje | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lobanje na mirnoj tabli | 4 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 |
| izvlacenja u igri | 531 | 1452 | 620 | 1132 | 606 | 508 | 689 | 524 | 574 | 610 | 640 | 655 |

`ActivatesThisTurn` iz profila je **unapred** i broji i pasivne dopune (snimak
008 cita 3 posle dva bacanja), pa se cilj racuna iz same table:
`skull_target = lobanje_pre + throw_delta`, gde je `throw_delta` 4 za prvo
bacanje i `skullsPerActivation[1]` (1) za svako sledece -- **osim drugog, koje je
dodalo 2**. Taj +1 je izmeren, uzrok nije nadjen: bacanje postavlja 1 lobanju po
konfiguraciji, pa je moguce da se dopuna u tom trenutku izvrsila dva puta.

### Sta se poklapa, a sta ne

- Poklapa se: broj lobanja na mirnoj tabli u svih 12 aktivacija (4, 6, 7 ... 16),
  potroseno punjenje (7 -> 0), podrzanost poteza, i tacni poeni u 2 od 12
  (023->024 55/55, 025->026 56/56).
- Ne poklapa se: tabla (39-55 polja) i specijali (11-23), sa njima i RNG
  (od -90 do +140). Znaci da se **skup koji se odmah unistava** (auto-eksplozija)
  ne poklapa, a ne samo izbor kandidata: `tools/monkey_check.py --candidates`
  proba svih 5 kandidata i nijedan ne daje ni igrine lobanje ni tablu.
- Alati: `tools/monkey_check.py` (12 aktivacija, TACNO/najblizi promasaj),
  `--candidates` (5 kandidata po aktivaciji). Fixture:
  `tests/fixtures/monkey_joojoo/20261120_111530_super-sized/` (cela partija).
  Testovi: `tests/test_monkey_joojoo_port.py` (7 testova: konfiguracija, izbor
  lobanja, cilj, kandidati, odigrana aktivacija).

### Da bi se zatvorilo

1. Koja polja ulaze u `count` kad `useChance` nije postavljen: `GetSlotPrioritize`
   dobija `logic[0x168]` kao listu kandidata (verovatno sva polja), a predikati
   (b__13_9 / b__13_7) filtriraju. Port sada uzima `plain` figure dozvoljenih
   boja; sa svim obicnim figurama prva aktivacija je na +13 izvlacenja (531 u
   igri), sa samo dozvoljenim bojama na -53.
2. Predikati `b__13_9` / `b__13_7` i `b__12_2` (`!positions.Contains`) -- procitati
   da se zna da li lobanja moze na specijal i sta se preskace.
3. `0x3c13d70`, `0x3d4f1fc`, `0x42fcd40`, `0x45cd790` su LINQ helperi
   (`Intersect` / `ToList` / `Take` / predikat); potvrditi ih na par tacnih
   bacanja pre nego sto se menja model.
4. Drugi mod (Hot Color ili Mutation Lab) sa 2-3 bacanja po partiji, da se
   razlikuje greska u izboru od greske u kaskadi.

---

## Valentine Vinnie SE (47) — sta je utvrdjeno 2026-11-20

Listinzi: `Debug/reverse/cupid2/` (disasembler), `Debug/reverse/cupid_powerup/`
(Ghidra C za osnovnu `Cupid` klasu i `CupidHeartPieceLogic`).
Snimci: `Debug/research/20261120_115017_super-sized` (Solo, pvpMode 1, Super Sized,
tabla 8x8, 14 aktivacija), fixtures u `tests/fixtures/vinnie_se/`.
Alat: `python tools/vinnie_se_check.py` (`vinnie_se_check.txt` u folderu).

### Konfiguracija procitana iz memorije (`profile.ability_detail`)

`class = Match3Engine.CupidSE`, `ActiveVariant = None` — **bez powerup varijante**,
pa `selectedExplosionShape`, `oneColorHeartAfterActivation` i ostali
`CupidSE-powerup1` override-i ne vaze.

| polje | vrednost |
| --- | --- |
| `piecesPerActivation` | `[3]` |
| `maxStagedPiecesActivations` | 2 |
| `specialPieceScoreValue` | 2 |
| `maxTries` | 30 |
| `asTempSpecials` | True |
| `allowBoardEdgePositions` | False |
| `allowBlueForCurrentActivation` | False |
| `scoreTarget` | 0 |
| `scoreFactor` / `colorFactor` | 0.1 / 0.9 |
| `maxScoreTopRange` | 50 |
| `chanceForBlue` / `chanceToNeighborBlue` / `chanceToAllowBlueAsTargetPosition` | -1 |
| `sourceCellToColored` | 3 unosa po aktivaciji (vidi nize) |

`CupidSE` ima samo `get_IsTwoColorHeart` i `.ctor`; sve radi nasledjeni `Cupid`.
`Use` je `0x5a2c5d4`, 14256 bajtova — prevelik za citanje u jednom prolazu.

### Sta kod kaze (procitano)

* `Cupid::GetExplosionArea` (0x5a2ffe8) pita varijantu za oblik
  (`GetExplosionShape`) i bira `BoardModel::GetHeart` (3) /
  `GetSurroundingEight` (2) / `GetExtendedPlus` (1) / **`GetPlus` (0, osnovno)**.
  Bez powerup-a varijanta je `CupidDefaultVariant`, dakle oblik je **plus**.
* `Cupid::CreateHeartPiece` (0x5a30230) pravi `ConvertSlotModel` preko
  `BoosterPiecesLogic.ConvertToPiece(target, useTwoColors)` i onda postavlja
  `slot.damageable = false` (`|= 1`) i `slot[0x21] = 0x100` (`setAsTempSpecials`).
* `Cupid::GetVarietyScore` (0x5a319b4) broji **koliko razlicitih boja** ima u
  prosledjenim konverzijama (`Dictionary<SlotColor,int>` po `slot.color` na
  `+0x10`); vraca broj razlicitih.
* `Cupid::GetNormalizedColors` (0x5a32570) cita `slot.color` (`+0x10`) i
  `slot.color2` (`+0x11`) i normalizuje par.
* U repu `Use` (0x5a2f7e0--) stoji `score = scoreFactor * <int> +
  colorFactor * <variety>` u `Fix64`, pa `Max` po kandidatima i `Log` — to je
  izbor cilja po `scoreFactor`/`colorFactor`/`maxScoreTopRange`.
* Redosled u `Use`: `GatherTargetOptions` -> `CreateHeartPiece` ->
  `ConvertAndDestroy` (na `GameLogic::Clone` sa `onDestroyed`) -> prava
  `ConvertAndDestroy`.

### Sta je izmereno na 14 aktivacija (`tools/vinnie_se_check.py`)

1. **Tri cilja po aktivaciji**, tacno onoliko koliko `piecesPerActivation` kaze.
   `sourceCellToColored` u snimku POSLE aktivacije daje tacne ciljeve
   (kljuc = cilj, vrednost = njegov plus); prikaz se osvezava svakog poteza, pa
   se ciljevi citaju iz prve sledece table.
2. **Srce nosi boju plocice na cilju** — 30/30 srca koja se mogu upariti
   (`raw_slots`, `value = 23`, `color = color1`). Boja cilja nikad nije plava
   (igraceva boja u ovom snimku je `slot_type 4`), nikad specijal.
3. **Srce pada niz rupu koju je samo napravilo**: u 003->004 sva tri su tacno
   jedan red nize; u 006->007 cilj (6,1) daje srce na (6,3) jer je i (6,2) bilo
   prazno. Gravitura je obicna, ne posebna.
4. **+15 poena po aktivaciji** u 10 od 14 (3 srca x 5 polja plusa = 15
   unistenih polja x 1 poen). Odstupanja: +16 (014), +18 (025), +8 (016) —
   dodatne kaskade; 016 je i jedina aktivacija bez ijednog srca na tabli posle.
5. **Punjenje ide na 0** posle aktivacije u 13 od 14 (016 ostaje 6, sto ide sa
   +8 i bez srca — ta aktivacija nije cist primer).
6. **Druga boja srca (`color2`) NIJE nađena pravilom**: u 30 uparivih srca
   `color2` je u {3,5,6,7} i nikad 2 (crvena) ni 4 (plava); pravila
   `global_most` 5/30, `global_least` 7/30, `below` 4/30, `plus_most` 1/30.
   To izgleda kao izvlacenje iz skupa od cetiri boje, ne kao deterministicki
   izbor.
7. **Izbor cilja nije deterministicki**: 4 seme RNG-a probane na stvarnom
   `EngineRNG` iz snimka (indeks u listi kandidata, indeks u svim poljima uz
   retry, `Range(0,n)` x2 uz retry, `shuffled` pa prvi validni) — **0/14**
   aktivacija se poklopilo u sva tri cilja. Znaci da `Use` pre izbora trosi
   izvlacenja koja jos ne znamo (varijanta, `Chance`), ili je skup/redosled
   kandidata drugaciji od `CanBeTarget` aproksimacije.

### Sta ostaje (blokira tacan port)

> Tekst ispod je rekonstruisan 2026-11-20: skript za ubacivanje sekcije El
> Magneto pogodio je ovo `### Sta ostaje` i prepisao sve do
> `## Monkey JooJoo (40)`, pa je originalni spisak izgubljen. Cinjenice su iz
> onoga sto je ostalo u dokumentu, iz `tools/vinnie_se_check.py`,
> `vinnie_se_probe.txt`, `vinnie_se_rng_probe.txt` i `Debug/reverse/cupid2/`.

1. **Port nije napisan**: `engine_cupid.py` ne postoji (`engine_cupid_powerup.py`
   je varijanta sa powerup-om). `tools/vinnie_se_check.py` zato stampa
   "PORT NIJE NAPISAN" i proverava samo invarijante (3 cilja, obicna plocica van
   ivice, boja srca = boja cilja, +15 poena).
2. **Izbor cilja nije deterministicki**: 24 hipoteze (redosled `row`/`col`/
   `rowrev` x `allowBlue` x izvlacenje `range`/`next`/`shuffle`/`poprandom`) na
   stvarnom `EngineRNG`-u iz snimka daju **0/14** (`vinnie_se_rng_probe.txt`).
   `vinnie_se_probe.txt` daje rangove ciljeva po redu i koloni za svaku
   aktivaciju, pa sledeci pokusaj treba vezati za te rangove (npr. najveci ili
   najmanji rank) umesto za sirove pozicije.
3. **Druga boja srca (`color2`) nije nađena pravilom**: u 30 uparivih srca
   `color2` je u {3,5,6,7} i nikad 2 (crvena) ni 4 (plava); pravila
   `global_most` 5/30, `global_least` 7/30, `below` 4/30, `plus_most` 1/30 —
   izgleda kao izvlacenje iz skupa od cetiri boje.
4. **`ArrangeTargetOptions` varijante nije procitan**: `Cupid::Use` zove
   virtuelni `variant.ArrangeTargetOptions(...)`; `CupidDefaultVariant` u indeksu
   ima samo `.ctor` (sve nasledjuje), pa treba proci kroz baznu klasu i videti
   sta radi sa listom kandidata pre nego sto se prvi uzme.
5. **`CanBeConverted` grana i matchable target**: korak 7 `Cupid::Use`
   (konverzija svake celije oblasti u boju targeta, uz poseban tretman matchable
   targeta, `FUN_05a2e554`) nije preveden u pravilo — bez toga se ne zna da li
   srce menja boju polja na koje padne.
6. **Punjenje metra**: 13 od 14 aktivacija prazni metar, 016 ostaje na 6 (uz +8
   i bez ijednog srca) — treba videti da li to dolazi od
   `energyTileWeightChangeOnActivationSinglePlayer` ili od same `Use`.
7. **Poeni**: +15 u 10 od 14; +16 (014), +18 (025), +8 (016) dolaze od dodatnih
   kaskada, pa port mora da reprodukuje kaskadu, ne samo 15 unistenih polja.

## El Magneto (buster 33)

`Match3Engine.ElMagneto` (SE je `ElMagnetoSE`, 48, samo `.ctor` — sve nasledjuje).
Adrese za `Debug/reverse/libil2cpp.so`; listing sa imenovanim pozivima:
`python tools/il2cpp_disasm.py --method "ElMagneto::Use" --out Debug/reverse/magneto_named`
(isto za `MakeColorSwaps`, `GetAllSlotColorCombinations`, `Combinations`,
`Participate`, `ElMagnetoConvertData::RecordSwitch`).

### Polja (offsets u objektu)

| offset | polje | u snimku |
|---|---|---|
| 0x44 | `aiLevel` (float) | 0.5 |
| 0x48 | `maxColorPaths` | 5 |
| 0x4c | `magnetCount` | 3 |
| 0x50 | `pickHighestChance` | -1 |
| 0x54 | `pickLowestChance` | -1 |
| 0x58 | `pickRandomlyChance` | 20 |
| 0x5c | `useAI` | False |
| 0x60 | `pickBehavior` (string) | "score" |
| 0x68 | `currentConvertData` | — |
| 0x78 | `magnets` (List<Point>) | — |
| 0x80 | `colors` (List<SlotColor>) | — |
| 0x88 | `dynamicallyCreateColorPaths` | True |
| 0x8c | `chanceToPickRed` | 25 |
| 0x90 | `chanceToPickBlue` | 35 |
| 0x94 | `colorPathsAmountToScan` | 5 |

Server salje i `scoreTarget = 1`, `specialPieceScoreValue = 3`; mod daje
`rules.boosterScoreTargetFactor = 1` (Super Sized Solo).

### `Use` 0x5a3c63c — redosled

1. `BoardModel.GetAvailableColorsOnBoard` -> `avail`; `m = Min(magnetCount, avail.Count)` (=3).
2. `GetAllSlotColorCombinations(this, m, avail)` -> `List<List<SlotColor>>`
   (kombinacije boja za `m` magneta).
3. **Dva izvlacenja `Chance`, oba uvek:**
   * `Chance(chanceToPickBlue)` (35) — ako polje igraca (SlotType) postoji na
     tabli; filtrira kombinacije: jedna grana trazi one koje sadrze tu boju,
     druga one koje je ne sadrze;
   * `Chance(chanceToPickRed)` (25) — isto za **suprotnu** boju: ako je boja
     igraca 4 uzima se 2, inace 4 (`csel` u 0x5a3ec58..0x5a3ec68).
4. Ako posle filtera ostane tacno jedna kombinacija: `maxColorPaths` puta se
   ta lista boja ponovo mesa (`Shuffle`) — tako nastaje do 5 varijanti.
5. `Shuffle(kombinacije)` -> `Take(maxColorPaths)` -> `ToList`, pa jos jedan
   `Shuffle` -> `Take(MaxColorPaths, Count)` -> `ToList`: **dva mesanja**,
   kandidat-liste boja.
6. Magnet-liste: druga lista (`x24`) se puni `Take(maxColorPaths)` rezultatom
   (ili `Enumerable.Repeat(avail, m)` kad je lista boja prazna) — **tacno
   poreklo pozicija magneta iz ove liste jos nije procitano** (vidi "ostaje").
7. Proizvod: za svaku listu boja x svaku listu magneta
   `new ElMagnetoColorAndMagnetPath(colors, magnets)`.
8. Za svakog kandidata: `GameLogic.Clone`, `MakeColorSwaps(clone, path,
   isSimulate=true, magnetIndex=0, null)`, `value = clone.CurrentPlayer.Score -
   player.Score`. `useAI == false` (nas slucaj) dodaje jos i virtuelnu ocenu
   same sposobnosti (`blr` na slot 0x218 sa `(this, clone)`) — **nije procitana**.
   `useAI == true` umesto toga pravi `AIAnalyzer(aiLevel, player, clone, 3)` sa
   `SetSeed(clone.RNG.counter)`, `SetTestMode(1)`, `CalculateNextMove(1)`.
9. Izbor (`pickBehavior` je sa servera, "score" — nije `null`, pa se grana sa
   `RandomWrapper(counter)` i `Chance(pickRandomlyChance/pickHighest/
   pickLowest)` **preskace**; ta grana se vrti samo kad je `pickBehavior` null):
   * "score": kandidati se obilaze redom; **prvi** sa
     `|value - scoreTarget| < Round(5 * boosterScoreTargetFactor)` pobedjuje
     (ovde: prag 5, cilj 1 -> prvi sa 0..5 poena); ako nijedan, uzima se
     najblizi cilju (`OrderBy(...).First()`);
   * "lowest"/ostalo: `OrderBy` po vrednosti pa `First`.
10. `ability.magnets`, `ability.colors` = izabrana putanja; onda
    `MakeColorSwaps(this, logic, izabrana, isSimulate=false, 0, null)` na
    pravoj tabli. Posle toga tabla se resava kao obican potez (spojevi,
    kaskade, dopuna) — buster ne brise nista direktno.

### `MakeColorSwaps` 0x5a3ff08 — pomera komade ka magnetu

`(GameLogic logic, ElMagnetoColorAndMagnetPath camp, bool isSimulate, int magnetIndex,
List<Point> magnitiedPositions)`. Za `magnetIndex < Min(colors.Count, magnets.Count)`:

* pravci `[(0,1), (0,-1), (1,0), (-1,0)]` (dole, gore, desno, levo);
* novo `ElMagnetoConvertData(colors[magnetIndex], magnets[magnetIndex])` u
  `ability.currentConvertData`;
* za svaki pravac se od magneta hoda **do izabrane daleke tacke** i to korak po
  korak: pomeraj je `(sign(dx), 0)`, `(0, sign(dy))` ili `(sign(dx), sign(dy))`
  (dijagonala), gde je `(dx, dy)` vektor od magneta do daleke tacke; kad je
  `|dy| > 0` i `|dx| > 0` koristi se `Fix64` kolicnik `dy/dx` i `Round` da se
  odredi koji korak je na pravoj (`Point::CubedDistanceTo` bira daleku tacku);
* svaki korak: `BoardModel.Swap(trenutno, sledece)` — **linija se pomera za
  jedno mesto ka magnetu**, a komad koji je bio na magnetu zavrsi na dalekom
  kraju; uslov je `slot.canBeMatched` (0x24) na sledecem polju, a polja iz
  `magnitiedPositions` se preskacu;
* svaki swap se belezi: `ConvertSlotModel` za oba polja (redom: polje blize
  magnetu pa dalje) i, kad `isSimulate == false`,
  `ElMagnetoConvertData.RecordSwitch(magnetIndex, from, to)`.

`Participate` (0x5a411b4) = u tabli && `valueType != 16` (BoardSpecial) &&
`hitPoints == 1` (0x20) && `canBeMatched` (0x24) — isto kao Foxy Roxy.

### Sta je izmereno na snimcima

`Debug/research/20261120_120724_super-sized` (Super Sized, `pvpMode 1`, 8x8,
33 snimka): **9 upotrebljivih aktivacija** (002->003, 006->007, 010->011,
013->014, 016->017, 019->020, 022->023, 025->026, 028->029; parovi su kopirani u
`tests/fixtures/el_magneto/20261120_120724_super-sized/`). U svakoj:

* `moves` se **ne menja** (buster ne kosta potez), `energy 7 -> 0` (metar se
  prazni), skor raste za 34-47;
* `energyTileWeightChangeOnActivationSinglePlayer = [0.9]` — tezina energije u
  dopuni se mnozi sa 0.9 i odseca (`simulation.booster_energy_weight`);
* tabla se promeni u 43-58 od 64 polja (pomeranje + kaskade + dopuna), brojevi
  boja ostanu priblizno isti; broj izvlacenja RNG-a po aktivaciji je 277-439;
* posle svake aktivacije na tabli su 3-4 munje (specijal 4) i 1-2 bombe (3).

### Snimak nosi i unutrasnje stanje sposobnosti (2026-11-20)

Najvaznije otkrice ove runde: `profile.ability_detail.fields` u svakom snimku
sadrzi **polja samog objekta** `ElMagneto`/`ElMagnetoSE`, ne samo konfiguraciju:

| polje u snimku | znacenje |
|---|---|
| `<magnets>k__BackingField` | `List<Point>` koje je `Use` izabrao — **redosled je igrin** |
| `<colors>k__BackingField` | `List<SlotColor>` izabrane putanje, `colors[i]` ide uz `magnets[i]` |
| `<currentConvertData>k__BackingField` | `ElMagnetoConvertData` poslednjeg magneta: `<color>`, `<magnet>` i `<sourceToTargetPairs>` — svaki potez koji je `RecordSwitch` zapisao |

To je ground truth i za izbor i za geometriju;
`Debug/reverse/el_magneto2/analyze_magneto.py` ispisuje ga po aktivaciji (tabla
pre, `magnets`, `colors`, parovi, brojevi po linijama svakog magneta).
`tools/booster_inventory.py` daje inventar svih snimljenih aktivacija
(`Debug/booster_inventory.txt`): 33 El Magneto 9, 48 El Magneto SE 12.

Izmereno na 12 aktivacija SE (`20261120_112621_super-sized`) i 9 na 33
(`20261120_120724_super-sized`):

* `magnets` je **uvek 3 od 4 sredine stranica** za 8x8 — nikad ugao, nikad
  centar, nikad obicno polje: `(Columns/2, 0)` = (4,0),
  `(Columns/2, Rows-1)` = (4,7), `(0, Rows/2)` = (0,4),
  `(Columns-1, Rows/2)` = (7,4). Tacno jedna od te cetiri **izostane**, i to
  varira po aktivaciji (znaci `Shuffle` pa `Take(magnetCount)` nad listom od 4
  tacke, ne izbor 3 od 4 po nekom pravilu). Koordinate se u kodu racunaju kao
  `x >> 1` (`Point::.ctor` sa `iVar11 >> 1`).

  Snimljeno na 9 aktivacija 33 (redosled je redosled u `ability.magnets`,
  `rng` je `before_rng_counter -> use_rng_after` iz `swap_trace`):

  | akt. | magnets | izostao | colors | rng |
  |---|---|---|---|---|
  | 002->003 | (4,0),(4,7),(0,4) | (7,4) | 4,6,7 | 308->325 |
  | 006->007 | (4,0),(0,4),(4,7) | (7,4) | 6,7,3 | 1256->1270 |
  | 010->011 | (7,4),(4,7),(0,4) | (4,0) | 3,5,6 | 2175->2189 |
  | 013->014 | (4,7),(7,4),(4,0) | (0,4) | 2,7,3 | 2903->2920 |
  | 016->017 | (7,4),(4,7),(4,0) | (0,4) | 5,6,4 | 3598->3615 |
  | 019->020 | (4,7),(4,0),(7,4) | (0,4) | 7,3,4 | 4721->4738 |
  | 022->023 | (4,0),(0,4),(4,7) | (7,4) | 3,6,7 | 5516->5530 |
  | 025->026 | (7,4),(4,7),(0,4) | (4,0) | 7,3,5 | 6518->6532 |
  | 028->029 | (4,0),(0,4),(4,7) | (7,4) | 6,5,3 | 7415->7429 |

  `colors` takodje ima uvek **3** clana (isto `m`), pa je `Take` u koraku 6
  ogranicen brojem magneta, ne samo `maxColorPaths` (=5).
* `colors` je za SE u 11 od 12 aktivacija **tacno skup dostupnih boja bez
  igraceve i "crvene"**: sve boje na tabli (6) bez `SlotType` igraca (4) i bez
  drugog od {2,4} (2) — dakle `{3,5,6,7}` u SlotColor brojevima. Prva
  aktivacija sesije (`003 -> 004`) je izuzetak: `{2,5,6,3}` (sadrzi 2, nema 7),
  pa tu grana sa `Chance` ocigledno radi drugacije — proveriti pri portu.
* `currentConvertData` je uvek **poslednji** magnet (`isLast == true`), a
  `<sourceToTargetPairs>` za njega ima 17-30 parova; skup polja "od" i skup
  polja "ka" su **isti skup** (permutacija), sto potvrdjuje da `MakeColorSwaps`
  pomera nizove komada, a ne pojedinacne komade.

### `Use` — prosireno citanje (2026-11-20, `Debug/reverse/el_magneto2/useC.c`)

Pseudokod je iz `DecompileMagneto5.java` (vidi "Kako je ovo dekompilirano").
`param_1` je `this` (ElMagneto), `param_2` je `GameLogic`.

1. `*(int*)(this+0x40) = *(int*)(this+0x4c)` — `magnetCount` se kopira u polje
   `Ability`-ja na 0x40.
2. `avail = board.GetAvailableColorsOnBoard()`; `m = Math.Min(magnetCount, avail.Count)`.
3. `combos = GetAllSlotColorCombinations(this, m, avail)` — **sve kombinacije od
   `m` boja** iz `avail`, redom iz iteratora `Combinations(m, n)`; 6 boja i m=4
   daje 15 kombinacija.
4. `blue = logic.CurrentPlayer.SlotType`; `red = logic.Opponent?.SlotType ??
   (blue == 4 ? 2 : 4)`; obe se upisuju u closure (`+0x10`, `+0x11`).
5. Dve grane sa `Chance` (uslov je `-2 < chanceToPickBlue`, odnosno
   `-2 < chanceToPickRed`, dakle **i -1 ulazi u granu**; `Chance` se izvrsava i
   vraca false, trosi jedno izvlacenje):
   * plava: `Chance(chanceToPickBlue)` bira kombinacije koje sadrze plavu
     (`b__4` = `!c.Contains(blue)`, `b__5` = `c.Contains(blue)`);
   * crvena: isto sa `chanceToPickRed` (`b__6`, `b__7`);
   * `b__8`/`b__10` (`colors => lista.Any(c => colors.Contains(c))`) filtriraju
     po listi boja kljuceva (`b__9`/`b__11` = `c => lista.Contains(c)`).
6. Kombinacije se mesa i skracuju: `Shuffle`, `Take(Math.Min(maxColorPaths,
   count))`, `ToList`, pa jos jednom `Shuffle`/`Take` (dva mesanja — isto kao u
   prethodnoj rundi za buster 33).
7. Magnet-liste se prave od sredina stranica (gore). **Gde tacno u kodu
   (ARM64 listing, `Debug/reverse/magneto_named/`):**

   * 0x5a3dcb8..0x5a3e994 — lista `Point`-ova (`x26` od 0x5a3e1a8) se puni
     iskljucivo iz dimenzija table (`BoardModel` +0x38 = visina, +0x3c =
     sirina): `(W/2, 0)`, `(W/2, H-1)`, `(0, H/2)`, `(W-1, H/2)` — cetiri
     sredine stranica, **bez RNG-a**;
   * 0x5a3f0c0..0x5a3f11c — `0x3c13d70(lista, logic.RNG)` pa `Take(m)`
     (`0x3d4900c`, `m` iz `Min(magnetCount, avail.Count)`) pa `ToList`
     (`0x3d4f1fc`) -> `x22`;
   * 0x5a3f12c..0x5a3f1a8 — `x24 = new List<List<Point>>` i u nju se dodaje
     **tacno jedan** element, taj `x22`; sve kandidat-putanje dele isti izbor
     magneta (nema izbora magneta po kombinaciji boja);
   * `0x3c13d70` je isti helper kao `0x3c13b80` kojim se mesa lista kombinacija
     boja (0x5a3f1cc), samo instanciran za `Point` — genericki kod se instancira
     po tipu, zato razlicita adresa. Obe vracaju **slucajno permutovanu** listu.

   Grana `magnetCount == 3` (buster 33) uzima prvih `m` = 3 posle mesanja, SE
   grana (`magnetCount != 3`) pravi svoje. Svaka lista se pakuje u
   `ElMagnetoColorAndMagnetPath(colors, magnets)`.
8. Za svakog kandidata: `clone = GameLogic.Clone`,
   `MakeColorSwaps(this, clone, path, isSimulate=true, 0, null)` (samo **prvi**
   magnet!), pa `value` = razlika skora klona i igraca **plus** virtuelna ocena
   sposobnosti (vtable slot 0x218 = `Ability::GetSpecialsLeftScore(GameLogic)`,
   0x5d7f2ec — `specialPieceScoreValue` po specijalu koji ostane). Sve u
   `Dictionary<ElMagnetoColorAndMagnetPath, float>` (closure `+0x10`);
   `b__0`/`b__1` su `k => dict[k]`, `b__2` je `k => Math.Abs(dict[k] - scoreTarget)`.
9. Izbor: `pickBehavior` nije null ("highest" za SE, "score" za 33) pa se grana
   sa `RandomWrapper(counter)` i `pickHighest/Lowest/RandomlyChance`
   **preskace**; zatim `OrderByDescending(b__0)` za "highest", `OrderBy(b__1)`
   za "lowest", `OrderBy(b__2).First()` za "score" — uz proveru praga
   `|value - scoreTarget| < Round(5 * faktor)` koja prekida obilazak na prvom
   kandidatu u toleranciji.
10. `this.colors`/`this.magnets` = pobednik, pa `MakeColorSwaps(this, logic,
    izabrana, isSimulate=false, 0, null)` na pravoj tabli. Ta funkcija se
    **rekurzivno** nastavlja na sledeci magnet kroz `b__2`
    (`MakeColorSwaps(..., magnetIndex + 1, magnitied)`) i na kraju zove
    `GameLogic.ConvertSlots` sa `isLast`.

### `MakeColorSwaps` — tacna geometrija (potvrdjena parovima iz snimka)

Za `magnetIndex` koji postoji u `colors` i `magnets`:

1. `dirs = [(0,1), (0,-1), (1,0), (-1,0)]`;
   `data = new ElMagnetoConvertData(colors[i], magnets[i])`.
2. `matched = board.Where(b__0).OrderBy(b__1)`, `b__0` =
   `slot.canBeMatched && slot.MatchesWithColor(color)` (`MatchesWithColor`
   0x59e5ec8: `IsPieceWithColor`, boja nije 0/1, `color == c || c == 12 || color2 == c`),
   `b__1` = `p => p.CubedDistanceTo(magnet)` = `dx*dx + dy*dy` (0x59326e4).
   `OrderBy` je stabilan, osnovni redosled je redosled table.
3. Susedi magneta: ako polje magneta moze u matcheve i nije u
   `magnitiedPositions`, dodaje se **sam magnet** (prvi komad ide u polje
   magneta); inace se za svaki pravac uzima `magnet + dir` koje je u tabli,
   `canBeMatched` i nije u `magnitiedPositions`.
4. Za svaki `matched` komad redom: `target` = sused sa **najmanjim
   `CubedDistanceTo(magnet)`**, medju njima onaj najblizi komadu
   (`OrderBy(b__5)` = rastojanje do komada, `Where(b__4)` = rastojanje do
   magneta jednako najmanjem). Komad se **hoda ka `target` korak po korak** i
   svaki korak je `BoardModel.Swap(trenutno, sledece)`; smer koraka je
   `(sign(dx),0)` ili `(0,sign(dy))`, a na dijagonali se `Fix64` kolicnikom
   `dy/dx` i `Round`-om bira koji je korak na pravoj.

   **Dokle ide hod:** ne do kraja table i ne fiksno — od **komada** (`P`) do
   `target`-a, tj. `|P - magnet| - 1` zamena; petlja je `while P != target`
   (0x5a408f4..0x5a40c7c: `op_Inequality(P, target)` pa `P = next`). Prekid pre
   toga nastupa samo ako `next` izadje iz table, ako `slot.canBeMatched` (0x24)
   nije zadovoljen, ili ako je `next` vec u `magnitiedPositions`
   (0x5a40a90..0x5a40aa8). Kad hod stigne do `target`-a (0x5a40c88), `target` i
   njegova 4 suseda se upisuju u `magnitiedPositions`, pa se susedi grade
   ponovo — zato svaki sledeci komad ide ka drugacijem `target`-u i linije se
   ne gaze. `CubedDistanceTo` se u celom metodu poziva samo jednom u toj petlji
   (0x5a407b8), za distancu `prvi-sused <-> komad`, a ne za biranje daleke
   tacke.
5. Posle hoda: `neighbours.Remove(target)`, `magnitiedPositions.Add(target)`, pa
   se lista suseda ponovo gradi (`canBeMatched`, nije u susedima ni u
   `magnitiedPositions`).
6. Swapovi se beleze: dva `ConvertSlotModel`-a (komad -> novo polje i obrnuto,
   vrednost 3) i `RecordSwitch(magnetIndex, od, na)` kad `isSimulate == false`.
7. Na kraju: `isLast = magnetIndex + 1 >= magnets.Count || magnetIndex + 1 >=
   colors.Count`, `logic.ConvertSlots(new ConversionModel(data, 0, isSimulate,
   this), isLast)` — spojevi i kaskade idu tek posle toga, kao obican potez.

### Kako je ovo dekompilirano (REA -> Ghidra, 2026-11-20)

REA MCP alati nisu bili dostupni u sesiji, a `rea decompile` odbija ARM64 ELF na
Windowsu (`provider ghidra -> target_format_unsupported`, Ghidra P0 primа samo
PE). Ghidra 12.1.4 radi direktno, kroz `analyzeHeadless.bat`:

```
analyzeHeadless.bat Debug/reverse/ghidra_proj magnetoB -import Debug/reverse/libil2cpp.so \
  -noanalysis -scriptPath Debug/reverse/el_magneto2 \
  -postScript DecompileMagneto5.java <izlazni .c>
```

Izlaz ove runde: `Debug/reverse/el_magneto2/magnetoB.c` (sirovi pseudokod) i
`useC.c` (bez inicijalizacije klasa).

`DecompileMagneto5.java` resava tri stvari bez kojih je pseudokod besmislen:

* **image base je 0x100000** — RVA iz indeksa se mapira kao `imageBase + rva`
  (`toAddr` bez toga dekompajluje funkciju na pogresnom mestu i vrati 6 linija);
* telo funkcije se zadaje eksplicitno (`AddressSet`, velicine iz
  `data/il2cpp_symbols.json`) jer import bez analize ne zna granice;
* za svaki `bl` cilj unutar tela pravi se funkcija — inace dekompajler prijavi
  "Possible PIC construction ... changing call to branch", proglasi ostatak
  nedostiznim i vrati samo prolog (tako su propale prve tri runde).

Imena za `FUN_xxxxxxxx` daje `data/il2cpp_symbols.json` (klase -> metode ->
`rva`); `data/il2cpp_method_index.json` je iz **druge** verzije igre (npr.
`Ability::Use` je tamo 0x5d7ef9c, u ovom `.so` 0x5902ee8), zato `bl` imena u
`tools/il2cpp_disasm.py` listinzima cesto ostaju prazna.

### Sta ostaje (blokira tacan port)

1. Tacan broj i redosled kandidata: dva `Shuffle`-a u koraku 6 `Use` (koliko
   izvlacenja trosi svaki). Redosled magneta je resen (jedno mesanje 4 sredine
   stranica pa `Take(3)`; vidi tabelu iznad — izmereni RNG skok po aktivaciji je
   14 ili 17, pa se broj izvlacenja po mesanju mora poklopiti sa tim).
2. Zasto prva aktivacija (`003 -> 004`) ima `colors` sa bojom 2 (a bez 7) —
   jedina od 12 koja ne prati "sve boje bez plave i crvene".
3. `GetSpecialsLeftScore` (0x5d7f2ec) — da li ulazi u `value` i sa kojim znakom
   (`specialPieceScoreValue` = 30 za SE).
4. `GetAllSlotColorCombinations` 0x5a3fa5c — tacan redosled kombinacija
   (`Combinations(m, n)` iterator), iako je skup poznat.
5. Rekurzivni nastavak `MakeColorSwaps` kroz `b__2` — da li `ConvertSlots` ide
   jednom na kraju ili posle svakog magneta (proveriti na RNG brojacu).

Do tada El Magneto **ne ulazi** u `EXACT_PLAN_BOOSTERS` ni u `BOOSTER_NAMES`
(pogresan plan je gori od "nepoznato"). Sledeci korak je `engine_magneto.py`
(`make_color_swaps` po gornjoj geometriji) i `tools/magneto_check.py` nad 12
aktivacija SE; cim se poklope tabla, RNG brojac i poeni, buster ulazi u
`simulation.py` i u `EXACT_PLAN_BOOSTERS`.

### Merenje porta 2026-11-20 (`engine_magneto.py`, `tools/magneto_check.py`)

> Sekcija `Sta ostaje` iznad je pisana pre porta; `engine_magneto.py`, hook u
> `simulation.py` i `tools/magneto_check.py` postoje od 2026-11-20.

Port je napisan po gornjoj geometriji (`engine_magneto.make_color_swaps`) i
zakacen u `strategy_lab/simulation.py` iza `EL_MAGNETO_SE_PORTED = False`, pa
planer ne planira sa njim dok se ne poklopi. `python tools/magneto_check.py`
pusta svaku snimljenu aktivaciju kroz simulator 1:1 i poredi tablu, specijale,
RNG brojac, poene i metar; `--captured` umesto izbora iz koda koristi putanju
koju je igra zapisala (`<magnets>` + `<colors>`), pa meri samo geometriju.

Rezultat: **0 od 12** u oba rezima (`magneto_check.txt` u folderu fixtures).
Portova aktivacija je **premala**: 3-12 `Swap`-ova po aktivaciji prema 17-30
parova u `<sourceToTargetPairs>`, a tabla posle porta ima 0-2 trojke, dok
aktivacija u igri donosi 50-60 poena i 3-4 munje + 1-2 bombe (dakle mnogo
istovremenih spojeva). RNG brojac staje 330-460 izvlacenja pre igre.

Znaci: pravilo "komad ide na najblize slobodno susedno polje magneta, pa to
polje ulazi u `magnitiedPositions`" nije ono sto `MakeColorSwaps` radi — ono
pomera **mnogo vise** komada po magnetu (verovatno celu liniju, a ne po jedan
komad na suseda). Sledeci korak je ponovno citanje `MakeColorSwaps` u
`Debug/reverse/el_magneto2/useC.c` sa `<sourceToTargetPairs>` kao oracle-om
(tacno se zna koji komad je odakle otisao gde), a ne izvodjenje pravila iz
zbirnog opisa. Do tada El Magneto ostaje van `EXACT_PLAN_BOOSTERS`.

## Monkey JooJoo (40): prvo razilazenje kaskade (2026-11-20, 002 -> 003)

### Ispravljena greska: vrednost specijala lobanje

`engine_monkey.place_skulls` je pisao **engine** vrednost `24` u simulacionu
tablu specijala. Tamo je lobanja `move_strategy.SPECIAL_JOOJOO_SKULL = 19`
(`engine_refill.SIM_JOOJOO_SKULL`). Posledice su bile dve:

* refill je na 4 od 5 kandidata bacao `Unported simulator special/color in
  refill board` (`engine_refill.fill_simulator_board`);
* kad nije bacio, prezivela lobanja bacanja je bila **inertna** — nije
  eksplodirala duz svoje boje kad je unistena (`_clear_cells_with_specials`
  je ne prepoznaje kao specijal 19).

Sada `place_skulls` pise `SIM_SKULL = 19`, a `explode_cells` prihvata obe
vrednosti (`SKULL_VALUES`). Merenje posle ispravke
(`tools/monkey_check.py Debug/research/20261120_111530_super-sized`):

| aktivacija | tabla pre | tabla posle | specijali pre/posle | rng igra/sim | poeni igra/sim |
|---|---:|---:|---|---|---|
| 002->003 | 55 | 31 | 11 / 8 | 1194 / 1205 | 37 / 37 |
| 008->009 | 46 | 38 | 17 / 11 | 4143 / 4129 | 49 / 47 |
| 011->012 | 49 | 41 | 14 / 13 | 6613 / 6605 | 48 / 48 |
| 025->026 | 45 | 45 | 23 / 23 | 14494 / 14478 | 56 / 56 |

Poeni se sada poklapaju u 4 od 12 aktivacija (002, 011, 015, 025), ali tacnih
je i dalje **0 od 12**.

### Gde se tacno razilazi (alat `tools/monkey_trace.py`)

Alat hvata unistena polja po kaskadi (monkeypatch preko
`_clear_cells_with_specials` / `_clear_matches_with_details`) i poredi ih sa
poljima koja je igra promenila izmedju dva snimka (polje koje igra dopuni
zadrzi istu kocku ~1/8, a kroz ~5 kaskada skoro nikad).

1. **RNG pre aktivacije se poklapa** u svim proverenim snimcima (002: 663,
   006: 1515, 008: 3523, 011: 6007). Razilazenje nije u prethodnom potezu i
   nije u broju izvlacenja do pocetka bacanja.
2. U **kaskadi 1** svi kandidati unistavaju polja koja igra nije dirala
   (prvi promanjeni: kandidat 0/1 polje (1,7), 2 -> (0,2), 3 -> (4,2),
   4 -> (3,3)). Igranih promenjenih polja je 47, a simulator unisti 30-46 —
   dakle skup unistenih polja nije isti ni po velicini.
3. Prezivela lobanja bacanja (jedna od 4, jer `autoExplodeAmount` 3 unisti
   prve tri) **ne pada na igrino mesto**: od 5 izvucenih kandidata samo
   kandidat 3 ima prezivelu lobanju na polju gde igra ima lobanju ((4,5)), a
   njega obaraju dva njegova unistena polja ((0,2), (3,3)) koja igra nije
   dirala.

Zakljucak: kaskada (refill, pad, lancane eksplozije) radi kao i za ostale
bustere; **razilazi se izbor bacenih polja**, a verovatno i oblast eksplozije
lobanje. Posto je RNG na ulazu tacan, izbor polja je jedina nepoznanica.

### Sta jos treba procitati

1. `Match3Engine.BoardModel::GetSlotPrioritize` 0x5972158 — pravi listu
   kandidata sam, u **dva prolaza** (`Where` delegati 0x70973f0 / 0x70973f8 i
   0x7097418 / 0x7097400 iz `_c_ChoosePositions_b__13_*`), sa `w2 = count`,
   i vraca dodatu listu koju `ChoosePositions` oduzima od preostalog broja
   (`sub w21, w21, w9` na 0x5a7bd74/0x5a7be78). Moj port uzima "jedan
   `shuffled` cele liste obicnih polja po pokusaju" — to je drugacija
   konstrukcija i drugaciji broj izvlacenja.
2. `Match3Engine.BoardAnalyzer::GetPossibleMoves` — grana
   `RandomWrapper::Chance(chanceToPickMatchablePiece)` (0x5a7bb14: `tbz w22,
   #0` je `useChanceToPickMatchablePiece`; za aktivaciju je false, ali
   `GetPossibleMoves` se zove i u drugim granama).
3. `RandomWrapper::Chance` i `MonkeyJoojoo._c_ChoosePositions_b__13_2` /
   `b__13_6` / `b__13_8` (96-121 B) — koje polje se smatra "matchable".
4. Tek posle toga `MonkeyJoojoo._c_ConvertToSpecialsAndAutoExplode_b__12_1`
   (koja polja se odmah unistavaju i kojim redom).

Port ostaje iza `simulation.MONKEY_JOOJOO_PORTED = False`; 0 od 12 tacnih.

### `BoardModel::GetSlotPrioritize` 0x5972158 — procitan (2026-11-20)

Potpis: `GetSlotPrioritize(RandomWrapper random, int amount, Func<int,int,bool>
prioritize, Func<int,int,bool> ignore)`. Listing:
`Debug/reverse/foxy/Match3Engine.BoardModel_GetSlotPrioritize.asm` (isti RVA
0x5972158; `--method` vraca drugi overload na 0x5e0d2d8 — koristiti RVA).

Algoritam:

1. `pass1 = Where(prioritize)` (0x5971578) — polja u redosledu table.
2. Ako `pass1.Count < amount`: `result.AddRange(pass1)` (0x59722ec) i onda
   `pass2 = Where(!ignore)` (0x5972330); inace se `pass2` ne pravi i `pass1`
   ostaje kandidat.
3. `shuffled = Shuffle(kandidat, random)` (0x5972364, `0x3c13d70`) — **jedno
   izvlacenje po polju liste** (izmereno: 40 izvlacenja za N = 40).
4. Ako `result.Count >= amount`, vrati `result`; inace dopuni iz `shuffled`
   uzimanjem sa **pocetka** (0x5972394 petlja, `RemoveAt(0)`).

Dakle: kad prioritetna polja zadovolje `amount`, bacaju se u **redosledu
table** (shuffle se izvrsi, ali se rezultat ne koristi); kad ne zadovolje,
prioritetna polja idu prva u redosledu table, a ostatak je izmesan.

`ChoosePositions` zove ovu funkciju **dva puta** sa dva para delegata
(0x70973f0/0x7097418 i 0x70973f8/0x7097400) i sabira rezultate
(`AddRange` 0x42fc3f8, oduzimanje `sub w21, w21, w9`). Svi delegati
`MonkeyJoojoo._c_ChoosePositions_b__13_1/_5/_7/_9` kompajliraju se u
`mov w0, wzr; ret` — **konstantno false**. Zato je `pass1` uvek prazan i sve
lobanje dolaze iz mesane liste: ponasanje je tacno `shuffled(cells)[:amount]`.

`engine_monkey.get_slot_prioritize` sada verno prati tu strukturu (dva prolaza,
redosled table u prvom, izvlacenje po polju drugog); `draw_candidates` zove
jednom po pokusaju. Merenje posle prepravke (12 aktivacija) je **identicno**
prethodnom (`monkey_final3.txt`): 0/12 tacnih, 002->003 tabla 31, poeni 37/37.

Proverene alternative liste kandidata (N i izvlacenja po pokusaju, 002):
dozvoljene obicne boje x-major N=40 (40), sve obicne x-major N=61 (61),
sve obicne y-major N=61 (61), sva polja N=64 (64). Nijedna ne povecava broj
prezivelih lobanja koje padnu na igrino polje (1/5, 0/5, 0/5, 1/5) — pa lista
ostaje "obicna polja dozvoljenih boja".

### `BoardModel::Where` 0x5971578 (2026-11-20)

`Where(predicate(x, y))` je obican dvostruki prolaz: spoljna petlja je
**Columns** (`[this+0x3c]`, `<Columns>k__BackingField`), unutrasnja **Rows**
(`[this+0x38]`), a predikat se zove kao `predicate(column, row)`
(0x597162c `blr x8`, `w1` = spoljni, `w2` = unutrasnji). Tocka se pravi sa
0x592e0d8. Znaci redosled nabrajanja je **x-major (kolone spolja, redovi
unutra)** i poklapa se sa `engine_monkey.plain_cells` — redosled kandidata nije
problem.

`<>c__DisplayClass133_0::<GetSlotPrioritize>b__0/b__1/b__2` (0x5e14f88,
0x5e14ff4, 0x5e15088) dele jedno telo: granaju se po **tipu vrednosti polja**
(`ushort` na `[slot+0x20]`; vrednosti 0x20, 0x21, 0x22, 0x27, 0x2c, 0x2f, 0x49,
0x5d, 0x66, 0x6e, 0x74, plus 0x0, 0x9, 0xa, 0xd) i zovu helpere
0x5e15b08 / 0x5e14710 / 0x5e158c8. To je familija "koji tip polja se sme uzeti",
ne filtar po boji — pa pravi filtar kandidata treba traziti u tim granama
(mapa vrednosti tipa polja), a ne u delegatima `MonkeyJoojoo._c` (svi false).

## Vinnie SE (47) - Ghidra 12.1.4 prolaz, 2026-11-20 (nastavak)

Ghidra je instalirana na `C:\Users\PC\tools\ghidra_12.1.4_PUBLIC`
(`support/analyzeHeadless.bat`). Dva vazna nalaza o samom alatu:

* ELF import podize image base na `0x100000`, pa se sve RVA iz
  `data/il2cpp_method_index.json` moraju povecati za `0x100000`
  (npr. `Cupid::Use` RVA `0x5a2c5d4` -> Ghidra adresa `0x5b2c5d4`).
  `Debug/reverse/cupid_powerup/base_ranges.txt` je vec u tom pomaku.
* Decompiler puca ("bad instruction data", ili spoji funkciju sa velikim
  blobom) kada se `createFunction` pozove nad opsegom iz skripte
  `DecompileLinear.java`. Ciscenje: svez projekat + raw slice.

Postupak koji radi (`Debug/reverse/cupid_slice`): iseci bajtove
`0x5a2b000..0x5a34000` iz `Debug/reverse/libil2cpp.so` (mapiranje preko
program headers), import kao `BinaryLoader` sa `-loader-baseAddr 0x5a2b000`
i `-processor AARCH64:LE:64:v8A`, pa `DecompileLinear.java` po opsezima.
Tako je `Cupid::Use` dekompajliran cisto (`Debug/reverse/cupid_use/Use.c`,
`Use_named.c`, 59 KB / 1626 linija).

### Sta `Cupid::Use` radi (potvrdjeno iz C koda)

1. `ResolveCupidVariant` -> `param_1[0x17]`; bez powerup-a to je
   `CupidDefaultVariant` (u indeksu ima samo `.ctor`, sve ostalo nasledjuje).
2. `BuildMatchablePositionsFromBoard`.
3. `iStack_1ac < param_1[0xf]` -> `param_1[0xf]` = `piecesPerActivation` = 3;
   svaka iteracija pravi jedno srce.
4. U svakoj iteraciji: `GatherTargetOptions(this, logic, allowBlue, 0)`; ako je
   lista prazna -> `GatherFallbackTargetOptions`; pa `FUN_03d13d70(lista, board)`
   (LINQ nad listom); pa virtualni poziv na varijanti
   `variant.ArrangeTargetOptions(this, logic, lista, matchable, ...)`.
5. Zatim `foreach (target in lista)`: preskace vec iskoriscene
   (`List.Contains`, `HashSet.Contains`), gradi `CupidHeartCreationContext`
   (`FUN_05bc2590`, 9 argumenata: logic, target, activationNumber, heartIndex,
   1, usesTwoColors, isMatchableTarget), racuna `GetExplosionArea`, i
   `HashSet.Add(area)`; petlja se ponavlja dok `Add` ne uspe (oblast se ne
   sme preklopiti sa prethodnim srcem).
6. `CreateHeartPiece(this, area?, target, usesTwoColors, 1, flag)`.
7. Za svaku celiju oblasti: `CanBeConverted(celija, boja targeta)` pa
   konverzija (`FUN_05ae5e54` = `ConvertSlotModel`), uz poseban tretman
   matchable targeta (`func_0x05a2e554`).
8. Na kraju `GetVarietyScore` + `count*` skorovi (`scoreFactor` 0.1 /
   `colorFactor` 0.9) i `Log`.

`GatherTargetOptions` (ASM, 304 B) je samo closure + `BoardModel::ForEach`;
po-celijski test je `Cupid.<>c__DisplayClass38_0::<GatherTargetOptions>b__0`
(RVA `0x5eacee4`) i on dalje skace na `CanBeTarget`.

### Novo merenje (`tools/vinnie_se_probe.py`, `tools/vinnie_se_rng_probe.py`)

* Sva 42 cilja su `value 0` (obicna plocica), nikad specijal; `n_plain` 58-63.
* Ciljevi NISU monotoni po redu skeniranja (row-major ili column-major), a
  rangovi u plain listi su razbacani (9..51) -> izbor nije "prva tri".
* 24 seme izbora (3 reda skeniranja x allowBlue x range/next/shuffle/poprandom,
  sekvencijalno sa uklanjanjem iskoriscene celije, `EngineRNG.from_capture`
  iz stanja pre aktivacije): **0/14** pogodaka u sva tri cilja.

### Zasto jos nema porta

Odluka o cilju je u `ArrangeTargetOptions` varijante, a za
`CupidDefaultVariant` ta metoda nije u indeksu (nasledjuje
`CupidVariantBase::ArrangeTargetOptions`, RVA `0x5f3ac30`, ciji je zapis u
indeksu ocigledno pogresan - 4 bajta). Jedina prava implementacija u kodu je
`CupidSEPowerUpVariant1::ArrangeTargetOptions` (RVA `0x5f34190`, 0x29c B) uz
`PopRandom` (`0x5f34434`) i `SelectCandidate` (`0x5f3a290`) - to je sledeci
korak: dekompajlirati taj opseg iz slice-a `0x5f33000..0x5f3b000` i videti
score/top-range/pop-random redosled, pa tek onda pisati `engine_cupid.py`.
## Vinnie SE (47) - ArrangeTargetOptions razresen, 2026-11-20 (drugi prolaz)

### Paznja: `data/il2cpp_*.json` su osvezeni iz druge verzije igre

U 12:29 su `data/il2cpp_symbols.json` i `data/il2cpp_method_index.json`
regenerisani i sada opisuju **noviju** verziju igre: `Cupid::Use` je tamo
`0x5ea4880`, dok nas `Debug/reverse/libil2cpp.so` (i snimci od 11:50) imaju
`Use` na `0x5a2c5d4`. Stare adrese su sacuvane u
`Debug/reverse/old_method_index.json` (`git show HEAD:data/il2cpp_method_index.json`)
i one vaze za nas `.so`. Provera: kada se sa novim adresama pozove `--rva`,
dobije se kod koji nije pocetak funkcije.

Stare (vazece) RVA za ovaj `.so`:

| metod | RVA |
|---|---|
| `CupidVariantBase::ArrangeTargetOptions` | `0x5ac36c0` (4 B, prazan stub) |
| `CupidSEPowerUpVariant1::ArrangeTargetOptions` | `0x5abcc20` (668 B) |
| `CupidSEPowerUpVariant1::PopRandom` | `0x5abcec4` (180 B) |
| `CupidSEPowerUpVariant1::SelectCandidate` | `0x5ac2d20` (944 B) |
| `Cupid::CanBeTarget` | `0x5a33384` |

### Sta `ArrangeTargetOptions` radi (iz C koda, `0x5abcc20`)

Nije sortiranje po skoru - to je **mesanje liste ponavljanim `PopRandom`**:

1. ako je `options.Count == 0`, `matchablePositions.Count == 0` ili je `logic`
   prazan -> izlazi bez promene;
2. deli `options` u dve liste preko `matchablePositions` (`.Where` +
   `.ToList`), sa `HashSet<Point>` i njegovim komparaterom;
3. `options.Clear()` pa petlja: uzima element iz jedne od dve liste preko
   `PopRandom(list, random)` i dodaje ga u `options`, dok se liste ne isprazne
   (prekid zavisi od `FUN_05bf5c4c(board, ability + 0x18, 0)`);
4. `PopRandom` = `index = random.Range(0, list.Count)`, uzmi i ukloni taj
   element.

`Cupid::Use` posle toga uzima **prvi** element te promesane liste, pa je izbor
cilja = prvi `PopRandom` iz skupa kandidata, a ostatak liste se trosi na
mesanje.

### `CanBeTarget` (0x5a33384) - filter kandidata (delimicno procitan)

Redom odbija celiju ako:

* `Participate(position, logic)` nije tacno;
* `slot + 0x12 != 0` (nije obicna plocica) ili `slot + 0x20 != 1`;
* `FUN_059e593c(slot)` je tacno;
* boja plocice je jednaka boji igracevog piece-a (0x59449bc / 0x59f5b9c) a
  `allowRed` je false -> **plava se nikad ne bira**;
* `FUN_0596f6c4(board, position)` je tacno (kada `ability + 0x82 == 0`);
* boja je jednaka drugoj boji (0x59443d0) a `allowRed` je false;
* na kraju `FUN_05972444(board, position, 0, 1, 0)`.

Tri pomocne funkcije (`0x596f6c4`, `0x59e593c`, `0x59e5ec8`) nisu jos
identifikovane, a one odlucuju koji obicni (ne-plavi) kandidati otpadaju.

### Provera modela na snimcima

`tools/vinnie_se_pop_probe.py` modeluje `Use` + `ArrangeTargetOptions`:
po srcu se uzme `PopRandom` iz skupa obicnih plocica (row/col order,
allowBlue da/ne) i po potrebi se lista do kraja isprazni (`drain`).
Rezultat: **0/14** tacnih sva tri cilja, `first` 1/14 (slucajno).

Dodatno, pomeraj u RNG toku 0..400 ne pomaze: nijedan offset ne daje tacna
sva tri cilja. Znaci model trosenja RNG-a jos nije tacan ili skup kandidata
nije "sve obicne ne-plave plocice" - najverovatnije zbog tri neidentifikovane
provere u `CanBeTarget`.

Zato `engine_cupid.py` nije napisan: izbor cilja nije dovoljno razresen da bi
port bio tacan, a pogadjanje je zabranjeno. Vinnie SE ostaje van
`EXACT_PLAN_BOOSTERS`.

Sledeci korak: dekompajlirati `0x596f6c4`, `0x59e593c`, `0x59e5ec8` i
`FUN_05bf5c4c` iz istog `.so` (slice oko `0x5960000..0x59f0000`), pa zatvoriti
model.

### `SlotModel` polja i zasto dumpovi delegata nisu upotrebljivi (2026-11-20)

`Match3Engine.SlotModel` (iz `data/il2cpp_symbols.json`): `blank` 0x0,
**`color` 0x10**, `color2` 0x11, **`value` 0x12**, `originalValue` 0x13,
`holdValue` 0x14, `relatedPlayerIndex` 0x15, `status` 0x18, `score` 0x1c,
`scoreModifierOrigin` 0x1d, `scoreModifierBonus` 0x1e, `energy` 0x1f,
`hitPoints` 0x20, `damageable` 0x21.

To potvrdjuje ranije citanje: `b__13_0` / `b__13_3` gledaju `[slot+0x12]`
(`value`) i porede sa 24 (`0x18`) — to je lobanja.

Helperi na koje su `DisplayClass133_0` delegati upucivali **nisu** predikati:
`0x5e15b08`, `0x5e14710`, `0x5e158c8` svi pocinju sa
`ldp w9, w8, [x0, #0x88]` / `str wNN, [x0, #0x8c]` i granaju se po stanju
iteratore (0x5e13890, 0x5e13ad8, 0x5e1461c) — to su tela **iteratora /
`<Where>d__*.MoveNext`**, ne `Func<int,int,bool>`. Isto vazi za
`b__0/b__1/b__2` na 0x5e14f88/0x5e14ff4/0x5e15088: `il2cpp_disasm --grep` ih
je mapirao na susedna iterator tela (velicine se preklapaju), pa se iz tih
listinga ne moze procitati filtar.

Zakljucak: pravi RVA delegata treba traziti u punom dumpu simbola
(`tools/il2cpp_symbols_dump.js` / `data/il2cpp_symbols.json`), a ne preko
`--grep`; do tada filtar polja ostaje nepoznat i port se ne menja.
## Vinnie SE (47) - grupisani model i identifikovane provere, 2026-11-20

### Grupisani model (`tools/vinnie_se_pop_probe.py`)

Model sada ima obe grupe: kandidati koji su u `matchablePositions` i ostali,
uz `RandomWrapper.Chance` poziv pre svakog `PopRandom`, redosled row/col,
`allowBlue` da/ne, sa i bez ivice, `chance` -1..99.

Mereno na svih 14 aktivacija: **0/14** tacnih sva tri cilja u svakoj
kombinaciji; prvi cilj tacan najvise 2/14. Grupisani model ne resava stvar.

### Identifikovane provere iz `CanBeTarget`

| RVA | metod | efekat na kandidata |
|---|---|---|
| `0x596f6c4` | `BoardModel::Edge` | odbija ivicnu celiju (`x==0 \|\| y==0 \|\| x==w-1 \|\| y==h-1`) |
| `0x59e593c` | `SlotModel::get_IsLiveEventPieceWorthPoints` | odbija ako je tacno |
| `0x59e5ec8` | `SlotModel::MatchesWithColor` | poredjenje boje plocice sa bojom igraca |
| `0x59449bc` | `GameLogic::get_CurrentOpponent` | boja protivnika (crvena) |
| `0x59443d0` | `GameLogic::get_CurrentPlayer` | boja igraca (plava) |
| `0x59f5b9c` | `PlayerControl::get_SlotType` | vraca boju tog igraca |
| `0x5972444` | `BoardModel::GetPlus` | plus oblik eksplozije (potvrdjeno) |
| `0x5af5c4c` | `RandomWrapper::Chance` | `next() % 100 <= p` |
| `0x5974514` | `BoardModel::ForEach` | prolazi red-major po `width` (0x38) x `height` (0x3c) |

`CupidVariantBase::ArrangeTargetOptions` (`0x5ac36c0`) nije 4-bajtni stub -
pocinje sa `mov x19,x0; bl ...` (index je pogresno prijavio velicinu), pa je
`CupidDefaultVariant` dobija kao pravu implementaciju; njeno telo jos nije
procitano (skok je van slice-a `0x5a2b000..0x5a34000`).

### Filter kandidata je sada potvrdjen na podacima

Za svih **42** cilja: `on_edge=0`, `blue=0`, `not_plain=0`. Znaci cilj je
uvek obicna plocica, van ivice, nikad plava - tacno kako `CanBeTarget` kaze.
Time skup kandidata pada sa 58-63 na **27-32** celije po tabli.

### Sta jos fali

Rangovi ciljeva u tom filtriranom skupu su razbacani (0..28), pa mesanje
postoji, ali nijedna kombinacija (`PopRandom` + `Chance`, obe grupe, oba
redosleda, obe boje, sa/bez ivice) ne daje tacan izbor. Preostalo je:
procitati telo `CupidVariantBase::ArrangeTargetOptions` (skok sa `0x5ac36c0`)
i tacno utvrditi koliko se RNG izvlacenja potrosi pre prvog `PopRandom`.
Tek tada `engine_cupid.py`; do tada Vinnie SE ostaje van `EXACT_PLAN_BOOSTERS`.

### Froggy Fu — RevertLotuses / PickRevertColor (2026-11-20, build 5.900)

`Use` (0x5ec2f18): ako `LotusPositions.Count >= 1` -> `RevertLotuses(logic, cb)` pa
`BeginNewActivation`; inace odmah `BeginNewActivation`. `LotusPositions` = `board.extraData`
(`[board+0x18]`) pod kljucem `get_LotusPositionsKey` (format sa `PlayerControl.Index`),
`DeserializePoints`.

`RevertLotuses` (0x5ec30f4), redom liste:
- preskace tacku van table ili slot cija `value != 40` (lotos);
- `orig = color2 == 1 ? color : color2` (SlotModel +0x11 / +0x10);
- `c = PickRevertColor(logic, p, orig)`; slot: `color = c`, `color2 = 1`, `value = 0`,
  `canBeMatched = (c != 1)`, `movable = 1`, `damageable = 1`, `status &= ~1`,
  `UpdateColorBasedAttributes`, `set_Item` ODMAH (kasniji lotosi vide nove boje suseda);
- `LotusPositions = []`; ako ima konverzija: `ConvertSlots(ConversionModel(list, 1, 63, cb))`,
  bez DestroyMatches i bez refila u samom RevertLotuses.

`PickRevertColor` (0x5eccb7c):
    if orig in {0, 1, 12}: return orig
    colors = spawningEngine.gameColors (GameLogic+0x60 -> +0x18); prazno -> orig
    neigh = boje 4 ortogonalna suseda (IsPointInBound), bez {0, 1, 12}
    if orig not in neigh: return orig            # bez RNG-a
    cand = [c for c in colors if c not in neigh] # predikat b__0 0x5ecec78 = !neigh.Contains
    if not cand: return orig
    return cand[rng.Range(0, len(cand))]         # 0x3f40af8: JEDNO RandomWrapper::Range

`RevertStamppedSlots` (0x5ec5a10): svaki `IsFroggyFuStampedSlot` slot:
`score = SubtractScoreBonus(score, scoreModifierBonus)`, `scoreModifierOrigin = scoreModifierBonus = 0`,
pa uvek `ConvertSlots(..., 1, 63, cb)`. Odakle se zove: nije procitano.
