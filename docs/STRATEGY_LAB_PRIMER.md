# Primer stvarnog eksperimenta — 31.10.2026.

Izvor: lokalni `Debug/runs`, dan 2026-10-31. Rezultat: `Debug/strategy_lab/strategy-lab-final.report.json` i istoimeni `.sqlite` posao.

Obrađeno je 1.274 jedinstvenih zabeleženih stanja table, 40 identiteta format/mod/cilj/setup i 5.096 procena četiri politike: istorijska odluka, `direct`, `extra`, `charge`. Podržana je 461 simulacija determinističkog prefiksa. Nema simuliranih celih partija, početnih tabli sa potvrđenog početka partije, niti uzoraka nepoznate dopune. Ostali zahtevi su izostavljeni uz konkretan razlog.

Worker je zabeležio 3,125 s obrade tabli; vreme čitanja izvora, zamrzavanja ulaza i pisanja izveštaja nije u tom broju. Seed je 1729. Konfiguracija čuva hash-ove pravila/profila i ulaznih fajlova. Izbor profila koristi samo selection table; konačna provera istog izabranog profila koristi validation table. Svaka poređena varijanta u istoj grupi koristi isti komplet podržanih tabli.

| Format / pravila / setup | Table za izbor | Izabran profil | Završna provera | Razlika prema istorijskoj odluci |
|---|---:|---|---:|---|
| Solo Challenge / None / Brocco Boogie, ID 44, prazni perk slotovi, cilj 1350 | 16 | direct | 6 | +3,00 pločice, 95% bootstrap CI [0,67; 5,83] |
| Solo Challenge / Color Crush / Queen Cobra, ID 32, prazni perk slotovi, ciljevi 800/1600/3175 | 11 | direct | 2 | 0,00 pločica, CI [0; 0] |
| Solo Challenge / Color Crush / UFO, ID 19, prazni perk slotovi, ciljevi 800/1600/3175 | 10 | direct | 4 | +4,50 pločica, CI [1,25; 7,75] |

Ovo nisu rangovi opreme: poređenja su unutar svakog stvarno zabeleženog setupa. Male grupe, korelacija među snimcima iste partije i ograničena mera ne dozvoljavaju zaključak o boljoj opremi, poenima cele partije ili uspešnosti Solo izazova. Color Crush sa Queen Cobra nema razliku na završnoj proveri. Nijedan profil nema oznaku potvrđene uspešnosti cele partije.

## Konkretna različita odluka

Snimak `Debug/runs/2026-10-31_13-04-40_351/move.json`, grupa sa ciljem 1350 i Brocco Boogie ID 44. Ovo je ista podržana grupa koja ima najviše selection tabli u ovom eksperimentu; nije proglašena najboljom opremom.

Tabla, vrednosti boja iz native koda, redovi i kolone od nule; sve specijalne figure su 0:

```text
    0 1 2 3 4 5 6
0   5 4 2 5 3 3 2
1   2 5 1 3 1 3 5
2   4 5 4 3 4 5 2
3   1 4 3 5 1 1 4
4   1 5 5 3 2 5 3
5   2 2 4 1 3 2 2
6   1 5 1 4 1 4 3
```

Istorijska strategija: **(3,2) → (3,3), desno**, prefiks 4 uklonjene pločice i garantovan extra potez. `direct`: **(5,3) → (6,3), dole**, prefiks 9 uklonjenih pločica, 3 plave, bez direktnog extra poteza.

Razlog razlike je eksplicitan: `direct` bira neposredan broj uklonjenih pločica, dok istorijska odluka bira extra. Razlika prefiksa je +5 pločica. Extra potez može kasnije vredeti više od toga; ovaj eksperiment to ne meri. Ovaj primer nije dokaz da bi nova grana osvojila više poena do kraja izazova.

## Šta je provereno

18 novih testova prolazi, uključujući offline/shadow paritet na stvarnim snimcima za None i Color Crush. Native bridge je dodatno izmeren na 50 stvarnih snimaka bez igre ili input drajvera: medijana 21,95 ms, p95 30,39 ms, maksimum 32,19 ms; pri budžetu 50 ms nije bilo prekoračenja u tom uzorku. Potpuni podaci su u `Debug/strategy_lab/timing.json`.

Live profil nije automatski aktiviran. Prvo ga je moguće izabrati u radu u senci. Nema verno simuliranog kompletnog setupa ili profila potvrđenog za ceo meč.
