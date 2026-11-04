# Jedna partija -> paket za simulator

1. Zatvori Memory GUI i druge memorijske readere. Igru ostavi otvorenu.
2. Udji u zeljeni mod sa zeljenim boosterom/perkovima; sacekaj da tabla miruje.
3. Dvoklik `Snimi partiju za simulator.bat`, ili iz korena projekta:

```powershell
python tools/capture_match.py
```

Ne povlaci poteze dok komanda ne zavrsi. Alat proverava druge Python readere,
koristi jedan agent, cita polja i radi dva uzastopna citanja radi provere
promene stanja, pa se odvaja. Ne poziva managed metode niti menja polja igre.
Jednokratno skeniranje GameLogic objekata potrebno je za izbor partije;
ako izbor nije jednoznacan, alat odbija da pogadja.

Paket nastaje u `Debug/match_captures/<vreme>/`, uz istoimeni ZIP:

- `profile.json`: pravila, globalna i efektivna spawn konfiguracija, override-i,
  dostupni katalozi boostera i figura, aktivni boosteri/perkovi, tabla/celije,
  polja engine-a i stanje RNG-a. Imena/nalozi igraca nisu obuhvaceni.
- `simulator_input.json`: tabla i boje prevedene postojecim adapterom,
  poeni po boji i razreseni override-i.
- `resolved_overrides.json`: konkretna interpretacija podrzanih override-a.
- `manifest.json`: verzija formata, SHA-256 fajlova/agenta i nerazresena polja.

Paket se automatski registruje lokalno u `data/simulator_profiles/`. Nista se
ne salje preko interneta. ZIP mozes proslediti u chat ili preneti na drugi PC.
Za citanje bez igre:

```powershell
python tools/capture_match.py --inspect Debug/match_captures/IME_FOLDERA
```

Simulator moze da ga ucita preko `simulator_capture.load_capture(path)`.
To proverava integritet pre ucitavanja. Registracija konfiguracije ne znaci
da su svi algoritmi tog moda vec implementirani. `full_simulation_ready`
ostaje false dok ceo engine nije portovan i validiran; nerazresena citanja
ostaju vidljiva i komanda tada vraca izlazni kod 2, uz sacuvan paket.

Na hard kill-u procesa moze ostati `Debug/match_capture.lock`; pre uklanjanja
proveri da capture vise nije aktivan. Alat ga pri normalnom izlasku/izuzetku
uklanja. Nepodrzani/novi tipovi se beleze kao problem, ne pretvaraju u nulu.

Jedna pocetna captura je korisna za konfiguraciju konkretnog setupa. Ne
pokriva buduce Mutation Lab izbore, promene runde i sve interakcije. Za takve
promene napravi novi paket kada se tabla smiri. Paket je dvostruko provereno
citanje stanja, ne dokaz atomskog snapshot-a svih niti.
