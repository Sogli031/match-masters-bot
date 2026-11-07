# Pasivno snimanje native događaja

Pokreni BlueStacks, Match Masters i Attach Reader. PID se menja posle restarta. Pročitaj ga sa `adb -s 127.0.0.1:5565 shell pidof com.funtomic.matchmasters`.

Iz korena projekta:

```
python -m strategy_lab.passive_trace --pid 4324 --seconds 180
python -m strategy_lab.trace_report Debug/strategy_lab/passive/trace-YYYYMMDD-HHMMSS.jsonl
```

Snimač proverava početne bajtove svih 11 hookova prema APK-u pre povezivanja bilo kog hooka. Pomerena ASLR baza se podržava. Druga verzija, druga veličina modula ili izmenjeni početni bajtovi prekidaju povezivanje. Simboli i biblioteka su u Debug/strategy_lab/native-current. Posle promene igre prvo osvežiti oba iz iste instalacije.

Beleže se ulaz/izlaz RNG Next overloadova, Generate, RefillSlots, pet pomoćnih funkcija dopune i CalculateEndGame/EndGame. RNG zapis sadrži seed/index/counter, celu matricu pri prvom viđenju svakog RNG objekta i pre/posle Generate. Svaki poziv ima ID, thread i vreme; argumenti/return su sirovi bitovi i nisu automatski protumačeni kao rezultat. Nema pozivanja managed metoda, zamene rezultata, menjanja memorije ni kliktanja. Hookovi ipak mogu menjati vreme izvršavanja.

Prozor je ograničen trajanjem i 10000 događaja. Izlazni fajl nikad se ne prepisuje. Dostignut limit, greške memorije, prekidi i neupareni pozivi moraju biti uzeti u obzir pre validacije. Snimač se pri izlasku odvaja.

Za pokrivenost snimiti: običan potez sa dopunom, direktan extra, extra iz dopune, početak i kraj jednog Solo izazova. Booster/perk snimati kada ih korisnik inače upotrebi, bez obaveznog namenskog trošenja. Prazan trag ne potvrđuje pravila. RNG objekti mogu pripadati AI simulacijama: identitet partije i povezivanje sa punim tablama nisu još implementirani. Trenutni snimač zato priprema dokaz za rekonstrukciju, ali ne proglašava preciznom simulaciju dopune ili efekte opreme.
