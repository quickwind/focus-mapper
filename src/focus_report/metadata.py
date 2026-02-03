from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .mapping.config import MappingConfig
from .spec import FocusSpec
from .validate import ValidationReport


@dataclass(frozen=True)
class SidecarMetadata:
    spec_version: str
    generated_at: str
    generator_name: str
    generator_version: str
    mapping_hash: str
    spec_source: dict | None
    mapping_targets: list[str]
    standard_columns: list[str]
    extension_columns: list[str]
    extension_definitions: dict[str, dict]
    validation_summary: dict[str, int]
    input_path: str
    output_path: str

    def to_dict(self) -> dict:
        return {
            "focus": {
                "spec_version": self.spec_version,
                "spec_source": self.spec_source,
            },
            "generated_at": self.generated_at,
            "data_generator": {
                "name": self.generator_name,
                "version": self.generator_version,
            },
            "mapping": {"sha256": self.mapping_hash},
            "mapping_targets": self.mapping_targets,
            "columns": {
                "standard": self.standard_columns,
                "extensions": self.extension_columns,
                "extension_definitions": self.extension_definitions,
            },
            "validation": {"summary": self.validation_summary},
            "io": {"input": self.input_path, "output": self.output_path},
        }

    def parquet_kv_metadata(self) -> dict[bytes, bytes]:
        # Keep values short; Parquet metadata is key/value bytes.
        spec_ref = None
        if isinstance(self.spec_source, dict):
            repo = self.spec_source.get("repo")
            ref = self.spec_source.get("ref")
            path = self.spec_source.get("path")
            if isinstance(repo, str) and isinstance(ref, str):
                spec_ref = f"{repo}@{ref}" + (
                    f":{path}" if isinstance(path, str) else ""
                )

        return {
            b"focus.spec_version": self.spec_version.encode("utf-8"),
            b"focus.generated_at": self.generated_at.encode("utf-8"),
            b"focus.data_generator": self.generator_name.encode("utf-8"),
            b"focus.data_generator_version": self.generator_version.encode("utf-8"),
            b"focus.mapping_sha256": self.mapping_hash.encode("utf-8"),
            **({b"focus.spec_ref": spec_ref.encode("utf-8")} if spec_ref else {}),
        }


def build_sidecar_metadata(
    *,
    spec: FocusSpec,
    mapping: MappingConfig,
    generator_name: str,
    generator_version: str,
    validation: ValidationReport,
    input_path: Path,
    output_path: Path,
) -> SidecarMetadata:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    mapping_hash = _sha256_text(mapping_yaml_canonical(mapping))

    extension_definitions: dict[str, dict] = {}
    for rule in mapping.rules:
        if rule.target.startswith("x_") and rule.description:
            extension_definitions[rule.target] = {"description": rule.description}

    return SidecarMetadata(
        spec_version=spec.version,
        generated_at=now,
        generator_name=generator_name,
        generator_version=generator_version,
        mapping_hash=mapping_hash,
        spec_source=spec.source,
        mapping_targets=[r.target for r in mapping.rules],
        standard_columns=spec.column_names,
        extension_columns=mapping.extension_targets,
        extension_definitions=extension_definitions,
        validation_summary={
            "errors": validation.summary.errors,
            "warnings": validation.summary.warnings,
        },
        input_path=str(input_path),
        output_path=str(output_path),
    )


def write_sidecar_metadata(meta: SidecarMetadata, path: Path) -> None:
    path.write_text(
        json.dumps(meta.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
