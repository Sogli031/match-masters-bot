import copy
from pathlib import Path

import numpy as np
import pytest

import engine_refill
import move_strategy as ms
from engine_refill import SquareRefill, UnsupportedRefill, fill_simulator_board
from engine_spawn_predicates import is_part_of_combo
from strategy_lab.simulation import step

CAPTURE = Path(__file__).resolve().parents[1] / "Debug/match_captures/20261031_223909_674630"
COLORS = [4, 3, 2, 5, 7, 6]


def entries(mapping):
    return {"entries": [{"key": k, "value": v} for k, v in mapping.items()]}


def profile():
    return {
        "rules": {"id": "square-match", "pvpMode": 1, "disableMatchPrevention": False,
                  "refillLogicOverride": {"disableFirstRoundLogic": False, "preventMatchChance": 0,
                                          "preventComboChance": 0, "preventSpecialComboChance": 0,
                                          "preventSquareMatchChance": 0},
                  "_colorScoreOverride": entries({3: 2, 6: 3, 7: 4, 5: 5}), "_colorEnergyOverride": None,
                  "_extraData": entries({"allowSquareMatches": True}), "weightsRandomizer": None},
        "state": {"<Turns>k__BackingField": 1, "<TurnsTotal>k__BackingField": 1},
        "players": [{"player_type": 0, "model": {"index": 0, "slotType": 4}}],
        "config": {"spawnEngine": {"newColorPickLogic": True, "colorPickmaxPoolSize": 70,
                                   "colorPickMaxPoolUnit": 10, "liveEventPieceChancesBySpawnedSolo": None,
                                   "liveEventPieceChancesBySpawned": None,
                                   "liveEventPieceChancesBySpawnedRumbleParty": None,
                                   "liveEventPieceChancesBySpawnedShowdown": None}},
        "spawning": {"<ForceNextCombo>k__BackingField": False, "<ForceBlueCombo>k__BackingField": False,
                     "<SquareMatchesAvailable>k__BackingField": True, "gameColors": COLORS,
                     "colorWeights": entries(dict.fromkeys(range(2, 9), 1)),
                     "baseColorWeights": entries(dict.fromkeys(range(2, 9), 1)),
                     "specialTilesData": entries({}), "spawnedColors": entries({}), "initialSpawnParams": {}},
    }


def engine_board():
    # Rows shifted by two: no line of three and no 2x2 square anywhere.
    return [[COLORS[(x + 2 * y) % 6] for x in range(7)] for y in range(7)]


def with_holes(board, cells):
    board = copy.deepcopy(board)
    for x, y in cells:
        board[y][x] = 0
    return board


def model(seed=1234):
    return SquareRefill.from_profile(profile(), seed=seed)


def test_each_hole_consumes_four_rolls_two_fair_names_and_one_color_roll():
    m = model()
    _, trace = m.fill(with_holes(engine_board(), [(0, 0), (1, 0), (2, 0), (3, 1)]))
    # Holes are visited y-major, x-minor as CountFillingSlots builds the list.
    assert [(t["x"], t["y"]) for t in trace] == [(0, 0), (1, 0), (2, 0), (3, 1)]
    assert all(t["rng_after"] - t["rng_before"] == 4 + 2 + 1 for t in trace)
    assert m.rng.counter == trace[-1]["rng_after"]


def test_fireworks_refill_keeps_existing_rockets_and_counts_replenish_roll():
    p = profile()
    p["rules"].update(boardModelName=engine_refill.FIREWORKS_FESTIVAL_BOARD)
    m = SquareRefill.from_profile(p, seed=1234)
    board = [[1 + (x + 2 * y) % 6 for x in range(7)] for y in range(7)]
    specials = [[0] * 7 for _ in range(7)]
    board[1][0] = 0
    specials[0][:4] = [ms.SPECIAL_FIREWORK_RIGHT] * 4
    _, after, trace = fill_simulator_board(m, board, specials)
    assert after[0] == specials[0]
    assert m.rng.counter == trace[-1]["rng_after"] + 1
    specials[0][0] = 0
    with pytest.raises(UnsupportedRefill, match="rocket conversion"):
        fill_simulator_board(m, board, specials)


