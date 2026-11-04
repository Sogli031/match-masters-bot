# Modovi procitani iz koda (IL2CPP), 2026-08-21

Do sada je `docs/game_mode_rules.md` opisivao modove iz **konfiguracije**
(`matchRules`, `BoardModelName`, dekompajlirani potpisi bez tela metoda) i iz
**posmatranja** (snimci table pre/posle poteza). Ovaj dokument je prvi koji
opisuje modove iz **koda koji se stvarno izvrsava**: `data/il2cpp_symbols.json`
(klase, polja, RVA) + `tools/il2cpp_disasm.py` nad `Debug/reverse/libil2cpp.so`.

Sve u ovom dokumentu je offline nalaz. Igra ne mora da radi.

## 1. Kako se cita board klasa

`Match3Engine.BoardModel` ima 104 metode. Mod je klasa koja nasledjuje
`BoardModel` i pregazi nekoliko njih. **Koju metodu je pregazila govori kada
pravilo pali** — to je najvazniji nalaz ovog prolaza, jer je bot do sada tu
granicu pogadjao iz snimaka:

| hook | kada se zove | posledica za simulator |
| --- | --- | --- |
| `AfterPerformedSwap(logic, combos[, mergeSwapData])` | **jednom po igracevom potezu**, na mecevima koje je napravila zamena | efekat vazi samo za prvu kaskadu |
| `OnAfterPerformedSwap(..., mergeSwapCondition)` | isto, zajednicka implementacija koju zovu obe preklopljene verzije | isto |
| `BeforeCombosDestroy(logic, combos, ref deferFall)` | **na svakom koraku rusenja**, tj. i na svakoj kaskadi | efekat vazi kroz celu kaskadu |
| `onMoveStart` / `onMoveEnd` | pocetak/kraj poteza | stanje se menja izmedju poteza |
| `onTurnStart` / `onGameStart` | pocetak runde / partije | dopuna plocica, reset brojaca |
| `Fill` / `RefillSlots` | inicijalno punjenje / dopuna posle pada | koliko mode-plocica postoji i kako se obnavlja |
| `GetMatchStampContribution(slot, pos)` | koliko jedna plocica doprinosi skoru meca | vrednost lista/kristala |
| `GetEnergyGivenPositions(...)` | koje celije pune buster | koje boje pune meter |
| `GetAreaOfBoardSpecialEffect(...)` | sta board-specijal rusi kad ga pogodis | oblik eksplozije |
| `GetConvertPoints(...)` | gde se nova mode-plocica postavlja | raspored |

