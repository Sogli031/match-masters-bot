# Doctor Color (buster 27): pravilo iz koda igre

## Offline analizator (2026-10-31)

`turn_analyzer.py` 1.2.0 prepoznaje ability 27 iz memorijskog indeksa.
Prebojava dve izvorne boje u zavrsnu, cuva tipove specijala, izuzima
`SPECIAL_MODE_TARGET` (engine BoardSpecial) i tek zatim razresava spojeve,
dopunu i kaskade. Punjenje se resetuje pre kaskada i zatim dopunjuje plavim
plocicama. Aktivacija ne trosi obican potez. Nema dodatnih empirijskih poena.

Izbor u probnom analizatoru je uniforman medju dostupnim putanjama.
Naknadno su stringovi pickBehavior razreseni (vidi dole): u snimljenoj
konfiguraciji nema grane highest/lowest. Ipak, tacan engine RNG, njegova
sekvenca i zavisnosti izmedju aktivacija nisu portovani; zato konzervativna
oznaka `doctor_color_selection` ostaje. Probne simulacije su zaustavljene
na zahtev korisnika dok se proveravaju dopuna i ostatak obracuna.
Provera je usmerena na Square Match Solo Challenge (partija 20:57:34).
Za Square Match ne koristi se stara mesana dopuna `None|solo_challenge`,
koja sadrzi figure drugih modova/boostera. Dok nema statistike po kljucu
`square-match|solo_challenge`, koristi se oznacena ravnomerna dopuna obicnih
plocica. Stari i novi izvestaj zato se razlikuju i po modelu dopune.
Visebojna polja i modovi koji kodiraju BoardSpecial drugim tipovima zahtevaju
dodatnu podrsku. GUI rangiranje u `move_strategy.py` ovim nije izmenjeno.

Izvor: `libil2cpp.so` verzije 5.817 (versionCode 3058170), mapa simbola
2026-10-31, disasembliranje u `Debug/reverse/doctorcolor/`. Parametri iz
`data/ability_config.json` (aktivna partija 2026-10-31) i iz memorije.

## Parametri

| polje | vrednost | znacenje |
|---|---|---|
| cost | 7 | energija za aktivaciju |
| colorPathsMaxAmount | 3 | koliko putanja se uzme u obzir |
| pickRandomlyChance | 20 | sansa da se postavi `pickBehavior` (vidi dole) |
| pickHighestChance / pickLowestChance | -1 | nikad |
| scoreTarget, scoreDistance | 5, 5 | ulaze u `Ability::GetScoreTarget`; uloga nije procitana |
| max_booster_spend_per_game | 5 | iz konfiguracije; NIJE provereno na partijama |
| mode `gimme-greens` | pickRandomlyChance 100 | override |

Naknadna provera limita: `PlayerControl::get_BoosterActivationsLeft`
(RVA 0x59f6e8c) cita `logic.gameRules.maxBoosterUsesPerTurn`
(MatchRulesModel +0x2b0). Ako je manje od 1, vraca -1; inace od limita
oduzima brojac iz PlayerModel +0xbc. Dakle ovaj getter ne cita
`max_booster_spend_per_game`. To polje ne treba koristiti kao dokaz limita
od pet aktivacija. Listing je sacuvan u `Debug/reverse/doctorcolor_rules`.

Put dopune: `BoardModel::RefillSlots` (0x59705d8) poziva SpawningEngine:
`CountFillingSlotsAndUpdateColorsDictionary`,
`FillAllEmptySlots`, uslovni `SuperFoceCombo`, `SetScoreAndEnergyOverrides`,
`RandomSpawnSpecialSlots` i `RandomSpawnLiveEventPieces`.
Ovo potvrdjuje da nezavisno uniformno uzorkovanje boje nije dovoljno
opste pravilo za engine. Uslove i tezine jos treba razresiti za Square Match.

## Putanje boja (`get_ColorPaths`)

14 putanja od po 3 boje, samo zelena/zuta/narandzasta/ljubicasta (crvena i
plava se nikad ne prebojavaju). Boje engine-a: Red 2, Green 3, Blue 4,
Yellow 5, Orange 6, Purple 7, White 8.

