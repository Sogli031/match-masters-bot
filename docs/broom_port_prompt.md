# Zadatak: tačan port Sweep SE metle (Bullseye Bash, Solo)

Radiš u `C:\Users\PC\Desktop\memory gui` (Match Masters bot, Python). Cilj: simulator
(`strategy_lab/simulation.py` + `move_strategy.py` + `engine_refill.py`) da pokretanje
metle (Sweep SE, specijal 45 / `ms.SPECIAL_SWEEP_SE_BROOM`) reprodukuje igru TAČNO:
tabla, specijali i RNG brojač. Kad to važi za (skoro) sva snimljena pokretanja, uključi
`SWEEP_EXACT_PORTED = True` u `move_strategy.py`.

Odgovaraj korisniku na srpskom (latinica). Ništa ne commit-uj dok korisnik ne kaže.

## Podaci

Snimljeni mečevi (svaka mirna tabla + memorijski profil sa RNG-om), Bullseye Bash,
pvpMode 1 (Solo), booster je metla (pojavljuje se posle `activate_booster`):

- `Debug/research/20261109_154641_bullseye-bash`
- `Debug/research/20261109_160222_bullseye-bash`
- plus dva novija `Debug/research/2026110916*_bullseye-bash` (najnovija dva foldera)

Pokretanje metle = prelaz NNN -> NNN+1 gde u NNN ima specijala 45, a u NNN+1 manje.
Folder `Debug/research` se ume obrisati (`Debug/Obrisi snimke partija.vbs`): kopiraj
prelaze koje koristiš za testove u `tests/fixtures/broom_bullseye/` (tu su već 008/009,
021/022, 030/031 prvog snimka).

## Alati

- `python tools/broom_check.py Debug/research/FOLDER` — svako pokretanje metle prema
  svim potezima, ispisuje TACNO ili najbliži promašaj (RNG igra/sim, polja, specijali).
- `python tools/broom_diag.py Debug/research/FOLDER [008 021]` — sva 4 smera metle za
  svako pokretanje (koji smer je stvarno odigran vidi se po najmanjoj razlici).
- `python tools/broom_show.py Debug/research/FOLDER 30 up` — tabla pre, posle
  pakovanja metle, igra, simulator, događaji i dopuna.
- `python tools/il2cpp_disasm.py --method "Klasa::Metoda" --out Debug/reverse/broom`
  — disasembler koda igre (ARM64). Već rastavljeno u `Debug/reverse/broom`.
- `engine_rng.EngineRNG` (`lab["engine_refill"].rng.clone().next()`) za stvarne
  vrednosti izvlačenja; polje specijala u kaskadi = izvlačenje % broj_polja.

## Šta je utvrđeno (2026-11-09)

1. Pakovanje metle (`_sweep_se_packed_board`, stabilno, cela linija) je tačno. Varijanta
   sa direktnim zamenama je lošija.
2. Swipe metle troši 1 izvlačenje odmah (`SWEEP_PRE_REFILL_DRAWS = 1`).
3. Prvi sloj spojeva posle metle (`SWEEP_SPLIT_LINE_COMBOS`, `_split_line_combos`,
   `_SWEEP_DRAW_COLOR`): spojevi ciljne boje se dele na prave linije (L od 6+3 = dva
   spoja), samo oni troše izvlačenje, druge boje zadržavaju oblik i čiste se bez
   izvlačenja, specijal ide na PRVO polje spoja (x-major, kolona pa red).
   Rezultat: 6 od 14 pokretanja tačno (oba prva snimka), testovi u
   `tests/test_sweep_broom_port.py`.
4. `BoardAnalyzer.GetAllCombos` skenira x-major, ali traženje spojeva ide u native
   (`UnmanagedUtils`) — ne može se pročitati, samo meriti.
5. Munja (Lightning, specijal 4; u igri "Fireworks"): `BoardModel.GetFireworks(12, pos,
   ignore)` -> `GetSlotPrioritize`: prioritetna polja (SlotModel +0x21) idu prva bez
   mešanja; ako ih je < 12, ostatak (bez `ignore`) se meša (`rng.shuffled`, jedno
   izvlačenje po kandidatu) i dopunjava do 12. Preneto u
   `EngineRefill.fireworks_targets` + kuka `_ENGINE_FIREWORKS` + `_CASCADE_COMBO_DRAWS`
   (izvlačenja munje idu posle izvlačenja spojeva kaskade, pre dopune), ali je
   ISKLJUČENO (`LIGHTNING_EXACT_TARGETS = False`): na snimcima i dalje 100-200
   izvlačenja razlike.

## Šta ostaje (po prioritetu)

1. **L-oblik 3+4 (snimak 160222, prelaz 020, metla gore):** RNG tačan, ali igra pravi
   BOMBU (3) a simulator deli na liniju 3 + liniju 4 (raketa). Pravilo deljenja verovatno
   važi samo kad linija ima 5+ (030: 6+3 deljeno). Ispravi `_split_line_combos` i proveri
   da 008/021/030 ostanu tačni.
2. **Munja:** šta je tačno lista kandidata (sva polja ili samo komadi; prazna polja;
   specijali), šta je `ignore` (samo polja tekućeg spoja ili sve što se uništava u sloju),
   šta je flag +0x21 (rastavi `SlotModel` getter na +0x21 ili nađi u `data/il2cpp_symbols.json`),
   i KADA se munja aktivira (u kom sloju, pre/posle izvlačenja spojeva). Uključi
   `LIGHTNING_EXACT_TARGETS` samo privremeno za merenje.
3. Prelazi 017 (prvi snimak), 025 i 031 (drugi snimak): razlog nepoznat; 031 je 1 izvlačenje.

## Pravila rada

- Svaka promena mora da zadrži sve dosad tačne prelaze (pokreni `tools/broom_check.py` na
  svim folderima) i ceo paket: `python -m pytest -q -p no:cacheprovider tests`.
  Pre ove sesije već pada 10 testova (test_auto_plan, test_cleo_exact_boundary,
  test_engine_billie, test_froggy_capture, test_mixy_liveness, 2x test_strategy_lab,
  test_strategy_lab_continuation, 2x test_vinnie_se_heart_refill) — ne smeju se dodati novi.
- Obične poteze ne kvari: ponovo pusti sačuvane promašaje dopune (svaki folder u
  `Debug/refill_misses` ima 000.json/001.json; `refill_monitor.check_transition`) i
  proveri da se nijedan ishod nije pogoršao.
- Novo pravilo iza prekidača, sa komentarom: šta je izmereno, na kom snimku, koliko tačno.
- `SWEEP_EXACT_PORTED = True` tek kad su skoro sva pokretanja tačna; inače bot i provera
  metlu vode kao nepredvidivu, a to je ispravno.
- Kad završiš: kratak izveštaj korisniku (koliko pokretanja tačno pre/posle, šta je
  uključeno, šta ostaje) i dodaj testove za nove tačne prelaze.
