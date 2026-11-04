"""Regresije offline analizatora odluka (turn_analyzer).

Table su sinteticke 7x7, bez slucajnih spojeva, da bi svaki test proveravao
jedno pravilo: obican swipe, garantovani extra, nesigurna kaskada posle
dopune, legalna aktivacija specijala, promena vlasnika reda i ponovljivost.
"""

import random
from pathlib import Path

import move_strategy as ms
import turn_analyzer as ta


def test_doctor_color_paths_are_exact_and_require_all_three_colors():
    assert len(ta.DOCTOR_COLOR_PATHS) == len(set(ta.DOCTOR_COLOR_PATHS)) == 14
    assert all(len(set(p)) == 3 and ms.BLUE not in p and ms.RED not in p
               for p in ta.DOCTOR_COLOR_PATHS)
    assert ta.doctor_color_paths([[ms.ORANGE, ms.GREEN]]) == []
    paths = ta.doctor_color_paths([[ms.ORANGE, ms.GREEN, ms.YELLOW]])
    assert len(paths) == 3
    assert set(paths) <= set(ta.DOCTOR_COLOR_PATHS)


def test_doctor_color_chains_both_sources_and_preserves_specials_and_input():
    board = [[ms.ORANGE, ms.GREEN, ms.YELLOW, ms.BLUE, ms.RED, ms.GREEN]]
    special = [[ms.SPECIAL_BOMB, 0, 0, 0, 0, ms.SPECIAL_MODE_TARGET]]
    out = ta.doctor_color_convert(board, special, (ms.ORANGE, ms.GREEN, ms.YELLOW))
    assert out == [[ms.YELLOW, ms.YELLOW, ms.YELLOW, ms.BLUE, ms.RED, ms.GREEN]]
    assert board[0][0] == ms.ORANGE
    assert special[0][0] == ms.SPECIAL_BOMB


def test_doctor_color_settles_converted_board_without_empirical_points(monkeypatch):
    decision = _decision(BASE, charge=7)
    decision.snapshot = {"ability": 27}
    analysis = ta.DecisionAnalysis(decision)
    action = next(a for a in analysis.sim.legal_actions(analysis.root)[0] if a["kind"] == "booster")
    seen = []

    def settle(state, rules, rng, events, info):
        seen.append([row[:] for row in state.board])
        info["blue"] = 2
        return 17.0

    monkeypatch.setattr(ta, "_settle", settle)
    before = analysis.root.copy()
    out = analysis.sim.step(analysis.root, action, random.Random(8))
    path = out.events[0]["path"]
    assert seen == [ta.doctor_color_convert(before.board, before.special, path)]
    assert out.points == 17.0  # no empirical bonus on top of cascades
    assert out.state.charge == 2
    assert out.state.moves_left == before.moves_left
    assert analysis.root.board == before.board and analysis.root.charge == 7
    assert "booster_empirical" not in out.info["unverified"]
    assert "doctor_color_selection" in out.info["unverified"]


def test_doctor_color_real_cascades_repeat_with_seed():
    board = [[ms.BLUE if color == ms.PURPLE else color for color in row] for row in BASE]
    board[0][:3] = [ms.ORANGE, ms.GREEN, ms.YELLOW]
    decision = _decision(board, charge=7)
    decision.snapshot = {"ability": 27}
    analysis = ta.DecisionAnalysis(decision)
    action = next(a for a in analysis.sim.legal_actions(analysis.root)[0] if a["kind"] == "booster")
    a = analysis.sim.step(analysis.root, action, random.Random(9))
    b = analysis.sim.step(analysis.root, action, random.Random(9))
    assert a.points > 0
    assert (a.points, a.state.board, a.state.special, a.events) == (b.points, b.state.board, b.state.special, b.events)


def test_doctor_color_no_available_path_is_noop_not_empirical_bonus():
    decision = _decision([[ms.BLUE] * 7 for _ in range(7)], charge=7)
    decision.snapshot = {"ability": 27}
    analysis = ta.DecisionAnalysis(decision)
    out = analysis.sim.step(analysis.root, {"kind": "booster"}, random.Random(0))
    assert out.points == 0 and out.state.charge == 0
    assert out.state.board == analysis.root.board