```
N Z Zu   N Zu Z   N Lj Zu   N Zu Lj   Z Zu Lj   Z N Lj   Z Lj Zu
Z Zu N   Lj N Zu  Lj Zu N   Lj Z Zu   Lj N Z    Zu N Lj  Zu Lj Z
```
(N narandzasta, Z zelena, Zu zuta, Lj ljubicasta; prva boja -> druga -> treca)

Dostupne su samo putanje cije su sve tri boje na tabli
(`AvailableColorPaths`, `BoardModel::GetAvailableColorsOnBoard`).

## Izvrsenje (`MakeColorSwaps`, rekurzivno)

1. `source = path[0]`, `target = path[1]`, `path.RemoveAt(0)`.
2. Sve plocice koje `MatchesWithColor(source)` i nisu `BoardSpecial` (16) --
   obicne i specijali te boje -- poredjane po `(x-3)^2 + (y+1)^2` (od vrha
   sredine), prelaze u `target` (`SlotModel::ToColor`, `GameLogic::ConvertSlots`).
   Nema ogranicenja broja.
3. Ako su ostale bar dve boje, ponovi sa ostatkom: sve plocice boje `path[1]`
   (stare i upravo prebojene) prelaze u `path[2]`.
4. Na kraju `GameLogic::EndMove` -- tek tada se razresavaju spojevi i kaskade.

Rezultat: dve boje se slivaju u trecu (npr. N Z Zu: sve narandzaste i zelene
postaju zute).

## Izbor putanje (`Use`)

1. Dostupne putanje se izmesaju i uzme se prvih `colorPathsMaxAmount` (3).
2. Svaka se odigra na klonu igre (`GameLogic::Clone`, simulacija bez EndMove
   animacije) i zapamti se dobitak poena (`PlayerControl::get_Score`).
3. Ako `pickBehavior` nije postavljen: `Chance(pickRandomlyChance)` ga postavlja
   na string A (ostaje do kraja partije, polje se ne brise); highest/lowest
   sanse su -1.
4. `pickBehavior == C` -> sortirano po poenima (rastuce), `== B` -> opadajuce,
   inace **nasumicna** putanja od kandidata.

Razreseno 2026-10-31 iz metadata fajla instalirane verzije 5.817:
**A = `random`, B = `highest`, C = `lowest`**. Ranija pretpostavka da je
A mozda `highest` bila je pogresna. Sa snimljenim parametrima (-1 za
highest/lowest) i pocetnim null stanjem, izbor ostaje u nasumicnoj grani:
null i `random` prolaze istom granom. Simulacija kandidata sama po sebi
ne znaci da aktivna konfiguracija bira najbolji rezultat.

Dokaz: `Debug/reverse/doctorcolor/pick_behavior_literals.json` cuva SHA-256
biblioteke i metadata fajla, RVA slota, relocation addend, kodirani token,
indeks literala i dekodirani tekst. Reference u `Use` su:

| grana | RVA slota | literal indeks | tekst |
|---|---|---|---|
| pickRandomlyChance (+0x58) | 0x702e390 | 36265 | random |
| pickHighestChance (+0x50) | 0x7095a18 | 31804 | highest |
| pickLowestChance (+0x54) | 0x7095a28 | 33598 | lowest |

Koriscen je `base.apk` procitan ADB kopiranjem instaliranog paketa u
`Debug/reverse/apk_5.817/base.apk`, bez Frida attach-a. Stari backup
`setup_new_pc/payload/apk/matchmasters/base.apk` ima drugaciji metadata
fajl i daje pogresne literale za ovu biblioteku. U v39 string tabela koristi
offsete; ELF `.rela.dyn` vodi od reference preko RELATIVE addend-a do
kodiranog string tokena. Za kind=5, indeks je `(token & 0x1fffffff) >> 1`.

Nasumicni selektor na RVA 0x3c1335c uzima `Range(0, list.Count)` i vraca
element sa tim indeksom. `RandomWrapper::Range` (0x5af1fd8) koristi ostatak
deljenja `Next()` opsegom. Ovo nije reprodukcija sekvence Python RNG-om;
za potpuno identican izbor na istoj tabli treba stanje/seme engine RNG-a.
Ne proglasavati strogo uniformnu raspodelu dokazanim svojstvom RNG-a samo
na osnovu imena RandomWrapper.

