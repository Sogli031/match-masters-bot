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
Otvoreno:

- **009:** povlacenje sklapa peticu, nastaje Lightning i odmah eksplodira. `GetFireworks` 0x597204c ->
  `GetSlotPrioritize` 0x5972158 mesa kandidate RNG-om igre, a jednostavne hipoteze o redosledu i
  kandidatima nisu dale tacnu tablu. Monitor ovo prijavljuje kao promasaj jer je Lightning napravljen
  u istom potezu, pa se ne vidi na tabli pre poteza.
- **Aktivacija** (003, 006, 011, 016; +191, +208, +191, +191) nije preneta.
  `stampedPositions` je samo klaster prethodnog poteza (x, y) i ne govori o narednom.
