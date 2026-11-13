""""Snimaj svaki potez" asks the agent for every booster's whole state."""
from pathlib import Path
from types import SimpleNamespace

import research_recorder

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def _script(calls):
    def arm(on):
        calls.append(on)
    return SimpleNamespace(exports_sync=SimpleNamespace(arm_booster_detail=arm))


def test_detail_follows_the_toggle_and_is_sent_only_on_change():
    calls = []
    recorder = research_recorder.ResearchRecorder()
    script = _script(calls)
    recorder._arm_booster_detail(script, True)
    recorder._arm_booster_detail(script, True)
    recorder._arm_booster_detail(script, False)
    recorder._arm_booster_detail(script, False)
    assert calls == [True, False]
    # A new agent (reattach) starts disarmed: arm it again.
    other = _script(calls)
    recorder._arm_booster_detail(other, False)
    assert calls == [True, False, False]


def test_older_agent_without_the_export_still_records():
    recorder = research_recorder.ResearchRecorder()
    recorder._arm_booster_detail(SimpleNamespace(exports_sync=SimpleNamespace()), True)


def test_record_arms_detail_before_reading_the_profile(monkeypatch):
    order = []
    recorder = research_recorder.ResearchRecorder()
    monkeypatch.setattr(recorder, "_arm_booster_detail", lambda script, on: order.append(("arm", on)))
    recorder._reader = SimpleNamespace(settled_profile=lambda *a, **k: order.append("profile"))
    script = SimpleNamespace(exports_sync=SimpleNamespace(arm_mixy_trace=lambda: None))
    assert recorder.record(script, enabled=lambda: True) is None
    assert order == [("arm", True), "profile"]


def test_agent_source_and_build_read_the_booster_detail():
    for name in ("matchmasters_board_dump.ts", "matchmasters_board_dump.js"):
        source = (TOOLS / name).read_text(encoding="utf-8")
        assert "armBoosterDetail" in source
        assert "ability_detail" in source
        assert "special_pieces_logics" in source
        assert "System.Collections.Generic.HashSet<" in source


def test_agent_traces_the_played_swap():
    for name in ("matchmasters_board_dump.ts", "matchmasters_board_dump.js"):
        source = (TOOLS / name).read_text(encoding="utf-8")
        assert "swap_trace" in source
        for method in ('"ValidSwapPerformed", 5', '"GetMergeSwapOutcome", 4', '"GetAreaOfEffectByPiece", 5',
                       '"GetAreaOfEffectDestructionSlots", 5', '"GetFireworks", 4'):
            assert method in source, (name, method)
        # Hint scans on the live board must not pass for the played merge.
        assert "swapTraceInSwap !== this.threadId" in source


def test_final_trace_is_kept_when_the_match_ends(tmp_path):
    import json

    recorder = research_recorder.ResearchRecorder()
    history = {"traces": [{"position1": [1, 5], "position2": [2, 5], "events": [{"type": "merge_outcome"}]}],
               "error": None}
    script = SimpleNamespace(exports_sync=SimpleNamespace(swap_trace_history=lambda: history))
    path = recorder.save_final_trace(script, tmp_path)
    assert path is not None
    assert json.loads((tmp_path / "kraj_partije_trag.json").read_text(encoding="utf-8")) == history


def test_final_trace_skips_old_agents_and_empty_history(tmp_path):
    recorder = research_recorder.ResearchRecorder()
    assert recorder.save_final_trace(SimpleNamespace(exports_sync=SimpleNamespace()), tmp_path) is None
    empty = SimpleNamespace(exports_sync=SimpleNamespace(swap_trace_history=lambda: {"traces": []}))
    assert recorder.save_final_trace(empty, tmp_path) is None
    assert recorder.save_final_trace(empty, None) is None
    assert not list(tmp_path.iterdir())


def test_gui_saves_the_trace_before_the_match_folder_is_dropped():
    source = (TOOLS.parent / "memory_gui.py").read_text(encoding="utf-8")
    save = source.index("self._research.save_final_trace")
    reset = source.index("self._reset_match_state()", save)
    assert save < reset
    for name in ("matchmasters_board_dump.ts", "matchmasters_board_dump.js"):
        assert "swapTraceHistory()" in (TOOLS / name).read_text(encoding="utf-8")
