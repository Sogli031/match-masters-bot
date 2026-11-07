# Citanje logike igre iz libil2cpp.so

Do sada je bot ucio pravila igre posmatranjem: odigraj potez, snimi tablu pre i
posle, pogadjaj model. Ovaj alat cita isto to iz same igre.

Postoje dva sloja i vazno je ne mesati ih:

| sloj | sta je | odakle |
| --- | --- | --- |
| **konfiguracija** | brojke: `cost`, parametri bustera, tezine, trajanja | `LogicModel` u memoriji (server ih salje) |
| **logika** | algoritam: koje celije se biraju, kojim redom, po kom uslovu | kompajlirani ARM64 kod u `libil2cpp.so` |

Konfiguraciju cita memorijski reader. Ovaj dokument je o drugom sloju.

## Zasto je uopste potreban zivi korak

`global-metadata.dat` je verzija 39 i nema javni offline parser, pa se iz samog
APK-a ne moze dobiti mapa **ime metoda -> adresa koda**. Bez te mape `.so` je
120 MB neoznacenih instrukcija.

Zivi IL2CPP runtime tu mapu ima i daje je besplatno, kroz svoj metadata API.
Zato je pipeline u dva koraka: jednom se uzme mapa iz zive igre, a posle toga
se radi offline nad `.so` fajlom, sa ugasenim BlueStacks-om.

## Korak 1 — mapa simbola (jednom po verziji igre)

Isti preduslovi kao za memorijski reader: pokrenut Pie64, pokrenuta igra, root,
`namespace_cleaned=yes`.

```bash
python .\tools\dump_il2cpp_symbols.py --index
```

Nastaje:

* `data\il2cpp_symbols.json` — klase koje odgovaraju filterima (podrazumevano
  ceo namespace `^Match3Engine\.` plus `Ability`, `Booster`, `Powerup`,
  `SpecialPiece`, `MutationLab`): polja sa **ofsetima**, metode sa **RVA
  adresama**, potpisi, clanovi enum-a.
* `data\il2cpp_method_index.json` — kompaktna mapa `rva -> Klasa::Metod` za
  **ceo** image, oko 152k unosa. Disasembler je koristi dva puta: da zna gde se
  funkcija zavrsava (sledeci unos) i da imenuje ono sto funkcija poziva.

Drugi filter po potrebi:

```bash
python .\tools\dump_il2cpp_symbols.py --pattern "Match3Engine\.Logic" --pattern "Refill"
```

Agent je strogo read-only i **ne poziva nijednu managed metodu** — sve ide kroz
metadata API. To je isto pravilo koje je board agent naucio na tezi nacin
(`get_Count` je rusio proces na attach).

## Korak 3 — vrednosti parametara (uzivo, u partiji)

Kod daje formulu, a brojke stoje u `LogicModel.Instance` koji server posalje pri
ulasku u partiju:

```bash
python .\tools\dump_il2cpp_symbols.py --abilities-only
```

Nastaje `data\ability_config.json`: svih 49 bustera sa `cost`, `additionalParams`
i `conditionalOverrides` (isti buster ima druge brojke po `pvpMode` / `modeId` /
`rulesId` / `powerupId`).

Trazi **aktivnu partiju** — van partije je `LogicModel.Instance` prazan i alat to
kaze umesto da vrati prazne vrednosti.

I ovde nema poziva metoda: `List<T>` se cita kao `_items` + `_size`, a
`System.Object` vrednost se raspakuje po klasi svoje kutije.

## Korak 2 — disasembler (offline)

```bash
python .\tools\il2cpp_disasm.py --extract
```

