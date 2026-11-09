# Zadatak: tačna dopuna dok je Jelly SE aktivan (Bullseye Bash, Solo)

Radiš u `C:\Users\PC\Desktop\memory gui` (Match Masters bot, Python). Cilj: da simulator
(`strategy_lab/simulation.py` + `move_strategy.py` + `engine_refill.py`) tačno reprodukuje
potez dok je na tabli aktivan Jelly SE booster (žele zona): tabla, specijali i RNG brojač.
Dok to ne važi, provera dopune ne sme da prijavljuje te poteze kao PROMAŠAJ, nego kao
"ne može da se proveri" (kao što je bilo za metlu pre porta).

Odgovaraj korisniku na srpskom (latinica). Ništa ne commit-uj dok korisnik ne kaže.
Ne diraj igru (adb, BlueStacks) i ne gasi/pokreći Memory GUI: druga sesija igra mečeve.

## Podaci

- Snimljen ceo meč sa RNG-om: `Debug/research/20261109_170604_bullseye-bash`
  (Bullseye Bash, pvpMode 1 Solo, booster Jelly SE). Uživo je dopuna pogodila 10 od 18;
  svih 8 promašaja je bilo dok je Jelly aktivan.
- Ti promašaji (pre/posle): `Debug/refill_misses/20261109_17*_bullseye-bash/000.json, 001.json`.
- Stanje jelly-ja je u `board_extra_data` snimka: ključevi `JellySEPhase0`,
  `JellySETargetColor0`, `JellySEallInfected0`, `JellySEsourceCellToInfected0`,
  `JellySEUsesLeftKeyPlayer0`, `JellySETotalUsesThisTurnTurnKey0`. U svim promašajima
  `JellySEPhase0 = 2`.
- `Debug/research` se ume obrisati: prelaze koje koristiš za testove kopiraj u
  `tests/fixtures/jelly_bullseye/`.
- Novi snimci: druga sesija može snimiti još mečeva sa jelly-jem (`Debug/research/*_bullseye-bash`).

## Šta već postoji

- `move_strategy.py`: `jelly_zone_cells`, `_jelly_zone_conversion_color`,
  `_apply_jelly_zone_conversion` (prefarbava komade u zoni posle spoja koji je dodiruje,
  samo kaskada 1), `_exact_jelly_plan`, `jelly_conversion_tiles`.
- `memory_gui.py: _jelly_zone_cells` čita zonu iz `BoardModel.extraData` (ne menjaj
  `memory_gui.py`, samo čitaj kao referencu).
- `strategy_lab/simulation.py`: korak sa `jelly_zone_cells` vraća "additional board layer"
  (nepodržano). Provera dopune (`refill_monitor.check_transition` preko
  `tools/analyze_research.capture_from/try_transition`) jelly zonu verovatno NE prenosi u
  simulator, pa jelly potez simulira kao običan i prijavljuje promašaj.
- Testovi: `tests/test_jelly_zone.py`, `tests/test_jelly_charge.py`, `tests/test_exact_jelly_plan.py`.
- Kod igre: klasa `Match3Engine.JellySE` (npr. `IsMatchTriggersJellyConversion`,
  `GetAllConvertSlotModels`, `GetNumberOfPiecesToConvert`, `GetBestPointsForInfection`,
  `AfterDestroyWithPassiveAbility`, `OnPlayerInitiatedMatch`, `GetWaves`).
  Disasembler: `python tools/il2cpp_disasm.py --method "Match3Engine.JellySE::Metoda" --out Debug/reverse/jelly`.
- Uzor kako je ovo urađeno za metlu: `docs/broom_port_prompt.md`, `tools/broom_check.py`,
  `tools/broom_diag.py`, `tools/broom_show.py`, `tests/test_sweep_broom_port.py`.

## Koraci

1. **Odmah:** neka provera dopune (`refill_monitor.py`) potez dok je Jelly aktivan
   (`JellySEPhase0` > 0 u `board_extra_data`, ili jelly zona pročitana) vodi kao
   "ne može da se proveri" sa razlogom, ne kao promašaj. Test na jednom sačuvanom promašaju.
2. Napravi alat kao `tools/broom_check.py` za jelly: za svaki prelaz snimka gde je jelly
   aktivan, prenesi zonu u simulator i uporedi sa igrom (tabla, specijali, RNG).
3. Utvrdi iz snimka + koda igre šta jelly radi u potezu: kada se zona prefarbava (pre/posle
   spoja, koja boja — `JellySETargetColor0`), da li i kako troši RNG (širenje zone,
   `GetBestPointsForInfection`, `GetWaves`), i kako to utiče na dopunu.
4. Prenesi to iza prekidača (npr. `JELLY_EXACT_PORTED`), uključi ga tek kad su skoro svi
   jelly prelazi tačni.

## Pravila rada

- Ceo paket: `python -m pytest -q -p no:cacheprovider tests`. Pre ove sesije pada 10 testova
  (test_auto_plan, test_cleo_exact_boundary, test_engine_billie, test_froggy_capture,
  test_mixy_liveness, 2x test_strategy_lab, test_strategy_lab_continuation,
  2x test_vinnie_se_heart_refill); ne smeju se dodati novi.
- Ne kvari metlu: `python tools/broom_check.py Debug/research/FOLDER` na snimcima
  `20261109_154641`, `160222`, `161238`, `163831`, `165206` (bullseye-bash) mora da ostane
  isti ili bolji (sada 32 od 39 tačno).
- Ne kvari obične poteze: ponovo pusti `Debug/refill_misses` kroz
  `refill_monitor.check_transition` i proveri da se nijedan ishod nije pogoršao.
- Novo pravilo iza prekidača, sa komentarom: šta je izmereno, na kom snimku, koliko tačno.
- Kad završiš: kratak izveštaj korisniku (koliko jelly prelaza tačno pre/posle, šta je
  uključeno, šta ostaje) i testovi za nove tačne prelaze.
