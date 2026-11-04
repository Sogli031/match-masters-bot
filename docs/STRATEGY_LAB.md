# Strategy Lab — lokalno uputstvo

Ovo je početna, **delimična implementacija**. Završen je tok: izbor zabeleženog režima/setupa → eksperiment → isti selektor odluke u offline i live radu → rad u senci ili eksperimentalna aktivna odluka. Nije završen kompletan simulator partije ni optimizacija opreme.

## Pokretanje i izbor

1. Dvoklik na `Pokreni Strategy Lab.bat`, ili u Memory GUI-ju izaberi **Strategy Lab** u gornjem meniju. Postojeći otvoreni Memory GUI treba restartovati da dobije meni i integraciju.
2. Klikni **Učitaj instalaciju i snimke**. Podrazumevani datum je današnji; prazno polje čita sve `Debug/runs`.
3. Na kartici **Režimi, cilj i oprema** filtriraj format i pravila table. Označi više redova pomoću Ctrl/Shift. Svaki red vezuje format, mod, cilj i stvarno zabeleženi booster/perk slotove. **Označi sve prikazane** bira te postojeće kombinacije.
4. `solo_unclassified` znači da snimak dokazuje Solo strategiju, ali ne dokazuje da li je Showdown, Rumble ili Party. Alat ne izmišlja format. Trenutna server rotacija nije dostupna iz starih snimaka.
5. Izaberi `quick` (do 40 jedinstvenih tabli po modu) ili `detailed` (do 200). Razlika je obim podataka, ne obećanje veće vernosti simulatora.
6. Klikni **Pokreni novi** i izaberi novo ime `.sqlite` posla. Izvori i konfiguracija zamrzavaju se u bazi.

Kartica **Podrška instalacije** prikazuje svih 36 `GameMode` vrednosti, 49 boostera iz lokalnog `data/ability_config.json` i 15 vrednosti perkova uključujući prazan slot. `booster_action=none` znači „bez posebnog načina aktivacije“, a ne „nema boostera“. Identitet koristi engine ability ID kada je zabeležen.

## Pauza, nastavak i rezultati

**Pauziraj** završava tekuću tablu i čuva potvrđene pokušaje. Možeš zatvoriti prozor ili računar. Sutra otvori ekran, klikni **Otvori posao…**, izaberi isti `.sqlite` i klikni **Nastavi**. Ne treba otvarati igru.

Jedna transakcija čuva sve profile za jednu tablu. Primarni ključ sprečava dvostruko brojanje. Nedovršen pokušaj se posle prekida ponavlja; potvrđen pokušaj se ne ponavlja. OS zaključavanje sprečava dva workera nad istim poslom. `.sqlite-wal` i `.sqlite-shm`, ako postoje dok proces radi, pripadaju bazi: ne kopirati samo glavni fajl usred pisanja. Zatvori worker pre prenošenja baze.

Prikazuju se završene kombinacije, table, procene profila i ETA posle pet merenja. Broj simulacija u JSON izveštaju broji samo podržane prefikse, ne odbijene zahteve.

**Otvori rezultate** prikazuje JSON sa odvojenim rezultatima po identitetu, razlozima izostavljanja, intervalima i konkretnim tablama. Pored baze automatski nastaju `.report.json`, `.report.md` i worker log. U JSON-u `differences` sadrži ilustrativne najveće razlike; to nije dokaz učinka cele partije.

## CLI za ponovljiv eksperiment

U PowerShell-u, iz korena projekta:

```powershell
python -m strategy_lab experiment --job Debug/strategy_lab/moj-eksperiment.sqlite --day 2026-10-31 --mode None --mode "Color Crush Mode" --seed 1729 --limit 2000 --detail detailed
```

Ova komanda je zaista izvršena sa imenom `strategy-lab-final.sqlite`. Postojeća baza se nikad ne prepisuje. Za novo izvršavanje izaberi drugo ime.