def test_square_match_does_not_draw_other_modes_booster_figures(monkeypatch):
    decision = _decision(BASE)
    decision.snapshot = {"id": "square-match", "ability": 27}
    monkeypatch.setattr(ta, "refill_stats", lambda: {"modes": {
        "None|versus": {"tiles": 100000, "counts": {"2:19": 100000}, "runs": 10}}})
    rules = ta.build_rules(decision)
    assert "refill_uniform" in rules.unverified
    assert all(special == 0 for (color, special), weight in rules.refill_table)

# Bez ijednog spoja; kolone/redovi se ne ponavljaju tri puta zaredom.
BASE = [
    [1, 2, 3, 4, 5, 6, 1],
    [3, 4, 5, 6, 1, 2, 3],
    [5, 6, 1, 2, 3, 4, 5],
    [1, 2, 3, 4, 5, 6, 1],
    [3, 4, 5, 6, 1, 2, 3],
    [5, 6, 1, 2, 3, 4, 5],
    [1, 2, 3, 4, 5, 6, 1],
]


def _empty():
    return [[0] * 7 for _ in range(7)]


def _decision(board, special=None, *, remaining=2, charge=0, maximum=7, perks=("none", "none"),
              proposed=None, mode="None", context=ta.CTX_VERSUS, multiplier=10.0):
    move = {
        "board": [row[:] for row in board],
        "special_board": special or _empty(),
        "mode": mode,
        "allow_square_matches": False,
        "strategy_context": {"mode": "versus_2"},
        "selected_perks": list(perks),
    }
    decision = ta.Decision(
        run="2026-01-01_00-00-00_000", path=Path("."), ts=None, move=move, delta={}, candidates=[],
        context=context, context_source="test", snapshot=None, mode=mode, round=1, total_rounds=2,
        remaining_moves=remaining, turn_owner="us", time_left=20.0, seconds_per_move=1.0,
        our_score=100, opp_score=50, booster_charge=charge, booster_max=maximum, perks=tuple(perks),
        proposed=proposed or {"type": "none"}, sent=True, outcome={"status": "test"},
        multiplier=multiplier, multiplier_source="test",
    )
    decision.perk_status = [
        {"slot": i + 1, "perk": p if p != "none" else None, "status": "dostupan" if p != "none" else "prazan"}
        for i, p in enumerate(perks)
    ]
    return decision


def _plain_three_board():
    board = [row[:] for row in BASE]
    # Red 6: 1 2 3 4 5 6 1 -> stavi 4 na (5,0) da swipe (5,0)<->(6,0)... jednostavnije:
    # napravi 3 u redu 0 swipe-om (1,2)->(0,2): kolona 2, red 0 dobija boju 5.
    board[0][0] = 5
    board[0][1] = 5
    board[1][2] = 5
    board[0][2] = 3
    return board


def test_plain_swipe_is_legal_and_scored_without_gate():
    decision = _decision(_plain_three_board())
    analysis = ta.DecisionAnalysis(decision, seed=3)
    actions, _ = analysis.sim.legal_actions(analysis.root)
    keys = {a["key"] for a in actions}
    assert any(a["kind"] == "swap" for a in actions)
    swap = next(a for a in actions if a["kind"] == "swap" and {a["start"], a["target"]} == {(0, 2), (1, 2)})
    assert swap["det_units"] >= 3
    assert not swap["guaranteed_extra"]
    out = analysis.sim.step(analysis.root, swap, random.Random(1))
    # Obican potez trosi potez i ne zadrzava red.
    assert out.state.moves_left == analysis.root.moves_left - 1
    assert out.points >= 3 * analysis.root.multiplier
    assert "swap (0, 2)->(1, 2)" in keys or "swap (1, 2)->(0, 2)" in keys


