# Nastavci primera 4 + extra naspram 9

Dodati adapter koristi postojeći turn_analyzer bez prepisivanja njegovih pravila. Ovo je parcijalni nastavak implementacije, ne ispunjenje zahteva za cele partije.

Komanda: `python -m strategy_lab.continuation_audit --samples 64`.

64 zajednička seeda, jedna stvarna tabla usred igre. Obrada: 18.906 s. Istorijska grana: 38.672; alternativa: 30.391 normalizovanih poena pri x1. Stvarni množilac nije poznat. Razlika alternativa minus istorijska: -8.281, uslovni normalni 95% interval [-12.205, -4.358]. Interval ne pokriva grešku modela dopune niti nepoznat množilac. U ovom ograničenom modelu zaključak prefiksa se obrće kada se uključe nastavci i extra odluka.

Razlozi prekida: `{'unsupported_empirical_booster': 128}`. Završene cele partije: 0. Nijedan prekid nije završen izazov; empirijska aktivacija boostera se izričito odbija.

Brzi dijagnostički uzorak od 8 seedova trajao je 2.015 s; detaljni od 64 seedova 18.906 s. To nisu merenja punih UI poslova.

19 testova prolazi (postojeći Strategy Lab i novi test ponovljivosti nastavaka). UI, SQLite format, aktivna live politika i kod drugog agenta nisu menjani.

Preostalo: inventar nezavisnih partija sa potvrđenim početkom/krajem, validacija dopune i tranzicija, dva verno inicijalizovana setupa, cilj i završetak cele partije, zajednički live izbor boostera/perka i integracija novih poslova u UI/CLI. Rang setupova/politika za kompletne izazove i shadow primer boostera/perka nisu ovim radom dokazani.
