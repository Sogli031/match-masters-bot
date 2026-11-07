"""Mixy code liveness: no phantom code moves once the engine has spent a code.

Two independent guards, both added 2026-09-13:

* the GUI counts a use on a re-deal that follows neither an activation nor a
  counted transient (the transient the poll missed);
* the runtime declares the exact code a broken refund was promised on dead
  until the engine deals another.
"""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import memory_gui  # noqa: E402
import move_strategy as ms  # noqa: E402
import runtime  # noqa: E402

GUI = memory_gui.MemoryWindow


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class Stub:
    """The Mixy tracking slice of MemoryWindow, without the Qt window."""

    ABILITY_MIXY_MEOW = GUI.ABILITY_MIXY_MEOW
    MIXY_CODE_PHASES = GUI.MIXY_CODE_PHASES
    MIXY_DEFAULT_MAX_USES = GUI.MIXY_DEFAULT_MAX_USES
    MIXY_REDEAL_AFTER_ACTIVATION_SECONDS = GUI.MIXY_REDEAL_AFTER_ACTIVATION_SECONDS
    MIXY_REDEAL_SAME_USE_SECONDS = GUI.MIXY_REDEAL_SAME_USE_SECONDS
    _mixy_max_uses_from = GUI._mixy_max_uses_from
    _mixy_engine_uses_left = staticmethod(GUI._mixy_engine_uses_left)
    _sync_mixy_uses_from_engine = GUI._sync_mixy_uses_from_engine
    _track_mixy_activation_uses = GUI._track_mixy_activation_uses
    _track_mixy_code_spend = GUI._track_mixy_code_spend
    _memory_mixy_state = GUI._memory_mixy_state

    def __init__(self, logs):
        self._mixy_code_reported = None
        self._mixy_spent_code = None
        self._mixy_spent_colors = set()
        self._mixy_spend_armed = True
        self._mixy_uses_this_activation = 0
        self._mixy_max_uses = 0
        self._mixy_prev_phase = None
        self._mixy_prev_energy = None
        self._mixy_transient_live = False
        self._mixy_prev_code = None
        self._mixy_last_use_at = 0.0
        self._mixy_activated_at = 0.0
        self._mixy_activation_count = 0
        self._mixy_turn_key = None
        self._log = logs.append


def gui_stub(logs):
    return Stub(logs)


def me(energy, phase, code, src=(), tgt=1, uses_left=None, caps=(2,)):
    frame = {
        "special_ability_type": 59,
        "energy": energy,
        "special_ability_fields": {
            "<Phase>k__BackingField": phase,
            "activeColors": list(code) if code is not None else None,
            "SourceColors": list(src),
            "TargetColor": tgt,
            "maxUsesByActivation": list(caps),
        },
    }
    if uses_left is not None:
        # What a manual dump from the new agent build carries.
        frame["special_ability_engine"] = {"uses_left": uses_left,
                                           "passive_uses_since_activate": 2 - uses_left,
                                           "activates": 1}
    return frame


