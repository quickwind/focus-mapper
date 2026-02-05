from __future__ import annotations

import builtins
from pathlib import Path

import pandas as pd
import pytest

from focus_mapper.errors import ParquetUnavailableError
from focus_mapper.io import read_table, write_table


def test_read_table_unsupported_suffix(tmp_path: Path) -> None:
    path = tmp_path / "input.txt"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported input format"):
        read_table(path)


def test_write_table_unsupported_suffix(tmp_path: Path) -> None:
    path = tmp_path / "output.txt"
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="Unsupported output format"):
        write_table(df, path)


def test_write_table_parquet_metadata_missing_pyarrow(
    tmp_path: Path, monkeypatch
) -> None:
    df = pd.DataFrame({"a": [1]})
    path = tmp_path / "out.parquet"

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("pyarrow"):
            raise ImportError("no pyarrow")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ParquetUnavailableError):
        write_table(df, path, parquet_metadata={b"k": b"v"})
