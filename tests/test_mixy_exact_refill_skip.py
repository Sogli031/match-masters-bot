"""A live Mixy Meow code keeps the exact-refill gate out of the move choice.

2026-11-07 05:35-05:37, Column Mania with the drop known: the exact-refill gate
re-simulates moves without the Mixy code, so it played a 3-blue match over code
moves the bot scored 151-192, and twice spent the code on a move it did not know
fired it. Like a lotus, a live code now leaves the bot's own pick alone.
"""
import move_strategy as ms
import runtime


def _state(uses, max_uses=2):
    return ms.MixyMeowState(active=True, code_colors=(5, 4), uses_this_activation=uses,
                            max_uses=max_uses, confidence=1.0, source="memory")


def test_live_code_blocks_the_exact_refill_override():
    assert runtime._mixy_code_live(True, _state(0))
    assert runtime._mixy_code_live(True, _state(1))


def test_spent_code_or_no_code_lets_exact_refill_decide():
    assert not runtime._mixy_code_live(True, _state(2))
    assert not runtime._mixy_code_live(False, _state(0))
    assert not runtime._mixy_code_live(None, None)


def test_unknown_use_count_counts_as_live():
    assert runtime._mixy_code_live(True, _state(5, max_uses=0))


def test_runtime_guards_the_exact_refill_branch_with_it():
    import inspect
    source = inspect.getsource(runtime)
    branch = source[source.index("exact_pick = exact_refill_choice(") - 3000:
                    source.index("exact_pick = exact_refill_choice(")]
    assert "_mixy_code_live(" in branch
