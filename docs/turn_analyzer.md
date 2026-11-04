# Offline analizator odluka (`turn_analyzer.py`)

Za svaku nasu odluku iz `Debug/runs`: sta je bot odigrao, sta je jos mogao i
koja pocetna akcija ima najvece ocekivane poene **do predaje reda**. Ne menja
nista u botu.

```bash
python tools/analyze_decisions.py decision 2026-10-31_11-46-47_172 --trace
python tools/analyze_decisions.py match 2026-10-31_11-40-09_780
python tools/analyze_decisions.py day 2026-10-31 --context versus
python tools/analyze_decisions.py validate --day 2026-10-31 --context versus
python tools/analyze_decisions.py refill-stats --since 2026-10-01
python tools/analyze_decisions.py compare stari.json novi.json
```

Opcije: `--seed`, `--samples` (najvise grana po akciji), `--detailed`
(64 grane za bliske kandidate umesto 8), `--max-steps` (eksplicitni limit),
`--all` (sve akcije u izvestaju odluke), `--workers`. Izlaz ide u
`Debug/analysis/` kao `.md` (citljivo, svaki red vodi do Debug foldera) i `.json`
(verzija analizatora, git commit, sha256 koda/modela/tezina/raspodele dopune,
konfiguracija, seed, sve akcije). Dve verzije na istoj grupi partija:
pokreni `match`/`day` sa obe, pa `compare`.

## Model

Tri odvojene operacije:

* `legal_actions(state)` -- swipe-ovi u oba smera (spoj ili kombinacija/disco),
  buster kad je pun, Remove Cross i Hammer na svim metama, Energy Boost, i
  redosledi dve slobodne akcije (EB -> RC@t, RC@t -> EB). Nema score gate-a.
  Smerovi i mete sa identicnim deterministickim ishodom dele racunanje i pisu
  se kao "ekvivalentne". Perkovi koje analizator ne simulira verno su legalni,
  ali se ispisuju kao nepodrzani -- ne dobijaju 0.
* `step(state, action, rng)` -- deterministicki deo iz `move_strategy`
  simulatora, zatim dopuna i kaskade dok se tabla ne smiri. Dnevnik dogadjaja
  belezi svaki talas, mnozilac koji je tada vazio, buster, perkove i zasto red
  ostaje ili prelazi. Extra i punjenje ne nose poene; buster nosi poene tek kad
  se ispali.
* `choose_action(state)` -- politika nastavka, ista za sve pocetne akcije
  (`POLICY_DOC`): pun buster prvo; zatim garantovani extra ako postoji; u
  poslednjem redu partije, pred swipe koji predaje red, perk sa najboljom metom;
  inace pohlepni swipe (jedinice + vrednost garantovanog extra + korisno
  punjenje). U ranijim redovima perk se cuva, a izvestaj pise koliko perkova
  ostaje pri predaji (njihova vrednost za kasnije redove nije u poenima).
  Vidi samo razresenu tablu.
* Pocetni planovi ukljucuju i "garantovani extra -> perk" (meta se bira na
  tabli posle extra-a). `tools/compare_perk_timing.py RUN ...` na istoj tabli
  poredi swipe, perk odmah i extra pa perk na 64 uparene grane, sa i bez poena
  bustera.
* Grane koje ne stignu do predaje (limit, tabla bez legalnog swipe-a jer se
  mesanje ne modeluje) su "prekinute": kod tri najbolje i odigrane akcije se
  jednom produze na 3x limit (isti seed); ako i dalje nisu zavrsene, pobednik
  se ne proglasava. Isto vazi kad je razlika objasnjiva poenima bustera.