def test_guaranteed_extra_keeps_the_turn_and_adds_no_points_by_itself():
    board = [row[:] for row in BASE]
    # Cetiri boje 6 u redu 3 posle swipe-a (2,3)->(3,3).
    board[3][0], board[3][1], board[3][2], board[2][3], board[3][3] = 6, 6, 6, 6, 2
    decision = _decision(board, remaining=1)
    analysis = ta.DecisionAnalysis(decision, seed=1)
    actions, _ = analysis.sim.legal_actions(analysis.root)
    four = next(a for a in actions if a["kind"] == "swap" and a["guaranteed_extra"])
    out = analysis.sim.step(analysis.root, four, random.Random(0))
    assert out.info["guaranteed_extra"]
    assert out.state.moves_left == 1 and out.state.over is None
    swipe_event = next(e for e in out.events if e.get("wave") == "swipe")
    # Poeni swipe-a su samo ocisceni pomnozeni mnoziocem -- extra nema svoju cenu.
    assert swipe_event["points"] == swipe_event["units"] * analysis.root.multiplier


def test_uncertain_cascade_marks_first_unknown_and_samples_refill():
    decision = _decision(_plain_three_board())
    analysis = ta.DecisionAnalysis(decision, seed=0)
    actions, _ = analysis.sim.legal_actions(analysis.root)
    swap = next(a for a in actions if a["kind"] == "swap")
    out = analysis.sim.step(analysis.root, swap, random.Random(5))
    assert out.info["first_unknown"] is not None
    assert out.info["first_unknown"]["where"] == "dopuna"
    assert any(e.get("wave") == "dopuna" for e in out.events)
    assert not any(v == ms.EMPTY for row in out.state.board for v in row)


def test_special_activation_is_a_legal_action():
    board = [row[:] for row in BASE]
    special = _empty()
    # Dva susedna specijala: swipe je kombinacija i legalan je bez spoja boja.
    # (Jedan specijal sa obicnom plocicom bez spoja nije legalan potez.)
    special[3][3] = ms.SPECIAL_HORIZONTAL
    special[3][4] = ms.SPECIAL_VERTICAL
    decision = _decision(board, special)
    analysis = ta.DecisionAnalysis(decision, seed=0)
    actions, _ = analysis.sim.legal_actions(analysis.root)
    activations = [a for a in actions if a["kind"] == "swap" and a["special_activation"]]
    assert any({a["start"], a["target"]} == {(3, 3), (3, 4)} for a in activations)
    combo = next(a for a in activations if {a["start"], a["target"]} == {(3, 3), (3, 4)})
    assert combo["result"].activated_specials >= 2


def test_last_move_hands_the_turn_over_and_scores_opponent_reply_separately():
    decision = _decision(_plain_three_board(), remaining=1, proposed={"type": "swap", "start": (1, 2), "target": (0, 2)})
    result = ta.analyze_decision(decision, seed=2, samples=4)
    played = next(a for a in result["actions"] if a["played"])
    assert played["p_another_decision"] == 0.0
    assert set(played["ended_by"]) == {"predaja (potezi)"}
    assert played["opponent_reply_units"] is not None
    assert played["total"]["mean"] == played["immediate"]["mean"]


def test_same_seed_same_trace_and_order_independent():
    decision = _decision(_plain_three_board(), remaining=2)
    first = ta.analyze_decision(decision, seed=11, samples=6)
    second = ta.analyze_decision(decision, seed=11, samples=6)
    assert [(a["key"], a["total"]["mean"]) for a in first["actions"]] == \
           [(a["key"], a["total"]["mean"]) for a in second["actions"]]
    # Redosled simuliranja kandidata ne menja rezultat jedne grane.
    analysis = ta.DecisionAnalysis(decision, seed=11)
    plans, _ = analysis.root_plans()
    forward = [analysis.rollout(p, 0).total for p in plans]
    analysis2 = ta.DecisionAnalysis(decision, seed=11)
    backward = [analysis2.rollout(p, 0).total for p in reversed(plans)][::-1]
    assert forward == backward
    trace_a = ta.DecisionAnalysis(decision, seed=11).trace(plans[0]["key"], 0)
    trace_b = ta.DecisionAnalysis(decision, seed=11).trace(plans[0]["key"], 0)
    assert trace_a == trace_b


