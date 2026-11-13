# Memory GUI (Match Masters bot)

## Teske analize i BlueStacks

Igra (BlueStacks, `HD-Player`) uvek ima prednost. 2026-11-11 je replay analiza sa vise
procesa usporila igru na ~20 fps, i to i na Idle prioritetu i vezana za poslednje jezgro.

- Pre bilo koje analize koja traje duze od ~1 minuta ili koristi vise procesa
  (replay svih `Debug/runs`, `Debug/research`, `Debug/refill_misses`): proveri da li
  `HD-Player` trosi procesor (igra se). Ako se igra, **pitaj korisnika pre pokretanja**
  i ponudi da sacekas da zavrsi partiju.
- Kad se pokrene: samo preko `tools/gentle.py` (`gentle_pool()` / `make_gentle()`):
  Idle prioritet, logicka jezgra 10 i 11, najvise 2 procesa. Nikad `Pool(n)` sa vise
  procesa i nikad bez `make_gentle()`.
- Izlaz uvek u fajl, ne kroz `| tail`, da se rezultat ne izgubi.
- Kad korisnik kaze da igra koci: odmah ugasi sve svoje `python.exe` procese
  (ne `pythonw.exe` -- to je bot).

## Napredak testova i analiza

Korisnik pita "dokle je" i "kad ce da zavrsi": svaki duzi posao mora da pise napredak
u fajl, da odgovor bude tacan, ne procena napamet.

- Testovi (pun `pytest`): pokreni sa procentom u izlazu, ne sa `-q`
  (`-o console_output_style=count` ili podrazumevani `[ 45%]` stil), izlaz u fajl.
  Zapamti vreme pocetka; poslednji pun prolaz traje ~80-95 s na gentle jezgrima.
- Analize preko `gentle_pool()`: posle svake stavke upisi `uradjeno/ukupno`, proteklo
  vreme i procenu kraja (ETA = proteklo / uradjeno * preostalo) u log fajl.
- Na pitanje o napretku: procitaj taj fajl i reci procenat, koliko je proteklo i
  otprilike kad ce biti gotovo (tacno vreme na satu, npr. "oko 14:05").
