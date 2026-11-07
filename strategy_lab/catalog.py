"""Read installation catalogs without importing the live runtime or GUI."""
import ast
import json
from pathlib import Path
import move_strategy as ms
from .policy import identity

ROOT = Path(__file__).resolve().parents[1]


def string_constants(path, prefix):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    result = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith(prefix):
                    result[target.id] = node.value.value
    return result


MODE_GAPS = {
    "ZANY_ZAPPERS": "Nedostaje efekat sedmog zappera i njegovo stanje.",
    "BURIED_TREASURE": "Nagrada je očekivanje 50%; nema vernog bacanja i početnog rasporeda.",
    "COLOR_CLIMB": "Potrebni su par boja igrača i rast množilaca tokom cele partije.",
    "COLUMN_MANIA": "Potrebni su množilac svake kolone i colsToIncrease.",
    "MULTIPLIER_MUSHROOMS": "Nedostaju verna inicijalizacija/spawn pečurki i protivnički odgovor.",
    "HOT_COLOR": "Potrebna je sekvenca promena vruće boje.",
    "FLOOR_IS_LAVA": "Potrebni su preostali stubci i njihovo stanje između poteza.",
    "DUSTVILLE_DUEL": "Dopuna, hici i vraćanje wanted figura su preneti; nedostaje tajming specijala u kaskadi i Brocco buster.",
    "CHEST": "Nedostaje verna distribucija novih kovčega i početne opreme.",
}


def catalog():
    from .simulation import PREFIX_MODES
    try:
        abilities=read_json(ROOT/"data"/"ability_config.json").get("abilities") or []
    except (OSError,ValueError):
        abilities=[]
    return {
        "source": "move_strategy.GameMode + data/ability_config.json + runtime.BOOSTER_ACTION_* + move_strategy.PERK_*",
        "modes": [{"key": mode.name, "label": mode.value,
                   "status": "delimično" if mode.value in PREFIX_MODES else "nedostaju pravila za Lab simulaciju",
                   "scope": "deterministički prefiks poteza" if mode.value in PREFIX_MODES else "native bot ima procenu; Lab je izostavlja iz rangiranja",
                   "gap": MODE_GAPS.get(mode.name, "Nema verifikovanog početnog stanja, dopune, cele ekonomije opreme i završetka partije.")}
                  for mode in ms.GameMode],
        "booster_actions": [{"key": v, "label": k.removeprefix("BOOSTER_ACTION_"), "status": "nedostaju pravila",
                      "gap": "Akcija GUI-ja nije identitet opremljenog boostera; nema verne početne aktivacije/efekta za rangiranje opreme."}
                     for k, v in string_constants(ROOT / "runtime.py", "BOOSTER_ACTION_").items()],
        "boosters": [{"key":a["type"],"label":a.get("title") or a.get("name") or str(a["type"]),
                      "cost":a.get("cost"),"status":"delimično: izbor poteza bez aktivacije",
                      "gap":"Početni efekat i cela aktivacija nisu sertifikovani u Lab-u; ne rangira se alternativni setup.",
                      "native_description":a.get("technical_desc")}
                     for a in abilities if "type" in a],
        "perks": [{"key": v, "label": k.removeprefix("PERK_"),
                   "status": "prazan slot podržan" if v == "none" else "delimično",
                   "gap": "Prazan slot ne troši resurs." if v == "none" else "Postoji native procena; Strategy Lab još nema veran prelaz celog efekta i početne slotove."}
                  for k, v in string_constants(ROOT / "move_strategy.py", "PERK_").items()],
        "equipment_ranking": {"supported": False, "reason": "Nema potvrđenog inicijalizatora cele partije za alternativnu opremu; nijedan setup se ne rangira kao slab."},
    }


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def records(runs, day=None):
    for path in sorted(Path(runs).glob((day or "*") + "*/move.json")):
        try:
            move = read_json(path)
            if not move.get("board") or not move.get("best_move"):
                continue
            yield path, move
        except (OSError, ValueError, TypeError):
            continue


def discover(runs, day=None):
    """Only observed format/rules/goal/setup tuples are offered together."""
    groups = {}
    from .policy import canonical, digest
    for path, move in records(runs, day):
        ident = identity(move)
        key = digest(ident)
        entry = groups.setdefault(key, {"key": key, "identity": ident, "records": 0, "sample": path.parent.name})
        entry["records"] += 1
    return sorted(groups.values(), key=lambda g: canonical(g["identity"]))
