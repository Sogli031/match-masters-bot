# Zajednicka dopuna: nalazi iz koda 5.817

Status: port grane poslednje runde Square Match Solo je zavrsen i povezan sa
Strategy Lab simulatorom (vidi "Port i povezivanje" na kraju). Jos NIJE
potvrdjen prema prelazu snimljenom iz igre. Probni obracuni sa uniformnom
dopunom nisu validacija engine-a.

## Izvori i granice

- `Debug/reverse/simulator_all/Match3Engine.SpawningEngine_*.asm` i
  `Match3Engine.BoardModel_RefillSlots__059705d8.asm`.
- `Debug/reverse/doctorcolor_rules/square_engine_config_with_weights.json`:
  jednokratni dump tokom partije koju je korisnik identifikovao kao Square
  Match. Cita SAMO `LogicModel.Instance`, bez heap walk-a, bez poziva managed
  metoda i bez kontinuiranog readera. Agent se posle dump-a odvaja.
- `data/recorded_rulesets.json`: arhivirane MatchRules vrednosti. Za
  `square-match` sadrzi i `refillLogicOverride` i `_gemWeights` samo kao
  type-placeholder-e. Naknadna puna captura ih razresava (vidi dole). Ne mesati globalni
  LogicModel sa efektivnim pravilima trenutne partije.

Ponovljiv dump: `python tools/dump_engine_config.py --output PUTANJA.json`.
GUI/reader moraju biti odvojeni pre pokretanja. TS agent se kompajlira iz
`tools` direktorijuma komandom
`frida-compile il2cpp_symbols_dump.ts -o il2cpp_symbols_dump.js -T none -S`.

## Sta kod direktno pokazuje

`BoardModel::RefillSlots` poziva, ovim redom:

1. `CountFillingSlotsAndUpdateColorsDictionary`.
2. `FillAllEmptySlots` (RVA 0x5a08754).
3. `SuperFoceCombo`, uslovno na `ForceNextCombo`.
4. `SetScoreAndEnergyOverrides`.
5. `RandomSpawnSpecialSlots`.
6. `RandomSpawnLiveEventPieces`.

`FillAllEmptySlots` cita vise od same liste boja: globalnu spawn konfiguraciju,
razliku skora, preostale poteze, runde i `MatchRulesModel.refillLogicOverride`.
Ima obe grane izbora tezina (`createWeightsListNew` i `createWeightsList`),
izvlacenje preko engine `RandomWrapper::Range`, provere vec formiranog spoja
(`BoardAnalyzer::IsPartOfCombo`) i mogucih poteza/specijalnih spojeva.
Pomocni `CalculateWhileCondition` (0x5a0a370) takodje proverava moguce
high-rank spojeve; proveru kvadrata uslovljava `SquareMatchesAvailable`.

Zato osnovne jednake tezine boja nisu dokaz da su zavrsne plocice nezavisne
i uniformno raspodeljene. Konacni rezultat zavisi od preostalih uslova i
redosleda izvrsenja. Tacne formule prevencije jos nisu sve rekonstruisane.

## Procitane globalne vrednosti

| polje | vrednost |
|---|---:|
| LogicModel.chainReactionChance | 20 |
| LogicModel.chainReactionChanceReductionStep | 10 |
| LogicModel.maxChainReactions | 100 |
| LogicModel.colorScore / normalScore | 1 / 1 |
| LogicModel.limitBoosterCollectEnergyAfterUse | false |
| LogicModel.limitBoosterActivationOncePerTurn | false |
| spawn.isFixFill | true |
| spawn.rubberBanding | true |
| spawn.maxDifferenceForPrevent | 40 |
| spawn.preventMatchBaselineChance | 50 |
| spawn.preventComboBaselineChance | 50 |
| spawn.preventComboMinimumChance | 25 |
| spawn.preventMatchMinimumChance | 0 |
| spawn.moveScoreEstimate | 15 |
| spawn.priorityFactor | 1.5 |
| spawn.newBoardGeneratorChance | 100 |
| spawn.newColorPickLogic | true |
| spawn.colorPickmaxPoolSize / colorPickMaxPoolUnit | 70 / 10 |
| spawn.wantedPossibleMatchesMin / Max | 4 / 8 |
| spawn.wantedPossibleSpecialMatchesMin / Max | 1 / 3 |

`spawn.gemsWeights` ima vrednost 1 za engine boje 2..8.
`initialSpawnParams.gemsWeights` i `possibleMatchesColorWeights` imaju 100
za boje 2..8. To je globalni katalog: ne znaci da je White dostupan u
Square Match partiji sa sest boja. Aktivni `gameColors` i override-i jos
treba da se ukljuce u rekonstruisani model.

`initialSpawnParams`: possibleMatches 5..9, row/column odds 50, bomb odds 40,
lightning odds 30, square odds 50. Ovi parametri nisu isto sto i prevencija
u redovnoj dopuni.

## Stanje redukcije kaskada

- `ResetChainComboReduction` (0x59fb7a4) postavlja
  `SpawningEngine.ChainReactionReduction=0` i pravi novu `spawnedColors` mapu.
- Direktni pozivi resetovanja postoje u `GameLogic::PerformSwap`,
  `PerformAbilityActivated`, `PerformBoardAbilityActivated`, `PerformUseAbility`
  i `PerformUseBoardAbility`.
- `IncreaseChainComboReduction` (0x59fb900) dodaje
  `configData.chainReactionChanceReductionStep` na stanje redukcije.
  Za sam taj metod nisu nadjeni direktni `bl` pozivi; treba proveriti inlining
  i mesta pisanja polja pre tvrdnje kada se povecanje zaista izvrsava.
- `GetChainComboReduction` (0x59fb898) vraca float `min(100, stanje)`.

## Pre vernog porta

1. Razresiti efektivne `refillLogicOverride`, `_gemWeights`, weightsRandomizer
   i initialSpawn override-e, uz potvrdu pravog rulesId trenutne instance.
2. Procitati obe formule tezina i njihove granicne slucajeve, redosled rupa,
   ponovne pokusaje, fallback i sve grane prevencije kvadratnih spojeva.
3. Portovati engine RNG uz eksplicitno stanje i broj potrosenih izvlačenja;
   Python seed nije isto stanje kao engine seed.
4. Razresiti specijalne/live-event figure i overrides po boji; ne ubacivati
   lobanje/pecurke na osnovu mesane statistike `mode=None`.
5. Porediti deterministicke prelaze sa snimcima pre statistickog rangiranja.

## Puna Square Match captura i razreseni override-i

`Debug/match_captures/20261031_223909_674630/profile.json` sadrzi kompletno
dekodirane obuhvacene objekte, RNG matricu i izabranu partiju (bez managed
poziva). Dva citanja state/rng/rules/slots bila su jednaka. Obuhvacena polja
nemaju nerazresena citanja. To nije potvrda svih buducih stanja ili atomskog
snapshot-a svih niti.

`refillLogicOverride`: disableFirstRoundLogic=false, svi prevent*Chance=0.
`_gemWeights=null`, `weightsRandomizer=null`, `_colorEnergyOverride=null`,
`specialPiecesWeights=null`, `disableMatchPrevention=false`.
`_colorScoreOverride`: engine Green=2, Orange=3, Purple=4, Yellow=5.
`maxBoosterUsesPerTurn=0`.

Efektivni `spawning.initialSpawnParams` vec sadrzi primenjeni plavi override:
gemsWeights[Blue=4]=130 (ostale 100), possibleMatchesColorWeights[4]=120
(ostale 100). Ne primenjivati isti override jos jednom na te efektivne vrednosti.
`gameColors` je [4,3,2,5,7,6], dakle bez White.

Vazna grana: `get_Rounds` (0x59441f8) vraca ceil(Turns / players.Count),
`get_RoundsTotal` (0x59440c8) vraca ceil(TurnsTotal / players.Count).
U capturi oba daju 1. Na 0x5a08bdc `FillAllEmptySlots` proverava jednakost;
ako je override null ili mu je disableFirstRoundLogic=false, prelazi na
0x5a08d8c, gde postavlja match/combo/special thresholds na 100, a square na
100 kad je SquareMatchesAvailable=true (inace -1).

Zato nule u sirovom override-u NISU efektivni pragovi ove grane. RNG provere
su `Range(0,100) <= threshold`. Ovo ne garantuje odsustvo svih spojeva: dalje
postoje pokusaji, ogranicenja i fallback koji se moraju preneti odvojeno.

`simulator_capture.resolve_square_overrides` sadrzi ovu ogranicenu,
testiranu interpretaciju. Izvedeni paket je
`Debug/match_captures/20261031_223909_674630_resolved/`; u njemu su
`resolved_overrides.json` i prevedene vrednosti poena. Pun simulator i dalje
ima full_simulation_ready=false dok se ne zavrsi port dopune.

## Port i povezivanje (2026-11-01)

`engine_refill.SquareRefill` prenosi `FillAllEmptySlots` za granu poslednje
runde. Ponovo procitano iz ARM64 (0x5a08754, 0x5a0a370, 0x5a07a48):

- Rupe idu redom y pa x (`Point.x` je nizih 32 bita, spoljna petlja je Rows).
- Po rupi: cetiri `Range(0,100)` (pragovi iz override-a +0x14/+0x18/+0x1c/+0x20,
  tj. match, combo, special combo, square), `GetColorsPriority` (po jedan
  `Next` za Red i Blue), `createWeightsListNew`, jedan `Range(0,100)` za boju.
  Sa sest boja to je 7 izvlacenja po rupi.
- `CalculateWhileCondition` proverava treci, drugi, prvi pa cetvrti prag:
  special combo -> formiran spoj sa vise od 3, combo -> `IsPartOfCombo`,
  match -> moguc high-rank obrazac 1, square -> obrazac 2 (samo kad je
  `SquareMatchesAvailable`). Codex-ova verzija je imala zamenjena prva tri;
  u ovoj grani su svi pragovi 100, pa rezultat nije bio pogresan.
- Ponovni pokusaji idu od pocetka liste prioriteta i staju kad se lista
  potrosi, cak i ako poslednja boja jos pravi spoj.
- `ForceNextCombo` grana (polje +0x10) mesa `gameColors` engine RNG-om i
  namerno trazi spoj; nije portovana i baca `UnsupportedRefill`.
- Posle dopune: `RandomSpawnSpecialSlots` ne vuce RNG kad je
  `specialTilesData` prazan, `RandomSpawnLiveEventPieces` se vraca pre
  izvlacenja kad je tabela sansi null. `BoardAnalyzer::GetCombosFromTestList`
  zove `Chance` samo kad je `matchCreatesSpecialChance >= 1` (Square: 0).

Adapter boja: simulator 99 je disco (SlotColor.All), ne None; Codex-ova mapa
je to mesala. Sada su disco i blokeri nepodrzani, a most vazi samo kad je
lokalni igrac engine Blue (bez permutacije boja).

Povezivanje: `move_strategy.engine_refill_active(callback)` posle svake
simulirane gravitacije (`_drop_and_refill`) puni rupe, pa se kaskade nastavljaju
na punoj tabli kao u engine-u. Bez callback-a sve radi kao ranije (rupe ostaju,
granica nepoznate dopune). Kesiranje simulacija je iskljuceno dok je aktivan.
`simulator_capture.lab_move(load_capture(DIR))` daje Strategy Lab stanje sa
modelom; `strategy_lab.simulation.step` tada vraca `metric="cleared_tiles"`,
pun potez i model sa pomerenim RNG-om (ulazni model se ne menja).
`spawnedColors` se brise na pocetku svakog poteza (ResetChainComboReduction).

## Provera prema igri

Potrebna su dva snimka iste partije: pre poteza (tabla miruje) i posle istog
poteza (tabla ponovo miruje, pre sledeceg poteza). Snimci se prave sa
`Snimi partiju za simulator.bat`. Zatim:

    python tools/verify_refill.py PRE_DIR POSLE_DIR [--move red,kol:red,kol]

Bez `--move` probaju se svi legalni potezi. Poklapanje mora biti na tabli,
specijalima, RNG brojacu i `spawnedColors`. Jedno poklapanje je dokaz za taj
prelaz; vise prelaza (obican potez, kaskada, dopuna iscrpljene liste) treba
pre `full_simulation_ready=true`.

