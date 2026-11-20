# Plan: planer brzi i bolji (2026-11-20)

Samostalan plan za novu sesiju. Projekat: `C:\Users\PC\Desktop\memory gui` (Match Masters bot).
Pre rada procitaj `CLAUDE.md` u projektu (teske analize: sva jezgra preko `tools/gentle.py`,
izlaz u fajl, napredak u log; pun pytest sa procentom u fajl; kad igra koci ugasi svoje `python.exe`).

## Kontekst

- Bot cita igru iz memorije; `strategy_lab/simulation.py` (`step()`) je tacan simulator igre sa RNG-om
  (uzivo ~96 % proverljivih poteza tacno). `strategy_lab/planner.py` je beam search nad njim
  (`plan()`, `plan_anytime()`, `background_plan()`, `_rank()`, `WIDTHS`, `STOP_RULE`).
  Uzivo ga vodi `square_solo_live.py` (konstante budzeta oko linija 255-360: `FIRST_MAX_WIDTH`,
  `BG_MAX_WIDTH`, `FIRST_PLAN_STEPS`, `SOLO_PLAN_STEPS`, `CHARLES_BG_AHEAD`, `RESTART_PLAN_SECONDS`...).
- Spoljni pregled (drugi agent) i nase merenje: `docs/agent_odgovori/9_Planer_pregled_odgovor.txt`;
  pitanje sa merenjima: `C:\Users\PC\Desktop\prioritet_za_agenta\9_Planer_pregled.txt`.
- Merenja (Super Sized tabla `tests/fixtures/monkey_joojoo/20261120_111530_super-sized/003.json`, 1 jezgro):
  sirina 4: 0.9 s / 2 912 sim; sirina 10: 15.4 s / 44 576 sim, skor 866; sirina 25: 35.6 s / 93 856 sim,
  skor 808 (manje od 10!). 0.35 ms po simulaciji. Profil sirine 10 (43.7 s): `copy.deepcopy` 12.8 s (29 %,
  3 M numpy skalara), glavni pozivalac `simulation.step_move`:
  `after = deepcopy({k: v for k, v in move.items() if k != "engine_refill"})`; jos `deepcopy(move["board"])`,
  `deepcopy(move["special_board"])` na pocetku `step_move`; `simulation.rules` (context manager) 4.6 s;
  `engine_refill.fill_simulator_board` 8.4 s; `move_strategy._line_runs` 4.6 s.
- Uzivo (`Debug/memory_gui.log`, 699 "plan do kraja"): medijan 0.6 s, p90 2.4 s, p99 96 s, 42 plana > 10 s.
- Skripta za merenje/profil koju treba ponovo napraviti (bila u temp): ucitaj snimak preko
  `tools.analyze_research.load`, `simulator_capture.lab_move`, dodaj `capture_mode(...)` u
  `simulation.PREFIX_MODES`, pa `planner.plan(state, width=w)` za w = 4, 10, 25 i `cProfile` sirine 10.

## Odluke koje ceka korisnik

- Da li prvi plan da bude brz (< 1.5 s, pa dubok plan u pozadini od drugog poteza) ili ostaje
  sirina 25 (korisnikova ranija odluka: uze sirine merljivo gube, 25 > 10 na 39 od 41 table).
- Koliko jezgara sme planer uzivo (predlog: ostaviti 1-2 slobodna za emulator).

## Koraci (redom)

### 1. Ubrzanje bez promene rezultata (prvo, nulti rizik)
1. Napravi referencu PRE izmene: za ~20-50 snimaka (Solo fixture iz `tests/fixtures/*`) sacuvaj
   `plan(state, width=10)` -> (akcije, skor, broj simulacija) u JSON u scratchpad/Debug.
