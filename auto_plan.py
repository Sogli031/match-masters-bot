"""Single-worker speculative planning; GUI owns validation, worker owns execution."""
import json
import threading
from contextlib import contextmanager
from contextvars import ContextVar


class PlanningCancelled(Exception):
    pass


_cancel_check = ContextVar('auto_plan_cancel_check', default=None)


@contextmanager
def planning_cancellation(check):
    token = _cancel_check.set(check)
    try:
        check_planning_cancelled()
        yield
    finally:
        _cancel_check.reset(token)


def check_planning_cancelled():
    check = _cancel_check.get()
    if check is not None and check():
        raise PlanningCancelled()


def snapshot_plan_key(snapshot, policy=()):
    """Include strategic state, excluding arrival timestamps and animation flags."""
    if not snapshot:
        return None
    state = dict(snapshot.get('state') or {})
    for key in ('game_state', 'chain_reaction', 'timer_paused', 'remaining_time',
                'accumulated_move_score', 'accumulated_turn_score'):
        state.pop(key, None)
    payload = {key: snapshot.get(key) for key in (
        'board', 'special_board', 'board_object', 'board_extra_data', 'cell_types',
        'jelly', 'froggy', 'active_mutations', 'mutation_fields',
    )}
    payload.update(state=state, policy=policy)
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))


def plan_key_difference(old_key, new_key):
    """What separates two plan keys, for the log: top-level and state field names."""
    try:
        old, new = json.loads(old_key), json.loads(new_key)
    except (TypeError, ValueError):
        return ['plan ponisten']
    changed = [key for key in sorted(set(old) | set(new))
               if key != 'state' and old.get(key) != new.get(key)]
    old_state, new_state = old.get('state') or {}, new.get('state') or {}
    changed += [f'state.{key}' for key in sorted(set(old_state) | set(new_state))
                if old_state.get(key) != new_state.get(key)]
    return changed


class AutoPlan:
    """One speculative computation of a move on one board.

    ``armed`` is whether the worker may *play* the move once the board is
    ready. Auto plans are armed from the start; a plan started on its own,
    with Auto off, computes and then holds the finished move until a move
    button arms it (or a changed board cancels it). ``on_computed`` is called
    from the worker thread the moment the search is done and the wait begins.
    """

    def __init__(self, key, armed=True, action="best_move", on_computed=None):
        self.key = key
        self.action = action
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self.cancelled = False
        self.ready = False
        self.executing = False
        self.armed = bool(armed)
        self.computed = False
        self._on_computed = on_computed

    def _refresh_wake(self):
        if self.cancelled or (self.ready and self.armed):
            self._wake.set()
        else:
            self._wake.clear()

    def update(self, key, ready):
        with self._lock:
            if self.executing:
                return
            if key != self.key:
                self.cancelled = True
            self.ready = bool(ready) and not self.cancelled
            self._refresh_wake()

    def arm(self):
        with self._lock:
            self.armed = True
            self._refresh_wake()

    def disarm(self):
        with self._lock:
            if self.executing:
                return
            self.armed = False
            self._refresh_wake()

    def cancel(self):
        self.update(None, False)

    def is_cancelled(self):
        with self._lock:
            return self.cancelled

    def wait_until_ready(self):
        with self._lock:
            self.computed = True
        if self._on_computed is not None:
            self._on_computed(self)
        # An armed plan whose board never settles gives up: a missing reader
        # or frozen GUI can never leave a worker alive forever. An unarmed
        # plan is waiting for a click, which can take as long as it takes --
        # a changed board cancels it, so it never outlives its usefulness.
        while not self._wake.wait(15):
            with self._lock:
                armed = self.armed
            if armed:
                self.cancel()
                break
        with self._lock:
            return self.ready and self.armed and not self.cancelled

    def claim_execution(self):
        with self._lock:
            if self.cancelled or not self.ready or not self.armed or self.executing:
                return False
            self.executing = True
            return True
