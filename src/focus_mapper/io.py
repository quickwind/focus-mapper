from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .errors import ParquetUnavailableError


def _suffix(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def read_table(path: Path, *, nrows: int | None = None) -> pd.DataFrame:
    suffix = _suffix(path)
    if suffix == "csv":
        return pd.read_csv(path, nrows=nrows)
    if suffix == "parquet":
        # Parquet doesn't support nrows directly in read_parquet but we can workaround or use pyarrow if needed
        # For now, let's just read and head if nrows is set, as parquet details are tricky
        # Actually pd.read_parquet doesn't support nrows. 
        # But we can use pyarrow dataset or just read all and head.
        # Given the request for performance, for parquet we might need a better way if files are huge.
        # But for now let's just read and head.
        df = pd.read_parquet(path)
        if nrows is not None:
            return df.head(nrows)
        return df
    raise ValueError(f"Unsupported input format: {path}")


def write_table(
    df: pd.DataFrame, path: Path, *, parquet_metadata: dict[bytes, bytes] | None = None
) -> None:
    suffix = _suffix(path)
    if suffix == "csv":
        df.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
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
                "Parquet metadata embedding requires pyarrow. Install with: pip install -e \".[parquet]\""
            ) from e

        table = pa.Table.from_pandas(df, preserve_index=False)
        schema = table.schema
        merged = dict(schema.metadata or {})
        merged.update(parquet_metadata)
        table = table.cast(schema.with_metadata(merged))
        pq.write_table(table, path)
        return

    df.to_parquet(path, index=False)
