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
| 7 Fireworks | botov Lightning | `GetFireworks(12)`: 12 polja, prvo damageable, bez vec unistenih | bilo 13 -> **12** |
| 8 Crosshair | crosshair | `GetCrosshair`, broj iz konfiguracije (string) | 6, izmereno |
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
