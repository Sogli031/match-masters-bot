"""Per-colour booster charge (Color Crystals 2026-11-12: a 70-point meter,
green 1, orange 2, purple 3, yellow 4 per tile)."""
import board_source
import move_strategy as ms

OVERRIDE = {"2": 0, "3": 1, "4": 0, "5": 4, "6": 2, "7": 3}
SNAPSHOT = {"state": {"rules": {"colors_count": 6, "color_energy_override": OVERRIDE}}}


def test_weights_are_read_off_the_override():
    assert board_source.charging_weights(SNAPSHOT) == {
        ms.GREEN: 1, ms.ORANGE: 2, ms.PURPLE: 3, ms.YELLOW: 4}
    assert board_source.charging_weights({"state": {"rules": {}}}) is None


def test_meter_and_weights_go_on_the_seven_point_scale():
    import memory_gui

    scaled = memory_gui.MemoryWindow._charge_scale({"energy": 24, "energy_to_ability": 70}, SNAPSHOT)
    assert scaled["booster_maximum"] == ms.BOOSTER_MAX_CHARGE
    assert abs(scaled["booster_charge"] - 2.4) < 1e-9
    assert abs(scaled["engine_charge_weights"][ms.YELLOW] - 0.4) < 1e-9
    assert abs(scaled["engine_charge_weights"][ms.GREEN] - 0.1) < 1e-9
    plain = memory_gui.MemoryWindow._charge_scale({"energy": 3, "energy_to_ability": 7}, {"state": {"rules": {}}})
    assert plain == {"booster_charge": 3, "booster_maximum": 7}


def _three(color):
    # A swap that lines up three of ``color`` in the top row, nothing else.
    board = [[color, color, 5, color, 1, 6, 2],
             [3, 4, 1, 2, 5, 3, 4],
             [1, 2, 3, 4, 6, 1, 2],
             [4, 5, 6, 1, 2, 3, 5],
             [2, 3, 4, 5, 1, 2, 6],
             [5, 6, 1, 3, 4, 5, 1],
             [3, 1, 2, 6, 5, 4, 3]]
    special = [[0] * 7 for _ in board]
    swapped, specials = ms.swap_cells(board, special, (0, 2), (0, 3))
    return ms.MoveCandidate((0, 2), (0, 3), ms.Direction.RIGHT, swapped, specials)


def test_a_yellow_three_charges_four_times_a_green_three():
    weights = {ms.GREEN: 0.1, ms.ORANGE: 0.2, ms.PURPLE: 0.3, ms.YELLOW: 0.4}
    colors = (ms.GREEN, ms.YELLOW, ms.PURPLE, ms.ORANGE)
    with ms.charge_colors_active((), colors, weights):
        yellow = ms.simulate_candidate(_three(ms.YELLOW)).blue_cells
        green = ms.simulate_candidate(_three(ms.GREEN)).blue_cells
    assert abs(yellow - 1.2) < 1e-9 and abs(green - 0.3) < 1e-9
    with ms.charge_colors_active((), colors):
        assert ms.simulate_candidate(_three(ms.YELLOW)).blue_cells == 3
