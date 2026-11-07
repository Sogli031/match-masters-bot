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
