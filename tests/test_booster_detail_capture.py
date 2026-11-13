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