`RandomWrapper::Chance` (0x5af5c4c) poredi `Next() % 100 <= percent`,
ne `< percent`. Parametar 20 zato nije dokaz tacno 20% verovatnoce.
To ne menja granu izbora u ovoj konfiguraciji (null i random imaju isti
izbor), ali je vazno za druge boostere i rekonstruisanje RNG sekvence.

Provera arhive: u 1072 snapshot-a sa poljem pickBehavior za ability 27 ono
je null; rezultat je sacuvan u `pick_behavior_snapshots.json`. To nije dokaz
da stanje nikad ne postaje random: arhiva moze da sadrzi klonove i nepotpun
obuhvat aktivacija.

## Provera na snimcima (2026-10-31, 44 aktivacije)

* `sourceColor/targetColor/isLast` iz memorije tokom upotrebe: 828/828 parova
  odgovara tabeli (prvi korak = prve dve boje putanje, poslednji = druge dve).
* Korak koji je cisto uhvacen prebojio je SVE plocice izvorne boje u 81/84
  slucajeva (3 su uhvacena usred animacije ili su imala figure moda).
* Skor se tokom prebojavanja ne menja; poeni dolaze iz kaskada posle `EndMove`.

Provera skripta: Claude scratchpad `dc_activations.py` (cita
`Debug/memory_board/board_snapshots*.jsonl`).

## Doctor Color SE (buster 45), 2026-11-20 — NIJE portovan

Snimci: `Debug/research/20261119_235400_square-match` (Showdown, 5 aktivacija) i
`Debug/research/20261120_113126_super-sized` (Solo, pvpMode 1, 8x8, 10 aktivacija,
`swap_traces` sa tablom posle prebojavanja). Kod: `Debug/reverse/doctorcolor_se/`
(ARM listing; Ghidra projekat foxyfull ima base +0x100000 u odnosu na indeks).

### Sta je potvrdjeno (2026-11-20)

* **Konverzija**: jedan korak, ne dva. Putanja je trojka (`DoctorColor::get_ColorPaths`,
  14 trojki), `MakeColorSwaps` koristi `colors[0]` i `colors[1]`; `GetDefaultColorPairs`
  (SE ctor, `ColorPairs`) vraca **par** `p` za `(colors[0], colors[1])`, i tada
  `colors[0]` **i** `p` postaju `colors[1]`. Specijali zadrzavaju tip a menjaju boju;
  `BoardSpecial` (mode target) se preskace. Provereno celija-po-celiju: za svih 10
  aktivacija iz `20261120_113126` prebojena tabla iz snimka
  (`swap_traces[0].events[destroy_pass].grid`) se dobija sa **0 razlika**.
* **Tabela parova** (engine `SlotColor`: red2, green3, blue4, yellow5, orange6, purple7,
  white8), redom iz ctor-a:
  `(6,3):7 (6,5):3 (6,7):5 (3,6):7 (3,5):6 (3,7):5 (5,3):7 (5,6):3 (5,7):6 (7,3):5 (7,5):3 (7,6):5`.
  Druga tabela (sa belom 8) vazi za `colorAmount == 8`; profil ima `colorAmount 3`.
  Ako para nema na tabli: protivnikova boja (solo: 2 ako smo 4), pa nasa, pa par.
* **`Use` uvek trosi 14 izvlacenja** pre prve dopune: `AvailableColorPaths`
  (sve tri boje trojke na tabli) se mesa sa game RNG-om (jedan `Next` po putanji,
  stabilan `OrderBy`); za ove table je dostupno svih 14 trojki, pa je 468 -> 482
  u aktivaciji 003 (i isto u svih 10).
* **Izbor para nije slucajan indeks**: `pickBehavior` je null, `pickRandomlyChance 0`,
  `pickHighestChance 80`, `pickLowestChance 0`; tri `Chance` poziva i izbor idu kroz
  *svez* `RandomWrapper` sa semom game brojaca (ne game RNG), pa je grana po aktivaciji
  konstantna. Kandidati su prvih `colorPathsMaxAmount` = 7 izmesanih trojki, a bira se
  najbolji/najgori po simuliranom skoru (`MakeColorSwaps` na klonu).

