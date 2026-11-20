# Memory GUI (Match Masters bot)

## Teske analize

2026-11-17 korisnik: teske analize koriste **sva jezgra, normalan prioritet** (Idle
pravilo i vezivanje za jezgra 10-11 je ukinuto). `tools/gentle.py` (`gentle_pool()`)
to sada i radi (`FULL_POWER = True`); koristi ga za sve analize.

- Izlaz uvek u fajl, ne kroz `| tail`, da se rezultat ne izgubi.
- Kad korisnik kaze da igra koci: odmah ugasi sve svoje `python.exe` procese
  (ne `pythonw.exe` -- to je bot).

## Napredak testova i analiza

Korisnik pita "dokle je" i "kad ce da zavrsi": svaki duzi posao mora da pise napredak
u fajl, da odgovor bude tacan, ne procena napamet.

- Testovi (pun `pytest`): pokreni sa procentom u izlazu, ne sa `-q`
  (`-o console_output_style=count` ili podrazumevani `[ 45%]` stil), izlaz u fajl.
  Zapamti vreme pocetka; poslednji pun prolaz traje ~80-95 s (merenje sa 2 jezgra, sa svima brze).
- Analize preko `gentle_pool()`: posle svake stavke upisi `uradjeno/ukupno`, proteklo
  vreme i procenu kraja (ETA = proteklo / uradjeno * preostalo) u log fajl.
- Na pitanje o napretku: procitaj taj fajl i reci procenat, koliko je proteklo i
  otprilike kad ce biti gotovo (tacno vreme na satu, npr. "oko 14:05").

## Kad ne znamo kako nesto radi u igri: fajl za drugog agenta

2026-11-20 korisnik: za BILO STA u igri sto ne znamo kako radi (booster, perk, mod, refill,
kaskada, skor, UI tok... ne samo boosteri) i kad god zapne, ne cekaj da korisnik pita -- odmah napravi fajl za drugog agenta i reci mu da ga prosledi.

- Mesto: `C:\Users\PC\Desktop\prioritet_za_agenta\<N>_<Tema>.txt` (sledeci slobodan broj).
- Fajl mora biti **potpuno samostalan** (agent nema istoriju razgovora ni binarne fajlove):
  kontekst igre i teme, sta je vec potvrdjeno na snimcima, tacan problem,
  numerisana pitanja, format odgovora (pseudokod C# + `[KOD: adresa]` / `[PRETPOSTAVKA]`
  + lista nepoznatih `bl 0x...`), i stvaran primer sa snimka (tabla, ocekivano vs simulator).
- Na kraj nalepi ARM64 disassembly svih metoda o kojima pitas:
  `python tools/il2cpp_disasm.py --method "Klasa::Metoda" --stdout` (ili `--grep`, `--rva`).
  Imena/adrese nadji u `data/il2cpp_method_index.json` (`entries`, utf-8).
- Ono sto mozes sam da procitas iz disassembly-ja upisi kao "vec procitano", da agent samo potvrdi.
- Kad korisnik nalepi odgovor drugog agenta: odmah ga sacuvaj doslovno u
  `docs/agent_odgovori/<N>_<Tema>_odgovor.txt` (isti broj/tema kao pitanje; korisniku se
  istorija ne cuva). Na vrh fajla jedan red: datum, na koje pitanje odgovara, i sta je od
  toga potvrdjeno/ubaceno u port. Tek onda radi po odgovoru.