Poznate granice: samo Square Match Solo u poslednjoj rundi, bez disco/live-event
figura i bez `ForceNextCombo`. Kaskade, mesto stvorenih specijala i sam
pronalazak spojeva dolaze iz postojeceg `move_strategy` simulatora, ne iz porta
engine-a; razlika u tim delovima ce se videti kao nepoklapanje table.

## Rezultat provere (2026-11-01)

Devet snimljenih prelaza Square Match Solo (tri partije, `Snimaj poteze (Enter).bat`)
poklapa se tacno: tabla, specijali, RNG brojac i `spawnedColors`. Pet obicnih
poteza (jedna dopuna) poklopilo se bez dodatnih pravila. Kaskade traze dodatna
engine izvlacenja pre dopune koja sledi: tri kaskade sa jednim spojem po 1,
jedna kaskada sa dva spoja (i aktivacijom horizontalnog specijala) 2. To vazi
i bez Blue spoja i pri punoj energiji, pa nije vezano za energiju/Doctor Color.

`SquareRefill.fill(board, chain_combos)` zato pre punjenja povlaci po jedan
`Next()` za svaki spoj unisten u kaskadi (spojevi igracevog poteza se ne
broje); `move_strategy._drop_and_refill` prosledjuje taj broj iz svake petlje
kaskada. Nije razdvojeno da li drugi broj potice od drugog spoja ili od
aktivacije specijala. Ovo je EMPIRIJSKO pravilo: izvor u kodu nije nadjen
(proverene `DestroyMatches`, `GetAllCombos`/`GetCombosFromTestList`,
energija i poeni, `BridgeRngTrace`, repni skokovi u RNG). Ostali kandidati su
virtuelni pozivi u `DestroyMatches` (tabla +0x278, logika specijala +0x258,
igrac +0x68/+0x268 posle prve dopune). Nije vidjena akcija sa tri ili vise
dopuna. Spoj u obliku L/T je u engine-u jedan ComboModel; ako ga simulator
broji kao dve grupe, to ce se videti kao jedno izvlacenje viska.
`tools/verify_refill.py` pri nepoklapanju sam proba "+1 izvlacenje pre dopune N".

Dopuna 2026-11-01: 24 od 24 snimljena prelaza (pet partija) poklapaju se tacno,
ukljucujuci potez sa tri dopune (dve kaskade sa po jednim spojem, ukupno 2
dodatna izvlacenja) i kvadrat koji pravi crosshair (engine SlotValue 8,
simulator `SPECIAL_CROSSHAIR`). Potezi sa boosterom/perkom nisu podrzani.

## Poeni, planer i Square Solo GUI (2026-11-01)

Poeni Square Solo = zbir vrednosti svih unistenih figura po boji
(`score_values` iz `_colorScoreOverride`, ostale boje 1); 26 od 26 snimaka.
Sa tacnom dopunom extra potez daje i cetvorka iz kaskade, i kvadrat
(`result.extra_moves`); `tools/verify_refill.py` sada poredi i skor i poteze.

`strategy_lab/planner.py`: beam pretraga nad tacnim simulatorom, do poslednjeg
poteza (ukljucujuci extra). `plan_anytime` prvo napravi uzak pun plan pa siri
dok ima vremena. Pretrazuje samo zamene: booster, perkovi i aktivacija
nasumicnih specijala nisu portovani. Plan vazi samo ako se igra tacno njim.

`Pokreni Square Solo.bat` / `square_solo_gui.py`: snimi -> proveri predvidjanje
-> isplaniraj -> prevuci (kalibracija i swipe iz Memory GUI-ja). Auto staje kad
se igra ne poklopi sa simulatorom, kad nema poteza ili podrzanog poteza.

## Booster i perkovi u planeru (2026-11-01, NEPROVERENO na snimcima)

`strategy_lab.simulation.step` zna i za `kind`: `energy_boost` (perk 22, pa
swipe; puni energiju svim unistenim figurama), `teleport` (perk 3, bilo koje
dve figure) i `booster` (Doctor Color, 27). Energija (Blue figure, max 7) se
poklapa na svih 32 snimljena poteza. Doctor Color: dostupne putanje se mesaju
glavnim RNG-om (Next po putanji), uzimaju prve 3, a izbor je prvi Next svezeg
RandomWrapper(seed) po modulu broja kandidata (DoctorColor.Use 0x5a38878).
Pretpostavke koje snimci tek treba da potvrde: Teleport i booster ne trose
potez, Energy Boost broji i kaskade, redosled get_ColorPaths iz beleske.
Specijal iz kaskade ide na poslednje polje x-major prolaza (kvadrat iz
kaskade, snimak solo_gui_20261101_004944/04).

Ispravka 2026-11-01 (snimci solo_gui_20261101_010124): Teleport je potvrdjen
(ne trosi potez, tacno poklapanje). Doctor Color NIJE potvrdjen i planer ga
iskljucuje (`planner.PLAN_BOOSTER = False`): igra izmedju koraka prebojavanja
razresava spojeve i dopunjava, a veliki spojevi posle prebojavanja prave
specijale sa nasumicnim metama koje simulator jos ne racuna. Potvrdjeno:
booster ne trosi potez, cetvorka u njegovim kaskadama ne daje potez, energija
ostaje 0 (kaskade boostera ne pune).

## Svi modovi (2026-11-01)

`engine_refill.EngineRefill` (staro ime `SquareRefill` i dalje radi) vise nije
vezan za Square Match Solo:

- Grana poslednje runde (`simulator_capture.resolve_refill_overrides`) vazi za
  svaki mod: provera 0x5a08bdc cita samo brojace rundi i `refillLogicOverride`.
  Potvrdjena je samo na Square Solo; ostali modovi se proveravaju snimcima.
- Van poslednje runde adaptivna formula pragova NIJE portovana. `lab_move(...,
  thresholds=...)` prima pretpostavljene pragove, a `threshold_hypotheses`
  nudi kandidate (100, -1, sirovi override, spawn baseline/minimum). Cetiri
  `Range(0,100)` po rupi se vuku bez obzira na prag, pa poklapanje sa igrom
  pokazuje koju vrednost engine koristi.
- Boje: `engine_refill.color_maps` primenjuje istu permutaciju igraca kao
  `board_source` (nasa boja = simulator BLUE, protivnikova = RED), pa versus i
  partije gde nismo engine Blue vise ne odbija.
- Mod se cita iz memorije: `simulator_capture.capture_mode` koristi isto
  mapiranje kao Memory GUI (rules id, board model, rule flagovi). Modovi van
  `strategy_lab.simulation.PREFIX_MODES` se prijavljuju kao nepodrzani.

`Proveri dopunu (Enter).bat` / `verify_refill_gui.py`: Enter (ili F8 iz igre)
snima, odmah poredi sa prethodnim snimkom i vodi zbir po modu i po hipotezi
pragova. Isti par snimaka bez odigranog poteza se prijavljuje kao takav.
Regresija posle promene: 47 od 47 snimljenih odigranih poteza i dalje se
poklapa; 3 para bez poteza i 1 Doctor Color (poznato nepodrzan) ne.

## Square Solo u Memory GUI-ju (2026-11-01)

Agent koji Memory GUI vec koristi ima novi RPC `matchProfile(full)`
(`tools/matchmasters_board_dump.ts`): pravila, `config` (bez kataloga),
`spawningEngine`, RNG, brojace rundi i igrace (samo poeni/boja/energija,
bez naloga). Cita samo polja, kao `capture_match`; Memory GUI vise ne mora
da se gasi da bi se procitale tezine i RNG. Prethodni build agenta je
`tools/matchmasters_board_dump.js.pre-match-profile`.

`square_solo_live.LiveSquareSolo` (Memory GUI, `SQUARE_SOLO_EXACT_PLAN`):
u Square Match Solo, pre svakog "best move" poteza, procita profil, napravi
`EngineRefill` i pusti `strategy_lab.planner` do kraja partije (6 s, manje
ako sat istice). Planerov swap ide na vrh rangiranja
(`runtime.promote_engine_plan_move`); booster/perk logika bota ostaje.
Sledeca tabla proverava predvidjanje (tabla, specijali, RNG brojac); prvo
pravo nepoklapanje iskljucuje planer do kraja partije. Svaka greska u ovom
putu ostavlja obican potez bota. Offline: 24/24 snimljena prelaza se kroz
live putanju predvidjaju tacno.

## Istrazivacki snimac (2026-11-01)

Prekidac "Snimaj svaki potez" u Memory GUI-ju (podrazumevano iskljucen; iskljucen
ne snima nista): posle svake promene table (bilo koji mod; Auto, dugme ili potez
rukom, bez cekanja pred potez; propustena tabla se obelezi kao
`missed_board_before` i analiza taj prelaz preskace)
`research_recorder.ResearchRecorder` saceka da igra miruje
(GameState -5, RNG isti u dva citanja), uzme svez `dump_board` i profil iz
agenta i snimi `Debug/research/<vreme>_<rules id>/NNN.json`. Izbor poteza se
ne menja. `python tools/analyze_research.py [FOLDER]` za svaki par proba sve
swap-ove (i hipoteze pragova van poslednje runde) i pise `analiza.txt`.
Panel "Dopuna" na dnu Memory GUI-ja (`refill_monitor`) pokazuje da li bot koristi
dopunu, da li ima podataka i koliko pogadja. Provera ide u posebnom procesu jer
`move_strategy` drzi pravila i dopunu u globalnim promenljivama; i bez prekidaca
cita table, ali tada u `Debug/research` ne pise nista. Promasaj se uvek cuva u
`Debug/refill_misses/<vreme>_<rules id>/` (000 pre, 001 posle; radi
`tools/analyze_research.py FOLDER`). Aktiviran krstic/munja se broji kao
neproverljivo (nasumicne mete nisu portovane).

Hot Color (2026-11-02, snimak `20261102_212038_hot-color`): `specialTilesData` je
Bomb (6) sa istim poljima kao Rainbow Heart i ide istom granom. Tabla se poklapa
i kad igra potrosi jos 2 izvlacenja posle poslednje dopune: to je promena vruce
boje (`onMoveEnd`). Potvrdjeno na `20261102_214618_hot-color`: svih 8 poteza sa
+2 menja `currHotColor`, a nijedan od 5 potpuno tacnih ne menja.
Planer NIJE ukljucen: vruca boja nije u poenima planera, a deo poteza cisti polja
koja simulator ne cisti (npr. 001->002: raketa od tri iste figure).

Cekanje izmedju poteza (partija 2026-11-02 22:17): konacna tabla stigne u memoriju
oko 1.2 s pre nego sto engine otvori potez (-7 -> -5). Sa dopunom je tabla stajala
otvorena 6.15 s pre sledeceg poteza umesto oko 2.2 s. Ispravke: u Solo Challenge se
potez ne racuna pre -5 (taj plan se igrao bez dopune), dug sat vise ne menja kljuc
plana, a svako ponistavanje se upisuje u log ("Racunanje ponisteno: ...").

Billie Boom (2026-11-02, snimak `20261102_230448_column-mania`): pre drona 5 od 6,
sa dronom 5 od 11 ukupno. Dron stoji, ali posle poteza igra troši +14 do +23
izvlacenja i pravi bombe. To je ranije merenje nad delom snimka. Naknadni port
pasivne grane i precizno razdvajanje od usisavanja opisani su na kraju dokumenta.

UFO oko (snimak `20261102_225912_hot-color`): promasaji su bili odmah posle boostera.
Uz `ufo_abduction_active` simulator daje tacnu tablu, pa partija ide sa 13 od 25 na
21 od 25 (`212038` sa 13 od 20 na 17 od 20); provera proba 0, 1 i 2 oka jer snimak ne
cuva broj. `simulation.step` ove poteze odbija kao nesigurnu granicu, pa provera za oko
koristi direktnu simulaciju. Predvidjanje se sa okom namerno ne gasi; preostali
promasaji idu u `Debug/refill_misses` dok se ne objasne.

Extra posle oka: uz tacnu dopunu oko vise nije granica, pa se cetvorka iz kaskade
posle njega racuna kao extra. Na 75 odigranih UFO poteza extra je predvidjen tacno i
pre i posle ove izmene, ali nijedan od njih nije bio takav slucaj, pa sam slucaj jos
nije potvrdjen partijom.