### Zasto jos nije portovan (izmereno, 2026-11-20)

Prebojavanje je tacno, ali **razresavanje posle prebojavanja** se ne poklapa:
u aktivaciji 003 simulator prve kaskade potrosi 196 izvlacenja (482 -> 678), igra 197
(482 -> 679), a onda igra **aktivira Lightning koji je nastao u toj kaskadi**
(`piece_area` 13 polja dijamanata oko [4,4], pa `fireworks` 679 -> 743, 64 izvlacenja),
dok ga simulator ostavlja na tabli (`special_creation ... survives: True`). Sa
`specials_explode_immediately=True` tabla se i dalje ne poklapa (51 celija, rng 1144
naspram 1294, skor 83 naspram 103). Znaci: nije problem SE nego to kako simulator
tretira specijal nastao u kaskadi koju je pokrenulo prebojavanje (bez swap origina);
`doctor_color_pick`/`convert` za tip 45 nisu hookovani. Prvi sledeci korak je to pravilo
u `GameLogic`/`BoardModel` (kreiranje specijala + jedno izvlacenje za izbor polja), pa
tek onda `engine_doctor_se.py` i `tests/fixtures/doctor_color_se/`.

### Druga runda (2026-11-20): kod potvrdjen, sweep nije nasao pravilo

Sve tabele su iz `Debug/reverse/dcse/` (`tools/il2cpp_disasm.py`):

* `ComboModel::IsFiveShapeFast` 0x59cc37c: za svaki red/kolonu bitmaski, vraca true ako
  neki red ili kolona sadrzi **5 uzastopnih** celija skupa. `GetComboType` 0x59cbc4c:
  Five (4) prvo, pa `count>=5 && redova>=3 && kolona>2` -> RShape (5), pa Crosshair (8),
  pa FourRow/FourColumn, inace Row/Column. `classify_cells` to vec radi isto.
* `GameLogic::MakeSpecialSlots` 0x5957238 NE trosi RNG: klonira `SlotModel` iz
  `combo+0x70` i upisuje ga na `combo.Position` (`set_Item`). Znaci izbor polja specijala
  nije ono jedno izvlacenje.
* `BoardAnalyzer::ConcatCombos` 0x592bd1c ne spaja pozicije: za svaki combo trazi
  (`IsCombosSharingSameColor` 0x5929db4 = presek pozicija) drugi combo iz nove liste,
  upisuje `[combo+0x28] = 2/3` (lanac) i brise `[nadjen+0x70]` (specijal). Liste se samo
  dodaju (`List.AddRange`). Znaci engine drzi comboe odvojeno i oznaci lanac.
* Postojeci model za "specijal nastao u kaskadi": `_classic_specials` +
  `_tag_auto_explosions` + `_with_auto_explosions` (move_strategy ~6176-6215): svaki
  klasicni specijal nastao u potezu dobija **rank-11 combo posle dopune** i tu opali.
  To je tacno oblik dogadjaja iz snimka (679 posle dopune), ali je vezan na
  `specialsAutoExplode`/Blow Em Up, a ovaj profil ima `specialsAutoExplode false`.

Sweep na 003 (64 celije + specijali, rng igre 1294, skor 103): varijante grupisanja
(union / svaki run odvojeno / petica odvojena) x drain 14/15 x `specials_explode_immediately`
False/True daju najbolje 48 pogresnih celija i rng 1082 — nijedna se ne poklapa, pa razlika
nije samo u tom pravilu: vec prva kaskada ostavlja drugu tablu. Sledece je citati
`BoardAnalyzer::GetAllCombos`/`GetSlotCombosForPiece` (koji comboi postoje posle
prebojavanja bez zamene) i `_with_auto_explosions` okidac u engine-u, ne podesavati
`find_matches` napamet.

## VAZECI LISTINZI (2026-11-20)

