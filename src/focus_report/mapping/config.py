from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..errors import MappingConfigError


@dataclass(frozen=True)
class MappingRule:
    target: str
    steps: list[dict[str, Any]]
    description: str | None = None
    validation: dict[str, Any] | None = None


@dataclass(frozen=True)
class MappingConfig:
    spec_version: str
    rules: list[MappingRule]
    validation_defaults: dict[str, Any]

    def rule_for_target(self, target: str) -> MappingRule | None:
        for r in self.rules:
            if r.target == target:
                return r
        return None

    @property
    def extension_targets(self) -> list[str]:
        return [r.target for r in self.rules if r.target.startswith("x_")]


def load_mapping_config(path: Path) -> MappingConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise MappingConfigError(f"Failed to read mapping YAML: {path}") from e

    if not isinstance(raw, dict):
        raise MappingConfigError("Mapping YAML must be a mapping at top level")

    spec_version = raw.get("spec_version")
    if not isinstance(spec_version, str) or not spec_version:
        raise MappingConfigError("mapping.spec_version must be a non-empty string")

    validation_raw = raw.get("validation")
    if validation_raw is None:
        validation_raw = {}
    if not isinstance(validation_raw, dict):
        raise MappingConfigError("mapping.validation must be a mapping if provided")
    default_validation = validation_raw.get("default", {})
    if default_validation is None:
        default_validation = {}
    if not isinstance(default_validation, dict):
        raise MappingConfigError("mapping.validation.default must be a mapping if provided")

    mappings = raw.get("mappings")
    if not isinstance(mappings, dict) or not mappings:
        raise MappingConfigError("mapping.mappings must be a non-empty mapping")

    rules: list[MappingRule] = []
    for target, body in mappings.items():
        if not isinstance(target, str) or not target:
            raise MappingConfigError("mapping.mappings keys must be non-empty strings")
        if not isinstance(body, dict):
            raise MappingConfigError(f"mapping.mappings[{target}] must be a mapping")

        steps = body.get("steps")
        if not isinstance(steps, list) or not steps:
            raise MappingConfigError(
                f"mapping.mappings[{target}].steps must be a non-empty list"
            )
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or "op" not in step:
                raise MappingConfigError(
                    f"mapping.mappings[{target}].steps[{i}] must include 'op'"
                )

        validation = body.get("validation")
        if validation is not None and not isinstance(validation, dict):
            raise MappingConfigError(
                f"mapping.mappings[{target}].validation must be a mapping if provided"
            )

        rules.append(
            MappingRule(
                target=target,
                steps=steps,
                description=body.get("description"),
                validation=validation,
            )
        )

    return MappingConfig(
        spec_version=spec_version,
        rules=rules,
        validation_defaults=default_validation,
    )
