# Match Masters memorijski citac table

Citac je strogo read-only: Frida agent poziva IL2CPP metadata API, cita
`GameLogic.board` i 49 `SlotModel` objekata, i salje snapshot kroz `send()`.
Ne menja APK, polja table, poene, poteze, RNG, Magisk ili Play Integrity.

## Jedan snapshot

Pokreni iskljucivo Pie64 i igru, udji u aktivnu 7x7 partiju, pa iz korena
projekta:

```powershell
python .\tools\matchmasters_board_reader.py `
  --serial 127.0.0.1:5555 `
  --once `
  --output .\Debug\memory_board\board_snapshots.jsonl `
  --latest .\Debug\memory_board\latest.json `
  --screenshot .\Debug\memory_board\live_board.png
```

Kontinuirani reader:

```powershell
python .\tools\matchmasters_board_reader.py `
  --serial 127.0.0.1:5555 `
  --poll-seconds 0.25
```

Reader je zakljucan na `127.0.0.1:5555` i odbija offline
`127.0.0.1:5695` i `emulator-5554`. Automatski proverava verziju
`frida-server`, root, PID igre i `namespace_cleaned=yes`. Zatim se kaci u
Frida `emulated` realm, jer je Pie64 x86_64, a Unity/IL2CPP deo igre ARM64.

GUI dugme **Pokreni Match Masters** radi isti Pie64/ADB/root/namespace redosled
i pokrece kontinuirani reader. U izboru table:

- `Tabla: ML` uvek koristi postojeci ONNX recognition.
- `Tabla: Memorija` zahteva svezi `Debug\memory_board\latest.json`.
- `Tabla: Auto (memorija -> ML)` koristi memoriju, a ako reader nije dostupan
  ili je snapshot stariji od 5 sekundi bezbedno pada nazad na ML.

Agent se ponovo kompajlira posle izmene TypeScript izvora komandom:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_board_agent.ps1
```

JSON schema je u `tools\memory_board_snapshot.schema.json`. Snapshot sadrzi
samo stanje table i tehnicke adrese IL2CPP objekata; nema nalog, token niti
mrezne identifikatore.

## Stanje partije u snapshotu

Pored table, snapshot nosi i `state` blok procitan iz istog `GameLogic`
objekta: `moves`, `moves_made_this_turn`, `chain_reaction`, `game_state`
(`GameState` enum), `turns`/`turns_total`, `current_round`/`rounds_total`,
`current_player_index` i listu `players` (skor, `turn_score`, `energy` /
`energy_to_ability` = buster brojilac/imenilac, `score_multiplier`,
`rounds_won`, `slot_type`, `energy_colors`, `is_my_turn`). `state.rules` je
`MatchRulesModel`, tj. sam engine opisuje mod (`id`, `moves_per_turn`,
`turns_per_game`, `extra_move_enabled`, `colors_count`, `energy_mult`,
`destroy_row_on_horizontal_match`, `vertical_match_increase_multiplier`...).

Ime igraca se namerno nikad ne cita — snapshot ostaje bez identifikatora naloga.

Citanje stanja se ukljucuje iz hosta (`configure(..., includeState)`), pa agent
do tog poziva dira samo tablu. `--no-state` ostavlja citac na samoj tabli ako
neko polje stanja ikad napravi problem.

Dva pravila koja su ovde skupo placena:

- Sve sto ima polje se cita kao polje; metod se zove samo za ono sto engine
  racuna (`get_EnergyToAbility`, `get_CurrentRound`, `get_Rounds`).
- Svaki pristup ide kroz `usable()`. Bridge umota i NULL pokazivac u
  `Il2Cpp.Object`, a citanje polja sa takvog objekta rusi ceo proces igre.

## Memorijski GUI

`memory_gui.py` (prečica `Pokreni Memory GUI.bat`) je zaseban prozor koji cita
iskljucivo iz memorije — nema skeniranja piksela ni OCR-a. Sam se kaci na igru
(bez zasebnog reader procesa) i prima snapshotove push-om, pa tabla, skor,
potezi i buster dolaze direktno iz `GameLogic`.