**Vaze samo listinzi u `Debug/reverse/dcse/` regenerisani 2026-11-20 uz
`Debug/strategy_lab/native-current/libil2cpp.so` (129.100.000 B, module_size
131.455.392 iz `data/il2cpp_symbols.json`).** Stariji fajlovi istog imena bili su
radjeni uz `Debug/reverse/libil2cpp.so` (122.794.688 B) koji ne odgovara
2026-11-20 dumpu simbola, pa im adrese (0x59xxxxx) padaju **nasred funkcija**;
njihovi zakljucci o `MakeSpecialSlots`/`ConcatCombos`/`GetComboType` nisu vazeci
dok se ne ponove. Nove adrese (RVA iz istog liba):

| metod | RVA |
|---|---|
| `BoardAnalyzer::GetAllCombos` | 0x5d99fdc |
| `BoardAnalyzer::GetCombosFromTestList` | 0x5da7aa0 |
| `BoardAnalyzer::GetSlotCombos` | 0x5da5aec |
| `BoardAnalyzer::GetSlotCombosForPiece` | 0x5da5c54 |
| `BoardAnalyzer::ComboSlotsForColor` | 0x5da62b4 |
| `ArrangeCombosIntoComboModelList` | 0x5da65ec |
| `AddComboToListOfComboModels` | 0x5da6734 |
| `BoardAnalyzer::MakeSpecialSlotCreated` | 0x5da881c |
| `GameLogic::MakeSpecialSlots` | 0x5dd3138 |
| `BoardAnalyzer::ConcatCombos` | 0x5da83c0 |
| `IsCombosSharingSameColor` | 0x5da6504 |
| `ComboModel::GetComboType` / `IsFiveShapeFast` | 0x5e44560 / 0x5e44c90 |
| `ComboModel::get_isHighRank` | 0x5e443ec |
| `MatchChecker::TryCreateMatch` | 0x5e09270 |
| `BlobMatchChecker::TryCreateMatchInternal` | 0x5e086f0 |
| `BlobMatchChecker::CheckPotentialComboPoints` | 0x5e08a00 |

## Treca runda (2026-11-20): comboi posle prebojavanja i ono jedno izvlacenje

**Koji comboi postoje bez zamene.** `GetAllCombos(logic, testSlots=null, …)` pravi
`bool[Rows,Columns]` i skenira **celu tablu** (spolja `Columns`, unutra `Rows`), pa
`GetCombosFromTestList` za svaku jos neobelezenu plocicu zove
`GetSlotCombos(board, point, checkList, CurrentEnergyChargingColors)` i tek onda
obelezi sve celije nadjenih comboa u `checkList` (to je jedini dedup;
`ConcatCombos` se tu ne zove). Bez zamene nema `MergeSwapData`, pa `GetSlotCombos`
ide pravo u `GetSlotCombosForPiece`: `IsPieceWithColor`, pa `ComboSlotsForColor` za
`color` (i za `color2` uz klon `checkList`), `IsCombosSharingSameColor` (kad obe boje
daju combo a jedna je boja trenutnog igraca, druga se odbacuje), pa
`ArrangeCombosIntoComboModelList(longer, shorter, …)` -> do dva `ComboModel`-a.

Skupljanje nije "maximalni niz": `MatchChecker::TryCreateMatch` delegira na
`BlobMatchChecker` — markira pocetnu celiju, `CheckPotentialComboPoints` u dva
suprotna smera ose (min. duzina 3; za Square Match 4 dijagonale, min. 4), pa
**rekurzivno iz svake skupljene celije** i `RemoveDuplicates`. Combo je dakle
povezana grupa iste boje; `GetComboType` je klasifikuje (Five -> RShape ->
Crosshair -> FourRow/Column).

**Ko dobija specijal.** U `GetCombosFromTestList`, po kombinaciji:
`noSpecialPieces` (+0x276) -> nista; `combo.isHighRank` (`type-4 < 5`, tj. 4..8)
-> reason 1; `everyMatchIsSpecial` (+0x275) -> 2;
`colorMatchCreatesSpecial.Contains(comboColor)` (+0x1a0) -> 3;
`matchCreatesSpecialChance` (+0x1d8) >= 1 i `RandomWrapper::Chance` -> 4 (jedino
mesto koje tu trosi izvlacenje); inace nema specijala. Zatim: ako `hitPoints`
(SlotModel +0x20) >= 2 i `tryReplaceOriginWithHighHP`, origin se bira ponovo
unutar comboa; ako je HP > 1 specijal se ne pravi; inace `MakeSpecialSlotCreated`
na `combo.origin` (+0x30), boja = `GetComboColor`, pa `UpdateColorBasedAttributes`.
Za reason 1 tip je fiksna tabela po obliku: `(type-4)` -> `7, 6, 5, 4, 8`.

