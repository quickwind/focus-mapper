from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .mapping.config import MappingConfig
from .spec import FocusSpec


@dataclass(frozen=True)
class SidecarMetadata:
    spec_version: str
    generated_at: str
    generator_name: str
    generator_version: str
    schema_id: str
    column_definitions: list[dict]
    input_path: str
    output_path: str
    # v1.3+ fields
    creation_date: str | None = None  # From mapping YAML
    dataset_type: str = "CostAndUsage"
    dataset_instance_name: str | None = None
    dataset_instance_id: str | None = None
    time_sectors: list[dict] | None = None
    dataset_instance_complete: bool | None = None

    def to_dict(self) -> dict:
        """Generate metadata dict, version-aware."""
        # Parse version for comparison
        version = self.spec_version.lstrip("v")

        if version >= "1.3":
            return self._to_dict_v1_3()
        return self._to_dict_v1_2()

    def _to_dict_v1_2(self) -> dict:
        """v1.0-v1.2: Object-based structure."""
        schema = {
            "SchemaId": self.schema_id,
            "FocusVersion": self.spec_version.lstrip("v"),
            "CreationDate": self.creation_date or self.generated_at,
            "DataGeneratorVersion": self.generator_version,
            "ColumnDefinition": self.column_definitions,
        }
        return {
            "DataGenerator": {"DataGenerator": self.generator_name},
            "Schema": schema,
        }

    def _to_dict_v1_3(self) -> dict:
        """v1.3+: Collection-based structure with DatasetInstance and Recency."""
        version = self.spec_version.lstrip("v")
        dataset_instance_id = self.dataset_instance_id or ""

        # DatasetInstance collection
        dataset_instance = {
            "DatasetInstanceId": dataset_instance_id,
            "DatasetInstanceName": self.dataset_instance_name or "Default",
            "FocusDatasetId": self.dataset_type,
        }

        # Recency collection
        recency: dict[str, Any] = {
            "DatasetInstanceId": dataset_instance_id,
            "RecencyLastUpdated": self.generated_at,
            "DatasetInstanceLastUpdated": self.generated_at,
        }

        # DatasetInstanceComplete is always included
        recency["DatasetInstanceComplete"] = (
            self.dataset_instance_complete
            if self.dataset_instance_complete is not None
            else True
        )

        # CostAndUsage datasets also include TimeSectors if available
        if self.dataset_type == "CostAndUsage" and self.time_sectors:
            recency["TimeSectors"] = self.time_sectors

        # Schema collection
        schema = {
            "SchemaId": self.schema_id,
            "FocusVersion": version,
            "CreationDate": self.creation_date or self.generated_at,
            "DataGeneratorVersion": self.generator_version,
            "DatasetInstanceId": dataset_instance_id,
            "ColumnDefinition": self.column_definitions,
        }

        return {
            "DataGenerator": {
                "DataGenerator": self.generator_name,
                "DataGeneratorVersion": self.generator_version,
            },
            "DatasetInstance": [dataset_instance],
            "Recency": [recency],
            "Schema": [schema],
        }

    def parquet_kv_metadata(self) -> dict[bytes, bytes]:
        # Keep values short; Parquet metadata is key/value bytes.
        return {
            b"SchemaId": self.schema_id.encode("utf-8"),
            b"FocusVersion": self.spec_version.encode("utf-8"),
            b"CreationDate": (self.creation_date or self.generated_at).encode("utf-8"),
            b"DataGenerator": self.generator_name.encode("utf-8"),
            b"DataGeneratorVersion": self.generator_version.encode("utf-8"),
        }


def build_sidecar_metadata(
    *,
    spec: FocusSpec,
    mapping: MappingConfig,
    generator_name: str,
    generator_version: str,
    input_path: Path,
    output_path: Path,
    output_df: pd.DataFrame,
    provider_tag_prefixes: list[str] | None = None,
    time_sectors: list[dict] | None = None,
    dataset_instance_complete: bool | None = None,
) -> SidecarMetadata:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    schema_id = _schema_id(
        spec=spec,
        mapping=mapping,
        generator_version=generator_version,
        columns=list(output_df.columns),
    )

    # Generate DatasetInstanceId for v1.3+
    dataset_instance_id = _dataset_instance_id(
        dataset_type=mapping.dataset_type,
        dataset_instance_name=mapping.dataset_instance_name,
        schema_id=schema_id,
        output_df=output_df,
    )

    column_definitions = _build_column_definitions(
        output_df=output_df,
        spec=spec,
        provider_tag_prefixes=provider_tag_prefixes or [],
    )

    return SidecarMetadata(
        spec_version=spec.version,
        generated_at=now,
        generator_name=generator_name,
        generator_version=generator_version,
        schema_id=schema_id,
        column_definitions=column_definitions,
        input_path=str(input_path),
        output_path=str(output_path),
        creation_date=mapping.creation_date,
        dataset_type=mapping.dataset_type,
        dataset_instance_name=mapping.dataset_instance_name,
        dataset_instance_id=dataset_instance_id,
        time_sectors=time_sectors,
        dataset_instance_complete=dataset_instance_complete,
    )