def test_booster_is_legal_only_when_full_and_marked_empirical():
    decision = _decision(_plain_three_board(), charge=7, maximum=7)
    analysis = ta.DecisionAnalysis(decision, seed=0)
    actions, _ = analysis.sim.legal_actions(analysis.root)
    booster = next(a for a in actions if a["kind"] == "booster")
    assert "booster_empirical" in booster["unverified"]
    not_full = ta.DecisionAnalysis(_decision(_plain_three_board(), charge=6, maximum=7), seed=0)
    assert not any(a["kind"] == "booster" for a in not_full.sim.legal_actions(not_full.root)[0])


def test_works_without_perks_and_lists_both_perk_orders():
    no_perks = ta.DecisionAnalysis(_decision(_plain_three_board()), seed=0)
    plans, unsupported = no_perks.root_plans()
    assert plans and not unsupported and all(p["kind"] == "swap" for p in plans)
    both = ta.DecisionAnalysis(_decision(_plain_three_board(), perks=("energy_boost", "remove_cross")), seed=0)
    plans, _ = both.root_plans()
    sequences = [p["key"] for p in plans if p["kind"] == "sequence"]
    assert any(k.startswith("perk energy_boost ->") for k in sequences)
    assert any(k.endswith("-> perk energy_boost") for k in sequences)


def test_unsupported_perk_is_visible_not_zero():
    analysis = ta.DecisionAnalysis(_decision(_plain_three_board(), perks=("shuffle", "none")), seed=0)
    plans, unsupported = analysis.root_plans()
    assert unsupported and unsupported[0]["perk"] == "shuffle"
    assert not any(p.get("first", {}).get("perk") == "shuffle" for p in plans)


def test_floor_lava_columns_from_move_json_are_one_based():
    decision = _decision(_plain_three_board(), mode="The Floor Is Lava")
    decision.move["floor_lava_state"] = {"columns": [1, 4], "source": "memory"}
    assert ta.build_rules(decision).lava_columns == (0, 3)


def test_context_classification():
    assert ta.classify_context({"strategy_context": {"mode": "versus_2"}})[0] == ta.CTX_VERSUS
    assert ta.classify_context({"strategy_context": {"mode": "solo_6", "solo_challenge": True}})[0] == ta.CTX_SOLO_CHALLENGE
    assert ta.classify_context({"strategy_context": {"mode": "solo_6"}}, {"rumble": 1})[0] == ta.CTX_RUMBLE
    assert ta.classify_context({"strategy_context": {"mode": "solo_6"}}, {"rumble": 2})[0] == ta.CTX_SHOWDOWN
    heuristic = ta.classify_context({"strategy_context": {"mode": "solo_6"},
                                     "screen_state_read": {"resolved": {"total_rounds": 2}}})
    assert heuristic == (ta.CTX_PARTY, "heuristika (2 runde)")


def _extra_board():
    board = [row[:] for row in BASE]
    board[3][0], board[3][1], board[3][2], board[2][3], board[3][3] = 6, 6, 6, 6, 2
    return board


def test_policy_takes_guaranteed_extra_before_perk_and_offers_extra_then_perk():
    decision = _decision(_extra_board(), remaining=1, perks=("none", "remove_cross"))
    decision.round, decision.total_rounds = 2, 2  # poslednji red partije
    analysis = ta.DecisionAnalysis(decision, seed=0)
    action, _ = analysis.sim.choose_action(analysis.root)
    assert action["kind"] == "swap" and action["guaranteed_extra"]
    plans, _ = analysis.root_plans()
    extra_then_perk = [p for p in plans if p["key"].endswith("-> perk remove_cross@najbolja")]
    assert extra_then_perk
    branch = analysis.rollout(extra_then_perk[0], 0)
    assert branch.perks_used and branch.perks_used[0].startswith("Remove Cross")
    assert branch.perks_left == 0


