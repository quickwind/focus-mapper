"""Tests for the focus_mapper library API."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from focus_mapper import (
    generate,
    validate,
    validate_mapping,
    GenerationResult,
    MappingValidationResult,
    ValidationReport,
)


class TestGenerateAPI:
    """Tests for the generate() API function."""

    def test_generate_from_paths(self, tmp_path: Path) -> None:
        """Test generate with file paths for input and mapping."""
        result = generate(
            input_data="tests/fixtures/telemetry_small.csv",
            mapping="tests/fixtures/mapping_v1_2.yaml",
            output_path=tmp_path / "focus.csv",
            write_output=True,
        )

        assert isinstance(result, GenerationResult)
        assert isinstance(result.output_df, pd.DataFrame)
        assert len(result.output_df) > 0
        assert "BilledCost" in result.output_df.columns
        assert (tmp_path / "focus.csv").exists()
        assert (tmp_path / "focus.csv.focus-metadata.json").exists()
        assert (tmp_path / "focus.csv.validation.json").exists()

    def test_generate_from_dataframe(self, tmp_path: Path) -> None:
        """Test generate with DataFrame input."""
        input_df = pd.read_csv("tests/fixtures/telemetry_small.csv")

        result = generate(
            input_data=input_df,
            mapping="tests/fixtures/mapping_v1_2.yaml",
            output_path=tmp_path / "focus.parquet",
        )

        assert isinstance(result, GenerationResult)
        assert len(result.output_df) == len(input_df)

    def test_generate_without_write(self) -> None:
        """Test generate with write_output=False."""
        result = generate(
            input_data="tests/fixtures/telemetry_small.csv",
            mapping="tests/fixtures/mapping_v1_2.yaml",
            write_output=False,
        )

        assert isinstance(result, GenerationResult)
        assert result.validation is not None

    def test_generate_v1_3(self, tmp_path: Path) -> None:
        """Test generate with v1.3 spec."""
        result = generate(
            input_data="tests/fixtures/telemetry_small.csv",
            mapping="tests/fixtures/mapping_v1_3.yaml",
            output_path=tmp_path / "focus_v1_3.csv",
            spec_version="v1.3",
            dataset_instance_complete=True,
        )

        assert isinstance(result, GenerationResult)
        assert "HostProviderName" in result.output_df.columns

    def test_generate_custom_generator_info(self, tmp_path: Path) -> None:
        """Test generate with custom generator name and version."""
        result = generate(
            input_data="tests/fixtures/telemetry_small.csv",
            mapping="tests/fixtures/mapping_v1_2.yaml",
            output_path=tmp_path / "focus.csv",
            generator_name="my-custom-tool",
            generator_version="2.0.0",
        )

        assert result.metadata.generator_name == "my-custom-tool"
        assert result.metadata.generator_version == "2.0.0"


class TestValidateAPI:
    """Tests for the validate() API function."""

    def test_validate_from_path(self, tmp_path: Path) -> None:
        """Test validate with file path input."""
        # First generate a file
        gen_result = generate(
            input_data="tests/fixtures/telemetry_small.csv",
            mapping="tests/fixtures/mapping_v1_2.yaml",
            output_path=tmp_path / "focus.csv",
        )

        # Then validate it
        report = validate(
            data=tmp_path / "focus.csv",
            spec_version="v1.2",
        )

        assert isinstance(report, ValidationReport)
        assert report.summary is not None

    def test_validate_from_dataframe(self) -> None:
        """Test validate with DataFrame input."""
        df = pd.DataFrame({
            "BilledCost": [100.00, 200.00],
            "BillingCurrency": ["USD", "USD"],
        })

        report = validate(data=df, spec_version="v1.2")

        assert isinstance(report, ValidationReport)
        # Should have findings for missing columns
        assert len(report.findings) > 0

    def test_validate_with_mapping(self) -> None:
        """Test validate with mapping for validation overrides."""
        df = pd.DataFrame({
            "BilledCost": [100.00],
            "BillingCurrency": ["USD"],
        })

        report = validate(
            data=df,
            spec_version="v1.2",
            mapping="tests/fixtures/mapping_v1_2.yaml",
        )

        assert isinstance(report, ValidationReport)

    def test_validate_write_report(self, tmp_path: Path) -> None:
        """Test validate with write_report=True."""
        df = pd.DataFrame({
            "BilledCost": [100.00],
            "BillingCurrency": ["USD"],
        })
        report_path = tmp_path / "validation.json"

        report = validate(
            data=df,
            spec_version="v1.2",
            output_path=report_path,
            write_report=True,
        )

        assert report_path.exists()


class TestValidateMappingAPI:
    """Tests for the validate_mapping() API function."""

    def test_validate_valid_mapping(self) -> None:
        """Test validate_mapping with a valid mapping file."""
        result = validate_mapping("tests/fixtures/mapping_v1_2.yaml")

        assert isinstance(result, MappingValidationResult)
        assert result.is_valid
        assert len(result.errors) == 0
        assert result.mapping is not None

    def test_validate_v1_3_mapping(self) -> None:
        """Test validate_mapping with v1.3 mapping."""
        result = validate_mapping("tests/fixtures/mapping_v1_3.yaml")

        assert result.is_valid
        assert result.mapping is not None
        assert result.mapping.spec_version == "v1.3"

    def test_validate_mapping_invalid_spec(self) -> None:
        """Test validate_mapping with invalid spec version."""
        from focus_mapper import load_mapping_config

        mapping = load_mapping_config(Path("tests/fixtures/mapping_v1_2.yaml"))
        # Modify to invalid version
        import dataclasses
        invalid_mapping = dataclasses.replace(mapping, spec_version="v9.9")

        result = validate_mapping(invalid_mapping)

        assert not result.is_valid
        assert any("spec version" in e.lower() for e in result.errors)

    def test_validate_mapping_checks_ops(self) -> None:
        """Test validate_mapping checks operation syntax."""
        from focus_mapper.mapping.config import MappingConfig, MappingRule

        # Create mapping with invalid op
        bad_mapping = MappingConfig(
            spec_version="v1.2",
            rules=[
                MappingRule(
                    target="BilledCost",
                    steps=[{"op": "invalid_op"}],
                ),
            ],
            validation_defaults={},
        )

        result = validate_mapping(bad_mapping)

        assert not result.is_valid
        assert any("unknown op" in e.lower() for e in result.errors)

    def test_validate_mapping_checks_required_params(self) -> None:
        """Test validate_mapping checks required op parameters."""
        from focus_mapper.mapping.config import MappingConfig, MappingRule

        # Create mapping with missing required param
        bad_mapping = MappingConfig(
            spec_version="v1.2",
            rules=[
                MappingRule(
                    target="BilledCost",
                    steps=[{"op": "from_column"}],  # missing 'column'
                ),
            ],
            validation_defaults={},
        )

        result = validate_mapping(bad_mapping)

        assert not result.is_valid
        assert any("requires 'column'" in e for e in result.errors)

    def test_validate_mapping_invalid_target(self) -> None:
        """Test validate_mapping detects invalid target columns."""
        from focus_mapper.mapping.config import MappingConfig, MappingRule

        bad_mapping = MappingConfig(
            spec_version="v1.2",
            rules=[
                MappingRule(
                    target="NotARealColumn",
                    steps=[{"op": "const", "value": "test"}],
                ),
            ],
            validation_defaults={},
        )

        result = validate_mapping(bad_mapping)

        assert not result.is_valid
        assert any("NotARealColumn" in e for e in result.errors)

    def test_validate_mapping_extension_columns_allowed(self) -> None:
        """Test validate_mapping allows extension columns."""
        from focus_mapper.mapping.config import MappingConfig, MappingRule

        mapping = MappingConfig(
            spec_version="v1.2",
            rules=[
                MappingRule(
                    target="x_CustomColumn",  # Extension column
                    steps=[{"op": "const", "value": "test"}],
                ),
            ],
            validation_defaults={},
        )

        result = validate_mapping(mapping)

        # Extension columns should not cause errors
        assert not any("x_CustomColumn" in e for e in result.errors)

    def test_validate_mapping_nonexistent_file(self) -> None:
        """Test validate_mapping with non-existent file."""
        result = validate_mapping("/nonexistent/path/mapping.yaml")

        assert not result.is_valid
        assert any("failed to load" in e.lower() for e in result.errors)