Drugo oko: boje dolaze i od figura koje raznese specijal, ne samo iz spoja. Prvi
aktiviran specijal se cita po kolonama zdesna ulevo, u koloni odozgo, pa lanac
(`_ufo_blast_colors`, samo uz tacnu dopunu). Izmereno na snimcima, nije potvrdjeno
disasemblerom. Svi UFO snimci: 55 od 63. Otvoreno: dve bombe (`231940` 006, `212038`
007, boje {5,6} i {4,6}) i `225912` 017/023/034, `231940` 019/020, `212038` 002.

Prioriteti sa dopunom (`move_strategy.exact_refill_choice`, poslednji korak u
`runtime`): extra ovog poteza, pa najvise plavih koliko booster jos prima, pa potez
koji ostavlja extra na sledecoj tabli; redosled bota resava izjednacenja. Booster,
perkovi i lotus se ne diraju. Log: `[dopuna: extra|plave|namestanje]`.

Prekidac "Dopuna ukljucena" (podrazumevano ukljucen, vazi do zatvaranja prozora):
iskljucen gasi dopunu u rangiranju, tacne planere, proveru i citanje za njih.
Rezultati provere idu i u `Debug/memory_gui.log` (linije "Dopuna: ...").

Obican izbor poteza (2026-11-02), samo Solo Challenge, svi modovi sa podacima:
`move_strategy.exact_refill_active` + `engine_refill.ExactRefillSession` daju
rangiranju tacnu dopunu. Kandidat na igranoj tabli krece od zivog RNG-a, a
kandidat na tabli na kojoj je zavrsio simulirani potez nastavlja od RNG-a tog
poteza, do `MAX_FOLLOWED_PLIES` poteza unapred (dublje bez dopune, jer svaka
simulacija zaobilazi kes). Hot Color: rotacija trosi 2 izvlacenja kad potez
ocisti vrucu boju; boja posle `next` nije poznata pa se ta linija prekida.
Specijalna polja: bilo koja jedna vrsta ide granom `_spawn_special_tiles`.
Na Hot Color tablama (20/4/6) oko 2.4 s umesto 0.6 s.
`square_solo_live.exact_refill_session` cita memoriju jednom, bez cekanja: tabla
koja nije mirna ili neprenet slucaj ide obicnim putem.

Mesto specijala iz kaskade (2026-11-03): nije fiksno. Bira ga ono izvlacenje po spoju
koje `EngineRefill.fill` trosi pre dopune: polje = izvlacenje % broj polja spoja, a polja
i spojevi idu po kolonama, pa odozgo (`_created_special_cell`, samo uz tacnu dopunu).
Izmereno na snimcima, nije potvrdjeno disasemblerom. Na 18 + 5 snimljenih partija:
21 promasaj popravljen, nijedan pogodak pokvaren. Poredak spojeva je izabran od sest
probanih, a L oblik je potvrdjen samo jednom. Kvadrat `211420` 24 je sada pogodjen, a
`024539` 18 takodje; `211420` 31 i dalje promasuje.
Zamena dva specijala sa 2 oka (2026-11-03): prvo oko uzima boju prevucene figure, drugo
boju drugog specijala. Snimci `212038` 006, `231940` 005 i `234242` 002 sada daju tacnu
tablu, a nijedan pogodak nije pokvaren (svih 216 UFO poteza). Izmereno, nije potvrdjeno
disasemblerom. Stari test u `test_ufo_eyes.py` ocekivao je drugo oko iz kaskade; njegovom
fixture-u nije nadjen izvor u snimcima, pa je promenjen.
Dopuna u svim modovima (2026-11-03): uz ukljucen prekidac dopuna vise nije vezana za Solo
Challenge, a potez se u svakom modu racuna tek na mirnoj tabli (`_prepares_ahead`). Iskljucen
prekidac vraca obican rad. Van poslednje runde formula pragova i dalje nije preneta, pa tamo
sesije nema i bot racuna obicnim putem, a razlog ide u log. Sa protivnikom se linije ne prate
dalje od jednog poteza, jer protivnik trosi isti RNG.

Color Crystals (2026-11-03, `005008`): kristal je engine vrednost 18, ista grana specijalnih
polja kao bomba. 20 od 21 proverljivog poteza. `015`, potezi 3->4, ostaje promasaj.

Disko kugla (2026-11-03, `005457` Drill Down): slot zadrzava boju ispod kugle i dopuna je broji
(na tabli se vidi samo 99). Probom svih boja 7 od 8 promasaja daje tacnu tablu; `003` ne daje.
Boja se sada cita iz sirovih slotova (`profile.ball_slots`), pa stari snimci nemaju boju i na
njima ti potezi ostaju promasaji. Potvrdjeno snimkom `010847`. Aktivirana kugla odmah izlazi sa
spiska po svom polju (`ball_spent`), jer druga moze da padne bas na to polje (`010847` 010). U
Drill Down aktivacija kugle busi samo njenu kolonu, od kugle nadole. Kugla prevucena na specijal
se spaja s njim: specijal ostaje na svom polju i tu se aktivira (`010847` 009; vidjen jedan takav
potez sa promasajem, ostalih 90 pogodaka sa kuglom se nije promenilo).

Pecurke (2026-11-03, `013455` Drill Down): pecurka je engine vrednost 19 i ide granom specijalnih
polja (spawnChance 30). Snimak `013829`: svih 6 parova koji su tacno jedan potez bez perka je pogodjeno;
ostali promasaji su parovi preko vise poteza (005, 006, 011) ili potez sa perkom (002).

Dubina pretrage van Solo Challenge (2026-11-03): uz ukljucenu dopunu svuda sem Solo Challenge ide
10/2/3. Merenje na 200 snimljenih tabli (50 van Solo Challenge, 150 iz Solo Challenge; versus snimaka
nema, a pravila moda nisu bila primenjena): 12/3/4 0.92 s, 14/4/6 4.05 s, 10/2/3 0.24 s, 6/2/3 0.16 s;
isti potez kao 12/3/4 na 98%, extra odmah 91 kod svih, bez izgubljenih. Ocena je pohlepna simulacija
4 poteza (extra 1.33, ocisceno oko 60.8, plave 9.7), bez boostera i perkova.

Auto i snimanje (2026-11-03): Auto je igrao odmah po smirivanju table, pa je pomerao RNG dok ga snimac
cita. U `013829` su se u Auto gubile dve od tri table, a bez Auto nijedna. Auto sada ceka snimak table
(`_waits_for_board_record`, najvise 3 s), uz ukljucenu dopunu ili snimanje.

Extra pre kugle (2026-11-03, `012055` 031): swap kuglom je ionako besplatan, pa njegov extra ne
dodaje potez, a moze da pokvari pravi extra (potezi 5->5, sledeca tabla bez extra).
`exact_refill_choice` zato prvo bira extra obicnom zamenom, a kuglu sa extra tek ako njega nema.

Perkovi u proveri (2026-11-03): potez koji nijedna zamena ne objasni proba se kao Teleport ili
Energy Boost (`refill_monitor._perk_reproducing_board`). Snimak ne cuva preostale perkove, pa se
probaju svi parovi, a vazi samo tabla tacna do poslednjeg polja. Tako su objasnjeni i raniji promasaji
`000937` 001, `212038` 001 i `233017` 019. Na izbor poteza ne utice.
Otvoreno u UFO partijama (205 od 208): `000937` 007, obican potez sa 2 oka (igra uzima boju 3,
simulator 6); `234242` 020, potez posle perka; `001650` 007, jos nije analiziran.

Live planer (`SQUARE_SOLO_EXACT_PLAN`) je iskljucen posle promasaja kaskade
(`Debug/square_live_misses/20261101_014738_386729.json`: sim ima kaskadu vise,
specijal na (3,6)/(4,5) umesto (4,4)).

## Billie pasivna dopuna i granica po kandidatu (2026-11-02)

Na izricit zahtev korisnika Billie dopuna je UKLJUCENA u obicno rangiranje,
iako deo snimka jos ne prolazi. Zajednicko pravilo za sve boostere/modove:
dopuna vazi samo u Solo Challengeu sa ukljucenim glavnim prekidacem i dostupnim
podacima. Prisutan miran specijal ne gasi celu partiju. Kandidat koji aktivira
neprenetu nasumicnu metu ili dodje do neprenete granice vraca se na obican
simulator bez dopune; drugi kandidati i dalje polaze od istog zivog RNG-a.
Time nisu automatski prenete aktivacije svih boostera niti sve grane modova.

`ExactRefillSession.finish` prepoznaje `random_outcomes`,
`uncertain_refill_boundary` i aktiviranu munju/krstic/All Aboard Bandit.
`_simulate_created_candidate_cached` tada odbacuje spekulativni rezultat i
ponavlja taj kandidat bez dopune. `exact_refill_choice` ne promovise takav
rezultat i ne trazi setup na tabli za koju nema nastavak RNG-a. Nema globalnog
iskljucivanja zbog jednog kandidata. Simulacija ostaje u workeru racunanja;
monitor i dalje radi u zasebnom procesu. Obicni modovi bez exact sesije ne
rade Billie izbor meta niti dodatni proračun kandidata.

### Preneto iz ARM64

- `engine_billie.BilliePassive` / `finish_passive`: obican zavrsetak poteza,
  podrazumevana varijanta sa bombama. `EndMoveWithPassiveAbility` 0x5a1437c
  direktno zove `ConvertToCrosses` 0x5a14054, pa default varijantu 0x5aa05f0.
  **Ne usisava boje pri obicnom swipe-u.**
- Kontekst 0x5abb640 prvo vuce `Chance(chanceToBlockNeighbors)` cak i na 100.
  Automatski zavrsetak koristi `postMatchCreate` i
  `chanceToPickMatchablePieceOnSecondaryCreate`, ovde 3 i 60.
- Kandidati koji mogu u spoj: `GetPossibleMoves` 0x591f870, x-major,
  Down/Right za obicne zamene, source pa target; redosled osa Up/Down pa
  Left/Right, zatim kvadrati. Pre vracanja u prvobitnu tablu uklanja se
  pomerena pozicija i dodaje njeno izvorno polje (0x5aa1a8c).
- Dozvoljene engine boje [6,3,5,7,8]; obicna polja, x=1..n-2,
  y=0..n-2. Gornji red jeste dozvoljen. Kandidati se mesaju preko engine
  stabilnih Next kljuceva. Zatim Chance(60) po pokusaju, uz izbor prvog
  kandidata i izbegavanje ortogonalnih suseda specijala kada je moguce.
- Fallback iskljucuje **sve prvobitne matchable kandidate**, ne samo izabrane.
  Ta razlika menja i broj izvlačenja i mete. Konverzija 0x5abb6c4 vuce jedan
  Range za svaku bombu, i kad je u convertValues samo jedna vrsta.
- Dopuna mora da broji skrivenu osnovnu boju drona. `ConvertBillieBoomPiece`
  0x5a13268 klonira slot pa `ToSpecial(25)` zadrzava primarnu boju.
  Prikaz BLOCKED=-1 tu informaciju gubi; ne sme se prevoditi u engine None=1.
- `DropSlotsDown` 0x596fdc0 preskace samo `movable=false`. Dron je
  `movable=true`, `canBeMatched=false`: sada pada zajedno sa kolonama, sa
  ocuvanim specijalom i originom. Na ovom snimku je uvek u poslednjem redu;
  pad drona iz viseg reda proveren je sintetickim testom, ne igrom.
- Zivi nastavak sesije za sve boostere kljucuje i boje i specijale. Iste boje sa razlicitim
  bombama ne smeju deliti sacuvani RNG sledeceg poteza.

### Merenje i preostale greske

Ponovljivo:

    python tools/verify_billie.py Debug/research/20261102_230448_column-mania --out Debug/analysis/billie_passive_20261102.json
    python -m pytest tests -q

