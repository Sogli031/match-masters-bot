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
                       '"GetAreaOfEffectDestructionSlots", 5', '"GetFireworks", 4',
                       # Cleo's own colour choice: probes, rolls, converted cells.
                       '"SwapPerformed", 3', '"ConvertToPiece", 1', '"GetAllCombos", 4', '"Chance", 1'):
            assert method in source, (name, method)
        # Hint scans on the live board must not pass for the played merge.
        assert "swapTraceInSwap !== this.threadId" in source



def test_cleo_hooks_only_while_the_booster_is_cleo():
    # RandomWrapper.Chance and the Cleo hooks crashed CupidSE's activation
    # (Vegas Views 2026-11-14): they are installed only for a Cleo booster.
    for name in ("matchmasters_board_dump.ts", "matchmasters_board_dump.js"):
        source = (TOOLS / name).read_text(encoding="utf-8")
        swap = source[source.index("function installSwapTrace"):source.index("function removeCleoTrace")]
        assert '"Chance", 1' not in swap and '"SwapPerformed", 3' not in swap, name
        cleo = source[source.index("function installCleoTrace"):source.index("function installJellyTrace")]
        for method in ('"SwapPerformed", 3', '"ConvertToPiece", 1', '"GetAllCombos", 4', '"Chance", 1'):
            assert method in cleo, (name, method)
        assert "removeCleoTrace()" in source, name

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


def test_agent_traces_woolly_workout_only_for_woolly():
    for name in ("matchmasters_board_dump.ts", "matchmasters_board_dump.js"):
        source = (TOOLS / name).read_text(encoding="utf-8")
        assert '"Match3Engine.WoollyWorkout"' in source
        assert '"ConvertSlots", 1' in source and "woolly_convert" in source
        assert "installWoollyTrace" in source and "removeWoollyTrace" in source


def test_agent_traces_checkmate_charles_only_for_charles():
    for name in ("matchmasters_board_dump.ts", "matchmasters_board_dump.js"):
        source = (TOOLS / name).read_text(encoding="utf-8")
        assert '"Match3Engine.CheckmateCharles"' in source
        for method in ('"ChoosePositionsForActivateExplosion", 1', '"RefillExplodedSpecials", 2',
                       '"ChoosePositionsForKnights", 2'):
            assert method in source
        assert "installCharlesTrace" in source and "removeCharlesTrace" in source


def test_disarm_removes_the_swap_trace_hooks():
    # Research off: the live trace's hooks read the whole board on every cascade step.
    for name in ("matchmasters_board_dump.ts", "matchmasters_board_dump.js"):
        source = (TOOLS / name).read_text(encoding="utf-8")
        arm = source[source.index("armBoosterDetail(on"):][:300]
        assert "removeSwapTrace()" in arm, name
        remove = source[source.index("function removeSwapTrace"):][:600]
        assert "swapTraceActive = null" in remove and "detach()" in remove, name