**Merenje na 003 (Doctor Color SE).** `Use` trosi 14 izvlacenja (468 -> 482),
kandidati `[(3,6,7), (7,3,5), (5,6,7)]`, indeks 1 -> putanja `(7,3,5)`
(ljubicasta->zelena, pa obe->zuta). Profil: `noSpecialPieces=false`,
`everyMatchIsSpecial=false`, `colorMatchCreatesSpecial=null`,
`matchCreatesSpecialChance=0`, `allSpecialsLightning=false`,
`extraMoveRandomSpecial=false` -> **samo high-rank combo pravi specijal, po fiksnoj
tabeli, bez RNG-a**. Post-recolor tabla (engine boje) ima tri grupe zute
(velicine 13, 4, 11); grupa od 13 sadrzi pet u koloni x=3 -> Five -> specijal 7
(Crosshair/Lightning), sto odgovara `value 7` koji igra kasnije detonira.

### Ono jedno izvlacenje: potvrdjeno vs pretpostavka

**Potvrdjeno iz snimka 003/004:**

* Prvi `destroy_pass` je na rng 482 i **`rng_after` je 482** — pronalazenje
  comboa, unistavanje i pravljenje specijala na 003 trose **0 izvlacenja**.
* Sledeci zabelezeni dogadjaj je na **679**, dakle dopuna je uzela **197**
  izvlacenja (482 -> 679).
* Cena dopune je **deterministicna: 5 + (broj boja Red/Blue u `spawnedColors`)
  po rupi** — 4 prevention flaga + `roll` + po jedan `Next(2)` za svaku
  crvenu/plavu u `spawnedColors` (`engine_spawn_weights.get_colors_priority`).
  `create_weights_list_new` i retry petlja **ne trose RNG**, pa nema varijanse
  po rupi. U profilu 003 `spawnedColors` sadrzi engine 2 i 4, dakle **tacno 7
  izvlacenja po rupi** (provereno po rupi na rekonstrukciji: svaka
  `rng_after - rng_before = 7`, bez ijednog retry-ja).
* Zato vazi **197 = 7 x rupe + chain_draws + draws_specijal-tile** (`chain_combos`
  su sirova `Next()`, `_spawn_special_tiles` je odvojen).
* **`destroy_pass` nije kompletan spisak razorenih celija**, pa se broj rupa iz
  njega ne moze izvesti. Sistematski: `piece_area` (efekat specijala) belezi
  svoje celije odvojeno, a u `destroy_pass` istog rng ulazi samo deo. Na 003:
  Row na (0,3) ima 8 celija, a u `destroy_pass` su 4 — `(1,3), (2,3), (6,3),
  (7,3)` nisu u listi. Isto vazi za sve ostale aktivacije: npr. bomba na (4,4)
  ima 13 celija, 10 nije ni u jednom `destroy_pass`-u sa tim rng-om; bomba na
  (5,5) u 001 ima 13 celija, 10 van liste. Znaci `destroy_pass` je zapis jedne
  faze unistavanja, ne ukupnog skupa.
* Iz toga, uz `197 = 7h + c + s`, ostaju dve aritmeticki konzistentne slike (i
  nijedna se ne moze iskljuciti iz 003/004):

  | rupe h | `chain_combos` c | specijal-tile s | ukupno |
  |---|---|---|---|
  | 27 (koliko pise u `destroy_pass`) | 0 | 8 (npr. 7 kandidata + 1 `spawnChance`) | 197 |
  | 28 | 1 | 0 (faza preskocena jer je `current >= maxSpawn`) | 197 |

  Port na 27 rupa racuna **28** izvlacenja za specijal-tile (27 kandidata + 1
  `spawnChance`), pa ni jedan red tabele nije ono sto port sada radi.