def write_sidecar_metadata(meta: SidecarMetadata, path: Path) -> None:
    path.write_text(
        json.dumps(meta.to_dict(), indent=2, sort_keys=False), encoding="utf-8"
    )


def _schema_id(
    *,
    spec: FocusSpec,
    mapping: MappingConfig,
    generator_version: str,
    columns: list[str],
) -> str:
    seed = "|".join(
        [
            spec.version,
            generator_version,
            mapping_yaml_canonical(mapping),
            ",".join(columns),
        ]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def _dataset_instance_id(
    *,
    dataset_type: str,
    dataset_instance_name: str | None,
    schema_id: str,
    output_df: pd.DataFrame,
) -> str:
    """Generate DatasetInstanceId as UUID5 hash of key fields + content hash."""
    # Use JSON serialization for content hash to handle complex types (dicts, etc.)
    content_str = output_df.to_json(orient="records", date_format="iso")
    content_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()[:16]

    seed = "|".join(
        [
            dataset_type,
            dataset_instance_name or "default",
            schema_id,
            content_hash,
        ]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def extract_time_sectors(
    output_df: pd.DataFrame,
    dataset_complete: bool,
    sector_complete_map: dict[tuple[str, str], bool] | None = None,
) -> list[dict]:
    """Extract TimeSectors from ChargePeriodStart/ChargePeriodEnd columns."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    sectors: list[dict] = []

    if "ChargePeriodStart" not in output_df.columns or "ChargePeriodEnd" not in output_df.columns:
        return sectors

    # Get distinct (start, end) pairs
    pairs = output_df[["ChargePeriodStart", "ChargePeriodEnd"]].drop_duplicates()

    for _, row in pairs.iterrows():
        start = str(row["ChargePeriodStart"])
        end = str(row["ChargePeriodEnd"])

        if sector_complete_map:
            complete = sector_complete_map.get((start, end), dataset_complete)
        else:
            complete = dataset_complete

        sectors.append({
            "TimeSectorStart": start,
            "TimeSectorEnd": end,
            "TimeSectorComplete": complete,
            "TimeSectorLastUpdated": now,
        })

    return sectors


def _build_column_definitions(
    *,
    output_df: pd.DataFrame,
    spec: FocusSpec,
    provider_tag_prefixes: list[str],
) -> list[dict]:
    out: list[dict] = []
    spec_by_name = {c.name: c for c in spec.columns}

    for col in output_df.columns:
        meta: dict = {"ColumnName": col}
        if col in spec_by_name:
            spec_col = spec_by_name[col]
            meta["DataType"] = _spec_type_to_metadata(spec_col.data_type)
            if spec_col.numeric_precision is not None:
                meta["NumericPrecision"] = int(spec_col.numeric_precision)
            if spec_col.numeric_scale is not None:
                meta["NumberScale"] = int(spec_col.numeric_scale)
            if col == "Tags":
                meta["ProviderTagPrefixes"] = list(provider_tag_prefixes)
        else:
            meta["DataType"] = _infer_extension_type(output_df[col])
        out.append(meta)

    return out


def _spec_type_to_metadata(data_type: str) -> str:
    t = data_type.strip().lower()
    if t == "string":
        return "STRING"
    if t == "date/time":
        return "DATETIME"
    if t == "decimal":
        return "DECIMAL"
    if t == "json":
        return "JSON"
    if t == "integer":
        return "INTEGER"
    if t == "boolean":
        return "BOOLEAN"
    return "STRING"


def _infer_extension_type(series: pd.Series) -> str:
    from pandas.api.types import (
        is_bool_dtype,
        is_datetime64_any_dtype,
        is_float_dtype,
        is_integer_dtype,
    )

    if is_datetime64_any_dtype(series):
        return "DATETIME"
    if is_integer_dtype(series) or is_float_dtype(series):
        return "DECIMAL"
    if is_bool_dtype(series):
        return "BOOLEAN"
    if series.dtype == "object":
        sample = next((v for v in series if v is not None and v is not pd.NA), None)
        if isinstance(sample, dict):
            return "JSON"
    return "STRING"


def mapping_yaml_canonical(mapping: MappingConfig) -> str:
    # Stable-ish canonical form for hashing: deterministic json.
    data = {
        "spec_version": mapping.spec_version,
        "validation": {"default": mapping.validation_defaults},
        "rules": [
            {
                "target": r.target,
                "description": r.description,
                "steps": r.steps,
                "validation": r.validation,
            }
            for r in mapping.rules
        ],
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":"))
