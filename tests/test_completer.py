import os
from focus_report.completer import PathCompleter


def test_path_completer_lists_files(tmp_path):
    (tmp_path / "data.csv").touch()
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "inner.txt").touch()

    completer = PathCompleter()

    prefix = str(tmp_path / "da")
    matches = []
    state = 0
    while True:
        m = completer(prefix, state)
        if m is None:
            break
        matches.append(m)
        state += 1

    assert matches == [str(tmp_path / "data.csv")]

    prefix = str(tmp_path / "sub")
    matches = []
    state = 0
    while True:
        m = completer(prefix, state)
        if m is None:
            break
        matches.append(m)
        state += 1

    expected = str(tmp_path / "subdir") + os.sep
    assert matches == [expected]