**Pretpostavka (nije potvrdjena):** druga slika — da igra ima 28 rupa i da je
visak od 1 izvlacenja `chain_combos=1` (196 = 28 x 7, pa +1). Argument je samo
posredan: kaskadu na 003 pokrece prebojavanje (bez swap origina), postoji tacno
jedan high-rank combo (pet u koloni x=3 -> Five -> Lightning koji igra kasnije
detonira), a `fill()` vec ima to izvlacenje za "combo unisten u kaskadi".
**Broj rupa koje je igra zaista dopunila nije izmeren.**

### Sta treba snimiti da se broj rupa i to izvlacenje razrese

1. **Tabla + `special_board` neposredno pre `BoardModel::RefillSlots`**, posle
   unistavanja i gravitacije (rupe su tada direktno vidljive; dovoljno je
   `color`/`color2`/`value`/`canBeMatched` po slotu). Ako moze i povratna
   vrednost `CountFillingSlotsAndUpdateColorsDictionary`, to je tacan broj rupa.
   `destroy_pass` iz sadasnjeg snimka to **ne moze da zameni** (nije kompletan,
   vidi gore), pa bez ovog snimka broj rupa ostaje 27 ili 28.
2. **RNG brojac na ulazu i izlazu iz `RefillSlots`** (i odvojeno iz
   `FillAllEmptySlots`) — razdvaja dopunu od faze specijal-tile.
3. **Trag po rupi iz dopune**: `(x, y)`, cetiri prevention flaga, izabrani
   prioritet, `roll`, izabrana boja, `spawnedColors` na ulazu, i svaki
   `spawnChance`/izbor specijal-tile. Time se i broj rupa i ono jedno izvlacenje
   vide bez nagadjanja (isti oblik kao `EngineRefill.fill` trace).

### Redosled u `BoardModel::RefillSlots` (novi listinzi, 2026-11-20)

`Debug/reverse/dcse/Match3Engine.BoardModel_RefillSlots.asm` (0x5e0b758):

1. `SpawningEngine::CountFillingSlotsAndUpdateColorsDictionary(board)` ->
   `positionsToFill` = **spisak rupa** (0x5e80ea4; vraca listu praznih polja).
2. `SpawningEngine::FillAllEmptySlots(logic, board, positionsToFill,
   isChainReaction, recalcColorCount=0)` (0x5e81bb0) — **samo dopuna**, 7
   izvlacenja po rupi (`RandomWrapper::Range` x4 + `GetColorsPriority` + `roll`).
3. `SuperFoceCombo` ako je `[engine+0x10]` (bela zastavica) — bez RNG-a.
4. `SetScoreAndEnergyOverrides` — bez RNG-a.
5. **`RandomSpawnSpecialSlots(board, logic, isRefill=true, positionsToFill)`**
   (0x5e7e088) — faza specijal-tile, **posle dopune**, i dobija **iste rupe**
   kao `availablePoints`. Zato je njen kandidatski skup = rupe.
6. `RandomSpawnLiveEventPieces` — isto posle dopune.

Dakle faza specijal-tile ne moze da bude pre dopune, i ne gleda drugu tablu:
`positionsToFill` je isti objekat koji je dopuna upravo popunila.

**Na sta se odnosi `current`** (`Match3Engine.SpawningEngine_ProcessSpecialTile.asm`,
0x5e7e9ac): `current` je **broj specijala tog `SlotValueType` na tabli u trenutku
poziva** (0x4048f44 nad `board`), tj. **posle dopune**: unisteni specijali ne
racunaju se, a specijali koje su comboi napravili u kaskadi racunaju se (oni su
na tabli pre dopune). Zatim:

* `amount = min(config[+0x14/+0x18] za refill, config[+0x28] - current)`, gde je
  `config[+0x28]` = `maxSpawn` (003: 4);
* ako je `amount <= 0`, faza se **preskace** (nula izvlacenja) osim kad je
  `logic.CurrentTurn == config[+0x10]` (forsirani potez);
* inace `ConvertSlots(..., amount, spawnChance, minGuaranteedPieces,
  availablePoints, excludedPoints)` (0x5e7eed8) prolazi kroz kandidate i za
  svakog baca **jedan `RandomWrapper::Chance(spawnChance)`** (0x5e7f588), osim
  dok je ostatak `amount` veci od preostalih kandidata (tada je konverzija
  garantovana, bez izvlacenja).