def test_multiplier_mushrooms_board_limits_mushroom_cells_and_their_shuffle_draws():
    tile = entries({"refillSpawn": 99, "maxSpawn": 99, "spawnChance": 100, "minGuaranteedPieces": 0})
    holes = [(x, y) for y in range(7) for x in (0, 3, 6)] + [(2, 6)]

    def run(board_model):
        p = profile()
        p["rules"]["boardModelName"] = board_model
        p["spawning"]["specialTilesData"] = entries({19: tile})
        m = SquareRefill.from_profile(p, seed=1234)
        _, trace = m.fill(with_holes(engine_board(), holes))
        return m.rng.counter, [t for t in trace if t.get("special_value") == 19]

    plain_draws, plain = run(1)
    assert any(t["x"] in (0, 6) or t["y"] == 6 for t in plain)
    for board_model in (29, 30):    # Multiplier Mushrooms, Mighty Mushrooms
        draws, mushrooms = run(board_model)
        assert mushrooms and all(0 < t["x"] < 6 and t["y"] < 6 and t["color"] in engine_refill.MUSHROOM_COLORS
                                 for t in mushrooms)
        assert draws < plain_draws


def hatch_profile():
    p = profile()
    weights = entries({"AllAboardSEBandit": 10, "CupidHeart": 10, "ColorCrystalPiece": 0, "MonkeyJoojooPiece": 10,
                       "FoxyRoxySEPiece": 10, "BroccoBoogiePiece": 10, "CleoCadabraPiece": 10})
    p["rules"].update(extraMoveRandomSpecial=True, additionalData=entries({"specialPiecesWeights": weights}))
    p["ball_slots"] = []
    return p