Dugmad: **Pokreni Match Masters**, **Prikaci citac**, **Restartuj frida-server**
(za slucaj zaglavljenog servera posle pada igre), **Kalibrisi ekran**, pa
**Najbolji potez**, **Extra move**, **Najvise poena** i **Auto**.

Kalibracija je obavezna pre prvog poteza: memorija daje sadrzaj table, ali
swipe mora da zna gde je koje polje na ekranu. Za nekalibrisan BlueStacks
raspored svaki potez pada na `BoardCalibrationError`, sto nema veze sa
citanjem iz memorije. Kalibracija se cuva u `display_calibration.json` i deli
se sa glavnim GUI-jem. Sve tri akcije prave isti
`runtime.CheckBestMoveRequest` kao glavni GUI, sa istim lookahead vrednostima —
razlikuje se samo ulaz (`pre_scanned_board` iz snapshota, `board_source=memory`,
`screen_state_read=None`).

Red ispod moda: **Booster** (koji booster imas — ciljanje za High Voltage,
Magic Wand, Laser Beam, Dragon, Woolly Workout i UFO radi samo kad je tacan
booster izabran), **po memoriji**, **Booster odmah** (aktiviraj cim je spreman,
bez cekanja na extra move), **Juri plave** i **Debug zapis**.

**Juri plave** je podrazumevano iskljuceno: bot prvo uzima extra move potez.
Ukljuceno, plava se pojacava i extra tier vise ne preskace rangiranje, pa extra
mora da nadigra napredak na busteru (isti prekidac kao „Juri booster" u glavnom
GUI-ju, `showdown_booster_rush`). Vazi samo za Solo/Party/Showdown; u versusu se
ignorise.

