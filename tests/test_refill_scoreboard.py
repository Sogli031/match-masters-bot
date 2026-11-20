import json


def test_worker_logs_each_checked_move(tmp_path):
    from refill_monitor import log_verdict

    path = tmp_path / "stats.jsonl"
    log_verdict({"mode": "bombs-away", "title": "Bombs Away", "move": None}, path)
    assert not path.exists()
    log_verdict({"mode": "bombs-away", "title": "Bombs Away", "move": {"verdict": "miss", "detail": "x"}}, path)
    line = json.loads(path.read_text(encoding="utf-8"))
    assert line["mode"] == "bombs-away" and line["verdict"] == "miss"


def test_table_puts_the_worst_mode_first_and_counts_unchecked():
    from tools.refill_scoreboard import table

    rows = [("a", "ok")] * 9 + [("a", "miss")] + [("b", "ok"), ("b", "miss"), ("b", "booster"), ("c", "gap")]
    lines = table(rows).splitlines()
    assert lines[1].split()[:5] == ["b", "1", "1", "50", "1"]
    assert lines[2].split()[:4] == ["a", "9", "1", "90"]
    assert lines[3].split()[:5] == ["c", "0", "0", "-", "1"]


def test_live_reads_since(tmp_path):
    from tools.refill_scoreboard import live

    path = tmp_path / "s.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in (
        {"time": "2026-11-18 10:00:00", "mode": "old", "verdict": "ok"},
        {"time": "2026-11-19 10:00:00", "mode": "new", "verdict": "miss"})) + "\nnot json\n", encoding="utf-8")
    text = live("2026-11-19", path)
    assert "new" in text and "old" not in text


def test_changes_names_what_broke():
    from tools.refill_scoreboard import changes, mode_of
    from pathlib import Path

    assert mode_of(Path("20261119_203212_264442_crystal-cave-master-league")) == "crystal-cave-master-league"
    text = changes({"f1": "miss", "f2": "ok"}, [{"folder": "f1", "verdict": "ok"}, {"folder": "f2", "verdict": "miss"}])
    assert text.splitlines() == ["Od proslog puta: popravljeno 1, pokvareno 1", "  POKVARENO f2"]
