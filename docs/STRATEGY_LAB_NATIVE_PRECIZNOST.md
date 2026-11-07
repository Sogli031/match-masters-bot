# Preciznost native pravila — trenutna verzija

Analizirana je biblioteka iz trenutno instaliranog APK-a (build 145d6d8793109a), odvojeno od starog libil2cpp.so. Nova mapa ima 1372 Match3Engine klase, 6183 metoda i 155843 indeksirane adrese. Svih 96 prethodno očitanih instrukcija tri funkcije odgovara bajtovima trenutnog APK-a. SHA-256 i detalji su u Debug/strategy_lab/native-current/provenance.json. ASM granice potiču iz indeksa sledećeg metoda, ne predstavljaju nezavisno potvrđen kompletan CFG.

Implementirano u strategy_lab/native_rules.py:
- izbor rezultata kada engine već pozove CalculateEndGame: Solo poredi skor sa poslednjim ciljem, Rumble sa cutoff-om;
- Versus prvenstveno koristi broj osvojenih rundi kada je winByRounds, zatim najbolji skor runde kada je winByBestRound, inače ukupni skor;
- u toj konkretnoj funkciji izjednačenje vodi Player2Win; to nije dokaz da engine u svim formatima uopšte dozvoljava da partija stigne dovde sa izjednačenjem;
- stvarni terminalni GameState 2..7 sada ulazi u live audit kao eksplicitan ishod; negativna procesna stanja nisu završene partije.

Ovaj kod računa rezultat, ne trenutak kada treba završiti partiju. Nije uključen kao izmišljeni uslov završetka simulatora. Rekonstrukcija je proverena prema instrukcijama i metadata poljima iste verzije; još nema runtime poređenja svih grana rezultata na odigranim partijama.

RefillSlots zapravo redom zove:
1. CountFillingSlotsAndUpdateColorsDictionary
2. FillAllEmptySlots
3. SuperFoceCombo, samo ako je ForceNextCombo postavljen
4. SetScoreAndEnergyOverrides
5. RandomSpawnSpecialSlots
6. RandomSpawnLiveEventPieces

Zato uniformna dopuna sama ne reprodukuje stvarnu dopunu. Pravila i stanje svih ovih pomoćnih funkcija tek treba rekonstruisati pre oznake pune vernosti. Njihova imena su potvrđeni pozivi, a ne dokaz svih internih efekata.

RandomWrapper ima sopstvenu matricu, indeks, seed i counter. Next koristi temperiranje i sopstveni ciklus; standardni Python random nije dokazano ekvivalentan. Chance koristi poređenje ostatka sa percent preko <=, pa zamena generičkim < menja granično ponašanje. RNG nije zamenjen nagađanim algoritmom; nedostaje poređenje sekvence sa sačuvanim kompletnim RNG stanjem i rasporedom poziva spawnera.

Testovi: 24 prolaze (native rezultat, postojeći Lab i nastavci). Potpuna preciznost dopune, kaskada sa event figurama i celih partija NIJE potvrđena. Nisu poslati potezi niti promenjena aktivna politika.
