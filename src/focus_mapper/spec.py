from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path as _Path
from typing import Any

from decimal import Decimal, InvalidOperation

import pandas as pd

from .errors import SpecError


@dataclass(frozen=True)
class FocusColumnSpec:
    """Represents the schema and constraints for a single FOCUS column."""

    name: str
    feature_level: str
    allows_nulls: bool
    data_type: str
    value_format: str | None = None
    allowed_values: list[str] | None = None
    numeric_precision: int | None = None
    numeric_scale: int | None = None

    @property
    def is_extension(self) -> bool:
        """Returns True if this is a custom extension column (starts with x_)."""
        return self.name.startswith("x_")


@dataclass(frozen=True)
class FocusSpec:
    """Represents a full FOCUS specification version (e.g., v1.2)."""

    version: str
    source: dict[str, Any] | None
    columns: list[FocusColumnSpec]

    @property
    def column_names(self) -> list[str]:
        """Returns a list of all standard column names in this spec."""
        return [c.name for c in self.columns]

    def get_column(self, name: str) -> FocusColumnSpec | None:
        """Retrieves a column specification by name."""
        for c in self.columns:
            if c.name == name:
                return c
        return None

    @property
    def mandatory_columns(self) -> list[FocusColumnSpec]:
        """Returns only the columns marked as 'Mandatory' in the spec."""
        return [c for c in self.columns if c.feature_level.lower() == "mandatory"]


def coerce_dataframe_to_spec(df: pd.DataFrame, *, spec: FocusSpec) -> pd.DataFrame:
    """Casts all standard columns in a DataFrame to the types defined in the FOCUS spec."""
    out = df.copy()
    for col in spec.columns:
        if col.name not in out.columns:
            continue
        series = out[col.name]
        if isinstance(series, pd.Series):
            out[col.name] = coerce_series_to_type(series, col)
    return out


def coerce_series_to_type(series: pd.Series, col: FocusColumnSpec) -> pd.Series:
    """Converts a pandas Series to the data type specified in the FOCUS column definition."""
    try:
        t = col.data_type.strip().lower()
        if t == "string":
            return series.astype("string")
        if t == "date/time":
            return pd.to_datetime(series, utc=True, errors="coerce")
        if t == "decimal":
            return _coerce_decimal(series)
        if t == "json":
            return _coerce_json(series)
        raise SpecError(f"Unsupported data type in spec: {col.data_type}")
    except SpecError:
        raise
    except Exception as err:
        raise Exception(f'Failed to convert type for column {col.name}: {err}')


def _coerce_decimal(series: pd.Series) -> pd.Series:
    """Safely converts a series to Decimal objects, handling nulls and numeric strings."""

    def conv(v: Any) -> Any:
        if v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)):
            return None
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError):
            return None

    return series.map(conv)


def _coerce_json(series: pd.Series) -> pd.Series:
    """Parses JSON strings into dictionaries, or preserves existing dicts."""

    def conv(v: Any) -> Any:
        if v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)):
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                return None
        return None

    return series.map(conv)


def load_focus_spec(version: str) -> FocusSpec:
    """Loads a FOCUS specification from a versioned JSON artifact."""
    normalized = version.lower().removeprefix("v")
    mod = normalized.replace(".", "_")

    try:
        pkg = f"focus_mapper.specs.v{mod}"
        with (
            resources.files(pkg)
            .joinpath(f"focus_v{mod}.json")
            .open("r", encoding="utf-8") as f
        ):
            raw = json.load(f)
    except FileNotFoundError as e:
        raise SpecError(
            "Missing embedded spec artifact. Run tools/populate_focus_spec.py "
            f"--version {normalized} to generate focus_v{mod}.json."
        ) from e
    except ModuleNotFoundError as e:
        raise SpecError(f"Unsupported spec version: {version}") from e

    cols: list[FocusColumnSpec] = []
    for item in raw["columns"]:
        cols.append(
            FocusColumnSpec(
                name=item["name"],
                feature_level=item["feature_level"],
                allows_nulls=bool(item["allows_nulls"]),
                data_type=item["data_type"],
                value_format=item.get("value_format"),
                allowed_values=item.get("allowed_values"),
                numeric_precision=item.get("numeric_precision"),
                numeric_scale=item.get("numeric_scale"),
            )
        )

    return FocusSpec(version=raw["version"], source=raw.get("source"), columns=cols)


def list_available_spec_versions() -> list[str]:
    specs_dir = _Path(__file__).resolve().parent / "specs"
    versions: list[str] = []
    if not specs_dir.exists():
        return versions
    for child in specs_dir.iterdir():
        if not child.is_dir():
            continue
        if not child.name.startswith("v"):
            continue
        mod = child.name[1:]
        json_path = child / f"focus_v{mod}.json"
        if json_path.exists():
            versions.append("v" + mod.replace("_", "."))
    return sorted(versions)