To objasnjava oblik `S` u tabeli iznad: sa `refillSpawn = 2` i
`spawnChance = 30`, ocekivano je ~2/0.3 = **~7 bacanja** da se dobiju dva
specijala — sto se poklapa sa `S = 8` za **27 rupa** (189 + 8 = 197). Varijanta
`28 rupa + 1` bi zahtevala da faza prodje tacno jedan kandidat, pa je slabije
podrzana kodom — ali se ni ona ne moze iskljuciti bez `current`/rupa iz snimka.

### Snimak pre `RefillSlots` (ugradjeno 2026-11-20)

Agent (`tools/matchmasters_board_dump.ts`, `installSwapTrace`) sada, uz iste
uslove kao ostali tragovi (samo ziva tabla tekuceg `GameLogic`-a), belezi:

* `refill_fill` — na ulazu u `FillAllEmptySlots`: `positions` (tacne rupe),
  `is_chain_reaction`, `rng_before` i `grid` **pre dopune** (rupe se vide kao
  prazna polja); na izlazu `holes` (broj rupa) i `rng_after` — RNG trosen samo
  dopunom.
* `spawn_specials` — na ulazu u `RandomSpawnSpecialSlots`: `is_refill`,
  `available` (kandidati) i `rng_before`; na izlazu `rng_after`.

`research_recorder` ih izdvaja i u vrh zapisa kao `refill_snapshots` (uz
`swap_traces`), pa se na sledecoj aktivaciji `holes`, `is_chain_reaction`,
dopuna-vs-specijali i ono jedno izvlacenje citaju direktno iz `NNN.json`.


### Treca runda (2026-11-20, libil2cpp 5.900): pravilo "odmah aktiviraj" PROCITANO

`DoctorColorSE::MakeColorSwaps` -> `ConvertSlots` -> `b__2`: `GetAllCombos(logic, null, false)`
pa `DestroyMatches(combos, chainReaction = 0)`: nov pocetak razresavanja, ne kaskada.
`MakeSpecialSlots` (0x5dd3138, bez RNG-a) novom specijalu stavlja `[slot+0x26] = 1`.
U `DestroyMatches` (0x5dcd2c4) posle `DropSlotsDown` + refill + `GetAllCombos`, ako
`rules.specialsAutoExplode` (MatchRulesModel+0xd0) ili `rules.specialsThatAutoExplode`
(+0x1d0) != null, `Where` sa predikatom `DisplayClass342_0.b__15` (0x5e007ec):

    ((rules.specialsAutoExplode && slot.IsClassicSpecial) ||
     (rules.specialsThatAutoExplode != null && rules.specialsThatAutoExplode.Contains(slot.type[+0x12])))
    && slot[+0x18] != 1 && slot.IsExplodeOnHit
    && (!slot.ShouldExplodeFromMatchOnly(logic) || slot[+0x26] != 0)

Za svaki takav slot: `[slot+0x26] = 0` i `ComboModel(type 0xb, [slot])` u listu sledece runde.
Dakle Lightning iz kaskade se aktivira jer je njegov tip u `specialsThatAutoExplode`.
Reader tu listu upisuje samo kao ime tipa (`"<System.Collections.Generic.List<...SlotValueType>>"`),
pa sadrzaj nije poznat: treba ga procitati sa zive igre. Uz `chainReaction > 0` engine za
ne-special-rank combo postavlja `[combo+0x48] = 1` i bira nasumicni slot iz comboa
u `[combo+0x30]` (RNG izvlacenje za polozaj specijala u kaskadi).

Zivo citanje 2026-11-20 (Solo super-sized, `gameRules` = GameLogic+0x48, reader sa citanjem
`List<SlotValueType>`): `specialsAutoExplode false`, `specialsThatAutoExplode null`.
Dakle uslov u DestroyMatches (0x5dcffe4) je u super-sized-u NETACAN i b__15 se ne zove:
Lightning iz snimka 003 se NE aktivira ovim putem. Lista u snimku ("<List...>") je iz drugog
rules objekta, ne iz `gameRules`. Uzrok trenutne aktivacije je i dalje otvoren.