Citac vidi koji booster igras kroz `PlayerModel.specialAbilityType`, pa se uz
**po memoriji** akcija bira sama. Mapirani su samo oni koji su sigurni po imenu
(`WoollyWorkout`, `UFOBeam`, `UFOBeamSE` — vidi `ABILITY_TO_BOOSTER_ACTION`).
Za nemapiran booster akcija se vraca na „bez akcije" i pored se ispise ime iz
igre (npr. „igra: Magic (nemapiran)"), da se mapa dopuni tek kad se potvrdi koji
je to nas booster. Pogresno pogodjeno mapiranje bi klikalo pogresno polje posle
Activate, pa se namerno ne nagadja. Debug je podrazumevano iskljucen jer snima pun
`Debug/runs` zapis; kad je ukljucen, GUI u log ispise putanju poslednjeg run-a.

### UFO SE: oci se broje iz igre, ne sa ekrana

Traka sa ocima iznad table se vise ne skenira. Ekranski brojac je promasio svih
12 UFO poteza iz sesije 2026-08-17 15:21-15:53, a lazni pozitiv u 15:53:32 je u
simulaciji pobrisao sve narandzaste plocice i prijavio izmisljen extra move.
`PlayerModel.activeSpecialAbilityType` isto ne moze da bude kapija: 49 se vidi
samo u kadru u kome traje animacija aktivacije, pa je sesija 2026-08-19
17:21-17:28 aktivirala UFO cetiri puta i svaka odluka posle toga je i dalje
citala 0 — abdukcija nije modelovana nijednom.

Umesto toga se cita sam buster, `SpecialAbility.Config.additionalParams`:

```
allowPickingBlues        False   (plava je POSLEDNJI izbor, ne zabrana -- vidi ispod)
allowPickingSpecials     False   (specijali ostaju na tabli)
specialPieceScoreValue   4
maxPassiveActivates      2       (oci opale na najvise 2 naredna poteza)
colorsToPickByActivation 2,2,1   (1. aktivacija 2 boje, 2. dve, 3. jedna)
```

`memory_gui.UfoAbductionTracker` od toga vodi evidenciju: aktivacija je pad
energije sa pune na nulu (ili uhvacen kadar sa `activeSpecialAbilityType=49`),
a oci se skidaju po odigranom potezu — koliko ih je stvarno opalilo javlja
`CheckBestMoveResult.ufo_abductions` iz intent zapisa. **U jednom potezu moze
da opali svako naoruzano oko** (`move_strategy.UFO_MAX_COLORS_PER_MOVE =
UFO_MAX_EYES`), ali samo na boju iz *direktnog* spajanja poteza, nikad iz
kaskade: snimci table 2026-09-12/13 pokazuju da swap koji spoji dve boje sa
dva naoruzana oka odnese obe u istom pasivnom prolazu, a swap sa jednom bojom
jednu, dok drugo oko ceka sledeci potez. (Ranije pravilo "najvise jedno oko po
potezu", izvedeno iz trace kadrova 2026-08-21, ostavljalo je fantomsko oko
posle svakog dvobojnog swap-a.) Sto ostane istekne posle
`maxPassiveActivates` poteza. Naoruzane oci **ne** zadrzavaju pun buster
(igrac, 2026-09-15; stari `ufo_pending_eye_gate` je uklonjen) — buster ceka
samo na siguran extra. Rangiranje poteza vec racuna sta oci odnose sa table.
**Plava ipak ide** (izmereno 2026-10-08, 15/15 poteza, Showdown i Solo
Challenge): ako je potez spojio samo plavu, oko odnese SVE plave i metar se
napuni u jednom potezu (0 -> 7); ako je spojio plavu i drugu boju, jedno oko
uzme drugu boju, dva oka uzmu obe. `move_strategy.UFO_BLUE_FALLBACK`.
Pre prve aktivacije endzin javlja `remaining_hud_eyes = 9` (sentinel); vise od
`UFO_MAX_EYES` se cita kao "nije naoruzano" (ispravka 2026-10-01).

Puna imena iz `IUFOBeamSEVariant` (izvucena iz `global-metadata.dat`):
`OnBeforeUse`, `TryHandlePassiveFire`, `GetPostBeamCallback`,
`GetMoveColorsTarget`, `GetRemainingMoveColorsToPick`, `GetRemainingHudEyes`,
`GetMoveColorsExplodedThisMove`, `SkipNextPassiveFireFromActivation` (potez u
kome aktiviras buster ne otima).

Da bi model jednom mogao da se zameni pravim brojacem, agent salje i
`special_ability_fields` — read-only pregled skalarnih polja zive
`SpecialAbility` instance (bez poziva metoda, isto kao mutation sweep). Od
2026-08-21 je i u `_ALLOWED_PLAYER_KEYS`, pa stize do hosta i vidi se u
`Debug/memory_board/latest.json`; tu treba da se pojave `PassiveActivates`,
`ColorsPicked` i `colorsToPick` kad se igra UFO.

Kad je **Debug zapis** ukljucen, agent prelazi u trace mod (100 ms poll) i
salje i NEsmirene kadrove izmedju dve stabilne table. Svaka akcija tako dobija
`Debug/runs/<run>/memory_frames.jsonl`: pun board + sirovi `slots` + skor,
energija i brojac poteza za svaki kadar dok se efekat odvija. To je jedini
nacin da se vidi sta je specijal ili buster stvarno ocistio — smirena tabla
stize tek posto je refil vec prekrio ocisc'ena polja. Citanje:

```powershell
python .	ools
ead_memory_frames.py .\Debug
uns\<run>
```

Prazna polja u kadru su ocisc'ena polja; kolone skor/buster pokazuju koji korak
kaskade je sta platio. Trace se gasi zajedno sa Debug checkboxom.

Iz memorije se, pored table, uzimaju i: legenda poena (`SlotModel.score` po
boji, zamena za Score Rally/Score Hero citanje sa ekrana), pravila moda
(`is_square_match`, `specials_auto_explode`, `vertical_match_destroy_color`),
Energized boje (`energy_colors`, bez plave), mnozilac pecuraka (po prisustvu
figure na tabli, jer vazi u svakom modu) i strategija (solo vs versus po broju
igraca).

**Ko sam ja u versusu** se odredjuje preko `PlayerClientControl.Type`
(`player_type=0` = Local), nikad preko `current_player_index` — taj kaze ko je
na potezu, pa bi na protivnikovoj polovini meca strategija dobila njegov skor,
buster i boju punjenja.

Auto ne meri pokret na ekranu: potez se igra kad engine kaze da sme —
`game_state=MovePlaying`, `is_my_turn`, `chain_reaction=0`, ima poteza i
snapshot je `stable`.

**Tajmer poteza.** `state.remaining_time` je engine-ov sopstveni odbrojavac
(`GameLogic.RemainingTime`, u sekundama), a `state.timer_paused` kaze da li
stoji. To je jedan od retkih getera koje agent zove: nista to ne cuva u polju —
`TurnTimer.RemainingTime` racuna `(timerDuration - stopwatch) / 1000` na svaki
poziv, pa bi citanje polja uvek davalo ceo budzet poteza umesto preostalog
vremena. Za mod bez tajmera (`is_timer=false`) geter vraca `timePerTurn` (1500),
pa se taj slucaj filtrira u agentu i polje ostaje `null`.

GUI od te vrednosti oduzima starost snapshota (procitana je u trenutku dump-a,
ne u trenutku odluke) i prikazuje je u redu **Tura**. Dva praga:

| ostalo | sta bot radi |
| --- | --- |
| `> 5 s` | normalno: perk i buster u igri |
| `<= 5 s` | samo obican swipe (perk/buster je vise klikova i tajmer ga presece na pola) |
| `<= 2 s` | ne igra nista — potez ne bi stigao do kraja |

Da odbrojavanje ne bi zastarelo, auto u tajmiranim modovima trazi svez dump kad
je snapshot stariji od 0.4 s. Agent salje samo kad se stanje **promeni**, a nasa
tura se ne menja dok bot razmislja, pa bi bez toga vreme tiho starilo.

**Protivnikov potez** auto prepoznaje sam, iz `is_my_turn`, i ceka; u logu se
javi jednom po turi, a red **Tura** stoji na `protivnikov potez`.

Mod se bira sam iz `state.rules.id` (mapa `RULES_ID_TO_MODE`); za nepoznat id
vazi rucno izabrani mod, a sirovi id se uvek prikazuje da bi se mapa dopunila.

## Poznata ogranicenja

- `GameLogic` postoji samo tokom aktivne partije. Na Home ekranu rucni dump
  namerno vraca `active Match3Engine.GameLogic not found`.
- Stabilan automatski snapshot zahteva tri identicna ocitavanja u razmaku od
  250 ms i ne salje ponovo isti hash.
- Nepoznata buduca `SlotValueType` vrednost ne rusi reader, ali se polje mapira
  kao obicno/nepoznato i belezi se upozorenje. Ako uz nepoznatu vrednost stoji
  `canBeMatched=false`, polje se mapira kao BLOCKED (`unmatchable_slot_value`
  upozorenje) — igra kroz njega ne pravi mec, pa bi citanje osnovne boje
  izmislilo poteze koje igra odbija.
- `SlotValue` 28 (`BroccoBoogiePiece`) je disko kugla koju ekranski put vec
  prepoznaje: free-swap, cisti boju partnera, ne puni buster na swapu. Do
  2026-08-17 je citana kao obicna figura svoje osnovne boje, pa je sim pravio
  meceve kroz nju (Debug/runs 2026-08-17_01-42-10: potez koji igra odbija).
- `snapshot.board_fields` je genericki, read-only sweep polja same `BoardModel`
  instance (isti mehanizam kao `rules.engine_fields`, bez poziva metoda). Sluzi
  da se nadju stanja koja mod drzi na tabli a ne na plocicama -- npr. Column
  Mania mnozioci po koloni, kojih nema u `SlotModel.score`.
- Od 2026-08-19 sweep vraca i *sadrzaj* polja tipa `List<int>` i
  `Dictionary<int,int>` (citano samo kroz `_items`/`_size` odnosno
  `entries`/`count`, bez poziva metoda). Zbog toga
  `FloorIsLavaBoard.ColumnsEruptionDictionary` -- brojac mecevanja po koloni,
  jedino stanje moda "The Floor Is Lava" -- stize kao `{"3": 1}` umesto kao
  oznaka tipa. Kljucevi su engine `x`, tj. vec nase kolone; host odbacuje
  kljuceve van table (`board_source.floor_lava_column_counts`).
- 2026-09-18: `Dictionary<int,int>` (i `extraData`) je do tada u praksi uvek
  stizao kao `{}`. Uzrok: citac je trazio polje `count` pre `_count`; polje
  `count` u ovom corlib-u ne postoji, `fieldValue` vraca `null`, a
  `Number(null) === 0` je "validan" broj, pa je petlja stajala na 0 elemenata.
  Popravljeno (null se preskace), a `Entry<int,int>` se od **scheme 4** cita
  sirovo (16 bajtova: hashCode, next, key, value). Uz recnik stize i
  `ColumnsEruptionDictionary__diag` (count, version, sirovi slotovi) i
  `lava_view` (tabla koju slusa `LavaBackground`; na zivoj partiji je to ista
  tabla koju agent cita).
- 2026-09-18, "samo memorija": memorijski GUI vise ne zove nijedan piksel
  detektor. Jelly zona se trazi samo kad neko u partiji ima JellySE (tip 60,
  `board_source.jelly_booster_in_match`) i nikad ne pada na detektor; perk
  slotovi se ne citaju sa ekrana; klik na ACTIVATE ide na fiksnu tacku panela
  (`runtime.BOOSTER_ACTIVATE_FIXED_POINT`, udeo u `booster_activation_region`)
  bez screenshota; Funky Tiles polja stizu kao `cell_types` (`CellModel.cellType`,
  Funky = 3, agent ih cita samo za board model 12) preko
  `board_source.funky_tile_cells`. Screenshot ostaje samo za "Debug zapis".
  Poznata rupa: perk potrosen pre kacenja GUI-ja na partiju koja vec traje.
- Znacenje brojaca, izmereno uzivo 2026-09-18: engine drzi unos za **svih 7
  kolona** kroz celu partiju, 0 = zemlja cela, 1 = slomljena; erupcija vraca na
  0; potez sa busterom ne menja nista. Zato recnik sa kljucevima bez ijedne
  jedinice znaci "nema oznacenih" i host mu veruje
  (`floor_lava_counts_are_authoritative`), a recnik bez kljuceva znaci
  neuspelo citanje i bot tada ostaje na svom brojacu.
- `SlotValue` 7 sa `status=0` je obicna munja. Potvrdjeno na slikama i sirovim
  slotovima iz Funky Tiles runova 2026-08-17_04-29 do `_04-32`; stari adapter
  ju je pogresno slao u granu za smerni vatromet i brisao iz `special_board`.
  Nenulti smerni statusi ostaju mapirani na cetiri pravca vatrometa.
- Live potvrda 2026-08-15 u aktivnoj partiji: svih 49 polja se poklapa sa
  ekranom (boje + 4 Color Crystal polja po poziciji i boji), `warnings` prazan.
  Slaganje ostalih specijala (linije, bomba, disco, lotus, metla) jos nije
  vidjeno uzivo jer ih ta tabla nije imala.
- Stanje partije potvrdjeno kroz tri poteza u `color-crystals` modu: potezi
  10 -> 9 -> 8 -> 7, skor 0 -> 3 -> 27 -> 30, buster 0/7 -> 3/7 -> 6/7, sve
  identicno ekranu. 20 s neprekidnog citanja na 250 ms nije srusilo igru.
- Versus jos nije proveren: dva igraca u `players`, protivnikov skor,
  `energy_colors` i runde preko 1 nisu videni uzivo.
- Posle izmene `.ts` obavezno pokreni `tools/build_board_agent.ps1`. Reader
  ucitava `.js`, pa stari kompajlat tiho radi umesto izmenjenog izvora.
