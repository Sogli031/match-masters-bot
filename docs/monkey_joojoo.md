# Monkey Joojoo (buster 40): analiza iz koda igre

Status: **delimicna analiza**, 2026-10-31. Dopuna i lobanje posle poteza preneti
2026-11-12 (vidi ispod); sama aktivacija boostera (`Use`, auto-eksplozija) nije.

## Kako lobanje rade (2026-11-12)

Bacis booster -> pojave se lobanje; svaka ima pravac po svojoj boji i kad udje u
match eksplodira po tom pravcu. Broj lobanja raste **samo uz booster**:
`skullsPerActivation` (Solo "4,1") daje 4 na prvo bacanje, pa +1 na svako sledece
(snimak: 5, 6, 7 ... 12, uvek +1 na `activate_booster`). Posle svakog poteza
`EndMoveWithPassiveAbility` 0x5a7c650 -> `ChoosePositions(logic, true)` 0x5a7b6b0
dopunjava tablu do tog broja, na figure koje su vec na tabli (boja se ne menja).
Zato se lobanje koje su eksplodirale "vrate" na drugim mestima, a potez bez
eksplozije lobanje ne dodaje nista i ne trosi RNG (007->008).

`ChoosePositions` (removePreviousPieces=false):

- cilj = zbir `skullsPerActivation[min(i, len-1)]` za svako bacanje u partiji
  (`ActivatesThisTurn`), najvise `maxPieces`; `count` = cilj - lobanje na tabli
  (`SlotValue` 24). Tabla u mirovanju pre poteza vec ima pun cilj, pa ga simulator
  cita odatle.
- kandidat: obicna figura (`SlotValue` 0, nije live-event) cija boja je u
  `AllowedColors` (engine 6, 3, 5, 7, 8; .cctor 0x5a7c9d0).
- "matchable": sve celije svih combo-a iz `BoardAnalyzer.GetPossibleMoves(board, true)`,
  vracene na mesto pre zamene (b__13_4, b__11, b__12) -- isti skup kao
  `engine_billie._possible_pieces`.
- `count` puta `Chance(chanceToPickMatchablePiece)` (Solo 20) -> k.
- tri `GetSlotPrioritize` (prioritet b__13_5/7/9 uvek false: x-major, promesano,
  jedno izvlacenje po kandidatu): k iz matchable, ostatak iz ne-matchable, a sta
  i dalje fali iz bilo kog neizabranog kandidata.
- `ConvertToSpecials` ne izvlaci RNG. Hot Color +2 ide posle.

Port: `EngineRefill.joojoo_end_move`, poziva ga `strategy_lab.simulation.step`
posle shuffle provere i `ExactRefillSession.finish` (tabla posle poteza se sada
prati). Samo Solo (`rules.pvpMode == 1`); van Solo sansa nije snimljena, pa
`refill_monitor` tamo i dalje samo prijavljuje "JooJoo: N novih lobanja".
Hot Color research `20261112_001019`: 9 od 9 odigranih poteza tacno (tabla,
polja lobanja, RNG). Test: `tests/test_joojoo_passive_refill.py`.

Nije provereno: uslov `logic.moves < 1` (poslednji potez partije ne dopunjava),
redosled prema shuffle-u, Rumble/Versus (sansa 40 iz osnovne konfiguracije), i
014->015 (+1 lobanja bez zabelezenog unosa, verovatno nezabelezeno bacanje).

## Izvori

- `data/il2cpp_symbols.json` i `data/il2cpp_method_index.json`: nova mapa
  simbola (1573 klase, 7388 metoda, 155843 adrese).
- `Debug/reverse/libil2cpp.so`: SHA-256
  `d7b802c59c263d0a092d019c897fba53f663839b205e6bb947c46f43034aae46`.
  Bajtovi provereno odgovaraju biblioteci u
  `Debug/reverse/apk_5.817/split_config.arm64_v8a.apk`.
- `Debug/reverse/monkey/`: 64 ARM64 listinga, ukljucujuci pomocne lambde
  i metode prikaza; broj listinga nije broj zavrsenih analiza.
- `data/ability_config.json`: osnovni parametri i uslovni override-i.
- `Debug/booster_manual/01_magic_wand_20261031_221201/monkey_live_snapshot.json`:
  stvarni Monkey ID 40 u `mutation-lab-solo-mode`. Naziv foldera je ostao
  od inicijalne pripreme pre nego sto je korisnik izabrao Monkey.
  `ability_live.json` u istom folderu pripada prethodnom Doctor Coloru;
  NE koristiti ga kao Monkey izvor.

## Parametri

