"""
Library API entrypoints for focus-mapper.

This module provides programmatic access to the main functionality,
allowing focus-mapper to be used as a library in other projects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from . import __version__
from .io import read_table, write_table
from .mapping.config import load_mapping_config, MappingConfig
from .mapping.executor import generate_focus_dataframe
from .metadata import (
    build_sidecar_metadata,
    write_sidecar_metadata,
    extract_time_sectors,
    SidecarMetadata,
)
from .spec import load_focus_spec, FocusSpec
from .validate import (
    validate_focus_dataframe,
    write_validation_report,
    ValidationReport,
)


@dataclass
class GenerationResult:
    """Result of a FOCUS generation operation."""

    output_df: pd.DataFrame
    """The generated FOCUS-compliant DataFrame."""

    validation: ValidationReport
    """Validation report for the generated data."""

    metadata: SidecarMetadata
    """Sidecar metadata for the generated data."""

    is_valid: bool
    """True if validation passed without errors."""


@dataclass
class MappingValidationResult:
    """Result of mapping YAML validation."""

    is_valid: bool
    """True if the mapping configuration is valid."""

    errors: list[str]
    """List of error messages."""

    warnings: list[str]
    """List of warning messages."""

    mapping: MappingConfig | None
    """Parsed mapping config if valid, None otherwise."""


def generate(
    input_data: pd.DataFrame | Path | str,
    mapping: MappingConfig | Path | str,
    *,
    spec_version: str | None = None,
    spec_dir: Path | str | None = None,
    output_path: Path | str | None = None,
    write_output: bool = True,
    write_metadata: bool = True,
    write_validation: bool = True,
    generator_name: str = "focus-mapper",
    generator_version: str | None = None,
    time_sectors: list[dict] | None = None,
    dataset_instance_complete: bool | None = None,
    sector_complete_map: dict[tuple[str, str], bool] | None = None,
    provider_tag_prefixes: list[str] | None = None,
) -> GenerationResult:
    """
    Generate a FOCUS-compliant dataset from input data.

    This is the main library entrypoint for generating FOCUS data.

    Args:
        input_data: Input data as DataFrame or path to CSV/Parquet file.
        mapping: Mapping configuration as MappingConfig or path to YAML file.
        spec_version: FOCUS spec version (e.g., "v1.2", "v1.3").
                      If None, uses version from mapping config.
        spec_dir: Optional directory containing spec JSON files.
                  Overrides bundled specs. Falls back to FOCUS_SPEC_DIR env var.
        output_path: Path for output file. Required if write_output=True.
        write_output: Whether to write the output DataFrame to file.
        write_metadata: Whether to write sidecar metadata JSON.
        write_validation: Whether to write validation report JSON.
        generator_name: Name for DataGenerator in metadata.
        generator_version: Version for DataGenerator. Defaults to library version.
        time_sectors: Pre-computed time sectors for v1.3+ CostAndUsage.
                      If None and data has ChargePeriod columns, auto-extracted.
        dataset_instance_complete: For v1.3+ metadata. Defaults to True if not provided.
        sector_complete_map: Optional map of (start, end) -> complete bool, only used if time_sectors is None.
        provider_tag_prefixes: Tag prefixes for provider columns.

    Returns:
        GenerationResult with output DataFrame, validation report, and metadata.

    Example:
        >>> from focus_mapper.api import generate
        >>> result = generate(
        ...     input_data="data/telemetry.csv",
        ...     mapping="mappings/my_mapping.yaml",
        ...     output_path="output/focus.parquet",
        ... )
        >>> if result.is_valid:
        ...     print(f"Generated {len(result.output_df)} rows")
        ... else:
        ...     print(f"Validation errors: {result.validation.summary.errors}")
    """
    # Resolve generator info
    import os
    gen_name = generator_name
    if gen_name == "focus-mapper" or gen_name is None:
        gen_name = os.environ.get("FOCUS_DATA_GENERATOR_NAME", "focus-mapper")
    gen_ver = generator_version or os.environ.get("FOCUS_DATA_GENERATOR_VERSION", __version__)

    # Resolve mapping
    if isinstance(mapping, (str, Path)):
        mapping = load_mapping_config(Path(mapping))

    # Resolve spec version
    version = spec_version or mapping.spec_version
    spec = load_focus_spec(version, spec_dir=spec_dir)

    # Resolve input data
    if isinstance(input_data, (str, Path)):
        input_path = Path(input_data)
        input_df = read_table(input_path)
    else:
        input_df = input_data
        input_path = Path("<in-memory>")

    # Resolve output path
    if output_path is not None:
        output_path = Path(output_path)
    elif write_output:
        raise ValueError("output_path is required when write_output=True")
    else:
        output_path = Path("focus.parquet")  # placeholder for metadata

    # Generate FOCUS DataFrame
    output_df = generate_focus_dataframe(input_df, mapping=mapping, spec=spec)

    # Validate
    validation = validate_focus_dataframe(output_df, spec=spec, mapping=mapping)

    # Auto-extract time sectors for v1.3+ CostAndUsage if not provided
    ver = spec.version.lstrip("v")
    if ver >= "1.3" and mapping.dataset_type == "CostAndUsage":
        if time_sectors is None:
            complete = dataset_instance_complete if dataset_instance_complete is not None else True
            time_sectors = extract_time_sectors(
                output_df, 
                dataset_complete=complete,
                sector_complete_map=sector_complete_map
            )
        if dataset_instance_complete is None:
            dataset_instance_complete = True

    # Build metadata
    metadata = build_sidecar_metadata(
        spec=spec,
        mapping=mapping,
        generator_name=gen_name,
        generator_version=gen_ver,
        input_path=input_path,
        output_path=output_path,
        output_df=output_df,
        provider_tag_prefixes=provider_tag_prefixes,
        time_sectors=time_sectors,
        dataset_instance_complete=dataset_instance_complete,
    )

    # Write outputs if requested
    if write_output and output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_table(output_df, output_path, parquet_metadata=metadata.parquet_kv_metadata())

        if write_metadata:
            metadata_path = output_path.with_name(output_path.name + ".focus-metadata.json")
            write_sidecar_metadata(metadata, metadata_path)

        if write_validation:
            validation_path = output_path.with_name(output_path.name + ".validation.json")
            write_validation_report(validation, validation_path)

    return GenerationResult(
        output_df=output_df,
        validation=validation,
        metadata=metadata,
        is_valid=validation.summary.errors == 0,
    )


def validate(
    data: pd.DataFrame | Path | str,
    *,
    spec_version: str = "v1.3",
    spec_dir: Path | str | None = None,
    mapping: MappingConfig | Path | str | None = None,
    output_path: Path | str | None = None,
    write_report: bool = False,
) -> ValidationReport:
    """
    Validate a FOCUS dataset against the specification.

    This is the main library entrypoint for validating FOCUS data.

    Args:
        data: Data to validate as DataFrame or path to CSV/Parquet file.
        spec_version: FOCUS spec version to validate against.
        spec_dir: Optional directory containing spec JSON files.
        mapping: Optional mapping config for validation rule overrides.
        output_path: Path for validation report JSON. Required if write_report=True.
        write_report: Whether to write the validation report to file.

    Returns:
        ValidationReport with findings and summary.

    Example:
        >>> from focus_mapper.api import validate
        >>> report = validate("output/focus.parquet", spec_version="v1.3")
        >>> if report.summary.errors == 0:
        ...     print("Dataset is FOCUS compliant!")
        ... else:
        ...     for f in report.findings:
        ...         if f.severity == "ERROR":
        ...             print(f"Error in {f.column}: {f.message}")
    """
    # Load spec
    spec = load_focus_spec(spec_version, spec_dir=spec_dir)

    # Resolve mapping if provided
    if isinstance(mapping, (str, Path)):
        mapping = load_mapping_config(Path(mapping))

    # Resolve input data
    if isinstance(data, (str, Path)):
        df = read_table(Path(data))
    else:
        df = data

    # Validate
    report = validate_focus_dataframe(df, spec=spec, mapping=mapping)

    # Write report if requested
    if write_report:
        if output_path is None:
            raise ValueError("output_path is required when write_report=True")
        write_validation_report(report, Path(output_path))

    return report


def validate_mapping(
    mapping: MappingConfig | Path | str,
    *,
    spec_version: str | None = None,
    spec_dir: Path | str | None = None,
    check_column_targets: bool = True,
    check_op_syntax: bool = True,
) -> MappingValidationResult:
    """
    Validate a mapping configuration file.

    This function checks the mapping YAML for configuration errors
    before using it for generation.

    Args:
        mapping: Mapping config as MappingConfig or path to YAML file.
        spec_version: FOCUS spec version for column validation.
                      If None, uses version from mapping config.
        spec_dir: Optional directory containing spec JSON files.
        check_column_targets: Validate target columns exist in spec.
        check_op_syntax: Validate operation syntax and parameters.

    Returns:
        MappingValidationResult with errors, warnings, and parsed config.

    Example:
        >>> from focus_mapper.api import validate_mapping
        >>> result = validate_mapping("mappings/my_mapping.yaml")
        >>> if result.is_valid:
        ...     print("Mapping is valid!")
        ... else:
        ...     for error in result.errors:
        ...         print(f"Error: {error}")
    """
    errors: list[str] = []
    warnings: list[str] = []
    parsed_mapping: MappingConfig | None = None

    # Try to load the mapping
    try:
        if isinstance(mapping, (str, Path)):
            parsed_mapping = load_mapping_config(Path(mapping))
        else:
            parsed_mapping = mapping
    except Exception as e:
        errors.append(f"Failed to load mapping: {e}")
        return MappingValidationResult(
            is_valid=False, errors=errors, warnings=warnings, mapping=None
        )

    # Determine spec version
    version = spec_version or parsed_mapping.spec_version
    try:
        spec = load_focus_spec(version, spec_dir=spec_dir)
    except Exception as e:
        errors.append(f"Failed to load spec version '{version}': {e}")
        return MappingValidationResult(
            is_valid=False, errors=errors, warnings=warnings, mapping=parsed_mapping
        )

    # Check column targets
    if check_column_targets:
        spec_columns = {c.name for c in spec.columns}
        for rule in parsed_mapping.rules:
            target = rule.target
            # Extension columns are always allowed
            if target.startswith("x_"):
                continue
            if target not in spec_columns:
                errors.append(
                    f"Target column '{target}' is not defined in FOCUS spec {version}"
                )

    # Check op syntax
    if check_op_syntax:
        valid_ops = {
            "from_column",
            "const",
            "null",
            "coalesce",
            "map_values",
            "concat",
            "cast",
            "round",
            "math",
            "when",
            "pandas_expr",
            "sql",
        }
        for rule in parsed_mapping.rules:
            for i, step in enumerate(rule.steps):
                op = step.get("op")
                if op is None:
                    errors.append(
                        f"Column '{rule.target}' step {i+1}: missing 'op' key"
                    )
                    continue
                if op not in valid_ops:
                    errors.append(
                        f"Column '{rule.target}' step {i+1}: unknown op '{op}'"
                    )

                # Check required parameters for specific ops
                if op == "from_column" and "column" not in step:
                    errors.append(
                        f"Column '{rule.target}' step {i+1}: 'from_column' requires 'column'"
                    )
                if op == "cast" and "to" not in step:
                    errors.append(
                        f"Column '{rule.target}' step {i+1}: 'cast' requires 'to'"
                    )
                if op == "map_values":
                    if "column" not in step:
                        errors.append(
                            f"Column '{rule.target}' step {i+1}: 'map_values' requires 'column'"
                        )
                    if "mapping" not in step:
                        errors.append(
                            f"Column '{rule.target}' step {i+1}: 'map_values' requires 'mapping'"
                        )
                if op == "concat" and "columns" not in step:
                    errors.append(
                        f"Column '{rule.target}' step {i+1}: 'concat' requires 'columns'"
                    )
                if op == "coalesce" and "columns" not in step:
                    errors.append(
                        f"Column '{rule.target}' step {i+1}: 'coalesce' requires 'columns'"
                    )
                if op == "math":
                    if "operator" not in step:
                        errors.append(
                            f"Column '{rule.target}' step {i+1}: 'math' requires 'operator'"
                        )
                    if "operands" not in step:
                        errors.append(
                            f"Column '{rule.target}' step {i+1}: 'math' requires 'operands'"
                        )
                if op == "when" and "column" not in step:
                    errors.append(
                        f"Column '{rule.target}' step {i+1}: 'when' requires 'column'"
                    )
                if op == "pandas_expr" and "expr" not in step:
                    errors.append(
                        f"Column '{rule.target}' step {i+1}: 'pandas_expr' requires 'expr'"
                    )

    # Check v1.3+ specific fields
    ver = parsed_mapping.spec_version.lstrip("v")
    if ver >= "1.3":
        if not parsed_mapping.creation_date:
            warnings.append("v1.3+ mapping: 'creation_date' is recommended")
        if not parsed_mapping.dataset_instance_name:
            warnings.append("v1.3+ mapping: 'dataset_instance_name' is recommended")

    return MappingValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        mapping=parsed_mapping,
    )