Provereno: `DigDownBoard` (Drillin' Down) gazi **samo** `AfterPerformedSwap` —
sto je tacno ono sto je bot 2026-08-10 empirijski dokazao 3/3 uzivo
("busi samo na igracevom mecu"). Pravilo "`AfterPerformedSwap` = samo direktan
potez" je time potvrdjeno na nezavisnom primeru i moze da se primeni na ostale.

## 2. Enum-i koji otkljucavaju konstante u kodu

```
ComboType   : Normal 0, Special 1, ComboRow 2, ComboColumn 3, Five 4, RShape 5,
              FourRow 6, FourColumn 7, Square 8, MergeSwap 9, Ability 10,
              Manual 11, Mutation 12
SlotColor   : Empty 0, None 1, Red 2, Green 3, Blue 4, Yellow 5, Orange 6,
              Purple 7, White 8, All 12
CellType    : Normal 0, Double 1, Vegas 2, Funky 3, RocketTarget 4, Bullseye 5,
              ExtraMove 6, BuriedTreasure 7, BuriedTreasureNoLuck 8, Hive 9
SlotValueType (mode plocice): BoardSpecial 16, ZanyZapperPiece 17,
              ColorCrystalPiece 18, MultiplierMushroomPiece 19,
              PirateChestPiece 20
```

Zato `cmp w8, #9` koji se ponavlja u `AfterPerformedSwap` skoro svakog moda
znaci **`combo.Type == MergeSwap`**, tj. "ovo je spoj dva specijala" — i takav
combo se u tim modovima tretira posebno (obicno preskace). `mov w1, #11` uz
`ComboModel::.ctor` znaci da mod pravi combo tipa `Manual`.

`get_BoardSpecialValueType` je disasembliran i vraca konstantu:
`ColorBombBoard` -> 18, `MultiplierMushroomsBoard` -> 19, `PlunderPiratesBoard`
-> 20, `ZanyZappersBoard` -> 17. To potvrdjuje mapiranje koje je adapter do sada
imao iz snimaka.

## 3. Konstante su **podrazumevane vrednosti**, ne fiksne

Svaki `get_MAX_...` / `get_..._SCORE` geter ima isti oblik:

```
if (extraData != null && extraData.ContainsKey(KEY))
    return Convert.ToInt32(extraData[KEY]);
return <konstanta u kodu>;
```

Dakle server preko `extraData` moze da pregazi svaku od njih. To objasnjava zasto
je snimak Dustville Duel-a pokazao **3** wanted plocice iako je podrazumevana
vrednost u kodu **2**, i isto za Candy World. **Zakljucak za bota: ove brojke se
citaju iz memorije, kod daje samo fallback.**

Podrazumevane vrednosti procitane iz koda:

| board | konstante (default) |
| --- | --- |
| `JungleRumbleBoard` (Green Leaf) | `LEAF_SCORE` **2**, `LEAF_FREQUENCY` **50** |
| `CrystalCaveBoard` (Purple Gem) | `INITIAL_SCORE` **2**, max plocica **1**, rate **1**, chance **1.0** |
| `BullseyeBoard` (Bounty) | `INITIAL_SCORE` **5**, `SCORE_INCREASE` **5**, `MIDDLE_ONLY` **true** |
| `DustvilleDuelBoard` | tiles **2**, `SCORE_BONUS_PER_HIT` **4**, `WANTED_SHOOTS` **4**, `MIN_BLUES_TO_PICK` **4**, rate 1 |
| `CandyWorldBoard` | max **2**, rate **1** |
| `ExtraMovesBoard` | initial **1**, max **2**, rate **2**, chance **1.0** |
| `FunkyTilesBoard` | max **3** |
| `VerticalRushBoard` | `DecreaseScoreMultiplierBy` **2** |
| `VegasViewsBoard` | initial 1, max 1, rate 1, `SCORE_MULTIPLIER` **2** |
| `BuriedTreasureBoard` | max **5**, rate 5, `SCORE` **10**, `CHANCE_FOR_SCORE` **50** |
| `NuclearBoard` | initial 3, max 3, rate 2, `NUCLEAR_HIT_POINTS` **20**, chance 100 |
| `ZanyZappersBoard` | `REQ_PIECE_COUNT` **7** |
| `FrozenFeudBoard` | `FROZEN_TILES_COUNT` **3** |
| `StockMarketBoard` | `MAX_SCORE` **10**, `ENERGY_COLORS_MAX_SCORE` **1** |
| `ColumnManiaBoard` | `MaxMultiplier` **99** |
| `MultiplierByRoundBoard` | pocetni mnozilac **99** |

Napomena o dumperu: u `il2cpp_symbols.json` ove konstante stoje kao
`is_literal: true, literal_value: null` — agent dekodira samo enum literale.
Brojke gore su izvucene iz disasembliranih getera. Popravka u agentu bi ih dala
direktno.

## 4. `IsAbilityUsedThisMove` — gejt koji bot uopste ne modeluje

Najveci sistemski nalaz. Ove board klase u svom hook-u **prve stvari proveravaju
da li je igrac u ovom potezu upotrebio buster/perk, i ako jeste, izlaze bez
ikakvog efekta**:

`BullseyeBoard.onMoveEnd`, `BuriedTreasureBoard`, `EnergizedBoard.BeforeCombosDestroy`,
`FloorIsLavaBoard.AfterPerformedSwap`, `FunkyTilesBoard.BeforeCombosDestroy` i
`GetAreaOfBoardSpecialCellEffect`, `LightsUpBoard`, `MultiplierMadnessBoard`,
`RainbowMultiplierBoard`, `SwitcherooBoard`, `VegasViewsBoard`,
`VerticalRushBoard`.

Dokaz na `VerticalRushBoard::AfterPerformedSwap` (rva `0x579b5b0`), dekodirano:

```
if (logic.CurrentPlayer.IsAbilityUsedThisMove)               return combos;  // izlaz
if (!logic.CurrentPlayer.NoFreeMoveBoardAbilityUsedThisMove) return combos;
if (!logic.isPerformedSwap)                                  return combos;
for (combo in combos) {
    if (combo.Type == MergeSwap) continue;   // spoj specijala se ne broji
    ...
}
... ScoreMultiplier -/+ DecreaseScoreMultiplierBy
```

(`tbnz`/`tbz` grane vode na `mov x0, x19; ret` — vracanje liste netaknute.)

Posledica za bota: **kad potez ukljucuje buster ili perk, mode-efekat u ovim
modovima ne pali.** Simulator ga svejedno racuna. Ovo direktno pogadja Floor Is
Lava (oznaka kolone se ne upisuje), Funky Tiles, Bullseye i Vertical Rush.

## 5. Nalaz po modu

### Potvrdjeno da je bot u pravu

| mod | sta kod potvrdjuje |
| --- | --- |
| **Drillin' Down** | `DigDownBoard` gazi samo `AfterPerformedSwap` -> samo direktan mec. Poklapa se sa merenjem 3/3. |
| **Arcade Man** | `MatchLineBoard` isto samo `AfterPerformedSwap`; `ExplodeRow`/`ExplodeCol` su lokalne funkcije koje redove/kolone ubacuju u `HashSet<int>` (dedupe). Bot vec ima `cascade_number == 1` gate — stara beleska "pali na svakoj kaskadi" je **netacna** i treba je ispraviti. |
| **Color Crush** | `ColorCrushBoard` gazi samo `AfterPerformedSwap` -> wipe samo na prvoj kaskadi, tacno kako bot radi. |
| **Laser** | `LightsabersBoard.AfterPerformedSwap` — samo direktan potez. Svako polje iz pocetnih spojeva emituje u cetiri pravca, do prve odgovarajuce figure iste boje; polja iz BILO KOG pocetnog spoja zaustavljaju zrak pre nego sto se putanja prihvati. Obe spojene boje emituju. Prihvacena putanja daje `ComboModel` tipa `Manual`. |
| **Floor Is Lava** | brojanje kolona je u `AfterPerformedSwap` (`GetDistinctXCoordinates` + `GetColumn`), a `BeforeCombosDestroy` samo isporucuje vec pripremljen `combosToAddToDestroy`. Botov `cascade_number == 1` je tacan. |
| **Color Crystals / Mushrooms / Chest / Zappers** | `get_BoardSpecialValueType` = 18 / 19 / 20 / 17, isto sto adapter cita. |

### Razilazenja i rupe, po vaznosti

Laser dopuna, 2026-10-28: lokalno disasembliran sacuvani `libil2cpp.so`,
`LightsabersBoard.AfterPerformedSwap` (RVA `0x578a3e0`). Na `0x578a978`
proverava se da li je sledece polje u listi originalnih combo pozicija;
`0x578a988` napusta ceo taj zrak ako jeste. Tek zatim skuplja prolazna
polja i proverava `MatchesWithSlot` (`0x578aa38`). Raniji simulator nije
imao ovu prepreku: u dvobojnim spojevima prolazio je kroz drugi spoj i
izracunavao lazni L posle pada. Ispravljeno u `_laser_effect_cells`;
opsta blokada extra kaskada posle lasera vise nije potrebna. Snimci
`2026-10-28_06-04-43_120` i `2026-10-28_06-43-17_660` sada ne daju
extra, a potvrdene kaskade `03-45-03_330` i `06-02-19_772` ostaju extra.
Listing: `Debug/reverse/laser/Match3Engine.LightsabersBoard_AfterPerformedSwap.asm`.
Ovo je staticki nalaz iz sacuvanog binarnog fajla, potvrden replay testovima;
nije nova proba uzivo. REA server je otvorio identitet fajla, ali njegova
Windows Ghidra integracija ne podrzava ARM64 ELF analizu, pa je listing
napravljen postojecim `tools/il2cpp_disasm.py`.

1. **`IsAbilityUsedThisMove` gejt (12 modova)** — opisano gore. Nista od toga
   nije u simulatoru.
2. **Energized: boje se menjaju svakog poteza.** `EnergizedBoard.onMoveEnd`
   zove `GetBoardUniquePlayerColors(player.Index)` pa `SetPlayerEnergyColors` +
   `SetBoardUniquePlayerColors`, i klasa ima polje `switchColorsOnMoveEnd`.
   Boje su k tome **po igracu** (`player.Index`) — protivnik ima svoje. Bot ima
   dve boje koje korisnik rucno izabere u GUI dijalogu i drzi ih fiksne celu
   partiju. Treba ih citati iz memorije (`GameLogic.CurrentEnergyChargingColors`
   / `OpponentEnergyChargingColors` — imena se vide u
   `CandyWorldBoard::GetEnergyGivenPositions`).
3. **Hot Color: sledeca boja je poznata unapred — RESENO 2026-08-21.**
   `HotColorBoard` drzi `currHotColor` (0x79), `nextHotColor` (0x7a),
   `currHotColorsBonus` (0x7c) i `nextHotColorsBonus` (0x80); `onMoveEnd` radi
   `curr = next; next = GetRandomColor(exclude: curr)`.

   `GetMatchStampContribution` je disasembliran i ceo se svodi na:

   ```
   if (slot.MatchesWithColor(currHotColor))
       return Math.Max(0, currHotColorsBonus - 1);
   return 0;
   ```

   Doprinos je dakle `bonus - 1` **povrh** jedinicnog peceta koje plocica ionako
   nosi, pa je `currHotColorsBonus` ukupna vrednost — isto ono 3/4/5 koje
   ekranski citac vidi na znacki. Time je polje iz memorije direktno zamenljivo
   sa dosadasnjim citanjem.

   Implementirano: `board_source.hot_color_state()` cita oba para iz
   `board_fields` (bez izmene agenta — `readBoardFields` je genericki sweep),
   `memory_gui` ih prosledjuje kroz `hot_color_state`, a lookahead ih koristi
   po plijevima: **ply 0** (potez koji se bira sad) na trenutnoj boji, **ply 1**
   na `nextHotColor`, **ply 2+** bez ikakvog hot-color bonusa jer je tamo boja
   svez `GetRandomColor` bacaj koji niko ne moze da zna. Ranije su svi plijevi
   koristili trenutnu boju, sto je od prvog plija nadalje sigurno pogresno.

4. **Green Leaf: list vredi 2 poena, a bot mu ne daje tezinu.** Stara beleska o
   "`GREEN_LEAF` nema `mode_target` tezinu" sad ima i broj: `LEAF_SCORE` = 2
   (default), preko `GetMatchStampContribution`. Popravka je jedna tezina.
5. **Vertical Rush je heuristika umesto pravila.** Bot: `vertical_match: +6.0`,
   `horizontal_match: -6.0`. Engine: `PlayerControl.ScoreMultiplier` se menja za
   `DecreaseScoreMultiplierBy` (default 2), samo na ne-`MergeSwap` combo-ima, i
   samo ako nije koriscen buster. Simulator uopste nema pojam `score_multiplier`.
6. **Multiplier modovi su otpisani kao "ne menjaju strategiju", a menjaju.**
   `RULES_ID_NO_STRATEGY_CHANGE` sadrzi `multiplier-madness` uz obrazlozenje da
   mnozilac skalira sve poteze podjednako. Ali
   `MultiplierMadnessBoard.BeforeCombosDestroy` zove `GetComboColor` i dize
   mnozilac **samo za odredjene boje** (`get_MultiplierColors` -> boja 7 =
   ljubicasta). Isto vazi za `RainbowMultiplierBoard` (boje po igracu),
   `ColumnManiaBoard` (`colsToIncrease`, `MaxMultiplier` 99),
   `LightsUpBoard` (`CurrentActiveColumn`, kolona se menja `RandomWrapper::Range`
   na kraju poteza — **implementiran 2026-08-21**, mnozilac dizu samo mecevi
   samog poteza, vidi `docs/game_mode_rules.md`),
   `EveryMoveIncreaseScoreMultiplierBoard` i
   `MultiplierByRoundBoard` (mnozilac po rundi). Sve su to poteznozavisne
   odluke, ne konstantan faktor.
7. **Stock Market prepisuje cenu boja svakog poteza.**
   `StockMarketBoard.BeforeCombosDestroy` cita `MatchRulesModel.colorScoreOverride`
   i klampuje na `MaxScore` 10 / `EnergyColorsMaxScore` 1; `onMoveEnd` upisuje
   nove vrednosti nazad (`SetScoreAndEnergyOverrides`). Bot ga vodi kao "nema
   strategije" — reaktivno je tacan jer cita legendu uzivo, ali ne planira da
   ce mec u boji X promeniti njenu cenu za sledeci potez.
8. **Plunder Pirates: sanduk se naplacuje na `onMoveEnd`**, kroz
   `GameLogic::DestroyMatches` sa combo-om tipa `Manual` — ne u trenutku meca.
   Vredi proveriti da li simulator to knjizi u istom potezu.
9. **Bullseye: `MIDDLE_ONLY = true`, skor pocinje na 5 i raste za 5** po potezu
   (`onMoveEnd`, ali samo ako nije koriscen buster). Bot ima `BOUNTY` tezine bez
   ovog rasta.
10. **Column Mania je sada mapiran iz koda**, ne ceka vise snimak:
    `onGameStart` oznaci kolone (`SetCell`, polje `colsToIncrease`),
    `AfterPerformedSwap` + `onMoveEnd` dizu mnozilac do 99.

### Mapiranje u bota (uradjeno 2026-08-21)

**`BOARD_MODEL_TO_MODE` u `memory_gui.py`.** Mod se sada resava iz
`MatchRulesModel.boardModelName` — broja koji engine sam upisuje — kad ruleset
id nista ne kaze. Do sada je jedini put bio string id, koji mora da se uhvati po
areni; zato je `docs/game_mode_rules.md` imao celu kolonu „id not yet captured"
(Arcade Man, Vertical Rush, Energized, Special O'Rama...). Ta kolona je time
zatvorena: rucno mapiran id i dalje pobedjuje, board model je fallback.

Iz mape su namerno izostavljeni **1 (`BoardModel`)** i **11 (`RainbowBoard`)** —
nemaju svoju klasu u metapodacima, oni *jesu* obicna tabla, pa je „bez posebnih
pravila" tacan odgovor, a ne „nemapirano".

**Cetiri nova moda.** Registrovani su `FROZEN_FEUD` (6), `VEGAS_VIEWS` (10),
`BURIED_TREASURE` (15) i `ZANY_ZAPPERS` (33): u `GameMode`, u `MODE_WEIGHTS`, u
`GAME_MODE_OPTIONS` oba fajla (`recognition.py` i `runtime.py`) i u
`BOARD_MODEL_TO_MODE`. Njihove plocice memorijski adapter vec isporucuje kao
`SPECIAL_MODE_TARGET` (`SlotValue` 16 odnosno 17), tako da se tabla cita tacno.

Pravilo koje sam primenio na tezine: **placa se samo ono za sta engine da broj.**

| mod | sta je implementirano | zasto tako |
| --- | --- | --- |
| Frozen Feud | **puna mehanika**: razbijena zaledjena plocica cisti celu svoju vrstu (`_frozen_feud_cells`) | `GetAreaOfBoardSpecialEffect` se svodi na `BoardModel.GetX(row, 0, 1, null)`. Nije vezano za direktan potez — hook je area-of-effect board specijala, pa pali i u kaskadi. `mode_target` je 0.0 jer se ociscene plocice vec placaju kao obicno ociscenje |
| Buried Treasure | `mode_target` = **5.0** | `SCORE` 10 × `CHANCE_FOR_SCORE` 50% = ocekivanih 5 poena po celiji, na istoj skali na kojoj radi Purple Gem. Prosek, ne obecanje — engine baca `RandomWrapper.Chance` po celiji |
| Vegas Views | **bonus po combo-u** (`_vegas_views_bonus`, 2026-10-23) | Vidi odeljak „Vegas Views” ispod |
| Zany Zappers | 0.0 (neutralno) | `REQ_PIECE_COUNT` je 7, ali board model ne zove nijednu skoring metodu — nema broja kojim bi se skupljanje platilo |

Nula znaci „igra se kao `GameMode.NONE`", dakle nista nije gore nego pre; dobitak
je sto se tabla cita, mod se prepoznaje i prestaje da se prijavljuje kao
nemapiran.

### Mnozilac skora se od 2026-08-23 cita (board 22 i 34)

Sest board modela drzi ceo svoj mod u `PlayerControl.ScoreMultiplier`, a taj
getter (rva `0x57e0d64`) je obican `model.scoreMultiplier` na `PlayerModel+0x50`
— dakle citljiv iz memorije bez ijednog poziva metode. Agent ga vec salje kao
`players[].score_multiplier`; `board_source.score_multiplier_state()` ga cita za
obe strane, a memory GUI ga prikazuje uz skor i loguje svaku promenu.

Dva su izmerena na snimcima (1285 snapshotova, 2026-08-23):

| board | rules id | pravilo | mereno |
| --- | --- | --- | --- |
| 34 `EveryMoveIncreaseScoreMultiplierBoard` | `moves-multiplier` | `AfterPerformedSwap` (rva `0x577ee8c`) cita mnozilac, proverava kap i upisuje +1 — **jednom po potezu** | mnozilac ide 1,2,3,…,14 u korak sa `moves_made_this_turn` |
| 22 `MultiplierMadnessBoard` | `multiplier-madness` | `BeforeCombosDestroy` (rva `0x5790184`) dize +1 **po unistenom combu mod-ove boje** (`get_MultiplierColors`), pa uzme jedan protivniku; `onGameStart` postavlja obe strane na 1 | 22 skoka u jednoj partiji, ali NE po potezu: tri skoka su pala unutar jednog istog poteza (kaskade) |

**Skoring (2026-08-23).** Oba su sada `GameMode` za sebe
(`MOVES_MULTIPLIER`, `MULTIPLIER_MADNESS`), prepoznaju se i po rules id-u i po
board modelu, a mnozilac stize do skoringa kroz `score_multiplier_state()`.
Poen mnozioca je cenjen kao i Lights Up-ov — vrednost jednog poteza baznih
poena, podeljena mnoziocem koji vec stoji (`_score_multiplier_point_value`,
18.0 → x1 vredi 18, x6 vredi 3, bez preostalih poteza 0).

Sta se boduje:

* **Multiplier Madness** — potez *zaradjuje* mnozilac, pa se broji svaki
  uniseni ljubicasti combo, kroz sve kaskade (`_multiplier_madness_points`).
* **Moves Multiplier** — svaki potez dize mnozilac za 1 bez obzira sta radi, pa
  nijedan kandidat ne moze da bude bolji od drugog zbog toga. Jedino sto se tu
  boduje je **extra potez**, koji kupuje jos jedno dizanje povrh sopstvenih
  poena.

Namerno se *nista drugo ne skalira* ni u jednom od dva moda. Mnozilac je jedan
broj nad celom tablom, pa mnozi i poene koje potez uzima sada i poene koje ce
buster i extra potez uzeti kasnije — obe strane svake trampe se pomeraju
zajedno, pa je odnos medju njima nepromenjen. Naduvavanje instant skora bi samo
obezvredilo plavo i extra za isti faktor, tacno ona greska zbog koje Column
Mania normalizuje nazad u „ocisceno polja".

### Board modeli koje bot i dalje nema

`RocketRiotBoard` (5), `StockMarketBoard` (20),
`MultiplierByRoundBoard` (24), `SwitcherooBoard` (25), `NuclearBoard` (31),
`ColumnManiaBoard` (32), `LightsUpBoard` (37). (`RainbowMultiplierBoard` (35)
je od 2026-09-13 mapiran kao Color Climb -- dve boje po igracu iz
`availableColors`, vidi `docs/game_mode_rules.md`.)

Dele dve prepreke, obe vece od jednog mapiranja:

1. **Sest ih trazi model mnozioca koji simulator nema.**
   `MultiplierMadness`, `RainbowMultiplier`, `ColumnMania`, `LightsUp`,
   `EveryMoveIncreaseScoreMultiplier`, `MultiplierByRound` svi rade nad
   `PlayerControl.ScoreMultiplier`. Uslov je poznat iz koda (boja iz
   `get_MultiplierColors`, kolona iz `colsToIncrease` / `CurrentActiveColumn`),
   ali dok mnozilac ne postoji kao pojam u skoringu, nema gde da se upise.
2. **Cetiri trazi novi efekat u simulatoru**, cija je skica ovde ali telo metode
   nije dekompajlirano:
   * `RocketRiotBoard` — `onMoveStart` bira nasumicnu poziciju
     (`RandomWrapper::Range`) i postavlja `RocketTarget` celiju; `onMoveEnd`
     opali bombu ako je meta pogodjena ili ako je poslednji potez
     (`FireOnLastMoveEnd`).
   * `NuclearBoard` — 3 plocice sa 20 „hit points" (`NUCLEAR_HIT_POINTS`),
     `BeforeCombosDestroy` ih smanjuje, `onMoveEnd` ih prebojava.
   * `SwitcherooBoard` — `onMoveEnd` menja boje igracima (`ToColor` nad `Where`
     selekcijom), gejtovano na `IsAbilityUsedThisMove`.
   * `StockMarketBoard` — prepisuje `colorScoreOverride` svakog poteza
     (`MAX_SCORE` 10). Bot je reaktivno tacan jer cita legendu uzivo; fali samo
     planiranje unapred.

## 6. Sta i dalje trazi zivu igru

* Vrednosti `extraData` koje gaze konstante iz odeljka 3.
* `GetBoardUniquePlayerColors` / `CurrentEnergyChargingColors` — koje su boje
  aktivne sad.
* `matchRules` id za modove kojima jos nije uhvacen `RULES_ID_TO_MODE` unos.
* Novi APK -> ceo pipeline ispocetka (RVA se pomeraju).

## 7. Froggy Fu lotus: dekodirano i izmereno (2026-08-21)

### Sta kod kaze

Ceo resolve lanac koji se izvrsi kad odigras mec pored lotusa —
`OnPlayerInitiatedMatch` -> `BuildSwapResolution` -> `TryBuildPlanForCombo` ->
`ResolveNextPlan` -> `RunPullAndConvertLotus` -> `DestroyResolveCluster` ->
`ComputeBlobSpecials` / `BuildMegaCombo` — **nema nijedan RNG poziv**. Da je
odsustvo pravo a ne slepilo alata: `RandomWrapper::Chance` i `::Next` se uredno
razresavaju po imenu drugde u istom dumpu (`BuriedTreasureBoard`, i sam
`FroggyFu::RollPreferredColorForActivation`).

Slucajnost postoji, ali u fazi **postavljanja** lotusa (`PickLotusPositions` ->
`FroggyFuLotusPlacementPlanner::BuildPlacementSelection`, `Roll*` metode,
`simulatedRuns`). Dakle: gde lotusi padnu je lutrija, sta se desi kad matchujes
pored njih nije.

Okidac (`TryBuildPlanForCombo`), dekodiran:

```
za svaki lotus koji ovaj potez jos nije iskoristio:
    ako nije na tabli ili slot.color != SlotColor.None -> preskoci
    merge-swap: ok = IsPointAdjacent(mergeSwapTarget, lotus)
    inace:      ok = TryGetComboPositionAdjacentToLotus(combo, lotus, out pos)
```

`IsPointAdjacent` je `|dx| + |dy| == 1` — **tacno 4 ortogonalna suseda**.

Zona privlacenja, obe metode procitane cele:

```
CalcBoardDistance(a, b, chebyshev) = chebyshev ? max(|dx|,|dy|) : |dx|+|dy|
InGatherRegion(p, lotus, r, cheb)  = CalcBoardDistance(p, lotus, cheb) <= r
```

`FroggyFu.GatherShape`: Square = 0 (Chebyshev), Diamond = 1 (Manhattan).
`GetValueForActivation(list, n)` = `list[max(0, min(n-1, count-1))]`.
`ComboShapeRank` je tabela na `0x1376520`, procitana direktno iz `.so`:
red/kolona 1, cetvorka 2, R-oblik 3, kvadrat 4, petica 5.

### Sta je merenje pokazalo

`tools/measure_froggy_lotus.py` cita `Debug/runs/*/memory_frames.jsonl` — kadrove
snimljene **usred kaskade**, gde se povuceni klaster vidi kao blob pre nego sto
bude unisten. Na 8 lotus poteza:

* **8/8: `blob - 1 == predvidjeno`.** Lotus se i sam pretvori u boju meca, pa
  blob nosi jednu plocicu vise nego sto je pokupljeno. To je novi potvrdjeni
  detalj mehanike.
* **Ziva konfiguracija je `gatherRadiusByActivation = 7`, `gatherShape = square`.**
  Na tabli 7x7 Chebyshev poluprecnik 7 pokriva **celu tablu**.

Zbog toga je botovo brojanje po celoj tabli bilo **tacno** za ovu konfiguraciju —
pretpostavka da zona nesto ogranicava je oborena merenjem. Brojanje je svejedno
prevedeno na `InGatherRegion` (`_lotus_collected_count`), jer sada prati
konfiguraciju umesto da je pogadja: pri `r=7` na 7x7 je to identican rezultat, a
manji poluprecnik ili veca tabla (`super-sized` je 9x9) bi ga promenili sami od
sebe. Kad se poluprecnik ne moze procitati, ostaje staro brojanje po tabli.

Iz istih parametara procitano i: `rainbowScoreByColor` =
`Yellow:4|Purple:3|Orange:2|Green:1|White:1|Blue:0|Red:0`, sto je tacno botova
`FROGGY_LOTUS_SCORE_VALUES` tabela umanjena za 1 — ista „doprinos = vrednost - 1
povrh jedinicnog peceta" konvencija kao kod Hot Color-a. Jos: `lotusCountByActivation`
2, `minLotusSeparation` 5, `entranceDestroyCountRangeByActivation` 8-12.

**Izmereno 2026-09-19** (16 lotus poteza u Floor Is Lava, gde poeni nisu mnozeni):
`poeni = ocisceno + (skupljeno + 1) * rainbowScoreByColor[boja]` — tacno na 12/16,
ostala 4 su razlika u kaskadi. `+1` je sam lotus, koji se pretvori u boju meca i
ode sa klasterom. Bot je do tada bojama upisanim u `score_rally_values` sa 1.0
(zelena/zuta/ljubicasta/narandzasta) racunao ceo unos tabele umesto unosa iz
konfiguracije, tj. poen vise po plocici, dok su plava i crvena (kojih u recniku
nema) izlazile tacno. Unos 1.0 je samo jedinicna plocica koju tabela vec sadrzi,
pa ga `_froggy_lotus_color_value` vise ne sabira; bonus se placa za
`skupljeno + 1` plocica.

**Hot Color / Score Rally (pravilo igraca, 2026-09-19):** vrednost boje se sabira
**preko cele tabele**, za svaku boju: `lotus = tabela + hot vrednost`. Zuta je
inace 5, a kao hot color sa 4 vredi 9; ljubicasta 4 -> sa hot 5 vredi 9;
narandzasta 3 -> sa hot 4 vredi 7; zelena 2 -> sa hot 3 vredi 5. Sabira se samo
unos veci od 1.0 (prava hot/rally vrednost).

### Pull dekodiran i potvrdjen 8/8 (korak 3)

`UnifiedFroggyFuAttractionPlanner` je konkretna implementacija iza interfejsa
`IFroggyFuAttractionPlanner`. Procitana su i tela lambdi, jer u njima zive
komparatori:

| deo | pravilo |
| --- | --- |
| kandidati (`BuildDominantCandidates`) | `slot.canBeMatched && slot.MatchesWithColor(dominant) && slot.movable`, pa `RemoveAll` za `allBlocked` / `alreadyPulled` / `avoid` i za sve van `InGatherRegion` |
| redosled plocica (`OrderPiecesOnion`) | `OrderBy(prsten).ThenBy(kvadrat rastojanja).ThenBy(x).ThenBy(y)` |
| mete (`BuildPrioritizedTargets`) | kutija `-r..r` po obe ose (dakle Chebyshev kutija i kad redosled vodi Manhattan), lotus celija izuzeta (`dx==0 && dy==0`), u granicama, `slot.canBeMatched`; sortirano Manhattan -> Chebyshev -> x -> y |
| izbor mete (`PickBestTarget`) | medju metama sa minimalnim (Manhattan, Chebyshev) do lotusa, uzmi najblizu **plocici koja se pomera** (`CubedDistanceTo`) |

Dve sitnice koje se lako promase: `Point` je `(x, y)` a botove celije su
`(row, col)`, pa `ThenBy(x).ThenBy(y)` nije isto sto i sortiranje po celiji; i
`Point.CubedDistanceTo` je uprkos imenu **kvadrat** euklidske, `dx*dx + dy*dy`.

`tools/validate_froggy_pull.py` poredi model sa snimljenim blobovima i daje
**8/8 poklapanja celija po celiju**.

Put do 8/8 je sam po sebi nalaz. Prvo merenje je davalo 7/8, i greska je bila u
proveri a ne u modelu:

* **`memory_frames.jsonl` ne pocinje pre poteza.** Prvi zapis je prvi *poll*, i
  zavisno od kasnjenja moze vec biti posle zamene. Citanje frejma 0 kao „pre" i
  primena zamene na njega ponisti zamenu koja se vec desila. Prava pre-potez
  tabla je `board` iz `move.json` — ono na cemu je odluka doneta.
* **Lotus se resava tamo gde ga je zamena ostavila.**
  `FroggyFu.SyncLotusPositionsForUserSwap` azurira zapamcene pozicije za potez
  koji je igrac upravo odigrao, pa potez koji prevuce sam lotus centrira pull na
  celiju na koju je sleteo, ne na onu sa koje je krenuo. Zabelezeno u
  `froggy_lotus_after_swap`.

Drugi lotus na tabli (`lotusCountByActivation` je 2) je usput potvrdjen: bira se
onaj koji je mec dodirnuo, ne bilo koji.

### Unistenje klastera i specijali (delimicno)

`DestroyResolveCluster` (3160 B) unisti povuceni klaster, a pre toga
`ComputeBlobSpecials` pusti `BoardAnalyzer::GetAllCombos` nad blobom i zadrzi
combo sa najboljim `ComboShapeRank`. Rang tabela je procitana direktno iz `.so`
(0x1376520): red/kolona 1, cetvorka 2, R-oblik 3, kvadrat 4, petica 5.

Blob je jednobojan, pa je **svaki oblik u njemu stvaran combo** — pravilo se
svodi na „uzmi najbolje rangiran oblik koji blob sadrzi". To je
`froggy_blob_special_shape`, i slaze se sa snimcima (precizirano nize: engine
combo-e nalazi skeniranjem, pa je oblik koji stvarno nastane oblik *tog*
comboa, a ne bilo koji koji blob sadrzi):

| blob | najduzi niz | model | snimljeno |
| --- | --- | --- | --- |
| 11 | 5 | `five` | lightning |
| 9 / 8 | 3 | `l` | bomba |
| 9 | 3 | `l` | bomba |

Kvadrati se broje samo kad ruleset ima square matching upaljen — u snimljenim
partijama je bio ugasen, pa `GetAllCombos` kvadrate uopste ne emituje.

**Merenje na 14 poteza (2026-08-21, trace poll spusten na 30 ms).**

* **Pull: 14/14 poklapanja celija po celiju.** Model nije menjan — sest novih
  poteza je legao na njega bez ijedne ispravke.
* **Boja se cuva, osim +1 za lotus.** Povlacenje su zamene, pa broj plocica te
  boje ostaje isti; jedina razlika je sto se lotus i sam pretvori u tu boju.
  Drzi 14/14 i sada sluzi kao invarijanta u alatu.
* **Brzi poll je uveo zamku koju treba znati.** Na 30 ms se hvata i kadar usred
  leta plocica, gde ista boja nakratko stoji na dva mesta: u jednom potezu je
  takav kadar imao +3 umesto +1, a sledeci je bio uredan. Zato alat bira kadar
  po invarijanti (+1), ne po „najveci blob" — sa starim pravilom bi taj potez
  ispao promasaj modela, a nije.

**Sta merenje i dalje NE moze da razresi.** Kad se broje *tipovi* specijala a ne
celije, u kadru u kom blob stoji sastavljen **nema nijednog novog specijala** —
u sva 14 poteza. Sve sto je ranije izgledalo kao novi specijal bio je postojeci
koji je povlacenje pomerilo, pa mu se celija promenila.

Znaci specijal nastaje **zajedno sa rusenjem klastera**, a vec sledeci kadar
ima gravitaciju. Gusci poll to nece resiti: nije stvar rezolucije nego toga sto
se stvaranje i rusenje dese u istom koraku. Poziciju moze dati samo
`DestroyResolveCluster` / `BuildMegaCombo` kroz disasembler — i dala je, vidi
sledeci odeljak.


### Gde sleti specijal: dekodirano (2026-08-21, korak 4)

Prethodni pasus je zavrsavao na tome da poziciju moze dati samo disasembler.
Dat je. Ceo lanac, od rusenja klastera do celije na kojoj se specijal pojavi:

```
DestroyResolveCluster(logic, resolution, combosToDestroy)
  blobByPlan = ComputeBlobSpecials(logic, resolution.resolvePlans, out otherCombos)
  za svaki plan:  megaCombo = BuildMegaCombo(logic, plan, blobByPlan)
```

**`ComputeBlobSpecials` (rva 0x583c660).** Pusti
`BoardAnalyzer.GetAllCombos(logic, testSlots: null, tryReplaceOriginWithHighHP: false, null)`
nad **celom tablom posle povlacenja**, pa svaki nadjeni combo razvrsta:

* combo koji ne dodiruje nijedan `plan.pulledClusterPositions` ide u
  `otherCombos` i rusi se **zajedno sa klasterom**, pre prve dopune (izmereno
  2026-11-04, vidi `docs/refill_engine.md`);
* combo koji ga dodiruje mora da bude `isHighRank` i da vec nosi
  `specialValueCreated`, inace se preskace;
* plan mu se bira po **najmanjem Manhattan rastojanju od bilo koje celije
  comboa do lotusa**, a na izjednacenje pobedjuje plan sa manjim indeksom;
* po planu se pamti najbolji `ComboShapeRank`, i test je **strogo veci**
  (`rank <= prethodni` -> preskoci), pa na izjednacenje ostaje combo koji je
  nadjen ranije.

`isHighRank` je `type - 4 < 5` bez znaka, dakle `Five, RShape, FourRow,
FourColumn, Square` — **obicna trojka nije high rank i ne pravi specijal**.

**`BuildMegaCombo` (rva 0x583d134).** Napravi jedan `ComboModel` tipa `Normal`
nad `plan.pulledClusterPositions` i na njega prepise:

| polje mega comboa | odakle |
| --- | --- |
| `origin` | `blob.origin` ako plan ima blob combo, inace `plan.adjacentColoringPos` |
| `specialValueCreated` | `blob.specialValueCreated.Clone()`, inace nista |
| `swap` | `[plan.lotus, plan.adjacentColoringPos]` |
| `lastCalculatedColor` | `plan.color` |
| `axisPositionsOverride` | `plan.originalColoringPositions` (samo ako nije merge-swap) |
| `isPlayerInitiated` | `false` |

Ako je klaster prazan, mega combo je `null` i nema ni rusenja ni specijala.

**Odakle `origin`.** Tu je bio ceo cvor, i odgovor je u `GetAllCombos`: kad mu
se ne prosledi test lista, pravi je sam —

```
for (x = 0; x < board.Columns; x++)
    for (y = 0; y < board.Rows; y++)
        testSlots.Add(new Point(x, y));
```

`x` je kolona, `y` je red (`checkList` se indeksira `[x, y]` sa dimenzijama
`(Columns, Rows)`), pa je redosled **po kolonama**: cela kolona 0 odozgo
nadole, pa kolona 1, i tako redom. `GetCombosFromTestList` seje redom, deljeni
`checkList` sprecava da se isti combo nadje dvaput, a
`ArrangeCombosIntoComboModelList` ubaci **seme na indeks 0** comboa, sto
`AddComboToListOfComboModels` prosledjuje `ComboModel..ctor` kao `origin`
(konstruktor ga samo upise, ne dira).

Dakle: **`origin` je prva celija comboa u tom skeniranju — najmanja kolona, a
na izjednacenje najmanji red.** Odatle specijal krece i odatle pada.

**Zasto je jedan blob jedan combo.** `BoardAnalyzer.MatchChecker` je
`BlobMatchChecker`. `TryCreateMatchInternal` upise seme u `checkList`, uzme
vertikalni pa horizontalni niz kroz njega (`DirectionsCol` = {Up, Down},
`DirectionsRow` = {Left, Right}, `patternMinSize` 3 — niz kraci od tri se
odbacuje ceo), i onda **rekurzivno pozove samog sebe na svakoj pokupljenoj
celiji koja jos nije u `checkList`**. Zato jedno seme proguta ceo povezani
klaster, a ne samo krst kroz sebe. Celija koja nije ni u jednom nizu od tri ne
ulazi ni u jedan combo. Kvadrati (`DirectionsTopLeftSquare` i tri sestre: tri
jednokoracne strane plus `Point.Zero`, `patternMinSize` 4) rade samo kad
ruleset ima square matching.

**Zasto se skenira samo blob a ne cela tabla.** Povlacenje su zamene, pa je boja
ocuvana i posle pull-a se ta boja nalazi **tacno na celijama bloba** — combo
neke druge boje ne moze da sadrzi nijednu od njih. Isti combo-i, manje posla.

**RNG i dalje nema.** `GetCombosFromTestList` *ima* `RandomWrapper.Chance`, ali
samo na grani „napravi specijal i od obicnog meca" (`randomSpecialChance`), do
koje se stize tek kad combo **nije** high rank. `ComputeBlobSpecials` uzima
iskljucivo high-rank combo-e, pa ta grana na lotus putanji nikad ne pali.

U `move_strategy` je to `froggy_blob_combos` (combo-i i njihova semena, redom
kojim ih engine nalazi) i `froggy_blob_special` (celija + oblik, ili `None`).

**Provera na snimcima: `python tools/validate_froggy_special.py` -> 10/10.**
Snimak ne moze da pokaze celiju direktno — kadar sa sastavljenim blobom nema
novi specijal, a sledeci vec ima gravitaciju. Ali gravitacija pomera samo
nadole i samo unutar kolone, pa je provereno da se specijal pojavi **u
predvidjenoj koloni, u predvidjenom redu ili ispod njega**: 10/10 poteza, od
toga 2 puta i tacno na predvidjenoj celiji (kadar uhvacen pre pada). Preostala
4 poteza nemaju snimljen novi specijal te vrste i alat ih broji kao „nema
podataka" umesto da ih tiho ubroji.

### Sta jos nije implementirano

Tabla posle lotus poteza se **ne simulira**. Bot dodaje bonus na skor i ostavlja
tablu netaknutu, dok engine povuce klaster, prefarba ga, unisti, pa nad njim
pusti `BoardAnalyzer::GetAllCombos` i napravi specijale.

Pull je dekodiran i potvrdjen (14/14), a od 2026-08-21 i **pozicija specijala**
(odeljak gore, 10/10 po koloni). U `move_strategy` sve to stoji kao ciste
funkcije sa testovima — `froggy_pull_landing_cells`, `froggy_blob_combos`,
`froggy_blob_special` — ali **jos nije zakaceno na izbor poteza**.

Sta jos fali za to:

* tabla posle poteza: klaster se rusi, specijal se upisuje na `origin`, pa ide
  gravitacija i dopuna (`RunPullAndConvertLotus`, 2280 B, jos nije procitan u
  delu koji pise u tablu);
* `TryBuildColoringMatchSpecialCombo` / `TryBuildSecondaryEggCombo` /
  `TryGetSecondaryLandingOrigin` — druga grana `DestroyResolveCluster`, pali se
  iza jednog ruleset flaga i pravi jos comboa pored mega comboa;
* kaskade koje mega combo pokrene, i extra-move racun nad njima.

Za referencu, velicine u planeru: `Pull` 2340 B, `BuildCascadePath` 1656,
`BuildPrioritizedTargets` 1128, `FilterExplicitCandidates` 784,
`StampGatherRegion` 696, `OrderPiecesOnion` 672, `PickBestTarget` 596,
`BuildDominantCandidates` 392; plus telo svake LINQ lambde kao zasebna metoda.

Namerno se ne kaci delimicno: poluispravna tabla bi *izgledala* tacno, a onda
bi je extra-move gate, kaskadno skorovanje i lookahead uzeli zdravo za gotovo —
gore nego je ne modelovati.

## 8. Froggy Fu u solo modu: punjenje bustera (2026-08-21)

Odeljak 7 opisuje mehaniku. Ovaj opisuje **kako se ona koristi u solo_6**, gde
cilj nije maksimum poena nego napunjen buster.

### Sta je merenje pokazalo

Na 14 snimljenih lotus poteza (`Debug/runs/*/observed_delta.json`):

* **Lotus zadrzava potez.** `observed_kept_the_turn` je `true` svuda gde je
  citljivo, nigde `false` (5 puta `null` = nepoznato). `extra_moves = 1` koje
  `rank_froggy_lotus_moves` bezuslovno upisuje je tacno.
* **Plavo kroz lotus puni buster.** Potez sa 11 plavih je odveo meter `0 -> 7`
  (pun), potvrdjeno i od igraca.
* **Ali bot to nije video.** `predicted_blue_cells` je bio **0** dok je
  `observed_booster_charge_gained` isao do 7:

  | run | predvidjeno plavih | izmereno punjenje |
  | --- | --- | --- |
  | 14-14-36_034 | 0 | 7 |
  | 12-43-00_456 | 1 | 6 |
  | 13-15-50_910 | 0 | 6 |

Uzrok: `FROGGY_LOTUS_SCORE_VALUES[BLUE] = 2.0` nosi ravan
`FROGGY_LOTUS_BLUE_CHARGE_CREDIT = 1.0` po plocici, ugurano u **poene**. Cela
buster mehanika (koliko meteru fali, overfill, solo multiplikator) taj kredit
nikad nije videla.

### Sta je promenjeno

**1. Naplata punjenja umesto ravnog kredita (samo `is_solo_6`).**
`_best_lotus_trigger_for_zone` sad uz svaki trigger vraca i `charge_cells`
(= pokupljeno, kad je boja `is_booster_charge_color`), a
`rank_froggy_lotus_moves` ih provlaci kroz obicne plave komponente
(`_froggy_lotus_charge_value` -> `_blue_priority_components_for_cells`). Ravan
kredit se pri tome oduzima od poena da se isto plavo ne plati dvaput.
`blue_cells` se puni **uvek**, i van solo, da prediction check prestane da
prijavljuje 0 za potez koji vidno puni meter.

Rangiranje u solo vise nije cist `-bonus`, nego `-(bonus + charge_value)` —
ista logika kao solo rush skala: **iz override-a u tezinu**. Zuti collect i
dalje moze da pobedi na poene; ono sto vise ne moze je da pobedi po difoltu
protiv collecta koji puni meter.

Overfill se **ne** kaznjava: skup je nedeljiv (ne mozes uzeti 3 od 11 plavih
koje lotus dohvata), isto obrazlozenje po kom je Color Crush izuzet u
`_base_blue_priority_components_for_cells`.

**2. Besplatan plavi potez ide pre lotusa (samo `is_solo_6`).**
`froggy_lotus_charge_extra_to_play_first`: lotus zadrzava potez i pali **samo
na igracevom direktnom mecu, nikad na kaskadi**, pa ga potez u medjuvremenu ne
moze slucajno okinuti — bezbedno je prvo ubaciti plavo u meter.

Dva stroga ogranicenja:

* **Obican extra ne kvalifikuje.** Samo potez koji stvarno puni meter
  (`_useful_booster_charge_cells > 0`) sme ispred lotusa; extra bez plavog nema
  sta da trazi tamo. Kaskadni extra se racuna isto kao direktan
  (`has_guaranteed_true_extra`).
* **Nikad ne menja vece punjenje za manje.** Zamka: meter 0/7, lotus sedi na 11
  plavih (napuni svih 7), a extra donosi 3 — ako taj extra pomeri plave ispod
  lotusa, ostanes na 3 umesto 7. Zato se odigra simulacija tog poteza
  (`_evaluate_candidate_with_result` daje slegnutu tablu) i defer prolazi samo
  ako `extra_charge + ono sto lotus jos dohvata na toj tabli >= ono sto bi
  lotus napunio sada`.

U runtime-u je to novi gejt `froggy_lotus_charge_extra_gate`, tacno iznad
`froggy_lotus_gate`.

### Sta i dalje ne radi

„Odigraj zutu jer je dosta poena, ali samo ako posle ima dobar potez za
punjenje" **nije** implementirano i ne moze da bude dok se ne simulira tabla
posle lotusa (odeljak 7, „Sta jos nije implementirano"). Ono sto jeste
pokriveno je slucaj kad se plavo i zuto porede *na istom potezu*; poredjenje
„zuto sad pa plavo sledeci potez" trazi tablu koju jos nemamo.

## 9. Tabla posle lotusa: RunPullAndConvertLotus i Pull (2026-08-21)

### Sta rade te metode

`RunPullAndConvertLotus` (rva 0x583bac0) **ne rusi nista i ne radi gravitaciju**.
Radi tacno tri stvari:

1. pozove planer (`IFroggyFuAttractionPlanner.Pull`) — sam pull, vec dekodiran;
2. **prepise lotus celiju u obicnu plocicu boje meca**: `color := plan.color`,
   `color2 := SlotColor.None`, `value := SlotValueType.Normal`, `canBeMatched`,
   `movable` i `damageable` na 1, status bit 0 obrisan, pa
   `UpdateColorBasedAttributes` i `board[plan.lotus] = clone`. Gejt pre toga je
   `slot.value == 40` (SlotValueType lotusa). **To je izmereni „+1 za lotus".**
3. `GameLogic.ConvertSlots(...)` sa nastavkom koji zove `ResolveNextPlan`.

Rusenje ide tek kroz `DestroyResolveCluster` -> `combosToDestroy`, a to je
**obican engine put koji bot vec simulira**.

`Pull` (rva 0x5840d4c) plocicu ne teleportuje. Za svaku (plocica, meta) para:

```
path = BuildCascadePath(piece, target, ...)
for (i = 0; i < path.Count - 1; i++) {
    board.Swap(path[i], path[i+1]);
    recorder.Record(path[i], path[i+1]);
}
```

— dakle plocica se probija do mete uzastopnim zamenama sa susedom, i **svaka
plocica preko koje predje pomeri se za jedno mesto unazad po stazi**.

`BuildCascadePath` (rva 0x5842464) je pohlepna setnja:

```
score(next) = |next.x - target.x| + |next.y - target.y|
            + (next.MatchesWithColor(dominant) ? Rows * Columns : 0)
```

Kazna velicine cele table znaci da staza **zaobilazi** plocice boje koja se
skuplja umesto da ih izbaci iz formacije. Preskacu se celije van table, vec na
stazi, `allBlocked`, `alreadyPulled`, `avoid` i one bez `canBeMatched`. Korak na
samu metu prekida setnju **pre** svih tih provera. Izjednacenje zadrzava prvi
pravac, pa je redosled bitan: `BoardModel..cctor` gradi `directions` kao
`Point(0,1), Point(1,0), Point(0,-1), Point(-1,0)`, a `Point` je `(x, y)` =
`(kolona, red)`, sto je u botovim `(red, kolona)` **dole, desno, gore, levo**.

U `move_strategy`: `froggy_cascade_path`, `froggy_pull_moves`,
`froggy_pull_apply`.

### Sta se moglo potvrditi, a sta ne

* **Blob ostaje 14/14.** Refaktor nije pomerio nijednu celiju gde boja sleti
  (`tools/validate_froggy_pull.py`).
* **Puna tabla — NIJE potvrdjena, i verovatno se ovim snimcima ne moze.**
  *(Prevazidjeno: `attractionMoveData` jeste dovoljan izvor, a tabla je
  zatvorena 9/9 — vidi odeljak 11.)*
  Poredjenje predvidjene table sa snimljenim kadrom promasuje ne-blob celije
  (npr. model 6/3/6 gde snimak ima 3/6/3 — plocice jesu tu, u drugim celijama).
  Provereno je i protiv **svih** kadrova svakog runa, ne samo blob kadra: model
  „zamena" daje najbolje 5-16 pogresnih celija, model „staza" 0-35, nijedan ne
  daje 0 osim dva slucajna pogotka.

  Razlog je u samom kodu: `AttractionMoveRecorder.Record` belezi **svaku**
  zamenu kao animacijski korak, pa se pull crta korak po korak. Zavrsena tabla
  posle pull-a postoji tek u trenutku kad se klaster i rusi — ista zamka kao kod
  pozicije specijala (odeljak 7). Blob se u kadru vidi jer je vec slegnut;
  plocice koje je gurnuo su jos u letu.

### Zbog cega ovo i dalje NIJE zakaceno na izbor poteza

Model je sad kompletan na papiru — pull sa stazama, konverzija lotusa, mega
combo, specijal na `origin`, pa obicno rusenje/gravitacija koje bot vec ima.
Ali **ne-blob raspored nije validiran nijednim merenjem**, a upravo on odredjuje
kaskade posle lotusa. Tabla bi izgledala tacno i bila pogresna tamo gde se ne
vidi, sto bi extra-move gate i lookahead uzeli zdravo za gotovo.

Da bi se zakacilo, treba nezavisan izvor za zavrsenu tablu. Postoji, i procitan
je — vidi odeljak 10.

## 10. attractionMoveData: engine sam belezi ceo gather (2026-08-21)

`Pull` svaku zamenu prijavi kroz `AttractionMoveRecorder.Record`, a rezultat
stoji na `FroggyFu.<attractionMoveData>k__BackingField` (offset 0x120) kao
`List<List<Point>>`: **jedan zapis po zameni, sa dve celije koje su zamenjene**.
To je jedini izvor za tablu koju pull ostavlja, jer se animacija crta korak po
korak upravo iz te liste.

Memorijski agent (`tools/matchmasters_board_dump.ts`) sada cita, uz to:

| polje | sta je |
| --- | --- |
| `<attractionMoveData>k__BackingField` | ceo gather, zamena po zamena |
| `<currentResolvePullCluster>k__BackingField` | blob koji se sprema za rusenje — direktna provera `froggy_pull_landing_cells` |
| `<stampedPositions>k__BackingField` | ozigosane celije |
| `plannedLotusPositionsThisActivation` | gde su lotusi postavljeni |

Instanca se nalazi preko `Il2Cpp.gc.choose(FroggyFu)` i **kesira** se: taj poziv
seta po hipu i predaleko je skup za trace poll od 30 ms, pa se promasaj ponavlja
najranije posle 2 s. Liste se citaju **samo preko polja** (`_items` / `_size`,
`listItemsByField`) — `get_Count` nad genericnom listom je vec jednom srusio
igru na attach, sto je zabelezeno u [[feedback-frida-agent-no-method-calls]].

`Point` je `(x, y)` = `(kolona, red)`, isto kao `readSlot` koji emituje `row: y`,
pa je botova celija `(point[1], point[0])`.

Polje putuje do snimaka kroz dve tacke koje se lako promase: allowlist u
`tools/matchmasters_board_reader.py` (`_safe_snapshot`) i `_compact_frame` u
`memory_gui.py` — obe su dopunjene, inace bi `froggy` tiho ispao.

### Sta zapis zapravo sadrzi (ispravka)

Prvo citanje je bilo pogresno: `attractionMoveData` **nije log zamena**.
`AttractionMoveRecorder.Record(data, a, b)`, dekodiran zajedno sa obe lambde
(`<Record>b__0` = `l[1] == a`, `<Record>b__1` = `l[1] == b`; `0x40f4d24` je
`List<Point>.set_Item`):

```
chain = data.FirstOrDefault(l => l[1] == a)   // zapis koji zavrsava u a
if (chain != null) chain[1] = b               // produzi ga na mestu
else               data.Add([a, b])
```

Dakle **jedan zapis po plocici, `[odakle, dokle]`**, a cela lista je
permutacija celija koje je gather dodirnuo. Potvrdjeno na svih 9 novih poteza:
skup izvora je jednak skupu odredista (`perm=True` 9/9).

**Zapis prezivljava izmedju poteza** — cisti ga tek `CleanupState`. Uzimanje
„najduzeg loga u runu" je zato pokupilo *prethodni* lotus u 5 od 9 poteza, i
svih 5 se nije slagalo sa modelom koji su preostala 4 potvrdila tacno. Alat sad
uzima log iz poslednjeg kadra koji ga nosi i **samo ako je permutacija**.

**Provera: `python tools/validate_froggy_gather.py`.**

| sta | rezultat |
| --- | --- |
| blob (`validate_froggy_pull`) | **23/23** celija po celiju |
| pozicija specijala (`validate_froggy_special`) | **15/15** po koloni |
| dodela plocica -> meta | tacna na svim runovima sa svezim logom (jedina razlika: model emituje i `plocica -> ista celija`, sto engine ne belezi) |
| **cela tabla posle pull-a** | **0/9** — *zatvoreno na 9/9, odeljak 11* |

Devet novih poteza je nezavisno potvrdilo blob i specijal bez ijedne izmene
modela. Ono sto i dalje **nije** tacno je gde zavrse *istisnute* plocice — one
koje gather gura u stranu. `froggy_pull_apply` ih razmesta po `BuildCascadePath`
stazi, a engine ih razmesta drugacije (5-35 pogresnih celija po potezu).

### Pokusaj uskladjivanja i zasto je odbacen

Sa 9 referentnih permutacija u ruci probano je uskladjivanje modela. Nalazi:

* **Redosled plocica je tacan na 7/9**, a dodela plocica -> meta na svih 9
  (jedina razlika: model emituje i `plocica -> ista celija`, sto engine ne
  belezi). Preostala dva odstupanja su sitna preuredjenja, verovatno tie-break u
  `OrderPiecesOnion`.
* **Mehanizam istiskivanja je proveren rucno i slaze se.** Za potez
  `15-25-53_791` lanac `(5,4) -> (6,3)` i cela osmoclana staza pulla `(1,4) ->
  (5,5)` reprodukuju se entry po entry iz engine-ovog zapisa.
* Pretraga po parametrima staze spusta gresku sa **167 na 70** pogresnih celija
  (od 441) i daje prvu tacnu tablu — **ali samo tako sto pregazi kod**: trazi
  redosled pravaca RDLU, iskljucen `visited` i iskljucenu kaznu za dominantnu
  boju. Sve troje jasno stoji u disasembleru, a `Point..ctor(x, y)` uz
  `BoardModel..cctor` (`Point(0,1), Point(1,0), Point(0,-1), Point(-1,0)`) daje
  **dole, desno, gore, levo**, ne RDLU.

Zato je fit **odbacen** i `froggy_cascade_path` ostaje kako je dekodiran.
Poboljsanje brojke na 9 uzoraka po cenu protivrecenja izvoru nije nalaz nego
overfit.

### `avoid` i `FilterExplicitCandidates` — dekodirani, i nisu krivci

`AttractionStepParams` (polja: `Logic` 0x10, `LotusPos` 0x18, `DominantColor`
0x20, `GatherRadius` 0x24, `GatherUsesChebyshevRegion` 0x28, `AllBlocked` 0x30,
`AlreadyPulled` 0x38, `StepConversions` 0x40, `AttractionMoveData` 0x48,
`StampScore` 0x50, `AvoidDisplacementCells` 0x58, `ExplicitCandidates` 0x60)
puni `RunPullAndConvertLotus`:

* `AvoidDisplacementCells` = `secondaryCells`, tj. rezultat
  `FroggyFu.BuildSecondaryCellSet(plan)`;
* `ExplicitCandidates` = `new List<Point>(plan.assignedSecondary.positions)` —
  postavlja se **samo ako plan ima `assignedSecondary`**.

`FilterExplicitCandidates(logic, explicitCandidates, allBlocked, alreadyPulled,
consumed)` je obican filter: izbaci sve sto je u `allBlocked`, `alreadyPulled`
ili `consumed`, pa sto nije `IsPointInBound`, pa provere nad slotom.

**Oba pripadaju sekundarnoj grani** (egg/coloring combo), koja pali iza ruleset
flaga i u snimljenim partijama je `null`. Dakle nisu uzrok razlike — suspekt je
iskljucen, ne potvrdjen.

### Pravi trag: `Pull` radi prsten po prsten

Dve lambde `Pull`-a, procitane:

* `<>c__DisplayClass4_0` drzi `lotusPos`, a `<Pull>b__0(pt)` je
  `|pt.x - lotusPos.x| + |pt.y - lotusPos.y| == 1` — **cetiri ortogonalna
  suseda lotusa**;
* `<>c__DisplayClass4_1` drzi `onRing: List<Point>`, a `<Pull>b__1(pt)` je
  `onRing.Contains(pt)`.

Znaci `Pull` izdvaja prsten neposredno uz lotus posebno. Trag je bio dobar ali
nepotpun: prsten se ne obradjuje prvi, nego se **uopste ne pomera** — vidi
odeljak 11, gde je uz to i lista kandidata koja se pravi iznova svakog koraka,
planerov sopstveni `Dirs`, i corsokak koji vraca `[source, target]`.

## 11. Gather zatvoren: 9/9 tabli posle lotusa (2026-08-21)

Odeljci 9 i 10 su stali na **0/9** za celu tablu: blob i specijal tacni, a
istisnute plocice zavrsavaju drugde. Tri nalaza iz disasemblera to zatvaraju, i
sva tri se proveravaju na `attractionMoveData` referenci bez ijednog podesenog
parametra.

**Stanje: `validate_froggy_gather` 9/9, `validate_froggy_pull` 23/23,
`validate_froggy_special` 15/15, `pytest tests` prolazi.**

### 11.1 `Pull` nije jedan prolaz — lista kandidata se pravi iznova svakog koraka

Petlja u `Pull` (0x58411c4 .. 0x58415d8) se vrti `candidates.Count` puta, ali
svaka iteracija ponovo zove `BuildDominantCandidates` (0x5841250) i
`OrderPiecesOnion` (0x5841290) **nad trenutnom tablom**, pa uzme samo
`ordered[0]` (`List.get_Item(0)`, `mov w1, wzr` na 0x58412a8). Petlja izlazi
ranije ako ostane bez meta (`ldr w8, [x22, #0x18]; cbz`) ili bez kandidata.

Posto je svaka staza niz zamena, plocica dominantne boje koju je ranija staza
gurnula u stranu se **kupi sa nove celije**. Model je do sada planirao ceo
redosled unapred, pa je kasnije poteze slao sa celija na kojima te boje vise
nema.

### 11.2 Prsten uz lotus se ne pomera i ne trosi metu

Pre petlje (0x584109c .. 0x5841184):

```
onRing = candidates.Where(<Pull>b__0).ToList()     // |dx| + |dy| == 1
foreach (pt in onRing) { prioritizedTargets.Remove(pt); alreadyPulled.Add(pt); }
candidates.RemoveAll(<Pull>b__1)                   // onRing.Contains(pt)
```

Te plocice su vec tamo gde ih gather hoce: ne pomeraju se, njihove celije nisu
mete, i nijedna staza ne prolazi preko njih (jer su u `alreadyPulled`). U blobu
ipak jesu — boja stoji na njima.

To je ujedno i objasnjenje stare zabeleske „model emituje i `plocica -> ista
celija`, sto engine ne belezi": stari model je prstenu dodeljivao njegovu
sopstvenu celiju kao metu.

### 11.3 `Dirs` je planerov, ne `BoardModel.directions`

Ovo je koštalo najvise. `BuildCascadePath` obilazi listu iz statickog polja
klase na 0x6de1f40, a ta klasa je **`UnifiedFroggyFuAttractionPlanner`**
(staticka polja: `Dirs: Point[]` na 0, `EmptyPoints: HashSet<Point>` na 8 — to
drugo je fallback za `AvoidDisplacementCells`), a ne `BoardModel`.

`UnifiedFroggyFuAttractionPlanner..cctor` (0x5842b94) puni `Point[4]` direktno
iz `Point` statika:

| indeks | staticko polje | offset | `Point(x, y)` | bot `(red, kolona)` |
| --- | --- | --- | --- | --- |
| 0 | `Point.Right` | 0x18 | (1, 0) | (0, +1) desno |
| 1 | `Point.Left` | 0x28 | (-1, 0) | (0, -1) levo |
| 2 | `Point.Down` | 0x10 | (0, 1) | (+1, 0) dole |
| 3 | `Point.Up` | 0x20 | (0, -1) | (-1, 0) gore |

Dakle **desno, levo, dole, gore** — a ne `dole, desno, gore, levo` iz
`BoardModel..cctor`, koja se ovde uopste ne cita. Posto se izjednacenje resava
strogim `b.ge` (0x58428d8, zadrzava se **prvi** najbolji), bocni korak uvek bije
uspravni pri istom rastojanju. Bas to je vidljivo u referenci: potez
`15-25-53_791`, staza `(2,6) -> (3,5)`, engine ide levo na `(2,5)` iako je dole
`(3,6)` isto na rastojanju 1.

Napomena za sledeci put: „koja je ovo klasa" se resava iz
`data/il2cpp_symbols.json` po **potpisu statickih polja** (tip + offset), a ne
po tome koja klasa deluje logicno.

### 11.4 Corsokak vraca `[source, target]`, ne polustazu

Kad nijedan sused nije prihvatljiv, `bestPoint` ostane `Point.MinValue`
(inicijalizacija sa 0x5842744), pa grana na 0x58429d0 **napravi novu listu i
vrati `[source, target]`** — jednu `BoardModel.Swap` izmedju celija koje ne
moraju biti susedne. Model je do sada vracao ono sto je prosetao, pa je plocica
ostajala na pola puta a sve istisnute za jedno mesto pogresno.

Rekonstrukcija iz reference to potvrdjuje direktno: potez `15-25-37_680`, pull
`(4,2) -> (1,1)` — engine zapis ima tacno par `(4,2)->(1,1)` i `(1,1)->(4,2)`,
tj. cistu zamenu dve celije na rastojanju 3.

### 11.5 Sta je ostalo isto

`BuildCascadePath` skor, kazna velicine table za dominantnu boju, `visited`,
redosled meta (`BuildPrioritizedTargets`), `PickBestTarget` i `OrderPiecesOnion`
nisu dirani — samo je `PickBestTarget` izdvojen iz `froggy_pull_moves` u
`_froggy_pick_best_target`, doslovno kako je dekodiran (referenca je
`sortedTargets[0]`, pa `Where` po Manhattan **i** Chebyshev, pa `OrderBy` po
udaljenosti od plocice).

U kodu: `_froggy_pull_run` je sada jedini prolaz kroz pull, a
`froggy_pull_moves`, `froggy_pull_landing_cells` i `froggy_pull_apply` su tri
pogleda na njegov rezultat.

Alat za dijagnozu (kadar po kadar, model uz engine zapis):
`python tools/diag_froggy_gather.py --run <ime_runa>`.

### 11.6 Sledeci korak

Tabla posle pull-a je tacna, pa lotus moze da se zakaci na izbor poteza — sto je
uradjeno u odeljku 12.

## 12. Lotus zakacen na izbor poteza (2026-08-21)

Odeljak 11 je zatvorio tablu posle pull-a. Sad lotus **stvarno opali u
simulaciji**, umesto da se vrednost dodaje preko gotovog rezultata.

**Provera: `python tools/validate_froggy_simulation.py` -> 23/23.** Alat pusta
svaki snimljeni lotus potez kroz `simulate_candidate` i trazi cetiri stvari:
da je lotus opalio, da je klaster predat rusenju kao JEDAN combo, da je
kreirani specijal tacno na `origin`-u koji daje `froggy_blob_special`, i da
obecani extra potez odgovara onome sto je igra stvarno uradila sa potezom
(`observed_delta.json` -> `state_delta.kept_the_turn`).

### Sta je bilo pre

Lotus je bio **sloj preko skora**, ne deo simulacije:

* `simulate_candidate` ga uopste nije video — lotus je BLOCKED celija sa
  specijalom koji se nikad ne aktivira, pa je simulirana tabla posle lotus
  poteza bila tabla na kojoj se **nista nije desilo**;
* `rank_froggy_lotus_moves` je posle toga dodavao bonus
  (`_lotus_collected_count` x vrednost boje), zakucavao `extra_moves = 1` i
  dopisivao `cleared_cells` / `blue_cells`.

Posledica: lookahead, extra-move gate i sve sto gleda tablu posle poteza radili
su nad tablom u kojoj ~10 plocica nije pomereno ni sruseno, i bez kreiranog
specijala.

### Kako je zakaceno

`froggy_lotus_gather(board, special_board, matches, allow_square_matches)`
(uz `FroggyLotusGatherResult`) radi `RunPullAndConvertLotus` + `BuildMegaCombo`
u obliku koji simulator ume da potrosi:

1. lotusi se citaju iz `special_board`-a **posle zamene** — swap ih vec pomera,
   sto je `SyncLotusPositionsForUserSwap`;
2. pali samo igracev **direktan** mec, i to samo ortogonalno uz lotus
   (`froggy_firing_lotuses`), jedan plan po lotusu;
3. `froggy_pull_apply` (sad nosi i `special_board` kroz zamene, jer
   `BoardModel.Swap` menja cele slotove) pomera plocice i pretvara lotus celiju
   u obicnu plocicu boje meca;
4. `BuildMegaCombo` rusi **ceo** `pulledClusterPositions`, ne samo celije koje
   leze u nizu od tri, pa se blob vraca kao jedan `MatchGroup`;
5. specijal ide na `origin` najboljeg high-rank combo-a unutar blob-a
   (`froggy_blob_special`), sto se u simulator ubacuje tako sto ta celija ide
   ispred para zamene u `swap_cells` — `_created_special_cell` uzima prvu celiju
   iz te liste koja pripada mecu, pa drugi mec istog poteza zadrzava staro
   pravilo.

U `simulate_candidate` to stoji na kaskadi 0 (jedinoj koja moze da upali lotus).
Posle toga sve ide **obicnim putem**: rusenje, plavo, kreirani specijal, extra
potez, gravitacija, kaskade.

### Sta se dobija

* tabla posle poteza je stvarna — lookahead i sve nizvodno vise ne nasledjuju
  netaknutu tablu;
* kreirani specijal postoji na tabli (linija/bomba koja sledeci potez vredi);
* extra potez se **izvodi** iz velicine klastera (`>= 4` celija), a ne
  pretpostavlja. Na 13 snimljenih poteza gde je potez izmeren igra ga je
  zadrzala 13/13, i simulacija to reprodukuje;
* plavo se broji stvarno: pre je `predicted_blue_cells` bilo 0 na potezima koji
  su vidljivo punili buster.

### Dvostruko brojanje — i zasto ga nema

Posto simulacija sad sama rusi klaster, svaka pokupljena plocica je vec
placena jednom po obicnoj tarifi (`_instant_score`: Score Rally vrednost, inace
`DEFAULT_CELL_SCORE`) i, ako je boja punjenja, vec ubelezena kao plavo. Zato
`_best_lotus_trigger_for_zone` uz `base_value_covered=True` skida bas toliko:

```
neto = FROGGY_LOTUS_SCORE_VALUES[boja] + rally[boja]
     - rally.get(boja, DEFAULT_CELL_SCORE)
     - (FROGGY_LOTUS_BLUE_CHARGE_CREDIT ako je boja punjenja)
```

pa ostaje tacno `rainbowScoreByColor` — ono sto lotus dodaje **preko** obicne
vrednosti plocice (zuta 4 umesto 5). `cleared_cells` i `blue_cells` se vise ne
dopisuju, a solo grana ne skida plavi kredit dvaput. Redosled izmedju lotus
poteza je isti (pomeraj je linearan po plocici), samo je skala sada tacna.

Nosac je `SimulationResult.froggy_lotus_gathered` -> `MoveEvaluation`.

### Rangiranje van solo moda — regresija koja je uhvacena i popravljena

Skidanje bazne vrednosti iz bonusa je **pomerilo tezinu iz `froggy_lotus_bonus`
u `score`**, a stari kljuc za sortiranje van solo-a je bio
`(-bonus, -collected, priority, -score)` — bonus prvi, score tek poslednji.

Posledica: plavo i crveno imaju `rainbowScoreByColor` = 0, pa im posle skidanja
bonus padne na **nulu**. U versusu je 10 plavih (score 11) gubilo od 4 zelena
(bonus 4, score 9) — bot bi presao na slabiji potez i jos ostao bez punjenja
bustera.

Popravka: kad je gather stvarno odradjen u simulaciji, rangira se po
**`score`**-u, jer on sad drzi sve (klaster placen plocicu po plocicu, plavo,
extra potez, kreirani specijal, plus lotus dodatak). Kad gather-a nema
(ekranski put), ostaje stari kljuc po bonusu — tamo simulacija lotus nije ni
videla, pa je bonus jedini signal. Isto vazi i za solo granu, gde se na to i
dalje dodaje `charge_value`.

Test: `test_froggy_lotus_ranking_uses_the_simulated_score_once_it_gathers`.

### Solo Challenge vs. Party/Showdown

Sva tri su `solo_6` — nema protivnika, ide se na maksimum poena — ali se **ne
igraju isto**, i lotus rangiranje je to mesalo: gate je bio `is_solo_6`, pa su i
Party i Showdown jurili plavo kao Solo Challenge.

Sad je gate **`is_solo_booster_rush`** (`solo_6` + toggle „Juri plave"):

| rezim | kljuc | sta odlucuje |
| --- | --- | --- |
| Solo Challenge (rush ON) | `-(worth + charge_value)` | plavo na istoj skali kao poeni |
| Party / Showdown (rush OFF) | `-worth`, pa `-charge_cells` | **poeni prvi**, plavo lomi izjednacenje |

Plavo u Party/Showdown nije ignorisano: gather ga stvarno pokupi, pa
`blue_cells` ulazi u `score` kroz `blue_bonus` po redovnoj tezini i tako se
takmici sa poenima — samo vise ne gazi veci collect.

Ravni kredit `FROGGY_LOTUS_BLUE_CHARGE_CREDIT` (+1 po plocici u tabeli boja) se
skida **samo tamo gde nesto drugo plati punjenje**: rush ga placa kroz
`charge_value`, a simulirani gather ga banci kao pravo plavo. U Party/Showdown
na ekranskom putu se ne desava ni jedno ni drugo, pa kredit ostaje i plavo
zadrzava svoju malu prednost nad crvenim, kao i pre.

Testovi: `test_froggy_lotus_party_and_showdown_take_the_points`,
`test_froggy_lotus_party_lets_the_blue_break_a_tie`.

### Pun buster: lotus ide na poene

Kad je buster spreman (`BoosterState.is_ready`) meter ne moze da primi jos jednu
plocicu, pa je plavo na tom potezu **bezvredno**. Tada lotus rangiranje:

* skida `blue_bonus` iz `_worth` — poeni, extra potez i kreirani specijal i
  dalje broje, samo meter prestaje da ima misljenje;
* ne racuna `charge_value` (ni u rush grani);
* izbacuje `-charge_cells` iz kljuca.

Vazi i u Solo Challenge-u: sa punim busterom i on prelazi na collect koji nosi
poene. Nepoznato ocitavanje bustera **nije** „ready", pa ne menja nista.

Test: `test_froggy_lotus_ignores_blue_once_the_booster_is_full`.

### Sta i dalje NIJE predvidjeno

* **Sve posle dopune.** Rupa koju klaster ostavi puni se nasumicnim plocicama,
  pa je kaskada iza toga pogadjanje — isto kao kod Color Crush-a. Zato gather
  dize `uncertain_refill_boundary` sa razlogom `BOARD_WIPE_REFILL_REASON`
  (deterministicki skup): kaskada odmah iza jos se broji jer pada od poznatih
  plocica, sve dublje ne. **Ovo se ne moze resiti citanjem koda — dopuna je RNG.**
* **Sekundarna grana** (`assignedSecondary`, egg/coloring combo,
  `FilterExplicitCandidates`) je dekodirana ali u svim snimcima `null`. Ako je
  neki ruleset upali, gather bi bio drugaciji i model to ne zna.
* `AllBlocked` i `AvoidDisplacementCells` se uzimaju kao prazni — u snimcima
  jesu.
* **Ekranski put ostaje na starom.** Gather trazi poluprecnik iz konfiguracije
  bustera, a to daje samo memorijski agent (`request.froggy_gather_region`).
  Bez njega `froggy_lotus_gather` vraca None i vazi staro ponasanje.
* `_lotus_collected_count` u rangiranju i dalje broji boju u zoni na tabli PRE
  poteza, sto je za jedan manje od blob-a (lotus se i sam pretvori). To je
  ranking velicina, nije dirana.

## Vegas Views (`VegasViewsBoard`, 10) — dekodirano 2026-10-23

`BeforeCombosDestroy` (rva `0x579a2c0`):

```
if (logic.CurrentPlayer.IsAbilityUsedThisMove) return combos;      // buster/perk -> nista
for combo in combosToDestroy:
    for p in combo.positions:
        if combo.type in {Special 1, Ability 10, Manual 11}: continue   // maska 0xC02
        if GetCell(p) != Vegas(2): continue
        SetCell(p, Normal)                                          // plocica potrosena
        vegasCombos.add(combo); marked |= combo.positions
repeat: combo cije je origin u `marked` -> isto u vegasCombos     // L razbijen na dva, blast u istom batch-u
for combo in vegasCombos: combo.Score = combo.Score * ScoreMultiplier
for p in marked: slot.score *= ScoreMultiplier                      // prikaz na plocicama
```

* `get_ScoreMultiplier` (rva `0x579928c`): override iz `extraData`, inace **2**. Kartica moda
  kaze „triple score”, pa server salje **3**; bot uzima 3 dok ne procita override.
* `onTurnStart`: ako je Vegas polja < Max (1), uz `ReplenishChance` pretvara
  `min(ReplenishRate, manjak)` Normal polja u Vegas. Nova plocica dolazi tek sledeceg poteza/turna.
* Nema cascade gate-a: i kaskada kroz plocicu je pogadja. Eksplozija specijala (Special combo)
  je **ne** trosi i ne mnozi.

U botu: agent salje `cell_types` i za board 10; `board_source.vegas_views_state` daje polje i
mnozilac; `_vegas_views_bonus` dodaje `(M-1) x vrednost combo-a` prvom kolor combo-u kroz polje
(swap ili kaskada) u `instant_score`, pa ulazi u rangiranje i u solo prag
(`_solo_goal_certain_points`). Nije modelovano: povlacenje combo-a preko `origin` (blast u istom
batch-u) i to sto lookahead ne zna da je plocica potrosena posle prvog poteza.
