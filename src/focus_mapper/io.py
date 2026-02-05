from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .errors import ParquetUnavailableError


def _suffix(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def read_table(path: Path) -> pd.DataFrame:
    suffix = _suffix(path)
    if suffix == "csv":
        return pd.read_csv(path)
    if suffix == "parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported input format: {path}")


def write_table(
    df: pd.DataFrame, path: Path, *, parquet_metadata: dict[bytes, bytes] | None = None
) -> None:
    suffix = _suffix(path)
    if suffix == "csv":
        df.to_csv(path, index=False)
        return

    if suffix != "parquet":
        raise ValueError(f"Unsupported output format: {path}")

    # For parquet, we want to embed key/value metadata when available.
    if parquet_metadata:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except Exception as e:  # pragma: no cover
            raise ParquetUnavailableError(
                "Parquet metadata embedding requires pyarrow. Install with: pip install -e '.[parquet]'"
            ) from e

        table = pa.Table.from_pandas(df, preserve_index=False)
        schema = table.schema
        merged = dict(schema.metadata or {})
        merged.update(parquet_metadata)
        table = table.cast(schema.with_metadata(merged))
        pq.write_table(table, path)
        return

    df.to_parquet(path, index=False)
