from __future__ import annotations

import runpy
import sys

import pytest


def test_main_module_version_exits_zero(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["focus-mapper", "--version"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("focus_mapper.__main__", run_name="__main__")
    assert exc.value.code == 0
