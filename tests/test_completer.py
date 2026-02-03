import os
import readline
from focus_report.completer import PathCompleter


def test_path_completer_lists_files(tmp_path, monkeypatch):
    (tmp_path / "data.csv").touch()
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "inner.txt").touch()

    completer = PathCompleter()

    # Mock readline to simulate typing at the end of a path
    # If user types /path/to/da, token is 'da'
    prefix = str(tmp_path / "da")
    monkeypatch.setattr("readline.get_line_buffer", lambda: prefix)

    matches = []
    state = 0
    while True:
        m = completer("da", state)  # readline provides only the current token
        if m is None:
            break
        matches.append(m)
        state += 1

    # Matches should only contain the basename part
    assert matches == ["data.csv"]

    # Test directory completion
    prefix = str(tmp_path / "sub")
    monkeypatch.setattr("readline.get_line_buffer", lambda: prefix)

    matches = []
    state = 0
    while True:
        m = completer("sub", state)
        if m is None:
            break
        matches.append(m)
        state += 1

    expected = "subdir" + os.sep
    assert matches == [expected]
