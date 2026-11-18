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