Prosireni skup ima 17 obicnih prelaza sa dronom i 10 zasebnih aktivacija
boostera dok je dron vec prisutan. Pocetni izdvojeni simulator bez pasive i
skrivene boje: **0/17**; port: **11/17**. Potpuni pogodak zahteva sve boje,
sve specijale, brojac, indeks, seed i celu RNG matricu. Preliminarne faze
bile su 0/17 (samo RNG/izbor bez skrivene boje), 2/17 (skrivena boja),
10/17 (ispravljen fallback skup), 11/17 (native redosled kandidata).
Ovo nije 100% tacan engine: 6 prelaza ostaje bez pogotka.

| Prelaz | Najblizi podrzani rezultat: razlicite boje / specijali | RNG igra / sim |
|---|---:|---:|
| 008->009 | 38 / 11 | 1600 / 1224 |
| 014->015 | 34 / 10 | 2796 / 2602 |
| 018->019 | 3 / 2 | 3523 / 3523 (i cela matrica ista) |
| 022->023 | 21 / 4 | 4317 / 4320 |
| 028->029 | 41 / 6 | 5218 / 5143 |
| 034->035 | 25 / 11 | 6066 / 5917 |

Za 008,014,028,034 alat nailazi i na aktivaciju nasumicnih meta koje odbija;
najblizi podrzani kandidat u tabeli nije dokaz koji je potez stvarno odigran.
Za 018 i 022 potrebna je dalja provera kaskada/specijalnih kombinacija; cak ni
jednak ceo RNG kod 018 ne znaci pogodak table.

Stari snimak ne cuva sirove slotove. Boja drona u ovoj proveri izvedena je iz
007 pre prve aktivacije: (6,3) je simulator Orange=6 / engine Orange=6.
Listing potvrdjuje zadrzavanje boje. To poreklo eksplicitno je u JSON izvestaju;
alat ne bira boju prema ciljnoj tabli. Novi `research_recorder` i monitor cuvaju
`billie_slots` (sirov slot: boja, flags, movable, canBeMatched). Ziva sesija
koristi samo sirove podatke i odbija sesiju ako ih nema ili konfiguracija odstupa.

Aktivacija `Use` 0x5a12fd0 -> `SuckAndConvertByScoreTarget` 0x5a1345c NIJE
preneta. Ona proba grupe boja na `GameLogic.Clone`; klonira se i RNG, pa probe
ne trose glavni counter. Odabir koristi svezi RandomWrapper(seed), ovde
Chance(-1), zatim prvi maksimalni -abs(score-target); exact score prekida probe.
Nedostaju verna `ConvertSlots -> DestroyMatches -> kaskade/dopuna`, svi
Participate/oznaceni slot flags i dodatni skor preostalih specijala u klonu.
To je zasebna visednevna stavka uz snimke aktivacija. `Remove`, druge Billie
varijante i nasumicne mete munja/krstica takodje nisu preneti.

Nije probano u pravoj partiji posle izmene. Potrebne su jos Billie Solo partije
sa ukljucenim "Snimaj svaki potez", posle restarta GUI-ja, radi nezavisne
provere skrivene boje, kaskada i kandidata koji idu bez dopune.

### Energy Boost ispravka na poslednjoj partiji

Snimak `20261102_235024_column-mania`, prelaz 031->032: obicna simulacija
pre pasive vec daje tacne boje, specijale i kompletan RNG (6534). Pogresno
pozvana pasiva dodavala je tri bombe i 27 izvlačenja (6561). U logu je tada
upotrebljen Energy Boost. `EndMoveWithPassiveAbility` 0x5a144d8 proverava
`PlayerControl.NoFreeMoveBoardAbilityUsedThisMove` 0x59f6fc4; posle besplatnog
perka ne zove ConvertToCrosses. Energy Boost putanja u `simulation.step` sada
preskace pasivu. Ziva konfiguracija prepoznaje aktivan/upotrebljen Energy Boost
iz sirovog stanja, preskace pasivu bez RNG-a i resetuje tu zastavicu za sledeci
potez. Ako je perk odabran tek nakon racunanja obicnog swapa, taj unapred
izracunat swap nije predvidjanje perka.

Monitor i `tools/verify_billie.py` sada probaju i snimljeni Energy Boost
kao poseban kandidat kada obican swipe ne pogodi i igrac ima taj perk.
Provera celog poslednjeg snimka: **17 -> 18 potpunih pogodaka**, 12 aktivacija
boostera izvan porta, 5 prelaza bez pogotka. Od tih pet cetiri imaju
nepodrzane nasumicne efekte; 027->028 ostaje stvaran promasaj jedne bombe
(simulator (2,4), igra (1,4)), uz tacne boje i ceo RNG. Nije uvedena korekcija
pozicije vezana za snimak. Prethodna partija ostaje 11/17.

Izvestaji: `Debug/analysis/billie_latest_fixed_20261102.json` i
`Debug/analysis/billie_previous_fixed_20261102.json`. Dodati su regresioni
test snimljenog Energy Boosta i test da ziva zastavica ne trosi RNG i vazi samo
za jedan potez. Nova prava partija posle ove ispravke nije probana.

### Izbor meta: special+special merge (2026-11-03)

`GetValidOutcomes` 0x592421c proverava `IsMergeSwapOutcome` pre obicnih
spojeva. Za kombinaciju dva specijala vraca combo tipa 9 sa ta dva polja;
ne trazi obicne spojeve njihovih boja posle zamene. Billie te specijale
ionako iskljucuje iz obicnih meta. `_possible_pieces` je ranije izmisljao
obicne spojeve za takvu zamenu i time menjao redosled/skup kandidata.
Sada preskace tu granu za prenete kombinacije raketa, bombi, munja i krstica.

Na snimku `20261103_000405_column-mania` ispravljeni su 006->007, 010->011
i 024->025: svi sada imaju tacne boje, specijale i celo RNG stanje. Rezultat
je **15/23 -> 18/23**, uz 11 aktivacija boostera izvan provere. Pet prelaza
i dalje nema pogodak; medju njima 019->020 ostaje veci neobjasnjen promasaj
kaskade, bez munje/krstica na pocetnoj tabli. Ne racunati ga kao uspeh.

Prethodni `235024` ide **18/23 -> 19/23**: 027->028 sada ima bombu na (1,4)
kao u igri, umesto (2,4). Izvestaji su `Debug/analysis/billie_000405_merge_fixed.json`
i `billie_235024_merge_fixed.json`. Dodati su regresioni testovi tih prelaza,
sa preskakanjem ako nema snimaka. Rekurzivna pretraga BlobMatchChecker je
istrazena odvojeno; nije ukljucena jer nije popravila poslednji snimak.
Nova prava partija posle ove izmene jos nije odigrana; potreban je restart GUI-ja.

### Multiplier Mushrooms sa Billie (2026-11-04)

Snimak `20261104_031513_multiplier-mushrooms`: **3 -> 23 od 25** proverljivih poteza
(11 aktivacija boostera izvan provere). Dva uzroka, oba procitana iz ARM64:

- `MultiplierMushroomsBoard.IgnorePosition` 0x59bd204: pecurka ne ide u krajnje kolone ni
  u donji red, a boja mora biti engine 6, 3, 5 ili 7 (ctor 0x59bb1b0). Svaki visak kandidata
  je jedno izvlacenje, pa je simulator odlazio ispred igre, vise sto je dopuna veca. Vazi za
  `boardModelName` 29.
- Billie blokira susede samo oko `IsSpecial` (0x5aa1a74). `IsBoardSpecial` 0x592e824 (engine
  16 do 20, medju njima pecurka 19 i kristal 18) nije `IsSpecial`.

Otvoreno: `008->009` (boje i RNG tacni, jedna bomba drugacija) i `031->032` (12 polja, jos
nije analizirano). Nova prava partija posle ove izmene jos nije odigrana.

### Mighty Mushrooms: dva tipa specijalnih polja (2026-11-07)

`mighty-mushrooms` (board 30) u dopuni stvara pecurku 19 i bombu 6. Do sada je
dopuna odbijala vise od jednog tipa. `RandomSpawnSpecialSlots` 0x5a04c2c
pravi listu tipova i **mesa je RNG-om igre** (`ArrayExtensions.Shuffle`
0x3c137a0, jedno izvlacenje po tipu, nijedno za jedan tip), pa redom zove
`ProcessSpecialTile` za svaki. `IgnorePosition` table pecuraka vazi za oba tipa.

Snimak `20261107_155618_mighty-mushrooms`: **0 -> 34 od 34** proverljivih poteza
(bez mesanja RNG je kasnio 2 izvlacenja i rasla je pecurka koje u igri nema).
Jedini promasaj u proveri dopune je `031->032`, prelaz na novi potez (potezi
1 -> 5). Modovi sa jednim tipom (srca, bombe, Multiplier Mushrooms) se ne menjaju.
Test: `tests/test_mighty_mushrooms_refill.py`.

## specialsAutoExplode i `moves-multiplier` (2026-11-04)

Procitano iz koda: `DestroyMatches`, posle dopune i `GetAllCombos` 0x595407c, ako je
`MatchRulesModel.specialsAutoExplode` (+0xc8) ukljucen, bira klasicne specijale
(`b__15` 0x5965dc0; `IsClassicSpecial` 0x5932b88 je vrednost 4..8) i pravi im kombinaciju
ranga 11 (`ComboModel` 0x5954248). Znaci da specijal **ne eksplodira odmah**: prvo ide
gravitacija i dopuna, pa eksplodira tamo gde je pao, zajedno sa novim spojevima.
Uz `specialsAutoExplodeOnMatchOnly` vazi samo za specijal nastao od spoja
(`ShouldExplodeFromMatchOnly` 0x59e67fc, `createdFromCombo` +0x26).

Izmereno na snimcima:

* Match-4 je +70 izvlacenja: 3 rupe, pa 7 rupa eksplodirane kolone, po 7 izvlacenja.
* Prisilna kombinacija ne trosi `Next()` kao spoj u kaskadi; dok je brojana, svaki potez
  je imao tacno 1 izvlacenje viska.
* Linija preko Cleo ostavlja figuru i jednu rupu manje (+63 = 3 + 6 rupa).
* Sirova boja Cleo ulazi u brojanje boja za dopunu, i van Match & Hatch.

Rezultat, `refill_monitor.check_transition` nad 3 partije (48 poteza; tacno znaci tabla,
specijali i potezi, a RNG mora da se slaze ili da razliku prijavi):

| | pre | posle |
| --- | --- | --- |
| tacno | 1 | 18 |
| promasaj | 7 | 4 |
| ne moze da se proveri | 29 | 15 |
| booster | 12 | 12 |

Svih 1516 snimljenih prelaza kroz stari i novi kod: nijedan tacan se nije pokvario, a
promene su samo u `moves-multiplier` (ukupno tacnih 943 -> 970).

Disko kugla (izmereno, partija `20261104_050645`, Brocco): obican swipe je bio tacan, a
promasivao je samo kad kaskada posle brisanja boje napravi specijal. Razlog nije u kugli:
kaskade tih poteza idu kroz posebnu petlju (`_simulate_disco_candidate`) gde je specijal i
dalje eksplodirao odmah. Potez 05:07:02 ima 7 + 6 + 7 = 20 rupa x 7 + 2 = 142 izvlacenja, a
simulator je imao 7 + 10. Sedam petlji sada ide kroz `_with_auto_explosions`, a grana sa
trenutnom eksplozijom je obrisana. Ista partija: tacno 14 -> 18 od 20 proverljivih, a
preostala 2 su perkovi Energy Boost i Remove Cross. Za `_simulate_clear_cells_perk`,
joojoo, High Voltage i Magic Wand nema snimljenog slucaja sa ovim pravilom.

Ostalo: 2 promasaja su perkovi koje monitor ne reprodukuje (`remove_cross`, a za drugi je
u logu samo da je perk iskoriscen), 2 sa Cleo na tabli (+84, +106) nisu objasnjena. Svih 15
neproverljivih su Cleo prevlacenja (booster figura nije u tacnom prolazu). U sacuvanim
promasajima ostaju i potezi sa disko kuglom i jedan prelaz 5->6 poteza, sto nije jedan potez.

## Match & Hatch: nasumican specijal (2026-11-04)

