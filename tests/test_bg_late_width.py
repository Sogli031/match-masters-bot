"""Background replan: width 60 only with 6 moves or fewer left (player, 2026-11-18)."""
import square_solo_live as live


def test_late_moves_allow_width_60():
    assert live._bg_max_width({"turn_state": {"remaining_moves": 6}}) == 60
    assert live._bg_max_width({"turn_state": {"remaining_moves": 1}}) == 60


def test_earlier_and_unknown_stay_at_25():
    assert live._bg_max_width({"turn_state": {"remaining_moves": 7}}) == 25
    assert live._bg_max_width({}) == 25