def test_engine_uses_left_overrules_the_inferred_count(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(memory_gui.time, "monotonic", clock)
    logs = []
    stub = gui_stub(logs)
    step(stub, me(0, 0, [6, 2, 5]))
    # No transient was ever seen, yet the engine says both uses are gone.
    state = step(stub, me(0, 1, [6, 2, 5], uses_left=0))
    assert stub._mixy_uses_this_activation == 2
    assert state.code_exhausted
    assert state.engine_uses_left == 0
    assert any("engine kaze UsesLeft=0" in line for line in logs)
    # ... and the other way round: the engine still has a use where the
    # inference over-counted.
    stub._mixy_uses_this_activation = 2
    state = step(stub, me(0, 1, [6, 2, 5], uses_left=1))
    assert stub._mixy_uses_this_activation == 1
    assert not state.code_exhausted
    # A plain poll (no engine block) leaves the counter alone.
    state = step(stub, me(0, 1, [6, 2, 5]))
    assert stub._mixy_uses_this_activation == 1
    assert state.engine_uses_left is None


def test_engine_uses_left_without_a_dealt_code_is_ignored(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(memory_gui.time, "monotonic", clock)
    stub = gui_stub([])
    # Before the first activation the key does not exist and the getter
    # returns 0 -- with no code dealt that must not pre-exhaust anything.
    step(stub, me(3, 0, None, uses_left=0))
    assert stub._mixy_uses_this_activation == 0


def step(stub, frame):
    stub._track_mixy_code_spend(frame)
    return stub._memory_mixy_state(frame)


def test_transient_edges_count_uses_as_before(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(memory_gui.time, "monotonic", clock)
    logs = []
    stub = gui_stub(logs)
    step(stub, me(7, 1, [6, 2]))
    clock.now += 1
    step(stub, me(0, 0, [6, 2]))                       # activation
    clock.now += 2
    step(stub, me(0, 0, [6, 2, 5]))                    # fresh code, inside the activation window
    assert stub._mixy_uses_this_activation == 0
    clock.now += 10
    step(stub, me(0, 1, [6, 2, 5], src=[6, 2], tgt=5))  # use #1 transient
    assert stub._mixy_uses_this_activation == 1
    clock.now += 5
    step(stub, me(0, 1, [5, 3, 6], src=[6, 2], tgt=5))  # its re-deal, same use (slowest measured: 5 s)
    assert stub._mixy_uses_this_activation == 1
    clock.now += 2
    state = step(stub, me(0, 1, [5, 3, 6]))
    assert not state.code_exhausted
    clock.now += 10
    step(stub, me(0, 1, [5, 3, 6], src=[3, 6], tgt=5))  # use #2 transient
    state = step(stub, me(0, 1, [5, 3, 6]))
    assert stub._mixy_uses_this_activation == 2
    assert state.code_exhausted


def test_missed_transient_is_recovered_from_the_redeal(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(memory_gui.time, "monotonic", clock)
    logs = []
    stub = gui_stub(logs)
    step(stub, me(0, 0, [6, 2, 5]))
    stub._mixy_activated_at = clock.now - 30
    clock.now += 5
    # The poll never saw SourceColors; the list simply changed.
    state = step(stub, me(0, 1, [5, 3, 6]))
    assert stub._mixy_uses_this_activation == 1
    assert any("bez vidjenog pogotka" in line for line in logs)
    assert not state.code_exhausted
    clock.now += 20
    state = step(stub, me(0, 1, [2, 7]))               # second silent re-deal
    assert stub._mixy_uses_this_activation == 2
    assert state.code_exhausted
    assert ms.MixyMeowState(**{**state.__dict__}).code_exhausted


def test_redeal_right_after_activation_is_not_a_use(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(memory_gui.time, "monotonic", clock)
    stub = gui_stub([])
    step(stub, me(7, 1, [3, 6]))
    clock.now += 1
    step(stub, me(0, 0, [3, 6]))                       # meter empties: activation
    clock.now += 2
    step(stub, me(0, 0, [2, 5]))                       # the activation's own fresh code
    assert stub._mixy_uses_this_activation == 0


def test_runtime_declares_the_burned_code_dead_until_it_redeals(monkeypatch):
    runtime.reset_mixy_refund_watch()
    state = ms.MixyMeowState(active=True, code_colors=(3, 6), confidence=1.0,
                             source="memory", max_uses=2, uses_this_activation=1)
    runtime._note_mixy_current_code(state)
    runtime._note_mixy_refund_promised(5)
    assert runtime._mixy_refund_watch["promised_code"] == (3, 6)
    # Verdict window long past, counter still one short: the refund burned.
    runtime._mixy_refund_watch["promised_at"] -= runtime.MIXY_REFUND_VERDICT_SECONDS + 1
    assert runtime._mixy_refund_burned(4) is True
    assert runtime._mixy_refund_watch["dead_code"] == (3, 6)
    assert runtime._mixy_code_dead_after_burn(state) is True
    # A re-dealt list is a fresh question, and the verdict is cleared.
    fresh = ms.MixyMeowState(active=True, code_colors=(2, 5), confidence=1.0,
                             source="memory", max_uses=2)
    assert runtime._mixy_code_dead_after_burn(fresh) is False
    assert runtime._mixy_refund_watch["dead_code"] is None
    runtime.reset_mixy_refund_watch()


def test_landed_refund_convicts_nothing():
    runtime.reset_mixy_refund_watch()
    state = ms.MixyMeowState(active=True, code_colors=(3, 6), confidence=1.0, source="memory")
    runtime._note_mixy_current_code(state)
    runtime._note_mixy_refund_promised(5)
    assert runtime._mixy_refund_burned(5) is False
    assert runtime._mixy_refund_watch["dead_code"] is None
    assert runtime._mixy_code_dead_after_burn(state) is False
    runtime.reset_mixy_refund_watch()


def test_extra_button_never_bets_on_the_refund_alone():
    """The 2026-09-13 02:42:41 press: a credited code match, no refund, move lost."""
    assert runtime.MIXY_REFUND_ONLY_EXTRA_FALLBACK is False
    refund_only = types.SimpleNamespace(direct_extra_moves=1.0, extra_moves=1.0, score=40.0)
    own_extra = types.SimpleNamespace(direct_extra_moves=2.0, extra_moves=2.0, score=30.0)
    # With the refund credited, only a candidate whose own swap earns an extra
    # beyond that credit counts as refund-proof.
    assert runtime._prefer_refund_proof_mixy_extra([refund_only, own_extra], True) is own_extra
    assert runtime._prefer_refund_proof_mixy_extra([refund_only], True) is refund_only
    assert refund_only.direct_extra_moves <= 1.0  # i.e. not refund-proof


def test_per_activation_cap_list_is_indexed_by_activation(monkeypatch):
    """Party Color Climb 2026-09-13 03:13: maxUsesByActivation [2, 1]."""
    clock = Clock()
    monkeypatch.setattr(memory_gui.time, "monotonic", clock)
    logs = []
    stub = gui_stub(logs)
    caps = (2, 1)
    step(stub, me(7, 1, [7, 3, 5], caps=caps))
    clock.now += 1
    step(stub, me(0, 0, [7, 3, 5], caps=caps))          # activation #1
    assert stub._mixy_activation_count == 1
    assert stub._mixy_max_uses == 2
    clock.now += 10
    step(stub, me(0, 1, [2, 7, 5], src=[2, 7], tgt=5, caps=caps))
    clock.now += 10
    state = step(stub, me(0, 1, [7, 3, 5], caps=caps))
    assert not state.code_exhausted                     # one of two used
    clock.now += 10
    step(stub, me(7, 1, [7, 3, 5], caps=caps))
    clock.now += 1
    step(stub, me(0, 0, [7, 3, 5], caps=caps))          # activation #2
    assert stub._mixy_activation_count == 2
    assert stub._mixy_max_uses == 1
    clock.now += 3
    step(stub, me(0, 0, [2, 5], caps=caps))
    clock.now += 10
    step(stub, me(0, 1, [2, 5], src=[2], tgt=5, caps=caps))  # the single use
    clock.now += 3
    state = step(stub, me(0, 1, [2, 5], caps=caps))
    assert state.code_exhausted                         # the 03:14:02 trap, now closed
    assert any("kod ima 1 upotrebu" in line for line in logs)


def test_activation_count_restarts_with_the_turn(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(memory_gui.time, "monotonic", clock)
    stub = gui_stub([])
    caps = (2, 1)
    stub._track_mixy_code_spend(me(7, 1, [7, 3], caps=caps), {"turns": 1, "current_round": 1})
    clock.now += 1
    stub._track_mixy_code_spend(me(0, 0, [7, 3], caps=caps), {"turns": 1, "current_round": 1})
    assert stub._mixy_activation_count == 1
    clock.now += 30
    stub._track_mixy_code_spend(me(7, 1, [7, 3], caps=caps), {"turns": 1, "current_round": 1})
    clock.now += 1
    stub._track_mixy_code_spend(me(0, 0, [7, 3], caps=caps), {"turns": 1, "current_round": 1})
    assert stub._mixy_max_uses == 1
    # Next turn: the first activation there gets the full cap again.
    clock.now += 60
    stub._track_mixy_code_spend(me(7, 1, [7, 3], caps=caps), {"turns": 2, "current_round": 1})
    clock.now += 1
    stub._track_mixy_code_spend(me(0, 0, [7, 3], caps=caps), {"turns": 2, "current_round": 1})
    assert stub._mixy_activation_count == 1
    assert stub._mixy_max_uses == 2


def test_cap_from_params_string_when_fields_lack_it():
    stub = gui_stub([])
    stub._mixy_activation_count = 3
    frame = {"special_ability_params": {"maxUsesByActivation": "2,1"}}
    assert stub._mixy_max_uses_from(frame, {}) == 1
    stub._mixy_activation_count = 1
    assert stub._mixy_max_uses_from(frame, {}) == 2
    assert stub._mixy_max_uses_from({}, {}) == 2


def test_exhausted_state_yields_no_code_moves():
    state = ms.MixyMeowState(active=True, code_colors=(3, 6), confidence=1.0,
                             source="memory", max_uses=2, uses_this_activation=2)
    board = [[(r * 2 + c) % 5 + 1 for c in range(5)] for r in range(5)]
    specials = [[0] * 5 for _ in range(5)]
    assert ms.rank_mixy_code_moves(board, specials, state, mode=ms.GameMode.NONE,
                                   include_future_value=False, lookahead_candidates=0) == []