2. U `step_move` zameni `deepcopy` rucnom kopijom samo onoga sto se menja
   (`[row[:] for row in board]`, plitke kopije `turn_state`, `booster_state`, `perks` i ostalih dict-ova
   koje step menja); nepromenljivo po referenci. Grepuj svako mesto koje posle mutira `after[...]`
   ili deljene liste, da nista ne ostane deljeno.
3. Na ulazu u `plan()` (ili u `lab_move`) pretvori tablu i specijale u ciste Python `int` liste.
4. `rules(state)` postavljati jednom po `plan()` ako se pravila ne menjaju unutar partije
   (proveri sta tacno `rules()` postavlja i da li ga neki step menja).
5. Provera: rezultati identicni referenci (akcije, skor, broj simulacija). Izmeri vreme pre/posle.
   Pun pytest. Ocekivano ~1.6x.

### 2. Kvalitet: `_rank` vidi tablu + raznovrsnost beam-a
1. U `_rank` (samo za sortiranje beam-a, NE `line.value`) dodaj vrednost specijala na tabli
   (raketa, bomba, munja/disko, crosshair; puta `score_multiplier`) i bonus za susedni par specijala;
   eventualno penal za tablu sa 1-2 moguca poteza. Tezine kao parametri u stanju (kao `rank_move_value`).
2. Diversified beam u `plan()`: u prvih K koraka najvise M linija sa istim prvim potezom (start K=6, M=4 za sirinu 25).
3. Meri postojecim alatima: `tools/plan_stop_curve.py`, `tools/plan_width_curve.py`, `tools/replan_compare.py`
   (isti skup tabli, isti budzet; ukupni skor i koliko tabli bolje/gore). Upozorenje iz koda: ranija cena
   napunjenosti boostera u `_rank` (`rank_charge_value`) je POGORSALA rezultat -- tezine meriti, ne pogadjati.
   Teske analize preko `tools/gentle.py` sa napretkom u log fajl.
4. Zadrzi samo ono sto merljivo popravi (i da sirina 25 vise ne gubi od 10).

### 3. Vise jezgara (root parallelism)
- Prve akcije podeliti na N procesa, svaki svoj beam, na kraju max po vrednosti. Pool napraviti jednom.
  Uzivo ograniciti broj procesa (ostaviti jezgra emulatoru), nizi prioritet kao `background_plan`.
- Provera: isti ili bolji skor na skupu tabli, vreme / N.

### 4. Budzet vremena (po odluci korisnika)
- Ako korisnik zeli: prvi plan i restart posle promasaja sa rokom ~1.5 s (`finish_cut`), odmah pozadinski
  plan od stanja posle prvog poteza (vec postoji mehanizam `CHARLES_BG_AHEAD` / `_start_background`).
- `max_steps` po tacnosti moda (kraci gde dopuna cesce promasuje).

### 5. Kasnije
- Cython za vruce petlje (`_line_runs`, `fill_simulator_board`, `is_part_of_possible_highrank_combo`, `step_move`)
  uz test Cython vs Python na 1000+ poteza.
- Gruba ocena nepodrzanih akcija samo za prvi korak.

## Stanje repozitorijuma pri pravljenju plana
- Poslednji commit `db90e66`; necommitovano: monitor upisuje vrednosti nepoznatih specijala
  (`simulation.py` "tile values"), `tests/test_spray_se_port.py`, Froggy `specials_left_score`
  (`engine_froggy_placement.py`, `tests/test_froggy_specials_left.py`), `docs/agent_odgovori/*`.
  Pun pytest prolazi (1723 passed, 230 skipped). Commit samo kad korisnik trazi.