Neizvesnost: prva nepoznata plocica (rupa za dopunu) ili nasumicna meta
(Crosshair, Lightning) se belezi kao `first_unknown`. Dopuna se uzorkuje iz
`Debug/analysis/refill_stats.json` (boja + mode figura na rupama, mereno na
potezima posle kojih je red ostao nas i sve poznate celije su se slozile); za mod
bez dovoljno merenja koristi se ravnomerna raspodela i to je oznaceno kao
neprovereno pravilo. Grana `i` svih pocetnih akcija ima isti seed, pa su razlike
uparene, a rezultat akcije ne zavisi od redosleda simuliranja.

Mnozilac: `score_multiplier` iz memorijskog snimka pre odluke kad postoji
(`Debug/analysis/snapshot_index.jsonl`), inace medijana poeni/instant tri
prethodna potvrdjena poteza iste partije. U Multiplier Mushrooms raste +1 po
pecurki i vazi vec za poene istog poteza (izmereno iz snimaka 2026-10-31).
Sat reda: tajmer stoji tokom animacija (`pauseTimerForAnimations`), akcija
trosi ~0.77 s (izmereno), ne botovih 6.5 s zidnog vremena.

Konteksti: versus (red = movesPerTurn + extra, pa protivnik; prikazuje se i
najbolji neposredan odgovor protivnika na predatoj tabli, odvojeno od nasih
poena), showdown/rumble/party (runda na sat), solo challenge (preostali potezi).
Rumble tip se cita iz memorije; bez nje se pogadja po broju rundi (oznaceno
"heuristika").

## Validacija

* Faza A (`turn_validation.phase_a_case`): legalnost odigrane akcije, poznate
  celije van rupa, mesto i tip specijala, deterministicki poeni (kad je mnozilac
  iz memorije), punjenje, garantovani extra vs zadrzan red, i stopa kaskada posle
  dopune (stvarno vs model).
* Faza B (`phase_b_case`): gde stvarni poeni padaju u simuliranu raspodelu
  (percentil, pokrivenost p10-p90, pristrasnost po modu i tipu akcije), ceo red
  sa oznakom kada je bot kasnije birao drugacije od politike nastavka. Dve
  odvojene cinjenice: `observed_extra` (swipe nije potrosio potez) prema
  P(extra), i `next_is_ours` (sledeca odluka je i dalje nasa) prema P(jos
  odluka). `kept_the_turn` iz observed_delta se ne koristi: u versusu je False i
  kad potezi padnu sa 3 na 2 a mi i dalje igramo.

## Poznata ogranicenja

* Doctor Color (ability 27 iz memorije): prebojavanje i kaskade su simulirani,
  uz oznacen uniformni izbor putanje (trajni pickBehavior jos nije razresen).
  Proverava se Square Match Solo Challenge; detalji u `doctor_color.md`.
  Za ostale bustere efekat se ne simulira: empirijski prosek poena po aktivaciji iz iste
  partije (inace `data/charge_value.json`). Svaka grana koja ga koristi je
  oznacena, a rangiranje koje od njega zavisi to i pise.
* Perkovi osim Remove Cross, Hammer i Energy Boost su nepodrzani.
* Rast mnozioca drugih modova (Lights Up, Column Mania, Madness...) nije
  modelovan u nastavku.
* Protivnikov odgovor je jedan pohlepan swipe bez njegovog bustera.
* Validacija 2026-10-31 (Mushrooms versus): simulator potcenjuje extra
  (60% predvidjeno, 80% stvarno) i precenjuje neposredne poene obicnog swipe-a
  za ~15%.

## Ispravke simulatora bota nadjene ovde

* `move_strategy._created_special_type`: 2x2 sa krakom bez reda i kolone od
  tri kroz istu celiju daje Crosshair, ne Bomb (76 prema 2 na snimcima
  2026-10-01..31; pravi L/T sa kvadratom ostaje Bomb 5/5). Test:
  `tests/test_square_arm_crosshair.py`.
* Nije ispravljeno u botu: u Multiplier Mushrooms Studio mnozilac raste +1 po
  pecurki, a `multiplier_mushrooms` sabira vrednost kape (1-4). Analizator
  broji pecurke (`_mushroom_count`).
