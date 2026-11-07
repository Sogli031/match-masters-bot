import pytest

import runtime


@pytest.mark.parametrize("contents", ["", "{", "\x00" * 32, "null", "[]"])
def test_corrupt_previous_move_does_not_block_next_action(tmp_path, contents):
    previous = tmp_path / "previous"
    previous.mkdir()
    (previous / "move.json").write_text(contents, encoding="utf-8")

    assert runtime.write_observed_delta_report(
        previous, tmp_path / "after", None, None, [[1]], [[0]]
    ) is None
    assert not (previous / runtime.OBSERVED_DELTA_FILENAME).exists()
