# Ucenje iz odigranih partija (learned_value)

Dva sloja iznad heuristike u `move_strategy.py`, oba nauceni iz `Debug/runs`
(tabla pre poteza, svi kandidati sa komponentama ocene, i sta je igra posle
uradila: poeni, punjenje metra, da li je potez zadrzan). Oba su opciona: bez
fajlova ispod bot igra tacno kao pre.

| Fajl | Pise | Cita | Sta nosi |
|---|---|---|---|
| `data/charge_value.json` | `tools/fit_weights.py` | `move_strategy` (kao i ranije) | ekonomija: vrednost celije punjenja, bustera, poteza |
| `data/learned_weights.json` | `tools/fit_weights.py` | `learned_value` | realizacija plavih, extra poteza, skala buducnosti; prekidaci `apply` |
| `models/move_value_model.json` | `tools/train_value_model.py` | `learned_value` | stabla (GBM) koja predvidjaju rezidual prioriteta; `blend` |

## Tok

```bash
python tools/fit_weights.py            # 1. ekonomija + kalibracija  (~1 min)
python tools/train_value_model.py      # 2. model vrednosti          (~3 min)
```

Redosled je bitan: trening cita ekonomiju iz `learned_weights.json` i
rekonstruise prioritet sa vec primenjenim mnoziocima. Oba alata primaju
`--since YYYY-MM-DD`, `--dry-run` (samo ispis) i `--runs DIR`. Model se upisuje
samo ako na test danima smanjuje gresku (`--force` zaobilazi).

Posle svake vece izmene heuristike (nove tezine, novi buster) ponovi oba
koraka: model uci rezidual prema *trenutnom* prioritetu, stari model uz nov
prioritet ispravlja pogresnu stvar.

## Valuta: jedinice simulatora, ne poeni

Poeni po ociscenoj celiji rastu tokom partije (versus: 1x na pocetku, 12-14x
pri kraju), pa se svaki potez i svaka aktivacija bustera prvo dele lokalnim
mnoziocem -- medijana `poeni / instant_score` susednih poteza iste partije,
bez samog poteza (`run_dataset.annotate_games`). Partija = niz runova istog
konteksta, istog dana, sa pauzama do 90 s i skorom koji ne pada.

Stvarna vrednost poteza (cilj modela):

    poeni / mnozilac + punjenje * charge_cell_value + (zadrzan potez) * move_value_total

## Sta je izmereno (2026-09-03, 14 398 runova, 10 166 poteza)

Ekonomija (jedinice simulatora):

| kontekst | celija punjenja | buster | potez (poeni) | potez (poeni+punjenje) |
|---|---|---|---|---|
| solo_race | 5.50 | 38.5 | 15.9 | 25.9 |
| solo_challenge | 6.21 | 43.5 | 11.0 | 21.6 |
| versus_2 | 4.89 | 34.3 | 14.6 | 23.2 |

Ranije rucno mereno (447 poteza): solo 5.14 / 36.0 / 16.3, versus 6.26 / 43.8 / 12.0.
`move_value` u `charge_value.json` ostaje medijana *poena* (ista definicija kao
ranije), da tezina extra poteza ne promeni skalu.

Kalibracija predvidjanja:

* plave: direktne se realizuju x0.99 (solo) / x0.89 (versus), posredne
  (kaskade, specijali) x0.93 / x0.83 -- simulator je dobar, mnozioci su blagi;
* extra potezi: obecani direktni i pouzdane kaskade zadrze potez u 98-100%;
  bez obecanja potez se zadrzi u 28% (solo, slucajne cetvorke iz dopune) /
  5% (versus);
* buducnost (`lookahead_bonus + board_potential`): nagib vrednosti sledeca
  tri poteza po obecanoj buducnosti je 0.07 (solo_race), 0.16 (solo_challenge),
  negativan (versus), korelacija ~0. Heuristika buducnost precenjuje; primenjen
  je mnozilac stegnut na donju granicu 0.25.

## Kako se primenjuje (`_weighted_priority`)

1. `future_factor *= future_scale(ctx)` -- popust na buducnost;
2. `blue_cells` se pre cenovnika deli na direktne i posredne i mnozi izmerenom
   realizacijom;
3. tezina garantovanog extra poteza se mnozi izmerenim udelom zadrzanih
   (samo popust, nikad premija; nepouzdane kaskade ostaju na nuli);
4. na kraju `+ blend * rezidual` modela, samo na spoljasnjem rangiranju
   (ugnjezdeni lookahead ostaje cista heuristika), stegnuto na +-60.
   Rezidual je u jedinicama stvarne vrednosti; na skalu prioriteta se vraca
   sa `residual_scale` = min(1/b, 2.0) (b = nagib linearne osnove, 0.205 na
   prvom treningu -- prioritet je ~5x "naduvan" preko odluka, ali unutar
   jedne odluke tolika skala preteruje, zato kapa 2x).

Prvi trening (6 272 poteza, 11 dana, validacija po danu): rang-korelacija sa
stvarnom vrednoscu 0.71 (sam prioritet) -> 0.80 (blend 0.5) -> 0.89 (pun
rezidual); MAE 20.2 -> 9.5. Model bi promenio kandidata sa najvisim
prioritetom u ~7.5% odluka (gornja granica, bez kategorijskih nivoa).
Trosak u igri: rangiranje ~40 ms po odluci, isto kao bez modela.

Kategorijski nivoi rangiranja (extra pre svega, disko, metla...) ostaju iznad
prioriteta, pa model bira *medju* kandidatima istog nivoa, ne preko njih.

## Iskljucivanje i podesavanje

* `MEMORY_GUI_LEARNED_VALUE=0` -- sve iskljuceno, bez brisanja fajlova;
  `=weights` -- samo kalibracija, bez modela.
* `data/learned_weights.json` -> `"apply": {"blue": true, "extra": true, "future": true}`
  gasi pojedinacne mnozioce; `"enabled": false` gasi sve mnozioce.
* `models/move_value_model.json` -> `"blend"` (0 = bez uticaja, 1 = pun
  rezidual); `python tools/train_value_model.py --blend 0.3` ga upisuje.
* `data/charge_value.prev.json` je kopija ekonomije pre poslednjeg merenja.

## Debug

`candidates.json` od sada nosi `priority_score` (heuristicki prioritet pre
reziduala) i `learned_residual`. `tools/rebuild_evaluation.check_reconstruction`
poredi offline rekonstrukciju sa upisanim prioritetom; trening ispisuje
medijanu razlike cim ima takvih snimaka.