`extraMoveRandomSpecial` (ARM64 `MakeSpecialSlotCreated` 0x592c21c): specijal koji pravi igracev
spoj (`isPlayerInit`) bira `GetRandomSpecialPiece` 0x59ded68. `SelectRandomItem` 0x5b04b68 uzima
`Next() % ukupna tezina`, pa prvi zbir iznad toga, redom iz `specialPiecesWeights`. Izvlacenje
ide pre dopune. Na snimcima je prvo izvlacenje dalo tacnu figuru u svih pregledanih novih slucajeva.
Redosled iz recnika je izmeren, nije procitan.

Slot zadrzava boju spoja (0x592c438), a tabla pokazuje 99 za Brocco, Foxy i Cleo; dopuna tu boju
broji. `profile.ball_slots` sada cuva i Foxy (31) i Cleo (32), pa stari snimci sa takvom figurom
koja miruje ostaju neproverljivi. `weightsRandomizer` je samo kes istih tezina, pa vise ne gasi
dopunu kad su iste. Figure u mirovanju su poznate, a aktivacija Cleo, Foxy, Bandit i lobanje nije
preneta: ta linija ide obicnim putem bez dopune.

Cetiri snimka `2026110403*` / `20261104_032503` (62 poteza): pogodjeno 19 -> 33, promasaja 9 -> 3,
neproverljivih 22 -> 14, booster 12. Otvoreno (u sva tri igra daje potez vise i obican specijal):
`032503` 015, `031014` 001 i `030904` 003. Nova prava partija jos nije odigrana.

## Froggy Fu: spojevi koje povlacenje sklopi (2026-11-04)

`ComputeBlobSpecials` pusti `GetAllCombos` nad celom tablom posle povlacenja. Spoj koji ne dodiruje
povuceni klaster ide u `otherCombos` i rusi se sa klasterom, u prvom sloju, pre prve dopune. Simulator
ih je cekao do sledeceg sloja, pa je dopuna imala drugi redosled rupa i dodatna izvlacenja za lanac.
`froggy_lotus_gather` sad te spojeve trazi na tabli posle povlacenja, sto pokriva i drugi spoj istog
poteza koji je povlacenje pomerilo ili razbilo. Ti spojevi su poznati pre dopune, pa vise ne nose
popust za nepoznatu dopunu. Na snimljenoj tabli iz `tests/test_arena_deadline_regressions.py` zato potez
sa cetvorkom ostaje prvi do oko 21,5 s, a ranije je to bilo oko 24 s. Lotus koji nije opalio ne dobija
bonus od tih spojeva.

`20261104_052333_moves-multiplier` (booster 63): 004, 005, 013 i 017 su sada tacni, uz 007 i 012.
**Drugi spoj istog poteza** (`20261104_054022`, prelaz 006). `BuildSwapResolution` 0x5a4ef68: kad potez
gradi tacno jedan plan, prvi spoj bez plana postaje `plan.assignedSecondary`. `RunPullAndConvertLotus`
0x5a52188 tada zove `Pull` dvaput: prvo za boju, sa tim celijama kao `AvoidDisplacementCells`, pa za te
iste celije kao `ExplicitCandidates`, sa zajednickim `alreadyPulled`. Figure tog spoja se ruse tamo gde
su sletele. Raniji stav da je ova grana uvek `null` nije tacan: samo nije bila snimljena.

Otvoreno:

- **009:** simulator posle povlacenja nalazi peticu i predvidja Lightning; nastanak i eksplozija u igri
  nisu neposredno potvrdjeni snimkom. Pocetna tabla sadrzi samo lotus, bez Lightninga. `GetFireworks` 0x597204c ->
  `GetSlotPrioritize` 0x5972158 mesa kandidate RNG-om igre, a jednostavne hipoteze o redosledu i
  kandidatima nisu dale tacnu tablu. Monitor ovo prijavljuje kao promasaj jer je Lightning napravljen
  u istom potezu, pa se ne vidi na tabli pre poteza.
- **Aktivacija** nije preneta u simulator, ali je potrosnja procitana (odeljak ispod).
  `stampedPositions` je samo klaster prethodnog poteza (x, y) i ne govori o narednom.
- **Remove Cross** (`20261104_054022` 001): 13 rupa, 91 izvlacenje, monitor ovaj perk ne reprodukuje.
- **Ista pretpostavka simulatora** postoji i za `20261104_054022` 004 (275 izvlacenja): pocetna tabla
  sadrzi samo lotus. Ovo nije dokaz da u igri iz lotusa nastaje Lightning.

## Froggy Fu: aktivacija iz koda (2026-11-04)

`BeginNewActivation` 0x5a4b338 troši RNG ovim redom:

1. `preferEnergyAdjacent = Chance(chanceToPlaceNextToEnergyMatch)`, 1 izvlačenje.
2. `entranceMushroomTarget = Range(min, max + 1)`, 1 izvlačenje.
3. `entranceDestroyCount = Range(min, max + 1)`, 1 izvlačenje.
4. `RollPreferredColorForActivation` 0x5a4b604, iza `HasEngineFix(7)`: filtrira pozitivne težine i boje iz
   `spawning.gameColors`, sortira po broju native `SlotColor`, pa `Next(zbir težina)`. Bez kandidata vraća
   `None` (1), bez izvlačenja. U osam snimljenih aktivacija troši po jedno izvlačenje; boja je tačna 8/8.
5. `PickEntranceExplosionTargets` 0x5a4ba10 pravi `max(simulatedRuns, 1)` pokušaja.

Pokušaj prvo uzme pečurke (`value == 0x13`): `Shuffle` pa `Take`, što troši po jedno izvlačenje na svaku pečurku u
bazenu. Ostatak bira `PickNormalCandidatesForAttempt` 0x5a4dcfc iz polja sa `value == 0`, `canBeMatched`, `movable`
i `GetCell != 3`, redom po kolonama. Težina polja je `100 + (min(score, 5) - 1) * ratio`, gde je `ratio`
`highScorePieceRatioThisActivation` ograničen na 0..100. Svaki izbor je `Next(ukupna težina)` bez vraćanja.

Bez pečuraka na tabli to daje `4 + 10n` izvlačenja pre rušenja i `7n` za dopunu, dakle `17n + 4`.

`FroggyFuEntranceAttemptEvaluator` procenjuje svaki pokušaj na klonu `GameLogic`-a. `CompareAttempts` 0x5a5adf0 redom
gleda: više postavljenih lotusa, više uz spoj, zatim uslovno više različitih boja, energiju, manji `separationDeficitSum`,
uslovno `minPiecesEligiblePlacedCount` i manji `scoreDistance`, a na kraju manji indeks. Prvi bolji ostaje.

Provera na 8 aktivacija iz `20261104_052333` i `20261104_054022`: pečurke i broj rušenja se poklapaju 8/8. Jedan od
10 pokušaja daje tačnu tablu i broj izvlačenja 7/8. Osmi (`054022` 002, 230 izvlačenja) ima kaskadu, koju ova provera
ne simulira. Na tih 7 aktivacija pobednik je pokušaj 0 ili 1.

Nije pročitano do kraja: `BuildPlacementSelection`, `AnalyzePossibleMoves`, `GreedySelectLotuses` i
`ScoreCandidateWithBreakdown`, koji određuju gde lotus staje.

Poznati deo aktivacije je izdvojen u `engine_froggy.py`: parametri aktivacije, preferirana boja i svi
pokušaji rušenja. `preview_entrance` koristi samo početni profil, sirove slotove i eksplicitan redni broj
aktivacije / engine fix 7; RNG klonira. `GetCell == 3` polja pozivalac mora proslediti zasebno, jer sirovi
slotovi ne sadrže tu osobinu ćelije. Modul još nije povezan sa izborom poteza: ne bira pobednički pokušaj
i ne postavlja lotuse. Nije tačna simulacija cele aktivacije.

`python tools/validate_froggy_entrance.py` proverava osam aktivacija: svi parametri, uključujući boju,
tačni su 8/8. Među generisanim pokušajima postoji jedan koji posle rušenja i jedne dopune daje tačnu
tablu van novih lotusa **i celo RNG stanje** 7/8. Izuzetak ostaje `054022` 002 sa kaskadom. Poređenje sa
završnim snimkom služi samo za proveru; ne predstavlja algoritam za izbor pobednika.

Lightning: dodatno su pročitani predikati `GetSlotPrioritize` 0x5979e04 / 0x5979e70 / 0x5979f04 i
`GetFireworks` 0x59795c8 / 0x59795f0. Prioritet su slotovi sa `canBeMatched && damageable`; ako ih ima
manje od traženog broja, svi se dodaju, a ostatak dolazi iz `canBeMatched && !damageable` van `ignore`.
Meša se samo lista iz koje treba dopuniti izbor, a ne već dodati prioritetni slotovi. `Shuffle` koristi
stabilno sortiranje po `RandomWrapper.Next` (selector 0x4073ad8). To još nije dovoljno za tačan ishod
dva lotus-Lightning snimka; produkciona simulacija tog slučaja ostaje neproverljiva.

Provera pretpostavke da Lightning vec stoji na tabli (2026-11-04): sirovi slotovi i `special_board`
pre `052333` 009 i `054022` 004 sadrze samo lotus (`value=40`), nijedan `Fireworks` (`value=7`).
U simulatorovom povucenom klasteru postoje uzastopne petice: red 1, kolone 2..6 u prvom i red 0,
kolone 0..4 u drugom slucaju (indeksi od nule; ukljucena pretvorena lotus celija).
Native `ComboModel.IsFiveShapeFast` 0x59cc37c proverava pet uzastopnih celija po osi;
`GetComboType` 0x59cbc4c za njih vraca `Five=4`. `GetCombosFromTestList` 0x592b3fc za high-rank
spoj bira creation mode 1, a tabela u `MakeSpecialSlotCreated` 0x592c498..0x592c4c0 mapira `Five`
na `SlotValueType.Fireworks=7`. `BuildMegaCombo` 0x5a539e4..0x5a53a14 klonira i prenosi taj
`specialValueCreated`. Dakle kod dozvoljava novi Fireworks iz lotus klastera; ovo nije samo naziv
koji je simulator dodelio petici. I dalje nije neposredno snimljen medjukadar nastanka, niti je ceo
ishod ova dva poteza tacno reprodukovan. Provera ne dokazuje da je svaka simulirana putanja povlacenja
u tim potezima identicna igri; zato se ne menjaju mete ni ocena pouzdanosti Lightninga.

## Laser Matches i mesanje table (2026-11-04)

Snimak `20261104_155626_laser-matches`, 33 od 34 poteza bez boostera posle ovih ispravki.

- **Lotus u laser modu:** potez koji opali Froggy lotus ne ispaljuje laser zrake. Izmereno na 8 poteza
  (7 zamena i 1 Teleport), grana u `LightsabersBoard` nije procitana. `_clear_matches_with_details(laser_rays=...)`.
- **`GameLogic.ShuffleBoard` 0x594ceac** (`engine_shuffle.py`): pokrece se kad posle poteza nema moguceg poteza.
  Ponavlja `BoardModel.Shuffle` 0x596eeac dok tabla nema kombo i broj poteza nije u `spawnEngine.wanted*`,
  najvise 100 proverenih pokusaja. Svaki krug vuce po jedan `Next` za figuru (stabilan `OrderBy`), a figure se dele
  redom y pa x i nose svoj specijal. Snimljeno 023->024: 7 krugova, 343 izvlacenja, tabla tacna.
- **Nesigurno:** samo jedno mesanje postoji u 72 sesije. Prvih 6 krugova je palo na kombo, pa uslov opsega nije
  proveren na odbijenoj tabli. Prihvacena tabla nema `isHighRank` oblik, pa se u specijalni opseg broji i trojka
  sa specijalom; to je pretpostavka iz tog snimka. U 2314 snimljenih tabli nijedna ne miruje bez moguceg poteza.
- **Primenjeno samo u `strategy_lab.simulation.step`** (provera dopune i Lab). `ExactRefillSession` u rangiranju
  uzivo i dalje ne mesa, nego vidi tablu bez poteza.
- **Ostaje:** 036->037, grom sa nasumicnim metama, nije prenet.

## Froggy lotus: Match & Hatch i Blow 'em up (2026-11-06)

Sacuvani promasaji iz `Debug/refill_misses` (dopuna ih cuva i kad je snimanje iskljuceno).

