from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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

    def to_dict(self) -> dict:
        return {
            "DataGenerator": {"DataGenerator": self.generator_name},
            "Schema": {
                "SchemaId": self.schema_id,
                "FocusVersion": self.spec_version,
                "CreationDate": self.generated_at,
                "DataGeneratorVersion": self.generator_version,
                "ColumnDefinition": self.column_definitions,
            },
        }

    def parquet_kv_metadata(self) -> dict[bytes, bytes]:
        # Keep values short; Parquet metadata is key/value bytes.
        return {
            b"SchemaId": self.schema_id.encode("utf-8"),
            b"FocusVersion": self.spec_version.encode("utf-8"),
            b"CreationDate": self.generated_at.encode("utf-8"),
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
) -> SidecarMetadata:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    schema_id = _schema_id(
        spec=spec,
        mapping=mapping,
        generator_version=generator_version,
        columns=list(output_df.columns),
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
    )


def write_sidecar_metadata(meta: SidecarMetadata, path: Path) -> None:
    path.write_text(
        json.dumps(meta.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
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
        return "STRING"
    if series.dtype == "object":
        sample = next((v for v in series if v is not None and v is not pd.NA), None)
        if isinstance(sample, dict):
            return "JSON"
    return "STRING"


def mapping_yaml_canonical(mapping: MappingConfig) -> str:
    # Stable-ish canonical form for hashing: deterministic json.
    data = {
        "spec_version": mapping.spec_version,
        "rules": [
            {"target": r.target, "description": r.description, "steps": r.steps}
            for r in mapping.rules
        ],
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":"))
