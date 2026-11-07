"""Index recorded rules and effective ability parameters without attaching to game."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def build():
    variants, abilities, errors = {}, {}, []
    count = 0
    paths = sorted((ROOT / "Debug/memory_board").glob("board_snapshots*.jsonl"))
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                try:
                    item = json.loads(line)
                except (ValueError, UnicodeError) as error:
                    errors.append({"file": path.name, "line": line_no, "error": str(error)})
                    continue
                snapshot = item.get("snapshot", item)
                state = snapshot.get("state") or {}
                rules = state.get("rules") or {}
                if not rules:
                    continue
                count += 1
                evidence = {"file": str(path.relative_to(ROOT)), "line": line_no,
                            "captured_at": snapshot.get("captured_at")}
                key = fingerprint(rules)
                if key not in variants:
                    variants[key] = {"rules": rules, "first_evidence": evidence, "snapshots": 0}
                variants[key]["snapshots"] += 1
                variants[key]["last_evidence"] = evidence
                for player in state.get("players", []):
                    ability = {"rules_id": rules.get("id"), "pvp_mode": rules.get("pvp_mode"),
                               "ability": player.get("special_ability_type"),
                               "energy_to_ability": player.get("energy_to_ability"),
                               "params": player.get("special_ability_params")}
                    if ability["ability"] is None:
                        continue
                    akey = fingerprint(ability)
                    abilities.setdefault(akey, {"config": ability, "evidence": evidence})
    result = {"scope": "Recorded evidence only; not current server rotation or proof of complete coverage",
              "files": [str(p.relative_to(ROOT)) for p in paths], "snapshots": count,
              "rules_variants": variants, "ability_variants": abilities, "parse_errors": errors}
    (ROOT / "data/recorded_rulesets.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ids = sorted({str(v["rules"].get("id")) for v in variants.values()})
    print(json.dumps({"snapshots": count, "rules_ids": ids, "rule_variants": len(variants),
                      "ability_variants": len(abilities), "parse_errors": len(errors)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