Izvlaci `libil2cpp.so` iz `split_config.arm64_v8a.apk` u `Debug\reverse\`.
Radi se jednom; igra ne mora da radi.

```bash
python .\tools\il2cpp_disasm.py --grep "Ability.*Effect"
```

Za svaki pogodjeni metod nastaje `.asm` listing u `Debug\reverse\`. Listing nije
sirov — anotiran je:

* **pozivi** — svaki `bl` dobija ime metoda iz indeksa. Ako adresa nije tacan
  pocetak poznate funkcije, ispisuje se samo adresa; namerno se ne pise
  „najblizi simbol + ofset", jer to nije podatak nego nagadjanje.
* **konstante** — PC-relativni `ldr` se razresava i cita se stvarna vrednost iz
  fajla, kao int, float i double. Tu zive pragovi i mnozioci.
* **polja** — `ldr w8, [x0, #0x28]` postaje `field cost`, ako se prosledi
  `--layout SpecialAbilityModel`. Bez `--layout` alat nudi kandidate samo kad ih
  je najvise tri, da ne izmislja.

Sazetak na kraju listinga (`poziva` / `polja` / `konstante`) je obicno korisniji
od samog koda.

Korisne opcije:

| opcija | sta radi |
| --- | --- |
| `--method "Klasa::Metod"` | tacno ime (ili podniz ako nema tacnog pogotka) |
| `--grep "regex"` | regex nad `Klasa::Metod` |
| `--rva 0x289d80c` | direktna adresa, kad ime nije poznato |
| `--layout Klasa` | imena polja za anotaciju pristupa |
| `--list` | ispis svih poznatih metoda sa adresama |
| `--xrefs "Klasa::Metod"` | ko sve zove taj metod (sweep celog koda, ~3s) |
| `--stdout` | ispis umesto snimanja u fajl |

## Provereno na pravim podacima (2026-08-21)

Dump je pustan uzivo: **1564 klase / 7282 metoda** u `il2cpp_symbols.json` i
**151940 adresa** u indeksu.

Dve nezavisne provere da mapa nije izmisljena:

* `SlotValueType.BroccoBoogiePiece = 28` — isto sto je bot vec empirijski
  utvrdio za disko plocicu.

  Vrednosti enum clanova se citaju iz `value__`, ne iz redosleda deklaracije.
  Redosled je bio radna pretpostavka dok je `SlotColor` nije oborio: tamo je
  `Empty = 0`, `None = 1` i `All = 12`, dakle prva dva su zamenjena a posle
  `White = 8` ide rupa. Maska `0x1003` koja se vrti kroz ceo UFO kod je upravo
  ta tri (`Empty|None|All`) — „nije prava boja".
* `SweepItSEPieceLogic::isPiecePaintable` je 28 bajtova koda i svodi se na
  `slot.value == 0` (`SlotModel+0x12` = `value`). Metla dakle boji **samo obicne
  plocice** — nijedan specijal, bez obzira na boju. Prosledjena boja se u toj
  proveri uopste ne koristi.

Nusprodukt: svaki buster ima svoju klasu (`Match3Engine.FroggyFu`, `MixyMeow`,
`Cupid`, `UFOBeamSE`, `CleoCadabra`...), a parametri su imenovana polja —
`SweepItSEPieceLogic` recimo drzi `chanceToRemoveBlues`, `chanceToRemoveMaxScore`,
`minPiecesToPaint`, `maxPiecesToPaint`, `paintBehavior`. Vrednosti tih polja
dolaze iz `SpecialPieceModelParam`, sto znaci da se **citaju iz memorije**, ne
iz koda.

### Trazenje pozivalaca

```bash
python .\tools\il2cpp_disasm.py --xrefs "SpecialAbilityOverrideSegment::Includes"
```

IL2CPP nema relokacije za interne pozive, pa se pozivaoci nalaze samo prolaskom
kroz ceo kod. `bl` je jedna rec (`100101` + predznacni imm26 u recima), pa se
17 miliona reci dekodira direktno, bez disasemblera — traje oko 3 sekunde.

Ovo je u praksi najkorisnija komanda: „ko postavlja ovu vrednost" i „kad se ovo
uopste racuna" su pitanja na koja se odgovara odavde. Tako je nadjeno da se
override segmenti bustera biraju tacno jednom, u `SpecialAbility::.ctor`.

Virtuelni pozivi (`blr`) se ovako ne vide.

## Sta ovo ne resava

* **String literali se najcesce ne vide.** IL2CPP ih ne drzi kao C stringove uz
  kod nego u metadata kesu koji se puni pri prvom pozivu metoda, pa offline
  ostaju nerazreseni. Ono sto se razresi (`adrp`+`add` u `.rodata`) alat ispise.
* **Ovo je disasembler, ne dekompajler.** Nema C-a, nema petlji u citljivom
  obliku. Za slozene metode je realan put: procitaj sazetak (koga zove, koje
  konstante drzi), pa iz imena pozvanih metoda rekonstruisi tok.
* **Virtuelni pozivi (`blr xN`) se ne razresavaju.** Meta se zna tek u izvrsenju.
* **Genericke i inflated metode nisu u indeksu.** IL2CPP runtime helperi i
  generici se ne mogu nabrojati kroz `image.classes`, pa veliki deo `bl` meta
  ostaje kao gola adresa. Alat ih tako i prijavljuje (`0x... (nepoznato)`) —
  namerno, umesto da ih pripise najblizem simbolu.
* **Adrese vaze za tacnu verziju APK-a.** Posle apdejta igre oba koraka se
  ponavljaju; `runtime.version` je zapisan u oba JSON-a upravo zbog toga.

## Redosled kad se nesto konkretno istrazuje

1. `--list | grep` da se vidi kako se metod zove.
2. Disasembluj ga i procitaj sazetak — koga zove.
3. Disasembluj i te pozvane metode. Prava logika je skoro uvek jedan nivo nize
   (`GetAreaOfEffectDestructionSlots`, `GetAbilityPositions` i slicno).
4. Nalaz uporedi sa onim sto simulator vec radi, pa upisi razliku u
   `docs/game_mode_rules.md` ili odgovarajuci test.
