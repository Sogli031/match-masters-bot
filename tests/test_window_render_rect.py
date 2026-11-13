import window_geometry
from window_geometry import WindowRect


class _Window:
    _hWnd = 1234
    left, top, width, height = 834, 30, 539, 931


def test_render_child_wins_over_client_with_toolbars(monkeypatch):
    render = WindowRect(835, 63, 505, 897)
    monkeypatch.setattr(window_geometry, "render_rect_for_hwnd", lambda hwnd: render)
    assert window_geometry.client_rect_for_window(_Window()) == render


def test_portrait_calibration_scales_to_the_render_area():
    import board_profiles

    cfg = board_profiles.load_board_config(
        "regular", base_dir=".", window_rect=WindowRect(835, 63, 505, 897))
    assert cfg["squareSize"] == 70
    sq = cfg["squareSize"]
    # Top-right tile centre, measured on the screenshot at ~(462, 385).
    x = cfg["left"] + sq // 2 + 6 * sq - 835
    y = cfg["up"] + sq // 2 - 63
    assert abs(x - 462) <= 4 and abs(y - 385) <= 6


class _Named:
    def __init__(self, title, width, height, minimized=False):
        self.title, self.width, self.height, self.isMinimized = title, width, height, minimized


def test_player_window_is_chosen_over_a_small_or_minimized_bluestacks_window():
    """2026-11-13 15:53 / 15:55: a ~2 px board right after a booster."""
    small = _Named("BlueStacks", 160, 28)
    minimized = _Named("BlueStacks App Player 2", 160, 28, minimized=True)
    player = _Named("BlueStacks App Player 1", 540, 934)
    manager = _Named("BlueStacks Multi Instance Manager", 842, 512)
    assert window_geometry.find_bluestacks_window([small, minimized, manager, player]) is player
    assert window_geometry.find_bluestacks_window([minimized]) is minimized
