"""The exact planner behind its own toggle (memory_gui "Planer", off by default)."""
from types import SimpleNamespace

import move_strategy as ms
import square_solo_live as sl


def _state(booster, mode_id="color-climb", pvp=1):
    return {"rules": {"pvp_mode": pvp, "id": mode_id},
            "players": [{"player_type": 0, "special_ability_type": booster,
                         "special_ability_name": "Neki Booster"}]}


def test_supported_booster_and_mode():
    assert sl.planner_support(_state(52), ms.GameMode.COLOR_CLIMB.value) is None
    assert sl.planner_support(_state(54), ms.GameMode.COLOR_CLIMB.value) is None


def test_unsupported_booster_mode_and_versus_are_named():
    assert "booster Neki Booster" in sl.planner_support(_state(27), ms.GameMode.COLOR_CLIMB.value)
    reason = sl.planner_support(_state(52, "fireworks-festival"), ms.GameMode.FIREWORKS.value)
    assert "mod fireworks-festival" in reason
    both = sl.planner_support(_state(27, "fireworks-festival"), ms.GameMode.FIREWORKS.value)
    assert "booster" in both and "mod" in both
    # Showdown (2) and Versus (0) are planned too (quick plan).
    assert sl.planner_support(_state(52, pvp=2), ms.GameMode.COLOR_CLIMB.value) is None
    assert sl.planner_support(_state(52, pvp=0), ms.GameMode.COLOR_CLIMB.value) is None


def _window(research_checked=False):
    import memory_gui
    logs, shown = [], []
    research = SimpleNamespace(checked=research_checked)
    research.isChecked = lambda: research.checked
    research.setChecked = lambda value: setattr(research, "checked", value)
    window = SimpleNamespace(
        _planner_support_key=None, _log=logs.append, ResearchCheck=research,
        statusBar=lambda: SimpleNamespace(showMessage=lambda text, *_: shown.append(text)),
        _effective_mode=memory_gui.MemoryWindow._effective_mode)
    window._start_research_for_planner = lambda why: memory_gui.MemoryWindow._start_research_for_planner(window, why)
    return window, logs, research


def test_unsupported_turns_recording_on_and_says_why_once():
    import memory_gui
    window, logs, research = _window()
    state = _state(27, "color-climb")
    assert not memory_gui.MemoryWindow._planner_supported(window, state)
    assert research.checked
    assert any("Planer ne radi ovde" in line for line in logs)
    count = len(logs)
    memory_gui.MemoryWindow._planner_supported(window, state)
    assert len(logs) == count      # once per match


def test_supported_does_not_record():
    import memory_gui
    window, logs, research = _window()
    assert memory_gui.MemoryWindow._planner_supported(window, _state(52, "color-climb"))
    assert not research.checked and any("podrzan" in line for line in logs)


def test_a_miss_turns_recording_on():
    import memory_gui
    window, logs, research = _window()
    memory_gui.MemoryWindow._on_planner_miss(window, "planer je promasio dopunu")
    assert research.checked


def test_agent_traces_any_other_booster():
    from pathlib import Path
    tools = Path(__file__).resolve().parents[1] / "tools"
    for name in ("matchmasters_board_dump.ts", "matchmasters_board_dump.js"):
        text = (tools / name).read_text(encoding="utf-8")
        assert "installBoosterTrace" in text and 'kind: "booster"' in text