```powershell
python -m strategy_lab pause Debug/strategy_lab/moj-eksperiment.sqlite
python -m strategy_lab resume Debug/strategy_lab/moj-eksperiment.sqlite
python -m strategy_lab status Debug/strategy_lab/moj-eksperiment.sqlite
python -m strategy_lab report Debug/strategy_lab/moj-eksperiment.sqlite
python -m strategy_lab catalog
```

Izmena koda pravila ili profila zahteva novi eksperiment. Stari izveštaji ostaju čitljivi. Seed određuje podelu jedinstvenih tabli i bootstrap; ova verzija ne uzorkuje nepoznatu dopunu. Ne predstavlja ponavljanje istog determinističkog prefiksa kao više nezavisnih simulacija.

## Uključivanje u Memory GUI

1. Otvori rezultate i karticu **Rezultati i live profil**.
2. U gornjoj listi izaberi tačan format/mod/cilj/setup. Izaberi `direct`, `extra` ili `charge`.
3. **Rad u senci**: postojeća strategija igra; isti `choose_action` kao offline beleži novu preporuku i metu.
4. **Aktivan eksperimentalni profil**: na podržanom stanju nova politika bira native potez. Ovo nije profil potvrđen za uspeh cele partije. Trenutno nema takvog potvrđenog profila.
5. **Postojeća strategija** odmah vraća prethodno ponašanje. Restart bota nije potreban za promenu izbora. Izbor i profil vide se na dnu Lab ekrana i u rezultatu izvršenog swipe-a u Memory GUI-ju.

Podrazumevano je postojeća strategija. Tokom isporuke nije uključena nijedna aktivna politika niti poslata akcija igri.

Profil vezuje format, pravila i zastavice, statički cilj i opremljeni setup. Trenutni skor nije deo identiteta cilja. Potrošeni perk ostaje deo identiteta originalnog setupa. Nepoznat booster, druga oprema, nepotpun mod, dostupni perk, spreman booster, nepodržana figura, pasivni efekat ili nestabilna tabla vraćaju postojeću strategiju uz razlog. Ručne komande Extra Move/Most Points/Least Points ostaju njihove izričite komande; profil se primenjuje na standardni `highest_points` tok.

Live adapter ponovo enumeriše sve legalne zamene i podržane specijalne kombinacije kroz isti mehanizam kao offline. Ne koristi `score > 0`, top-k niti strateški gate kao test legalnosti. Podržana stanja su ona u kojima trenutno nema dostupne alternativne booster/perk akcije. Dostupni perk ili spreman booster izazivaju eksplicitni fallback cele odluke; nisu tiho izbačeni iz poređenja.

Tačka izbora je posle native strateških gate-ova i posle provere table/claim-a, pre postojećeg izvršenja. Native objekat odluke ide postojećem izvršiocu. Provere bezbednosti i potvrde ostaju u botu. Po swipe-u traži se svež snimak ako izvor postoji; naredna odluka prolazi kroz uobičajeno ponovno čitanje table.

`Debug/strategy_lab/live.jsonl` odvojeno čuva preporuku oba pristupa, plan, poslati swipe i native zapažanja. Klik i rano očitanje nisu proglašeni potvrđenim ishodom. Konačan ishod ostaje `unknown` ako ga engine nije izričito isporučio. Paket pune odluke je u `Debug/strategy_lab/decisions` i može služiti za identičan replay kandidata.

Budžet izbora je 50 ms. Merenje na 50 stvarnih snimaka: medijana 21,95 ms, p95 30,39 ms, maksimum 32,19 ms, bez fallback-a zbog vremena u tom uzorku. Ako izbor prekorači budžet, postojeća strategija igra i razlog se beleži. Budžet se proverava nakon izračunavanja; nije preemptivno prekidanje Python funkcije. Merenje ne uključuje animaciju igre i disk audit posle izbora.

## Stvarna podrška i nezavršeni zahtevi

