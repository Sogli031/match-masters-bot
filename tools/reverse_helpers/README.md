# Pomocne skripte za citanje libil2cpp.so (2026-10-14)

Sve rade nad `Debug/reverse/libil2cpp.so` i `data/il2cpp_*.json`. Pokretati sa `python -I`.

| skripta | sta radi |
| --- | --- |
| `branch_scan.py <rva> ...` | ko skace na adresu: i `bl` i repni `b` (il2cpp_disasm --xrefs vidi samo `bl`) |
| `strb_scan.py <offset> [1\|4]` | ko upisuje polje na datom ofsetu (`strb`/`str w`), npr. zastavice GameLogic-a; mnogo laznih pogodaka iz drugih klasa, gledati samo trazenu klasu |
| `cctor_points.py <rva> <size> <klasa>` | izvlaci staticke `Point[]` nizove iz `.cctor` (dometi specijala) |
| `combo_type_callers.py <tip>` | ko pravi ComboModel datog ComboType-a (`w1` pre poziva konstruktora) |
| `cleo_rule.py` | poredi izabranu Cleo boju sa simulacijom na svim Debug/runs |
| `run_tests.py tests/test_*.py` | zamena za pytest (pytest nije instaliran) |

Kodni segment: virtuelna adresa = ofset u fajlu + 0x4000.