- **Match & Hatch, 9 od 10 lotus poteza sada tacno.** Specijal iz lotus klastera igra ostavlja po
  obliku (bomba), bez nasumicnog "izleglog" specijala, i ne trosi izvlacenje. Simulator je na tom
  polju izvlacio nasumican specijal (srce) i bio tacno +1 izvlacenje ispred igre.
  `_clear_matches_with_details(froggy_blob_cells=...)` sada preskace `_ENGINE_RANDOM_SPECIAL` za klaster.
  Otvoreno: `133129` (+6/7 izvlacenja).
- **Blow 'em up, 3 od 8 nisu promasaji.** Lotus klaster koji pravi peticu daje munju, koja zbog
  `specialsAutoExplode` puca u istom potezu po nasumicnim metama. Te zamene se ne mogu proveriti, a
  najbliza proverljiva bila je 150 do 280 izvlacenja daleko. Monitor sada takav slucaj (kandidat sa
  nasumicnom metom i najblizi proverljiv dalje od 70 izvlacenja) vodi kao "ne moze da se proveri".
  Isto vazi za `20261102_211420` 021->022 (191 izvlacenje).
- **Blow 'em up, 4 lotus poteza sa bombom i dalje promasuju** (`134252`, `134406`, `134452`,
  `134534`): simulator 14 do 21 izvlacenje ispred, jednom -1, oko 18 do 34 polja. Probano i odbaceno:
  jedno izvlacenje vise ili manje bilo gde u potezu, brojanje prisilne eksplozije kao kombo, bomba na
  drugom polju klastera, eksplozija bombe u istom sloju sa klasterom, bez drugog spoja. U
  `moves-multiplier` (takodje `specialsAutoExplode`) isti lotus potezi su tacni; razlike u pravilima
  su `specialsAutoExplodeOnMatchOnly` (tamo true, ovde false), `soloRefillMode` i
  `refillLogicOverride`. Sledeci korak je `ShouldExplodeFromMatchOnly` 0x59e67fc i `b__15` 0x5965dc0
  bez tog uslova.

## Plunder Pirates: sanduk u dopuni (2026-11-06)

Snimak `Debug/research/20261106_143840_plunder-pirates` (44 table, `boardModelName` 8 =
`PlunderPiratesBoard`, sanduk = `PirateChestPiece`, SlotValue 20). Pre izmene nijedan potez nije
mogao da se proveri (`specialTilesData` sa sandukom nije bio prenet); sada je **27 od 29** obicnih
poteza tacno (12 boostera, 1 Teleport tacan, 1 preskocen).

- **Stvaranje:** isti `ProcessSpecialTile` kao srca i bombe; konfiguracija nema
  `minGuaranteedPieces` (podrazumevano 0), `replenishAtTurn` -1 se prihvata, drugo nije preneto.
  U simulatoru sanduk je `CHEST` (8) sa specijalom 9; u engine tabli boja 1, `canBeMatched` false.
- **Skupljanje:** nijedna mirna tabla nema sanduk u donjem redu. Sanduk koji pad dovede na dno
  uklanja se u sledecem sloju zajedno sa spojevima koje je dopuna napravila; bez spojeva sledi
  zaseban pad i dopuna (`_collect_bottom_chests`, dogadjaj `pirate_chest_collect`). Varijanta sa
  uvek zasebnom dopunom daje isti rezultat na ovom snimku, pa redosled nije potvrdjen.
- **Eksplozije ne diraju sanduk** (`damageable` false): 041->042 raketa je presla preko sanduka i
  on je ostao. Vazi za svaki mod, jer sanduk postoji samo na ovoj tabli.
- **Froggy povlacenje zaobilazi sanduk:** nije ni cilj ni polje putanje (`canBeMatched` false,
  `_froggy_can_be_matched`); 017->018 sanduk je ostao na mestu.

Otvoreno: 007->008 (dva lotusa, 150 izvlacenja razlike) i 032->033 (sanduk skupljen uz kaskadne
spojeve, 7 polja i 6 izvlacenja razlike, novi sanduk na drugom mestu).

## Dustville Duel: wanted figure u dopuni (2026-11-07)

Snimak `20261107_083610_dustville-duel-master-league`: pre ovoga nijedan potez nije mogao da se
proveri, sada je 24 od 28 obicnih poteza tacno, plus TELEPORT (ostalo: 5 Brocco bustera).

- **Figura**: obican narandzasti komad sa `SlotValue 16` (simulator `SPECIAL_MODE_TARGET` na
  narandzastoj); u dopuni se broji kao boja i spaja se normalno.
- **Hici** (`GetAreaOfBoardSpecialEffect` 0x59862e4 -> `GetAreaOfBluesAndRedsByMinAndChances`
  0x59757b0): svaka unistena figura (spoj, eksplozija) gadja `wantedShoots` obicnih komada. Plave i
  crvene (boja igraca i protivnika; solo: Blue <-> Red) se skupljaju x-major i mesaju (`OrderBy Next`),
  neutralne su boje 6, 3, 5, 7 tim redom, nemesane. Posle toga jos 4 izvlacenja: lista boja se mesa
  iako se rezultat ne koristi (bez njih 003/022/026/030 ne pogadjaju RNG). Polja koja se vec rusе se
  izbacuju. Hitac: plava dok nije izabrano `minBluesToPick`, posle `Chance(chanceToPickBlue)` (podrazumevano
  0, `Chance` i tada izvlaci), inace crvena, inace neutralna; `Range(0, n)` za izbor.
- **Disko na narandzastu**: figura na koju je disko prevucen ne puca; ostale obrisane figure pucaju
  (010 i 018: tri figure, tacno samo sa dva hica). Bot to vrednuje kao izgubljeno punjenje.
- **Vracanje** (`onTurnStart` 0x5986058 + `convertToWanted` 0x5985cd8): na pocetku sledeceg poteza,
  ako fali figura, `Chance(round(replenishChance * 100))`, pa `min(replenishRate, fali)` obicnih
  narandzastih (x-major, mesano) postaje figura. Snimci su posle toga, uvek 3 figure.

Otvoreno: 016 i 028 (raketa iz kaskade pogodi figuru: RNG tacan, tabla ne), 014 (munja), Brocco
buster. Uzivo 09:08:20 i 09:08:51: figura spojena u kaskadi 2, hici daju RNG -24 i +43 prema igri;
ni "bez hitaca" ni "hici bez rusenja" ne pogadjaju. Svaki specijal ili hitac posle prvog sloja zato
gasi tacnu liniju, a monitor takav potez javlja kao neproverljiv kad nijedan proverljiv nije blizu.

### Kvadrat iz kaskade: nisan ide u krug (2026-11-07)

Specijal kombinacije iz kaskade stoji na polju `izvlacenje % velicina`. Za kvadrat
2x2 polja se broje **u krug od gornjeg levog** (gore levo, gore desno, dole desno,
dole levo), ne redom kolona pa red. Crazy Columns `20261107_161715` 005->006 i
026->027: izvlacenje % 4 = 3, igra je stavila nisan dole levo, a simulator dole
desno. Na 17 sesija sa kvadratima: 5 poteza popravljeno, nijedan izgubljen.
Test: `tests/test_cascade_square_crosshair.py`.

### Versus Square Match: grana pragova (2026-11-07)

Snimak `20261107_162536_square-match` (2 igraca, 6 rundi): `refillLogicOverride`
ima `disableFirstRoundLogic: true` i nule za spojeve, pa vazi prilagodljiva
formula (`FillAllEmptySlots` 0x5a08c00-0x5a08e1c: `GetScoreDifference`, polja
`spawnEngine` +0x50..+0x64, Fix64 racun). Preneta je za Versus sa dva igraca:
racuna se iz trenutne razlike u poenima, preostalih poteza, `moveScoreEstimate`
i `PlayerModel.spawnBonus` oba igraca. Bez citljive vrednosti `spawnBonus` dopuna
ostaje iskljucena. `Turns` broji unazad
(6, 5, 4, 3), pa je grana `Rounds == RoundsTotal` zapravo **prva** runda, sto
odgovara imenu `disableFirstRoundLogic`; u modovima sa jednom rundom to je isto.

### Color Crush u Showdown-u sa Froggy-jem (2026-11-07)

Partija 16:32-16:33, 8 promasaja u proveri dopune:

- Showdown je `pvpMode` 2 sa jednim igracem na tabli, dakle `IsSingleplayerBoard`:
  crvena se brise kao svaka boja. `lab_move` je gledao samo `pvpMode == 1` i
  crvenu drzao inertnom. Bot u igri je vec racunao tacno (citao je
  `is_singleplayer_board` iz memorije); gresila je provera i planer.
- Potez koji pali lotus ne brise boju: gather zamenjuje razresavanje zamene.
  3 od 5 lotus poteza tacno bez brisanja, nijedan sa njim. Ovo je menjalo i
  bota u igri: lotus u Color Crush-u je bio precenjen za 5-8 polja.

Otvoreno: lotus potezi 163303 i 163325 (igra izvlaci 49-84 vise) i obican potez
163247 (`Color Crush cascade special timing is not ported`).
Test: `tests/test_color_crush_showdown_froggy.py`.

### Funky Tiles master league: zapperi i Funky polja (2026-11-07)

Dopuna stvara Zany Zapper (SlotValue 17; simulator 26 sa dva udarca, 25 sa
jednim, novi ima dva). Snimak `20261107_180730_funky-tiles-master-league`:
**12 -> 24 od 25** proverljivih poteza (25. je perk). Pravila:

- Funky polje (CellModel.cellType 3) pali plus-2 eksploziju kad potez unisti
  njegovo polje bilo cime, ne samo spojem (`BeforeCombosDestroy` cita
  `cellsUsedThisMove`). U simulatoru je to dodatni talas u istoj kaskadi.
- Potroseno polje se premesta pre sledeceg poteza (`onMoveStart` 0x598ff2c,
  `GetSlotPrioritize`): unutrasnja polja bez ivica i bez preostalih Funky
  polja, x-major, izmesana (jedno izvlacenje po polju), uzima se koliko
  fali do 2. `onTurnStart` postavlja istu oznaku.
- Zapper sa dva udarca gubi najvise jedan udarac po talasu unistavanja.
- Zapper koji dopuna stvori trosi jos jedno izvlacenje.

Snimak istrazivanja sada cuva `cell_types`; stari bez njega se ne proverava.
Pretraga unapred ne prati tablu posle poteza koji pali Funky polje.
Testovi: `tests/test_funky_tiles_zapper_refill.py`, `tests/test_funky_tiles_chain.py`.

## Mutation Lab: lotus uz brisanje reda (2026-11-11)

Mutacija 22 (`destroyRowOnHorizontalMatch`) i Froggy lotus (`froggy_line_destruction_matches`):

- klaster brise **jedan red, red svog specijala** (horizontalni krak L-a), i to samo kad je lotus
  opalio horizontalni spoj; vertikalni spoj koji pali lotus ne brise nijedan red;
- ravan spoj koji je povlacenje napravilo drugde na tabli (`otherCombos`) brise svoj red tamo gde
  stoji posle povlacenja (`142337`: obrisani redovi 2 i 4, a red 3 gde je stajao spoj nije);
- rastureni drugi spoj istog swipe-a (`assignedSecondary`) ne brise nista.

Simulator je brisao sve redove klastera i palio specijale koje igra ostavlja. `Debug/refill_misses`
14:21-14:25: pre 0 od 7 lotus poteza tacno, sada 5 od 7. Kolone (mutacija 23) su preslikane, nisu merene.
Test: `tests/test_mutation_lab_lotus_row_sweep.py`.

Otvoreno: `142210` i `142528`, oba sa `assignedSecondary`. U `142210` raspored kolone 3 u igri
(sestica ispod bombe klastera) ne moze da nastane iz nase table posle povlacenja, dakle greska je u
`froggy_pull_apply` za drugi spoj, ne u brisanju reda.

## Zany Zappers: zapper preskace boje igraca (2026-11-11)

