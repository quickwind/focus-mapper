from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

from decimal import Decimal, InvalidOperation

import pandas as pd

from .errors import SpecError


@dataclass(frozen=True)
class FocusColumnSpec:
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
        return self.name.startswith("x_")


@dataclass(frozen=True)
class FocusSpec:
    version: str
    source: dict[str, Any] | None
    columns: list[FocusColumnSpec]

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def get_column(self, name: str) -> FocusColumnSpec | None:
        for c in self.columns:
            if c.name == name:
                return c
        return None

    @property
    def mandatory_columns(self) -> list[FocusColumnSpec]:
        return [c for c in self.columns if c.feature_level.lower() == "mandatory"]


def coerce_dataframe_to_spec(df: pd.DataFrame, *, spec: FocusSpec) -> pd.DataFrame:
    out = df.copy()
    for col in spec.columns:
        if col.name not in out.columns:
            continue
        series = out[col.name]
        if isinstance(series, pd.Series):
            out.loc[:, col.name] = coerce_series_to_type(series, col)
    return out


def coerce_series_to_type(series: pd.Series, col: FocusColumnSpec) -> pd.Series:
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


def _coerce_decimal(series: pd.Series) -> pd.Series:
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
    normalized = version.lower().removeprefix("v")
    if normalized != "1.2":
        raise SpecError(f"Unsupported spec version: {version}")

    try:
        pkg = "focus_report.specs.v1_2"
        with (
            resources.files(pkg)
            .joinpath("focus_v1_2.json")
            .open("r", encoding="utf-8") as f
        ):
            raw = json.load(f)
    except FileNotFoundError as e:
        raise SpecError(
            "Missing embedded spec artifact. Run tools/vendor_focus_v1_2.py to generate focus_v1_2.json."
        ) from e

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
