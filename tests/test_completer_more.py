from __future__ import annotations

import os
from pathlib import Path

import focus_mapper.completer as completer
from focus_mapper.completer import ColumnCompleter, PathCompleter


def test_column_completer_case_insensitive() -> None:
    comp = ColumnCompleter(["BillingCost", "billingPeriod", "Other"])
    assert comp("b", 0) in {"BillingCost", "billingPeriod"}


def test_path_completer_returns_basename(tmp_path: Path) -> None:
    base = tmp_path / "tests"
    base.mkdir()
    (base / "fixtures").mkdir()
    (base / "files").mkdir()

    prefix = str(base) + os.sep + "fi"
    class DummyReadline:
        @staticmethod
        def get_line_buffer() -> str:
            return prefix

    original = completer.readline
    completer.readline = DummyReadline()
    try:
        comp = PathCompleter()
        first = comp(prefix, 0)
    finally:
        completer.readline = original
    assert first in {"fixtures" + os.sep, "files" + os.sep}