| polje | osnovno | Solo (potvrdjeno snapshotom) | Rumble override |
|---|---|---|---|
| cost | 7 | 7 | bez posebnog override-a |
| piecesAmount | 5 | 5 | bez posebnog override-a |
| autoExplodeAmount | 5 | 3 | bez posebnog override-a |
| chanceToPickMatchablePiece | 40 | 20 | bez posebnog override-a |
| skullsPerActivation | 5,3,2 | 4,1 | 4,2 |
| scoreTarget | 35 | 35 | bez posebnog override-a |
| maxTries | 5 | 5 | bez posebnog override-a |
| specialPieceScoreValue | 0 | 0 | bez posebnog override-a |
| removePreviousPieces | false | false | bez posebnog override-a |

`maxPieces=99` procitan je iz zive instance. Konfiguracija sadrzi
`max_booster_spend_per_game=5`, ali njegovu prakticnu ulogu ne tumaciti kao
dokazan limit aktivacija u partiji.

## Potvrdjeno statickim citanjem

- `get_BoosterPieceValueType` (RVA `0x5a7a7b4`) vraca **24**.
- `Use` (`0x5a7b09c`) poziva bazni `Ability::Use`, postavlja pasivnu
  sposobnost preko `GameLogic::SetPassiveAbility`, postavlja
  `WasJustActivated=true` i pravi do `maxTries` kandidata pozivom
  `ChoosePositions(logic, false)`.
- Ako ima vise kandidata, `Use` pravi klonove (`GameLogic::Clone`), poziva
  `ConvertToSpecialsAndAutoExplode` i cita skor preko trenutnog igraca.
  Poziva i `Ability::GetScoreTarget`. Lambda `Use>b__0`
  (`0x5a7d148`) vraca `-abs(candidateScore - scoreTarget)`.
  To potvrdjuje funkciju ocene; konkretan genericki selektor i sva pravila
  izjednacenja jos nisu razreseni.
- `RefillExplodedSpecials` (`0x5a7c610`) postavlja
  `WasJustActivated=false`, poziva `ChoosePositions(logic, true)` i zatim
  `ConvertToSpecials(..., unconvertExisting=false)`.
- `EndMoveWithPassiveAbility` (`0x5a7c650`) vraca false ako je
  `WasJustActivated=true` ili ako je `logic.moves < 1`. Inace bira pozicije
  sa ukljucenim `useChanceToPickMatchablePiece` i poziva konverziju bez
  uklanjanja prethodnih figura.

## Smerovi eksplozije figure

`MonkeyJoojooPieceLogic::GetAreaOfPieceExplode` (`0x5aeb64c`) bira smerove
prema `SlotModel.color` (offset `0x10`). Ako je boja `None=1`, prvo cita
boju table na `effectPos`. Zatim prosledjuje smerove u
`BoardModel::GetAreaOfEffectForDirections` sa oba bool argumenta postavljena
na true. Ovo su smerovi iz koda, a ne jos potvrdjena duzina zraka:

| boja engine-a | smerovi (dx,dy) |
|---|---|
| Green 3 | (-1,-1), (1,-1), (-1,1), (1,1) |
| Yellow 5 | (0,1), (-1,-1), (1,-1) |
| Orange 6 | (0,-1), (-1,1), (1,1) |
| ostale | (0,-1), (0,1), (-1,0), (1,0) |

Za tacan domet i tretman prepreka treba procitati zajednicki
`BoardModel::GetAreaOfEffectForDirections`.

## Ostalo za zavrsetak

1. ~~`ChoosePositions`~~ procitan 2026-11-12 (gore).
2. Razresiti genericke selektore u `Use`, nacin racunanja skora kandidata
   i ulogu `scoreTarget` u zajednickoj `Ability::GetScoreTarget`.
3. Procitati callback-e konverzije/automatskog aktiviranja: koje figure
   eksplodiraju odmah, kojim redom i kada se dopunjuju.
4. Procitati zajednicki domet eksplozije i pravila spajanja figura.
5. Proveriti na postojecim snimcima; ne proglasavati padom prekinutu
   sesiju skupom uspesno validiranih aktivacija.

## Incident tokom prikupljanja

Igra je pala tokom prve prijavljene aktivacije. Sacuvani `android_logcat.txt`
belezi `Il2CppExceptionWrapper`, SIGABRT, nit `gum-js-loop`. Uzrok na nivou
konkretnog poziva nije utvrdjen. Paralelni symbol agent je prethodno prijavio
timeout pri `script.load()`. Reader je zaustavljen; analiza iznad je offline.
Snimci posle poruke readera da je presao na novokonstruisani `GameLogic`
mogu pripadati simulacionom klonu i ne smeju se automatski tretirati kao
stvarna tabla igraca.
