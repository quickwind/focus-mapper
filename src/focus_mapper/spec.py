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
    description: str | None = None
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
    metadata: dict[str, Any] | None = None

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
            dt_series = pd.to_datetime(series, errors="coerce")
            # Ensure proper UTC conversion - handle both timezone-naive and timezone-aware datetimes
            if dt_series.dt.tz is None:
                # Treat timezone-naive datetimes as UTC
                dt_series = dt_series.dt.tz_localize('UTC')
            else:
                # Convert timezone-aware datetimes to UTC
                dt_series = dt_series.dt.tz_convert('UTC')
            return dt_series
        if t == "decimal":
            return _coerce_decimal(series)
        if t == "json":
            return _coerce_json(series)
        raise SpecError(f"Unsupported data type in spec: {col.data_type}")
    except SpecError:
        raise
    except Exception as err:
        raise Exception(f"Failed to convert type for column {col.name}: {err}")


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


def _resolve_spec_search_paths(spec_dir: str | _Path | None) -> list[_Path]:
    """
    Returns a list of directories to search for spec files, in priority order:
    1. Explicit spec_dir argument
    2. FOCUS_SPEC_DIR environment variable
    """
    import os
    paths: list[_Path] = []
    if spec_dir is not None:
        paths.append(_Path(spec_dir))
    
    env_dir = os.environ.get("FOCUS_SPEC_DIR")
    if env_dir:
        paths.append(_Path(env_dir))
    return paths


def load_focus_spec(version: str, *, spec_dir: str | _Path | None = None) -> FocusSpec:
    """
    Loads a FOCUS specification from a versioned JSON artifact.

    Args:
        version: Spec version (e.g., "v1.2", "1.3")
        spec_dir: Optional directory containing spec JSON files.
                  Files should be named focus_v{x}_{y}.json (e.g., focus_v1_2.json).
                  If not provided, checks FOCUS_SPEC_DIR env var, then falls back
                  to bundled specs.

    The spec directory can contain multiple version files to override multiple
    versions at once.

    Returns:
        FocusSpec object

    Raises:
        SpecError: If spec version is not found or invalid
    """
    normalized = version.lower().removeprefix("v")
    mod = normalized.replace(".", "_")
    filename = f"focus_spec_v{normalized}.json"

    raw: dict[str, Any] | None = None

    # Check external directories (arg -> env)
    for candidate_dir in _resolve_spec_search_paths(spec_dir):
        spec_path = candidate_dir / filename
        if spec_path.exists():
            with open(spec_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            break

    # Priority 3: Bundled specs
    if raw is None:
        try:
            pkg = f"focus_mapper.specs.v{mod}"
            with (
                resources.files(pkg)
                .joinpath(filename)
                .open("r", encoding="utf-8") as f
            ):
                raw = json.load(f)
        except FileNotFoundError as e:
            raise SpecError(
                "Missing embedded spec artifact. Run tools/populate_focus_spec.py "
                f"--version {normalized} to generate {filename}."
            ) from e
        except ModuleNotFoundError as e:
            raise SpecError(f"Unsupported spec version: {version}") from e

    if raw is None:
        raise SpecError(f"Spec version {version} not found in spec_dir or bundled specs")

    cols: list[FocusColumnSpec] = []
    for item in raw["columns"]:
        cols.append(
            FocusColumnSpec(
                name=item["name"],
                feature_level=item["feature_level"],
                allows_nulls=bool(item["allows_nulls"]),
                data_type=item["data_type"],
                description=item.get("description"),
                value_format=item.get("value_format"),
                allowed_values=item.get("allowed_values"),
                numeric_precision=item.get("numeric_precision"),
                numeric_scale=item.get("numeric_scale"),
            )
        )

    return FocusSpec(
        version=raw["version"],
        source=raw.get("source"),
        columns=cols,
        metadata=raw.get("metadata"),
    )


def list_available_spec_versions(*, spec_dir: str | _Path | None = None) -> list[str]:
    """
    Lists available FOCUS spec versions.
    
    If spec_dir is provided (or FOCUS_SPEC_DIR env var is set), scans that directory 
    for 'focus_spec_v*.json' files.
    Otherwise, scans the bundled specs directory.
    """
    import re

    # Resolve scan directories
    search_paths = _resolve_spec_search_paths(spec_dir)
    # For listing, we use the first valid external directory found (if any),
    # matching the priority logic (Arg > Env). We don't merge them.
    versions: set[str] = set()

    # 1. Scan External Directories (Arg > Env)
    # We use the first valid external directory found
    scan_dir: _Path | None = None
    for p in search_paths:
        if p.exists():
            scan_dir = p
            break
            
    if scan_dir is not None:
        # Look for focus_spec_vX_Y.json or focus_spec_vX.Y.json
        pat = re.compile(r"^focus_spec_v(.+)\.json$")
        
        for child in scan_dir.iterdir():
            if not child.is_file():
                continue
            m = pat.match(child.name)
            if m:
                raw_ver = m.group(1)
                # Normalize version string (e.g., 1_0 -> v1.0)
                dot_ver = raw_ver.replace("_", ".")
                versions.add(f"v{dot_ver}")

    # 2. Scan Bundled Specs
    specs_dir = _Path(__file__).resolve().parent / "specs"
    if specs_dir.exists():
        for child in specs_dir.iterdir():
            if not child.is_dir():
                continue
            if not child.name.startswith("v"):
                continue
            mod = child.name[1:]
            # Standardize on dot version
            dot_version = mod.replace("_", ".")
            versions.add(f"v{dot_version}")
            
    return sorted(list(versions))