`ZanyZappersBoard` (33) stvara zappere istom dopunom kao Funky Tiles (17: refillSpawn 3, maxSpawn 3,
spawnChance 50, minGuaranteedPieces 2), ali kao Color Crystals preskace boje igraca
(`spawnColorsToIgnore`, plava i crvena) u listi kandidata. `Debug/refill_misses` 14:35-14:38:
`143601` sada tacno (bez toga mesanje ima jednog kandidata vise, RNG +1 i zapper polje dalje);
`143528` +17 -> +5, `143807` +12 -> +8, `143814` +13 -> +3 izvlacenja.
Test: `tests/test_zany_zappers_refill_colors.py`.

Otvoreno: `143814` (sve boje tacne, igra stvara dva zappera a simulator jedan; nijedna proba
filtera kandidata ni bacanja sanse ne pogadja sve snimke), `143733` (RNG tacan, specijal 4 kolonu
pored), `143807`, `143833`, `143528` (zapper koji opali u istom potezu), `143556` (nasumicne mete,
ne moze da se proveri).

### Zany Zappers: zapper samo u gornja 4 reda (2026-11-11)

`ZanyZappersBoard.GetConvertPoints` 0x59c9664: dozvoljene boje, pa `<>c.b__13_1` 0x59c99c4
(`point.y < 4`, `MAX_ROW_FILL`), pa `Intersect(availablePoints, ...)` koji cuva redosled liste rupa
dopune (red po red, ne x-major), mesanje, `Take(amount)`. Simulator je mesao sve rupe x-major, pa je
igra izvlacila 1-3 manje i stavljala zappere u gornje redove. `Debug/refill_misses` 14:35-19:31:
**1 -> 25 od 34** tacno; preostalih 9 imaju i pogresne boje (disco u Zany Zappers: RNG -41 do -126;
nasumicne mete zappera i Shuffle sa zapperom nepodrzani; 143733/143807/143833/192629), nije stvaranje zappera.
Test: `tests/test_zany_zappers_top_rows.py`.

## Gem Grab master league: polje specijala iz kaskade (2026-11-11)

`crystal-cave-master-league` ima `specialsAutoExplode` + `OnMatchOnly`, pa specijal iz kaskade odmah
eksplodira i njegovo polje odredjuje celu tablu. Svih 9 promasaja 20:08-20:27 (vecina posle disko
lopte, ali nije kriva lopta: desetine disko poteza iste partije su tacne) su tacni sa tri pravila u
`_created_special_cell`:

- kristal u spoju se preskace pri izvlacenju polja (`blocked`): 201813, 201829, 201918;
- uz auto-eksploziju L/T ostaje x-major redosled, ne `cross_dup` (`_CASCADE_AUTO_EXPLODE`, postavlja
  ga `_classic_specials`): 200834, 201152, 201415, 202506, 202538;
- prisilna `auto_explode` kombinacija ne trosi izvlacenje, pa nema ni rang: 202726 (cetvorka pored
  horizontale koja eksplodira uzela je sledece izvlacenje).

Svih 113 snimljenih promasaja sa `specialsAutoExplode`: tacnih 4 -> 14 (i 2 stara Blow Em Up),
nijedan izgubljen; 39 promasaja Color Crystals/Gem Grab: menjaju se samo ciljani.
Test: `tests/test_gem_grab_cascade_special_cell.py`.

## Jelly SE u Laser Matches: zraci pre prefarbavanja (2026-11-11)

`LightsabersBoard.AfterPerformedSwap` puca na sam swipe, pre nego sto jelly prefarba zonu: zraci idu
iz originalnih spojeva swipe-a, na tabli pre konverzije. Simulator ih je pucao iz prefarbanog bloba
i brisao 1-5 polja previse (RNG +7..+35). research `20261111_205245_laser-matches`: jelly potezi na
poslednjoj upotrebi zone 0 -> 7 od 8, a potez sa obnovom zone (003) prolazi proveru preko traga nove
zone. Score Market (`20261111_205920`): 3 od 3 poslednje upotrebe tacno i pre ovoga.

Otvoreno: 011 (swipe sa dva spoja koja oba diraju zonu: -7, nijedna boja konverzije ne pogadja) i
obnova zone u Score Market-u 005 (RNG do obnove tacan, redovi 3-4 razliciti, potez daje i +2 poteza).
Sama obnova zone (`GetBestPointsForInfection`, ~110 izvlacenja) i dalje nije preneta; provera je
prolazi samo uz zapisan trag iz igre, a rangiranje uzivo je ne predvidja.
Test: `tests/test_jelly_laser_rays.py` (fixture `tests/fixtures/jelly_laser`).

## Jelly SE: namestanje plave konverzije (2026-11-11)

Dok zona stoji, metar je prazan (jelly je booster), a konverzija u plavoj puni ceo metar odjednom
(snimljeno 14-18 plavih). Potez u zonu ne trosi potez (9->9), potez van nje trosi. Bot je uzimao
plavu konverziju kad je bila na tabli (3 od 3), ali nikad nije namestao jednu za sledeci potez:
sesija tacne dopune sa zonom nije pratila ni jedan potez napred (`max_plies = 0`), pa ni
`_exact_jelly_plan` nikad nije opalio (0 puta u logu).

- `square_solo_live`: sa zonom se prati jedan potez; `ExactRefillSession.finish` ne prati tablu posle
  konverzije (zona potrosena ili obnovljena). Potez koji ne dira zonu ostavlja je na istim poljima
  (research 2026-11-11: 6 od 6).
- `_exact_jelly_blue_setup` (u `exact_refill_choice`, pre Solo izlaza): kad nista na tabli ne puni
  metar, potez koji ne dira zonu i ostavlja plavi spoj u nju na sledecoj tabli, ako to puni metar i
  daje bar 2 plave vise. Placen potez samo uz bar 2 preostala poteza (konverzija treba potez).
- Na 4 snimka (36 odluka sa zonom): menja se 8 odluka, sve u namestanje koje puni metar (7 plavih
  prema 3-5 sada); ostalih 28 iste. Laser nije imao takvu priliku.
- Prosireno: proverava se svaki potez van zone (ne samo prvih 12), na tacnoj tabli posle njega i svaki
  sledeci potez (plave koje padnu u zonu se racunaju), a posle poteza koji zadrzava red i jos jedan
  potez van zone (sesija prati do 2 poteza bez konverzije). Vremenski limit 1.5 s, na snimcima najvise
  0.2 s. 21:02 003 sada ide preko besplatnog poteza umesto placenog.

Neprovereno u igri: snimci imaju potez koji je bot stvarno odigrao, pa ishod namestanja jos nije
viden. Test: `tests/test_jelly_blue_setup.py` (fixture `tests/fixtures/jelly_blue_setup`).

## Solo Challenge "Predji zastavicu": provera na snimcima (2026-11-11)

Na 11 551 snimljenom Solo Challenge potezu (Debug/runs od 2026-10) `_solo_goal_certain_points`
je obecao prelaz zastavice 215 puta; pre ispravke 1 nije presao (Vertical Rush 2026-11-10 04:07:22:
razmak 465, obecano 64 x 8 = 512, igra platila 64 x 7 = 448), sada 0. Obicna trojka svuda placa
3 x vrednost boje x mnozilac. U Vertical Rush-u potez menja mnozilac pre isplate: sam vertikalni
direktan spoj +1 (22/22), sam horizontalni -1, najmanje 1 (10/13, ostali zadrzali); vise spojeva
nikad nije spustilo vise od 1, pa uzimaju -1 kao donju granicu (`_vertical_rush_move_multiplier`).
Test: `tests/test_vertical_rush_goal_multiplier.py`.

Ostala precenjivanja (390 poteza, nijedan lazan prelaz) su greske predvidjanja dopune iz tog
vremena, ne formule: sami direktni spojevi su ih presli samo u 50 poteza, uglavnom lotus i Hot Color.

## Niz extra poteza racuna punjenje boostera (2026-11-11)

`_plan_exact_extra_sequence` (sa tacnom dopunom i bez nje, Solo Challenge i ostali solo) je
linije poredio samo po poenima i broju extra poteza. Sada svaka linija prati mesto u metru
(`session.blue_missing`, bez dopune `booster_state.remaining`): korisna plava vredi
`BLUE_PRIORITY_WEIGHT`, a potez koji dopuni metar i zadrzi red dobija i `BOOSTER_FILL_PRIORITY_BONUS`
+ `MEASURED_MOVE_VALUE` (booster opali bez trosenja poteza). Metar dopunjen placenim potezom dobija
samo celije. U Solo Challenge-u se punjenje dodaje van granice poena do cilja.
Hot Color 15:04:58 (metar 6/7): plavi extra (7 poena, puni metar) sada ide pre zute cetvorke (16).
Testovi: `tests/test_exact_extra_plan.py`, `tests/test_solo_extra_plan_charge.py`.
Planer je simulirao munju i nisan nesemenjenim `random`-om: ista Bounty tabla (2026-11-09 16:27:01)
dala je u tri prolaza dva razlicita izbora. Sa tacnom dopunom to uzivo nije smetalo (sesija takve
linije izbacuje), ali bez dopune (`plan_visible_extra_sequence`) jeste. Sada svaka simulacija u
planeru ima seme od table i poteza (`_seeded_plan_simulation`), pa ista tabla uvek daje isti plan.

## Mutation Lab: prag mutacije kupuje poteze (2026-11-11)

`mutationLabTargetsPerSoloTarget` ([[0, 100, 250, 500]] uz soloTargets [2100]): prelaz praga nudi
mutaciju i `mutationLabMovesRefill` (3) poteza. Partija 15:28: rezultat 88, poslednji potez, metar
3/7; bot je svim potezima dao prioritet 0 kao poslednjem, a plava trojka za 12 je presla 100 i
dobila 3 poteza (metar 6/7 preneo se dalje). `goal_from_snapshot` sada te pragove dodaje kao faze
sa dopunom od 3 poteza, pa potez koji prelazi prag nije poslednji (`_evaluation_turn_state`), a
"Predji zastavicu" i `solo_target_refill_gate` ciljaju i njih. Snimak memorije ugnezdenu listu nosi
samo kao naziv tipa; uzima se iz `match_profile` pravila citaca tacne dopune kad su iste partije
(isti id i soloTargets). Pragovi posle 500 nisu potvrdjeni snimkom. Test:
`tests/test_mutation_lab_pick_refill.py`.

## Mutation Lab: brisanje boje samo na spoju swipe-a (2026-11-11)

`VerticalMatchDestroyColor` (30) i `MatchesDestroyColor` (25): swipe bez sopstvenog spoja (disco
lopta) ne brise boju, ni na prvom kasnijem spoju (`COLOR_RULE_FIRST_MATCH = False`; brisanje reda
i dalje ide na prvi spoj). `check_transition` na svih 268 promasaja sa ovim mutacijama: 152 -> 184
tacnih, nijedan izgubljen. Partija 15:35-15:39: 6 od 9 promasaja tacno.

Otvoreno: polje specijala iz L/T spoja u kaskadi (`CASCADE_LT_CELL_ORDER`). 15:36:38 i 15:39:16
pogadja "red pa kolona, ugao jednom", a Five Colors 2026-11-10 05:51:27 i jos 4 snimka "ugao
dvaput"; oblik (L/T/krst) ih ne razdvaja. 384 para sa takvim specijalom su nadjena, poredjenje
redosleda nije zavrseno. `_lt_listed_cells` ima varijante (vidi dopunu 2026-11-12 ispod).

Dopuna (2026-11-11 16:35): podrazumevano je sada `cross_dup` (ugao dvaput samo kod krsta, kad je
zajednicko polje unutar kolone; kod L jednom). refill_misses 161931, 162337 i 162351 (Mutation Lab,
sve L) tacni su sa njim, a sa starim nijedan; Five Colors krst ostaje isti.

Provera na svim snimcima (refill_misses + research, 2.486 parova; 276 u kojima L/T u kaskadi menja
listu): tacnih 53 -> 88 sa `cross_dup` (38 promasaja postaje tacno, 3 tacna postaju promasaj:
20261104_195751 Mutation Lab, score-market 20261110_010501 015, five-colors 20261110_053945 122;
jedan "unsupported" postaje promasaj). Varijanta "ugao jednom samo na desnom kraju reda" daje 75,
`unique` je proveren samo na ova 4. Ta tri gubitka imaju ugao na levom kraju ili u sredini reda,
ali oblik ih i dalje ne razdvaja potpuno od dobitaka.

