"""Build a source-backed offline inventory; discovery is not verified support."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    symbols_path = ROOT / "data/il2cpp_symbols.json"
    symbols = json.loads(symbols_path.read_text(encoding="utf-8"))
    abilities = json.loads((ROOT / "data/ability_config.json").read_text(encoding="utf-8"))
    classes = symbols["classes"]
    by_name = {c["full_name"]: c for c in classes}

    def derives(c, base):
        seen = set()
        while c and c["full_name"] not in seen:
            seen.add(c["full_name"])
            parent = c.get("parent")
            if parent == base:
                return True
            c = by_name.get(parent)
        return False

    families = {
        "boards": [c for c in classes if derives(c, "Match3Engine.BoardModel")],
        "abilities": [c for c in classes if derives(c, "Match3Engine.Ability")],
        "pieces": [c for c in classes if derives(c, "Match3Engine.SpecialPiecesLogic")],
        "core": [c for c in classes if c["full_name"] in {
            "Match3Engine.BoardModel", "Match3Engine.GameLogic", "Match3Engine.SpawningEngine",
            "Match3Engine.PlayerControl", "Match3Engine.SlotModel", "Match3Engine.RandomWrapper",
            "Match3Engine.BoardAnalyzer", "Match3Engine.MergeTwoLogic"}],
    }
    tree = ast.parse((ROOT / "move_strategy.py").read_text(encoding="utf-8"))
    modes = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "GameMode":
            for statement in node.body:
                if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Constant):
                    modes.append({"name": statement.targets[0].id, "label": statement.value.value})
    inventory = {
        "scope": "5.817 static discovery; not a claim of completed reconstruction or simulator support",
        "runtime": symbols.get("runtime"),
        "symbols_sha256": hashlib.sha256(symbols_path.read_bytes()).hexdigest(),
        "local_modes": modes,
        "booster_configs": abilities["abilities"],
        "families": {key: [{"class": c["full_name"], "parent": c.get("parent"),
                            "fields": c.get("fields", []), "methods": c["methods"],
                            "status": "discovered_unverified"} for c in values]
                     for key, values in families.items()},
        "boundaries": ["Server rulesets are not equivalent to local GameMode labels.",
                       "A method listing is evidence of code presence, not reconstructed semantics.",
                       "Runtime overrides, RNG state and recorded behavior require separate verification."],
    }
    out = ROOT / "data/simulator_inventory.json"
    out.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Simulator: inventar i pokrivenost", "",
             "Generisano: `python tools/build_simulator_inventory.py`.", "",
             "Ovo je inventar koda 5.817, ne tvrdnja da su sva pravila procitana,",
             "implementirana ili validirana. Lokalni GameMode nije isto sto i server rulesId.", "",
             f"Lokalnih modova: {len(modes)}; konfiguracija boostera: {len(abilities['abilities'])}.", "",
             "## Grupe iz engine-a", "", "| grupa | klasa | metoda | status |", "|---|---|---:|---|"]
    for key, values in families.items():
        for c in values:
            lines.append(f"| {key} | {c['full_name']} | {len(c['methods'])} | inventarisano; nije sertifikovano |")
    lines += ["", "## Lokalni modovi", "", "| naziv | prikaz |", "|---|---|"]
    lines += [f"| {m['name']} | {m['label']} |" for m in modes]
    lines += ["", "## Boosteri iz konfiguracije", "", "| engine ID | naziv |", "|---:|---|"]
    lines += [f"| {a['type']} | {a.get('title')} |" for a in abilities['abilities']]
    lines += ["", "## Redosled rekonstrukcije", "",
              "1. Zajednicki engine: RNG, dopuna i tezine, spojevi, specijali, poeni, energija, extra i kraj reda.",
              "2. Square Match + Doctor Color: zatvoriti poznate rupe i proveriti na sacuvanoj partiji.",
              "3. Ostale table i override-i: svaki metod vezati za potvrdu iz koda i snimaka.",
              "4. Boosteri, pasive i perkovi; zatim njihove interakcije sa modovima.",
              "5. Podrska simulatora se priznaje tek posle regresionih testova i replay provere.", "",
              "Detaljni potpisi, RVA adrese, polja i server parametri su u `data/simulator_inventory.json`.",
              "Postojeci nalazi ostaju u `docs/game_mode_logic_from_code.md`, `docs/booster_logic_from_code.md`",
              "i pojedinacnim dokumentima. Njihovo postojanje samo po sebi nije dokaz kompletne podrske."]
    recorded = ROOT / "data/recorded_rulesets.json"
    if recorded.exists():
        catalog = json.loads(recorded.read_text(encoding="utf-8"))
        ids = sorted({str(v["rules"].get("id")) for v in catalog["rules_variants"].values()})
        lines += ["", "## Sacuvana memorijska evidencija", "",
                  f"Snapshot-ova: {catalog['snapshots']}; rulesId: {len(ids)}; "
                  f"varijanti pravila: {len(catalog['rules_variants'])}; "
                  f"varijanti boostera: {len(catalog['ability_variants'])}.", "",
                  "Ponovno generisanje: `python tools/build_ruleset_catalog.py`.", "",
                  "Izvorni fajl i broj reda za svaku konfiguraciju su u `data/recorded_rulesets.json`.",
                  "Ovo je arhiva, ne dokaz trenutne rotacije ili svih server modova.", ""]
        lines += [f"- `{rules_id}`" for rules_id in ids]
    extracted = list((ROOT / "Debug/reverse/simulator_all").glob("*.asm"))
    if extracted:
        lines += ["", "## Offline listing", "",
                  f"Izvezenih listinga: {len(extracted)} u `Debug/reverse/simulator_all`.",
                  "Imena sadrze RVA da overload-i ne prepisuju jedni druge.",
                  "Obuhvat: metode sa adresama u mapi, namespace Match3Engine; "
                  "ne i sve neimenovane/genericke funkcije u biblioteci.",
                  "Listing ima ogranicenje duzine iz disasemblera; broj fajlova nije potvrda kompletne semantike."]
    (ROOT / "docs/simulator_coverage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"local_modes": len(modes), "booster_configs": len(abilities['abilities']),
                      "families": {k: {"classes": len(v), "methods": sum(len(c['methods']) for c in v)}
                                   for k, v in families.items()}}, indent=2))


if __name__ == "__main__":
    build()