def test_policy_spends_perk_before_final_handover_but_keeps_it_earlier():
    final = _decision(_plain_three_board(), remaining=1, perks=("none", "remove_cross"))
    final.round, final.total_rounds = 2, 2
    analysis = ta.DecisionAnalysis(final, seed=0)
    action, _ = analysis.sim.choose_action(analysis.root)
    assert action["kind"] == "perk"
    earlier = _decision(_plain_three_board(), remaining=1, perks=("none", "remove_cross"))
    earlier.round, earlier.total_rounds = 1, 2
    analysis = ta.DecisionAnalysis(earlier, seed=0)
    action, _ = analysis.sim.choose_action(analysis.root)
    assert action["kind"] == "swap"
    swap_plan = next(p for p in analysis.root_plans()[0] if p["kind"] == "swap")
    assert analysis.rollout(swap_plan, 0).perks_left == 1


def test_booster_dependent_choice_is_not_a_reliable_winner():
    decision = _decision(_plain_three_board(), charge=7, maximum=7, remaining=1,
                         proposed={"type": "swap", "start": (1, 2), "target": (0, 2)})
    result = ta.analyze_decision(decision, seed=0, samples=4)
    verdict = result["verdict"]
    assert result["actions"][0]["booster_points_mean"] > 0
    assert verdict["booster_dependent"] is True
    assert verdict["reliable_winner"] is False
    assert any("bustera" in text for text in verdict["depends_on_unverified"])


def _rich_board(seed=7):
    """Nasumicna tabla bez spojeva, ali sa dosta legalnih poteza."""
    rng = random.Random(seed)
    while True:
        board = [[rng.randint(1, 6) for _ in range(7)] for _ in range(7)]
        if not ms.find_matches(board) and len(ta.legal_swaps(ta.DecisionAnalysis(_decision(board)).root,
                                                             ta.build_rules(_decision(board)), {})) >= 16:
            return board


def test_branch_without_legal_swipe_counts_as_cut_not_as_handover():
    decision = _decision(_plain_three_board(), remaining=6,
                         proposed={"type": "swap", "start": (1, 2), "target": (0, 2)})
    result = ta.analyze_decision(decision, seed=0, samples=2)
    played = next(a for a in result["actions"] if a["played"])
    assert set(played["ended_by"]) <= ta.CUT_ENDINGS | {"predaja (potezi)"}
    if ta.ENDED_NO_MOVES in played["ended_by"]:
        assert played["share_limit"] > 0
        assert result["verdict"]["limit_cut_after_extension"]


def test_limit_cut_branches_are_extended_or_mark_winner_undecided():
    decision = _decision(_rich_board(), remaining=6,
                         proposed=None)
    first = ta.DecisionAnalysis(decision).root_plans()[0][0]["first"]
    decision.proposed = {"type": "swap", "start": first["start"], "target": first["target"]}
    short = ta.analyze_decision(decision, seed=0, samples=2, max_steps=1)
    assert short["verdict"]["limit_cut_after_extension"]
    assert short["verdict"]["reliable_winner"] is False
    enough = ta.analyze_decision(decision, seed=0, samples=2, max_steps=4)
    played = next(a for a in enough["actions"] if a["played"])
    assert played["extended_branches"] == 2
    assert all(k not in ta.CUT_ENDINGS for k in played["ended_by"])


def test_observed_extra_and_next_decision_are_separate():
    this = _decision(_plain_three_board(), remaining=3, proposed={"type": "swap", "start": (1, 2), "target": (0, 2)})
    nxt = _decision(_plain_three_board(), remaining=2)
    nxt.run = "2026-01-01_00-00-05_000"
    out = {"after_run": nxt.run, "after_turn_owner": "us", "kept_turn": False}
    ta._observed_turn_flags(this, nxt, out)
    # Potezi 3 -> 2 (bez extra), ali sledeca odluka je i dalje nasa.
    assert out["observed_extra"] is False
    assert out["next_is_ours"] is True
    handover = {"after_turn_owner": "opponent"}
    last = _decision(_plain_three_board(), remaining=1, proposed={"type": "swap", "start": (1, 2), "target": (0, 2)})
    ta._observed_turn_flags(last, None, handover)
    assert handover["next_is_ours"] is False and handover["observed_extra"] is False