Dopuna (2026-11-12): podrazumevano je `first_scanned`. Prvo ide onaj deo (red ili kolona) cije
prvo polje dolazi ranije u x-major skeniranju (kolona, pa red); kad oba pocinju u uglu, prva je
kolona; zajednicko polje samo jednom. Mutation Lab 2026-11-11 23:11 - 2026-11-12 00:03 (mutacija
30, 11 promasaja): 8 su bili L/T/krst u kaskadi i svih 8 je tacno (tabla, specijali, RNG), sa
`cross_dup` nijedan, sa `scan` 5, sa `unique` 4. Brute force po polju specijala dao je tacno jedno
resenje po potezu i svako se slaze sa pravilom. Stari slucajevi ostaju tacni (161931, 162337, 162351,
Five Colors 055127 -- bomba na (2,2) pada na (4,2), isti ishod kao "ugao dvaput"), a 20261104_195751
postaje tacan. Neresena 3 iz te partije: 231203 (odigran potez nije najblizi, igra -92 RNG vise),
231839 (ulaz poteza nije zabelezen), 234128 (L/T u kaskadi, ali nijedno polje specijala ne daje
tacnu tablu, RNG -49). Provera na svim snimcima nije uradjena.

## Gem Grab (CrystalCaveBoard, board 3) (2026-11-11)

Kristal je `SlotValue` 16 na ljubicastoj plocici, broj u `SlotModel.score`; simulator ga drzi kao
`make_purple_gem_special(score)` i u dopunu ga salje kao BoardSpecial sa tim brojem. CrystalCave nema
svoj `RefillSlots`: `onMoveStart` 0x5983b80 dopunjava kristale (manje od `maxBoardSpecialTiles` ->
jedan `Chance(round(replenishChance*100))` -> `ConvertSlots` 0x59836d4 sa
`min(replenishRate, missing)`). Kandidati (`IgnorePosition` 0x59835c8): obicne ljubicaste plocice bez
specijala, x-major. `GetSlotPrioritize` 0x5972158: prioritet je najvisi red kandidata (b__1: y == min
y); ako on sam pokriva broj, mesa se i uzima; inace se uzme ceo (bez mesanja), a ostatak se mesa i
dopunjava. Svaki izabrani dobija `nextBoardSpecialScore++` (bajt). Snimak u mirovanju vec ima nove
kristale, pa se `EngineRefill.crystal_move_start` primenjuje na kraju `simulation.step`.
research 20261111_163705: 5 od 6 proverljivih poteza tacno (tabla, brojevi, RNG); sesti je kaskada
posle srca (Vinnie SE) i L spoja, ne kristal. Test: `tests/test_gem_grab_crystals.py`.

## Provera dopune: tabla iz samog poteza (2026-11-12)

Crazy Columns 2026-11-12 00:46-00:48 (Auto, "Snimaj svaki potez" iskljuceno): provera je za 29 poteza
dobila jednu tablu ("preskocen potez, nema table pre njega"); Hot Color pre toga, sa ukljucenim
snimanjem, 41. Van Solo Challenge-a i bez snimanja potez ne ceka citanje posmatraca
(`_waits_for_board_record`, zbog sata), pa sledeci potez pomeri RNG ispod njega i tabla se odbaci.
Nije bilo vezano za booster ni lotus.

Sada `_late_exact_refill` (kasna tacna dopuna) sam cita profil u mirovanju i istu tablu daje proveri
(`ResearchRecorder.capture_resting`), bez dodatnog cekanja; isti kljuc kao `record` (tabla, specijali,
RNG brojac) izbacuje duplikat kad je i posmatrac uhvatio tablu. Pokriva poteze koji koriste kasnu
dopunu (obican izbor sa dopunom, lotus); potezi samo na poene na kraju ture i dalje mogu ostati bez
table. Test: `tests/test_research_capture_resting.py`. Uzivo jos nije provereno.

## "Tabla jos nije mirna" (2026-11-12)

U logu 2026-11-11/12 je 45 izbora bez dopune sa razlogom "tabla jos nije mirna" / "igra jos razresava".
29 su bila racunanja koja su posle ponistena (tabla se pomerila), ali su vec bila upisana kao potez bez
dopune (Hot Color 00:55:21: odigran potez u 00:55:26 je imao dopunu). 9 su bili booster. 7 prevlacenja
je stvarno odigrano bez dopune: kasna dopuna je uzela najnoviji snimak koji agent jos nije potvrdio kao
miran.

- `_report_when_computed`: racunanje na tabli koja se jos pomera prijavljuje se tek kad se njegov potez
  zaista odigra; ponisteno se ne broji (`UNSETTLED_REFILL_REASONS`).
- `_late_exact_refill` -> `_wait_resting_snapshot`: daje istoj planiranoj tabli najvise
  `LATE_REFILL_SETTLE_SECONDS` (0,6 s) da postane mirna, uz zahtev za svez snimak, umesto da odmah odustane.
Testovi u `tests/test_refill_monitor.py`. Uzivo jos nije provereno.

Dopuna (2026-11-12 01:25): pre aktivacije boostera ili perka (obicna partija, kasna dopuna) `runtime`
poziva `late_exact_refill` samo da bi tabla u mirovanju otisla proveri; izbor se ne menja. Color Climb
01:21-01:23: 6 od 16 proverljivih poteza bilo je "preskocen" iza boostera, jer tabla pre boostera nije
citana i potez pre njega se spajao sa boosterom.

## Crosshair (Square) mete iz koda (2026-11-13)

`BoardModel.GetCrosshair` 0x59718d8 cita `MatchRulesModel.additionalData["gemPickThreshold"]`
(u snimljenom Square Match-u: `maxTotalPieces` 7, `selectionOrder`
`maxEnergyPieces,maxMatchingColorPieces,maxClassicSpecialPieces`, brojevi 3, 0, 0; bez kljuca
igra loguje gresku i vraca null). Redom po `selectionOrder` svaka strategija bira do svog broja
(min sa onim sto jos fali), pa dve rezerve do `maxTotalPieces`:

- `maxEnergyPieces` (b__6/b__9): boja ili color2 u `GameLogic.CurrentEnergyChargingColors`;
  bez `colorEnergyOverride` je to boja trenutnog igraca (za bota plava).
- `maxMatchingColorPieces` (b__7/b__10): `MatchesWithSlot` sa samim crosshair-om.
- `maxClassicSpecialPieces` (b__5/b__8): `SlotModel.IsClassicSpecial`.
- rezerva 1 (b__3 = b__0): bilo koja figura van ignore liste; rezerva 2 (b__4): bilo koja
  jos neizabrana figura, i one koje se vec ruse.

Svaki izbor je `AddSelectedPieces` 0x5978ef0: izabrane doda u pozivaocev ignore, pa
`GetSlotPrioritize` sa uvek laznim prioritetom (b__111_1): Where lista (x-major) figura koje
`canBeMatched` i ne iskljucuje uslov (b__0: u ignore listi ili `!damageable`, SlotModel +0x21),
promesana jednim izvlacenjem po kandidatu, prvih n. Strategija sa brojem 0 ne izvlaci nista.
Izvlacenja se knjize kao kod Lightninga (`pending_effect_draws`, posle izvlacenja kombinacija
kaskade, pre dopune).

Port: `EngineRefill.crosshair_targets`, a u simulatoru `move_strategy._crosshair_effect_cells`
preko istog hook-a kao Lightning. Potez sa crosshair-om vise ne prekida tacnu liniju
(`exact_targets`). Test: `tests/test_crosshair_targets.py`.

Nije provereno na snimku: nijedan sacuvan snimak (Debug/research, refill_misses,
refill_unsupported) nema aktivaciju crosshair-a. Prvi promasaj ce refill monitor upisati u
`Debug/refill_misses`. Otvoreno: specijalne ploce (ne-klasicni specijali) prijavljuju
`UnsupportedRefill`, a `colorEnergyOverride` i color2 nisu preneti.

## Lightning mete iz koda, svi modovi (2026-11-13)

`GetFireworks` 0x597204c zove `GetSlotPrioritize(random, amount, b__0, b__1)`: prioritet b__0 je
`SlotModel.damageable` (+0x21), ignore b__1 je pozivaoceva lista celija koje se vec ruse.
`GetSlotPrioritize` pravi prioritetnu listu svojim b__0 (`canBeMatched` +0x24 i prioritet) i
**ne gleda ignore**: ulaze sve zauzete figure, i sam Lightning i celije koje ova kaskada vec rusi.
Ako ih ima bar `amount`, mesa se samo ta lista (jedno izvlacenje po kandidatu) i uzima prvih
`amount`. Tek kraca lista se uzima cela i dopunjuje promesanim `canBeMatched && !damageable`
figurama van ignore liste (b__1); na tabli simulatora takvih nema. Disco lopta i kovceg nisu
`canBeMatched` (`NON_MATCHABLE_PIECES`).

Isto pravilo je ranije izmereno samo za Sweep SE i Jelly zonu ("occupied slots"). Zato je
`LIGHTNING_EXACT_TARGETS` sada ukljucen za svaki mod sa tacnom dopunom. Raniji opsti model
(celije van ignore liste, ukljucujuci i prazne) nije odgovarao kodu.

Score Market 18:58:30 (`test_score_market_exact_drop_finds_yellow_extra_before_ready_booster`):
vidljiva cetvorka iz istog talasa kao Lightning prenosi se kao `exact_prefix_extra` i kad su mete
Lightninga tacne, jer kasniji nasumican efekat (pecurka) i dalje vraca kandidata na obican model.

Nije provereno na snimku: nijedan sacuvan snimak nema Lightning koji je stajao na tabli pa
opalio. Spojevi Lightning+Lightning (FourthOfJuly, 24 mete) i Lightning sa drugim specijalom
i dalje idu kao nasumicni. Test: `tests/test_fireworks_targets.py`.

## everyMatchIsSpecial: redosled izvlacenja i Lightning posle disco poteza (2026-11-13)

Candy World refill_misses 2026-11-13 13:31-14:08 (26 promasaja): **23 tacna, pre 0**.

- Kaskada pod `everyMatchIsSpecial` prvo izvuce tip svake obicne trojke (`Range(0, 6)` nad
  `EVERY_MATCH_SPECIALS`), pa po jedno izvlacenje polja za svaki spoj, obe liste x-major po prvoj
  celiji spoja. Tipovi i polja nisu isprepletani: tako je 14 od 24 tacno, isprepletano 3,
  kaskada po redovima 9. Simulator tipove trosi odmah, a polja knjizi za dopunu, pa
  `move_strategy._every_match_draw_plan` cita obe vrednosti unapred.
- Spojevi samog poteza vuku samo tipove, prvo spoj sa poljem na koje je figura prevucena
  (target). To se oslanja samo na 13:47:15.
- Lightning u kaskadi posle disco poteza (i ostalih sporednih petlji kaskada: booster,
  specijalni swap, perk) mesao je pre izvlacenja polja, jer `_CASCADE_COMBO_DRAWS` tu nije bio
  postavljen. Sada te petlje prosledjuju `combo_draws`. Sa tim su 13:52:11, 13:52:34 i 13:54:01
  tacni sa Lightning pravilom iz koda (sve zauzete damageable figure, i one koje se vec ruse;
  disco lopta je `canBeMatched=false`, `damageable=false` u raw slotovima), sto je prva provera
  tog pravila na snimku.

- Bombon (plavo i crveno) se broji jednom: od dva spoja razlicitih boja koja dele bombon veci ga
  uzima, a drugi uopste nije spoj (bez specijala i izvlacenja; ostale celije mu ostaju). Pri istoj
  velicini ostaje prvi nadjeni (`move_strategy._drop_shared_candy_combos`). Tako su 13:31:05,
  13:36:05, 13:45:10 i 14:07:58 (prvi promasaj restartovanog bota) tacni.

Ukupno 23 od 26 tacnih. Ostaju 13:47:24 (zamena bombe i linije, RNG -54), 14:00:07 (u trecoj
kaskadi igra ima drugaciji spoj; pomeranje Lightning mesanja ne pomaze) i 13:57:31 (simulator ne
podrzava figuru na tabli). Test: `tests/test_candy_world_every_match_order.py`.