- Pravilo: kad korisnik nalepi odgovor drugog agenta, prvo ga sacuvaj u `docs/agent_odgovori/`;
  kad nesto o igri ne znamo, napravi samostalan fajl u `C:\Users\PC\Desktop\prioritet_za_agenta\`.

## Stanje 2026-11-20 ~16:00 (za novu sesiju)

Nista nije commitovano. Korisnik: commit tek kad trazi.

Uradjeno:
- Korak 1 GOTOV: `step_move` bez `deepcopy` (`_grid`, kopija samo `turn_state`/`booster_state`),
  `rules()` deli stalne prekidace (jednom po `plan()`, `board_layers=False`) od slojeva table.
  1.4x na Super Sized tabli (13.8 -> 9.8 s, sirina 10). Planovi identicni na 44 table
  (`tools/plan_reference.py`, referenca `Debug/plan_ref_before.json`). Pun pytest 1723 passed, 230 skipped.
- Korak 2 IZMEREN (`Debug/rank_sweep/*.log`, 44 table): `rank_special_value` 5 -> w10 +4.7 % (26 bolje/8 gore),
  w25 +5.1 % (19/7); 3: +2.9 %, 8: +5.4 % (25/10), 15: +3.5 %, 40 gore. `rank_pair_value` i raznovrsnost
  (`diverse_steps/_max`) ne pomazu. Kod je u `planner.py` (`_board_value`, `_diverse`), sve iskljuceno.
  SLEDECE: podrazumevano `rank_special_value` = 5 (konstanta u `_board_value` kad stanje nema kljuc).
- Korak 3 NAPISAN, nije meren: `planner.PLAN_WORKERS` (podrazumevano 1), `_plan_split`, `root_actions`,
  test `tests/test_planner_split.py` (2 passed). Odluka korisnika: jezgra "sta god je najbolje" -> predlog 4
  procesa samo za prvi plan u glavnom procesu, pozadinski 1. Meriti sekvencijalno (Pool radnici ne mogu
  imati svoj Pool): sirina 25 sa 1 vs 4 procesa (i 4 x sirina 7), kvalitet prema `Debug/rank_sweep/sv5_w25.json`.
- Korak 4: korisnik je odlucio da prvi plan ostaje sirina 25 (bez promene).
- Dustville (odgovor 10, `docs/agent_odgovori/10_Dustville_kaskada_odgovor.txt`): hici figure su sada
  unutar lanca specijala (`move_strategy._resolve_special_chain`, `fire_figures` posle svakog BFS koraka).
  Promasaj 20261120_092439 sada tacan; 091919 i 092004 (Froggy lotos) i dalje ne. Pun pytest posle ove
  izmene: 1726 passed, 230 skipped (2026-11-20). Rezerva starog fajla: `%TEMP%\move_strategy_before_dv.py`.

Odgovor 11 sacuvan (`docs/agent_odgovori/11_FroggyFu_lotos_trke_odgovor.txt`): postavljanje lotosa
(CompareAttempts, EvaluateAttempt, broj lotosa) i Pull su u portu vec tacni, nista nije menjano. Dve tvrdnje
odgovora odbacene jer port prolazi 23/23 snimaka (Pull kandidati su UNUTAR oblasti; smerovi Right,Left,Down,Up).
Lotos u engine-u je SlotValue 40; grana 23 u GetAreaOfEffectDestructionSlots nije lotos.
Odgovor 12 sacuvan: revert/stamp/GetSlotPrioritize se poklapaju; ubaceno samo `revert_lotuses` preskace polje iz
LotusPositions koje vise nije lotos (+ test). Mighty Mushrooms + Froggy: promasaji sa razlicitim RNG su SVI potezi sa
skupljanjem lotosa (003034 +84, 041307 +140, 052438 +32, simulator vise), ne obicni potezi.
Odgovor 13 sacuvan: skupljanje ide kroz jedan DestroyMatches (kao simulator). Ubaceno: lotos pogodjen eksplozijom
postaje rupa (`move_strategy` lanac i zamena dva specijala). Rainbow 211812/212012 posle toga i dalje razliciti,
pa strategy_lab i dalje odbija takav potez na Rainbow. Pun pytest posle Dustville i ove izmene: 1726 passed, 230 skipped.
Odgovor 14 sacuvan: dopuna (RefillSlots -> SpawningEngine) je ista kao kod nas; Mighty/MultiplierMushroomsBoard nemaju
override RefillSlots.
NADJENO (2026-11-20, lokalno): Mighty Mushrooms 041307 -- tabla posle Pull-a i prvi talas identicni igri (swap_traces
destroy_pass grid). Uzrok: Versus pragovi dopune (`simulator_capture.versus_adaptive_thresholds`, refillLogicOverride 0/0
-> adaptivna formula po razlici skora, maxDifferenceForPrevent 40) igra racuna sa SKOROM U TRENUTKU DOPUNE (poeni ovog
poteza vec dodati: igrac 2029 -> 3154, skupljanje lotosa = mnogo poena), simulator sa skorom s pocetka poteza.
Sa pragovima 100/100 041307 je TACAN (RNG 2419, sve boje i specijali). 003034 / 052438 / 044447 imaju jos nesto.
UBACENO: `EngineRefill.live_points` + `engine_refill.live_versus_thresholds` (pragovi pri svakoj dopuni sa skorom +
poeni do te dopune), `move_strategy._WAVE_LOG` (talasi akcije), `strategy_lab.simulation._live_points`. Svih 404
refill_misses: tacnih 286 -> 287 (samo 041307 promenjen, nijedan pokvaren). Empirijsko pravilo za pecurke na svih 404
ne menja nista ni sa ni bez njega -- ostavljeno (zasnovano na research snimcima van refill_misses).
Test: tests/test_versus_live_score_thresholds.py. Pun pytest: 1727 passed (+1 popravljen), 230 skipped.
REŠENO (2026-11-20): 003034 / 052438 / 044447 / 235847 / Column Mania 095618 tacni. Svih 404 refill_misses: 287 -> 292.
- Red rusenja posle skupljanja lotosa: GetPulledClusterPositionsList (prsten, mete redom povlacenja, lotos), pa ostali
  spojevi (`move_strategy._FROGGY_PULL_ORDER`).
- Pragovi dopune: formula iz 5.900 (odgovor 15), `simulator_capture.fill_all_empty_slots_thresholds`, pri svakoj dopuni;
  zamenila staro pravilo kraj ture / pecurke.
- Kraj ture: Froggy vraca lotose u boju (strategy_lab step). Odgovor 16: tok ture potvrdjen (bez dopune i RNG), ali
  pozivalac FroggyFu.Remove (svaka tura ili isteк trajanja) nije nadjen; 044447 je jedini takav snimak u refill_misses.
  Ako se pojavi snimak gde lotos PREZIVI kraj ture, simulator ce tu pogresiti -- tada traziti vtable PlayerControl
  +0x188/+0x198 i FroggyFu OnTurnEnd.
Testovi: tests/test_versus_live_score_thresholds.py. Pun pytest: 1733 passed, 230 skipped.
Na cekanju kod drugog agenta: nista za Froggy;
`3_AllAboardSE.txt` (bandit figura: simulator odbija svaki potez kad je na tabli), `6_DoctorColorSE_lightning.txt`.
Odgovor 8 (kaskada specijala) je sacuvan, nije ubacen u port.
Provera promasaja: `for d in Debug/refill_misses/2026...; python tools/trace_refill_miss.py $d` (danas 49 OK / 26 razlika).
Trke (Showdown/Rumble/Party): dopuna ne usporava (~24 poteza u trci sa i bez); log nema konacni skor --
korisniku ponudjeno da se doda upis skora na kraju partije (nije odgovorio).

## Stanje 2026-11-20 vece (za novu sesiju) -- Showdown strategija

Nista nije commitovano (commit tek kad korisnik trazi). Pun pytest: 1733 passed, 230 skipped.
Uradjeno danas (Froggy / Versus tacnost simulatora, odgovori 11-16 u `docs/agent_odgovori/`):
- lotos pogodjen eksplozijom postaje rupa (`move_strategy` lanac + zamena dva specijala; Rainbow i dalje odbija);
- red rusenja posle skupljanja lotosa (`move_strategy._FROGGY_PULL_ORDER`);
- pragovi dopune iz 5.900 (`simulator_capture.fill_all_empty_slots_thresholds`, pri svakoj dopuni u
  `engine_refill` fill, sa skorom do te dopune: `strategy_lab.simulation._live_points`, `move_strategy._WAVE_LOG`);
- kraj ture: Froggy vraca lotose (`strategy_lab.simulation.step`).
- Provera: `python Debug/live_score_check/run_all.py Debug/live_score_check/X.json` (svih 404 refill_misses,
  sva jezgra); poslednje: 292 tacnih (`final2.json`).

SLEDECI ZADATAK (korisnik: "simuliraj showdown i podesi najbolju strategiju"):
- Korisnik snima nove Showdown trke (Research + Dopuna ukljucena) u `Debug/research/<datum>_<mod>/NNN.json`.
  Sad postoje samo 3 (20261120_140316/140353 color-crush, 155006 multiplier-mushrooms) -- premalo.
- Napraviti alat (npr. `tools/showdown_strategy.py`, preko `tools/gentle.py`, napredak u fajl): svaku snimljenu trku
  odigrati u simulatoru od starta do kraja (start stanje kao `tools/best_line_search.start_state`: score, booster,
  perks, `time_left`, `action_seconds`), politika kao uzivo (`square_solo_live.py` RACE_*: RACE_TURN_START_SECONDS,
  RACE_PLAN_SECONDS, RACE_MIN_WIDTH, RACE_BG_*; `strategy_lab.planner.plan_anytime`), sat trke placa i vreme
  razmisljanja i `RACE_ACTION_SECONDS`. Prvo proveriti lanac: bot-ove akcije iz snimka odigrane u simulatoru
  daju skor igre (`best_line_search` "chain check").
- Uporediti varijante: budzet starta / kasnijih poteza, sirine, `rank_special_value` (5 i dr.), cuvanje/paljenje
  boostera, perkovi. Mera: konacni skor po trci, zbir i bolje/gore. Najbolje staviti kao podrazumevano u
  `square_solo_live.py` / planer, pun pytest, javiti korisniku tablicu.

## Stanje 2026-11-20 ~17:50 -- Showdown strategija izmerena

Alat `tools/showdown_strategy.py` (gentle_pool, napredak u OUT/napredak.txt): trka od snimka do kraja po zivoj
politici (prvi plan RACE_TURN_START_SECONDS + race pravilo, nosena linija, pozadinski plan RACE_BG_AHEAD unapred,
odbacen ako ne stigne do svoje table, sat placa razmisljanje i RACE_ACTION_SECONDS). `--every 4` = start i od
svakog 4. snimka. Ziva trka NE cuva booster (booster_hold samo na Charles putu) -- to je osnova.
Snimci: 172207 multiplier-mushrooms 1:1 (5539), 155006 lomi se na 3. potezu, 140316/140353 kratke.
Rezultat (`Debug/showdown_strategy3/rezultat.txt`, 12 startova, zbir): sada 57804, sv5 60550 (+4.8 %), sv3 59235,
sv8 57544, sv10 48438, cuvanje boostera 53655, start12 57268, bg_share 0.85 57376, bg5 54703
(run 2: bg2 / bg_share 1.0 / bg sirina 60 gore). Razlike su haoticne (ista podesavanja +-500 po trci od sata).
UBACENO: `planner.RANK_SPECIAL_VALUE = 5` podrazumevano (sve mode). Pun pytest 1733 passed, 230 skipped.
Za bolju meru: vise celih Showdown snimaka 1:1.

## Stanje 2026-11-20 ~18:40 -- Rainbow lotos, brzina sa Auto / snimacem

- Auto: `_request_dump` najmanje 0.4 s izmedju citanja (`DUMP_MIN_GAP_SECONDS`), tabla u pokretu se trazi tek
  posle 1 s bez snimka (`UNSTABLE_DUMP_AFTER_SECONDS`), dok igra protivnik 3x duza granica (test_dump_gap.py).
- Agent: `armBoosterDetail(false)` skida swap trace kuke (`removeSwapTrace`); js ponovo izgradjen frida-compile.
- Rainbow: skupljanje lotosa 1:1 (3 trke 18:02/18:03/18:13, 13 skupljanja, 42/42 prelaza; trka 18:13 cela 1:1).
  Skinuta zabrana u `strategy_lab.simulation.step` i `square_solo_live` ("izbor preuzima Froggy strategija");
  planer sada igra Rainbow. Simulirano od starta 18:13: planer 1383, bot 1217. I dalje odbijeno: eksplozija na
  lotos (refill_misses 211812 / 212012 = zamena dva specijala pored lotosa) -> pitanje 17
  (`Desktop\prioritet_za_agenta\17_Rainbow_lotos_zamena_dva_specijala.txt`). Pun pytest 1735 passed, 230 skipped.
- Odgovor 17 ubacen (zamena dva specijala + lotos, `_simulate_special_swap_candidate`): 212012 RNG tacan, 211812 ne;
  Rainbow i dalje odbija taj potez. refill_misses 292 -> 305 tacnih (`Debug/live_score_check/odgovor17.json`).
  Planer na Rainbow-u se vise ne gasi posle promasaja (samo Color Crush). Pun pytest 1735 passed, 230 skipped.
- Trka 18:51 Rainbow sa planerom: 1392 (bot ranije 1217 / 1122), cela 1:1. Prvi plan trke: "plan preuzak" sada po
  `full_width` (najsiri ceo prolaz), ne po sirini najboljeg plana (18:51:32 sirina 4 gora od 1 -> igrao bot).
- Crazy Columns + Froggy (research 20261120_185952): lotos stamp = rainbow(boja) x (kolona + 1) po skupljenom polju
  (`_froggy_stamp_points(by_column=True)`), 4 od 4; trka 2265 / 2266 (1 poen na potezu sa specijalima).
- Odgovor 18 sacuvan (nista ubaceno), pitanje 19 (put povlacenja kod merge swap-a) ceka drugog agenta.
- Lotos pogodjen eksplozijom NE postaje rupa (`move_strategy.LOTUS_HIT_BY_BLAST = False`): swap trace refill_miss
  20261120_191211 (Crazy Columns) -- GetAreaOfEffectByPiece bombe preskace lotos; i Rainbow research 181732 009.
  refill_misses 305 -> 307 (`lotus_hit_off.json`), nijedan pokvaren. Pitanje 20 (specijal grupe kod merge swap-a) ceka.
- Odgovor 20: specijal skupljene grupe kod merge swap-a se postavlja posle celog prolaza na svoje polje (Type 11
  prvi, pa MegaCombo). refill_miss 212012: tabla i specijali 1:1, RNG tacan, poeni +3; 211812 i dalje +16 RNG.
  Rainbow i dalje odbija taj potez. refill_misses 307 tacnih. Pun pytest 1735 passed, 230 skipped.
- `_simulate_booster_effect_cells` (Remove Cross, Charles, Brocco...) sada puni `cascade_color_counts`: na tabli sa
  mnoziocem svaki talas po svom mnoziocu. Multiplier Mushrooms 192514 000 (Remove Cross) 60 -> 98 = igra; trka 7853 1:1.
- Odgovor 22 (BlobMatchChecker): polje specijala kaskadnog kombo-a po listi kako je engine obilazi
  (`move_strategy._blob_listing`, kolona pa red, kvadrati, rekurzija). refill_misses 307 -> 313, 0 pokvarenih.
  test_versus_handover_board: 18 -> 15 (broj simulatora, bez snimka).
