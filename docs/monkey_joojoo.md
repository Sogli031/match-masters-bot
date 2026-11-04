# Monkey Joojoo (buster 40): analiza iz koda igre

Status: **delimicna analiza**, 2026-10-31. Nije ugradjeno u simulator.
Ovo nije tvrdnja da je celo pravilo procitano ili potvrdjeno aktivacijama.

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

1. Procitati `ChoosePositions` i njegove predikate: dozvoljene plocice,
   prioriteti, broj lobanja po aktivaciji, granicne situacije i nasumicnost.
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