def test_random_special_is_one_draw_modulo_total_weight_in_table_order():
    m = SquareRefill.from_profile(hatch_profile(), seed=1234)
    roll = m.peek_draws(1)[0] % 60
    order = (18, 11, 19, 29, 16, 13)
    before = m.rng.counter
    assert m.random_special((3, 3), 1) == order[roll // 10]
    assert m.rng.counter == before + 1
    assert SquareRefill.from_profile(profile(), seed=1234).random_special((3, 3), 1) is None


def test_cached_randomizer_over_the_same_weights_is_not_another_configuration():
    p = hatch_profile()
    weights = p["rules"]["additionalData"]["entries"][0]["value"]
    p["rules"]["weightsRandomizer"] = {"_weights": weights}
    assert SquareRefill.from_profile(p, seed=1).random_specials
    p["rules"]["weightsRandomizer"] = {"_weights": entries({"CupidHeart": 5})}
    with pytest.raises(UnsupportedRefill, match="WeightsRandomizer"):
        SquareRefill.from_profile(p, seed=1)


def test_resting_cleo_without_its_slot_colour_ends_the_exact_line():
    m = SquareRefill.from_profile(hatch_profile(), seed=1)
    board = [[(x + 2 * y) % 6 + 1 for x in range(7)] for y in range(7)]
    special = [[0] * 7 for _ in range(7)]
    board[3][3], special[3][3] = 99, 13
    with pytest.raises(UnsupportedRefill, match="raw slot colour"):
        fill_simulator_board(m, board, special)
    m.balls = [(3, 3, 3)]
    fill_simulator_board(m, board, special)


@pytest.mark.skipif(not (CAPTURE.parents[1] / "research/20261104_032503_match-and-hatch").is_dir(),
                    reason="Match & Hatch recording not present")
@pytest.mark.parametrize("before_name, after_name", [("000", "001"), ("004", "005"), ("026", "027")])
def test_recorded_match_and_hatch_special_matches_the_game(before_name, after_name):
    from refill_monitor import check_transition
    from simulator_capture import capture_mode
    from strategy_lab import simulation
    import json
    folder = CAPTURE.parents[1] / "research/20261104_032503_match-and-hatch"
    before, after = (json.loads((folder / f"{n}.json").read_text(encoding="utf-8")) for n in (before_name, after_name))
    modes = simulation.PREFIX_MODES
    simulation.PREFIX_MODES = set(modes) | {capture_mode(before["profile"]).value}
    try:
        assert check_transition(before, after)["verdict"] == "ok"
    finally:
        simulation.PREFIX_MODES = modes


def test_each_destroyed_cascade_combo_costs_one_draw_before_the_refill():
    m = model()
    board = with_holes(engine_board(), [(0, 0)])
    _, (own,) = m.fill(board)
    _, (cascade,) = m.fill(board, chain_combos=2)
    assert own["rng_before"] == 0 and cascade["rng_before"] == own["rng_after"] + 2


def test_fill_is_deterministic_and_never_mutates_its_input():
    board = with_holes(engine_board(), [(x, 0) for x in range(7)])
    before = copy.deepcopy(board)
    a, b = model(), model()
    first, trace_a = a.fill(board)
    second, trace_b = b.fill(board)
    assert board == before
    assert [[s["color"] for s in row] for row in first] == [[s["color"] for s in row] for row in second]
    assert trace_a == trace_b


def test_last_round_prevention_avoids_combos_unless_the_priority_list_is_exhausted():
    m = model(seed=7)
    for _ in range(30):
        board = with_holes(engine_board(), [(x, 0) for x in range(7)] + [(x, 1) for x in range(0, 7, 2)])
        filled, trace = m.fill(board)
        for t in trace:
            if not t["exhausted"]:
                assert not is_part_of_combo(filled, t["x"], t["y"], square=True)


def test_retry_walks_priority_from_its_head_after_the_weighted_pick(monkeypatch):
    m = model(seed=99)
    board = engine_board()
    # Two of the same colour under a hole: most picks would complete a line.
    board[1][3] = board[2][3] = 5
    board = with_holes(board, [(3, 0)])
    _, (t,) = m.fill(board)
    assert t["attempts"][1:] == t["priority"][:len(t["attempts"]) - 1]
    assert t["color"] != 5 or t["exhausted"]


def test_scores_follow_the_color_override_after_filling():
    filled, trace = model().fill(with_holes(engine_board(), [(0, 0), (4, 0)]))
    scores = {3: 2, 6: 3, 7: 4, 5: 5}
    for t in trace:
        assert filled[t["y"]][t["x"]]["score"] == scores.get(t["color"], 1)


@pytest.mark.parametrize("patch, message", [
    (lambda p: p["spawning"].update({"<ForceNextCombo>k__BackingField": True}), "Forced-combo"),
    (lambda p: p["rules"]["refillLogicOverride"].update({"disableFirstRoundLogic": True}), "Adaptive thresholds"),
    (lambda p: p["state"].update({"<TurnsTotal>k__BackingField": 3}), "Adaptive thresholds"),
    (lambda p: p["config"]["spawnEngine"].update({"liveEventPieceChancesBySpawned": [1]}), "Live event"),
    (lambda p: p["players"].append(dict(p["players"][0])), "one local player"),
    (lambda p: p["spawning"].update({"specialTilesData": entries({1: 2})}), "Special tile"),
])
def test_unported_branches_raise_instead_of_guessing(patch, message):
    p = profile()
    patch(p)
    with pytest.raises(UnsupportedRefill, match=message):
        SquareRefill.from_profile(p, seed=1)


def test_simulator_bridge_maps_colors_and_leaves_numpy_inputs_alone():
    sim = np.array([[engine_refill.ENGINE_TO_SIM[c] for c in row] for row in engine_board()], dtype=np.int16)
    sim[0, :3] = ms.EMPTY
    special = np.zeros_like(sim)
    before = sim.copy()
    out, specials, trace = fill_simulator_board(model(), sim, special)
    assert (sim == before).all()
    assert len(trace) == 3 and not (out == ms.EMPTY).any()
    assert [int(out[0][x]) for x in range(3)] == [engine_refill.ENGINE_TO_SIM[t["color"]] for t in trace]
    with pytest.raises(UnsupportedRefill):
        fill_simulator_board(model(), [[99, 0]], [[0, 0]])
    # A Square Match crosshair stays on the board as engine SlotValue 8.
    special[3, 3] = ms.SPECIAL_CROSSHAIR
    _, kept, _ = fill_simulator_board(model(), sim, special)
    assert int(kept[3][3]) == ms.SPECIAL_CROSSHAIR


def test_local_player_colour_is_permuted_like_board_source():
    p = profile()
    p["players"] = [{"player_type": 0, "model": {"index": 0, "slotType": 2}},
                    {"player_type": 1, "model": {"index": 1, "slotType": 4}}]
    to_engine, to_sim = engine_refill.color_maps(p)
    # Our engine Red reads as the simulator's BLUE, the opponent's Blue as RED.
    assert to_sim[2] == ms.BLUE and to_sim[4] == ms.RED
    assert sorted(to_sim.values()) == sorted(engine_refill.ENGINE_TO_SIM.values())
    assert all(to_engine[to_sim[c]] == c for c in to_sim)


def test_explicit_thresholds_open_the_non_final_round():
    p = profile()
    p["state"]["<TurnsTotal>k__BackingField"] = 3
    hypothesis = {"match": -1, "combo": -1, "special_combo": -1, "square": -1}
    m = SquareRefill.from_profile(p, seed=1, thresholds=hypothesis)
    assert m.thresholds == hypothesis and m.clone().thresholds == hypothesis


def lab_move(m):
    board = [[engine_refill.ENGINE_TO_SIM[c] for c in row] for row in engine_board()]
    # Swapping (3,2) down onto (4,2) lines up three Yellows in row 4.
    board[3][2], board[4][1], board[4][3] = ms.YELLOW, ms.YELLOW, ms.YELLOW
    return {"mode": ms.GameMode.NONE.value, "board": board, "special_board": [[0] * 7 for _ in range(7)],
            "allow_square_matches": True, "single_player_board": True, "engine_refill": m}


def test_lab_step_fills_every_cascade_and_advances_only_the_returned_model(monkeypatch):
    # This drop happens to leave no move; the shuffle has its own test and would
    # add its draws to the count asserted here.
    monkeypatch.setattr("engine_shuffle.has_possible_move", lambda *args: True)
    m = model()
    move = lab_move(m)
    action = {"start": [3, 2], "target": [4, 2], "direction": "down"}
    result = step(move, action)
    assert result["supported"], result.get("reason")
    assert result["metric"] == "cleared_tiles"
    assert not any(int(v) == ms.EMPTY for row in result["state"]["board"] for v in row)
    assert m.rng.counter == 0
    refills = result["refills"]
    cascade_combos = sum(1 for e in result["events"] if e.get("type") == "match" and e["cascade"] > 1)
    assert result["state"]["engine_refill"].rng.counter == 7 * sum(map(len, refills)) + cascade_combos
    without = step({k: v for k, v in move.items() if k != "engine_refill"}, action)
    assert without["terminal_reason"].startswith("unknown_refill")


def test_hook_is_off_outside_the_context():
    assert ms._ENGINE_REFILL is None
    with ms.engine_refill_active(lambda b, s: (b, s)):
        assert ms._ENGINE_REFILL is not None
    assert ms._ENGINE_REFILL is None


@pytest.mark.skipif(not CAPTURE.is_dir(), reason="Square Match capture not present")
def test_verify_tool_finds_the_move_and_reports_a_changed_cell(tmp_path, monkeypatch):
    from simulator_capture import lab_move as capture_move, load_capture
    from strategy_lab.simulation import legal_actions
    from tools import capture_match, verify_refill

    monkeypatch.setattr(capture_match, "ROOT", tmp_path)
    before = load_capture(CAPTURE)
    move = capture_move(before)
    action = legal_actions(move)[1][0]
    result = step(move, action)

    def save_after(name, board):
        profile = copy.deepcopy(before["profile"])
        for slot in profile["board"]["slots"]:
            slot["color"] = engine_refill.SIM_TO_ENGINE[int(board[slot["y"]][slot["x"]])]
        profile["rng"].update(result["state"]["engine_refill"].rng.to_capture())
        profile["spawning"]["spawnedColors"] = entries(result["state"]["engine_refill"].spawned_colors)
        next(p for p in profile["players"] if p["player_type"] == 0)["model"]["score"] = result["state"]["score"]
        profile["state"]["moves"] = result["state"]["turn_state"]["remaining_moves"]
        capture_match.save_package(profile, {"version": "test"}, tmp_path / name)
        return tmp_path / name

    board = [[int(v) for v in row] for row in result["state"]["board"]]
    exact = save_after("exact", board)
    found = [(r["action"]["start"], r["action"]["target"])
             for r in verify_refill.compare(CAPTURE, exact) if r.get("match")]
    assert (action["start"], action["target"]) in found
    board[6][0] = next(c for c in (1, 2, 3) if c != board[6][0])
    (report,) = verify_refill.compare(CAPTURE, save_after("changed", board), action)
    assert not report["match"] and any(d.startswith("board: 1 polja") for d in report["differences"])


@pytest.mark.skipif(not CAPTURE.is_dir(), reason="Square Match capture not present")
def test_captured_square_match_profile_drives_every_legal_action():
    from simulator_capture import lab_move as capture_move, load_capture
    from strategy_lab.simulation import legal_actions

    move = capture_move(load_capture(CAPTURE))
    assert move["engine_refill"].rng.counter == 387
    _, actions = legal_actions(move)
    results = [step(move, a) for a in actions]
    assert actions and all(r["supported"] for r in results)
    assert move["engine_refill"].rng.counter == 387
