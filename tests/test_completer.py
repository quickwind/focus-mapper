import os
from focus_report.completer import PathCompleter


def test_path_completer_lists_files(tmp_path, monkeypatch):
    (tmp_path / "data.csv").touch()
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "inner.txt").touch()

    completer = PathCompleter()

    prefix = str(tmp_path / "da")
    monkeypatch.setattr("readline.get_line_buffer", lambda: prefix)
    monkeypatch.setattr(
        "readline.get_completer_delims", lambda: " \t\n/\"\\'`@$><=;|&{("
    )

    matches = []
    state = 0
    while True:
        m = completer(prefix, state)
        if m is None:
            break
        matches.append(m)
        state += 1

    assert matches == ["data.csv"]

    prefix = str(tmp_path / "sub")
    monkeypatch.setattr("readline.get_line_buffer", lambda: prefix)

    matches = []
    state = 0
    while True:
        m = completer(prefix, state)
        if m is None:
            break
        matches.append(m)
        state += 1

    expected = "subdir" + os.sep
    assert matches == [expected]