Delimični adapter prefiksa postoji za **None, Color Crush Mode, Vertical Rush Mode, Blow Em Up, Lightning Strike i Shared Energy**. Potvrda zajedničkog mehanizma za dve različite grupe pravila postoji u testovima i stvarnom eksperimentu za None i Color Crush. Ostala četiri adaptera nemaju jednaku potvrdu stvarnim snimcima. Nijedan mod nema oznaku verne simulacije cele partije.

Mera je **broj uklonjenih pločica u poznatom determinističkom prefiksu pre nepoznate dopune**. Nije heuristički score, skor igre, procenat završenih Solo izazova ili procenat Versus pobeda. Kod prelaza vraća tablu, resurse i preostale poteze, ali označava granicu nepoznate dopune i ne nastavlja praznu tablu kao da je validna cela partija. Množilac i protivnički odgovor cele partije nisu modelovani.

Nije implementirano pitanje A: verno inicijalizovanje i rangiranje alternativne opreme, uključujući sve legalne kombinacije i prazne slotove na početku. Nema inicijalizatora početne energije, specijalnih figura, pasivnih efekata i spawn raspodele za celu partiju. Nepodržana oprema se izostavlja, ne dobija nulu. Pitanje B je ograničeno na podržane swap-only odluke; vreme aktivacije boostera, redosled perkova i protivnička politika nisu predmet ovih eksperimenata.

Za ostale modove nedostaci su u katalogu i postojećem `docs/game_mode_rules.md`: npr. Column Mania traži stanje množilaca svake kolone; Color Climb par boja i rast množilaca; Hot Color sekvencu boja; Floor Is Lava stanje stubaca; Zany Zappers efekat sedme figure; Multiplier Mushrooms veran spawn i rast; Chest raspodelu novih kovčega. Ostali modovi nemaju verifikovanu inicijalizaciju i dopunu za Lab. Zbog toga se ne može ponuditi „proveren profil za svaki potez cele partije“ niti tvrditi da su svi kriterijumi originalnog zahteva završeni.

Postojeća strategija u eksperimentu znači istorijski zabeleženu native odluku. Obe grane meri trenutni adapter, čiji je hash zabeležen. To nije rekonstrukcija svih verzija istorijskog runtime-a. Tablice za izbor i završnu proveru su odvojene po hash-u jedinstvene table; ipak mogu poticati iz iste partije. Bootstrap intervali ne pokrivaju korelaciju unutar partije niti grešku modela. Nijedan profil se automatski ne proglašava boljim za celu igru.

## Razvoj i provera

Proverene su lokalna i navedena razvojna putanja. `C:\Users\PC\Desktop\Match-Masters-Bot-main - Copy` ne postoji. Arhivsko `docs/archive/flow.txt` pominje tu putanju za ML trening; u ovoj kopiji nisu pronađena primenljiva AGENTS/CLAUDE razvojna uputstva. Izmene su zato rađene ovde. Nisu menjani `turn_analyzer.py`, `turn_validation.py`, postojeći simulator pravila niti testovi drugog agenta.

Novi kod je u `strategy_lab/`; mali pozivi su u `runtime.py` i `memory_gui.py`. Offline paket ne uvozi `runtime`, `capture`, `pyautogui` ni `turn_analyzer`.

```powershell
python -m pytest tests/test_strategy_lab.py -q
python -m strategy_lab.benchmark
```

18 novih testova proverava identičnu offline/shadow akciju i metu, native izvršni objekat, dva prava snimka, dva skupa pravila, specijalnu kombinaciju, legalan potez sa negativnim utility-jem, pogrešan setup, nepotpun mod, rok, verziju pravila, pauzu/nastavak, zaključavanje workera, zamrznute ulaze, cilj bez trenutnog skora i povratak stare strategije. Tk ekran je inicijalizovan bez igre i uspešno kreira widgete.

U širem pokretanju 143 testa su prošla, a jedan postojeći test iz `test_auto_plan.py` očekuje srpski status dok GUI već vraća engleski. Ta nepovezana poruka nije menjana. Detaljan primer je u `STRATEGY_LAB_PRIMER.md`.
