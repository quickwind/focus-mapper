"""Tests for v1.3 metadata functionality."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from focus_mapper.mapping.config import load_mapping_config, MappingConfig
from focus_mapper.metadata import (
    build_sidecar_metadata,
    extract_time_sectors,
    _dataset_instance_id,
)
from focus_mapper.spec import load_focus_spec


class TestMappingConfigV13:
    """Tests for MappingConfig with v1.3 fields."""

    def test_load_v1_3_mapping_with_new_fields(self) -> None:
        """Test loading v1.3 mapping with creation_date, dataset_type, dataset_instance_name."""
        mapping = load_mapping_config(Path("tests/fixtures/mapping_v1_3.yaml"))

        assert mapping.spec_version == "v1.3"
        assert mapping.creation_date == "2026-02-07T10:00:00Z"
        assert mapping.dataset_type == "CostAndUsage"
        assert mapping.dataset_instance_name == "Hourly Billing Report v1.3"

    def test_load_v1_2_mapping_with_creation_date(self) -> None:
        """Test loading v1.2 mapping with creation_date (defined in v1.2 spec)."""
        mapping = load_mapping_config(Path("tests/fixtures/mapping_v1_2.yaml"))

        assert mapping.spec_version == "v1.2"
        assert mapping.creation_date == "2026-02-07T09:00:00Z"
        assert mapping.dataset_type == "CostAndUsage"  # Default
        assert mapping.dataset_instance_name is None


class TestMetadataGenerationV13:
    """Tests for v1.3 metadata structure generation."""

    @pytest.fixture
    def v1_3_mapping(self) -> MappingConfig:
        return load_mapping_config(Path("tests/fixtures/mapping_v1_3.yaml"))

    @pytest.fixture
    def v1_3_spec(self):
        return load_focus_spec("v1.3")

    @pytest.fixture
    def sample_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "HostProviderName": ["TestProvider"],
            "BillingAccountId": ["ACC001"],
            "BillingCurrency": ["USD"],
            "BilledCost": [100.00],
            "ChargePeriodStart": ["2026-01-01T00:00:00Z"],
            "ChargePeriodEnd": ["2026-01-01T01:00:00Z"],
        })

    def test_v1_3_metadata_has_dataset_instance(
        self, v1_3_mapping, v1_3_spec, sample_df, tmp_path
    ) -> None:
        """Test v1.3 metadata contains DatasetInstance collection."""
        meta = build_sidecar_metadata(
            spec=v1_3_spec,
            mapping=v1_3_mapping,
            generator_name="test",
            generator_version="0.1.0",
            input_path=tmp_path / "in.csv",
            output_path=tmp_path / "out.csv",
            output_df=sample_df,
        )
        result = meta.to_dict()

        assert "DatasetInstance" in result
        assert isinstance(result["DatasetInstance"], list)
        assert len(result["DatasetInstance"]) == 1
        ds = result["DatasetInstance"][0]
        assert ds["DatasetInstanceName"] == "Hourly Billing Report v1.3"
        assert ds["FocusDatasetId"] == "CostAndUsage"
        assert "DatasetInstanceId" in ds

    def test_v1_3_metadata_has_recency(
        self, v1_3_mapping, v1_3_spec, sample_df, tmp_path
    ) -> None:
        """Test v1.3 metadata contains Recency collection."""
        meta = build_sidecar_metadata(
            spec=v1_3_spec,
            mapping=v1_3_mapping,
            generator_name="test",
            generator_version="0.1.0",
            input_path=tmp_path / "in.csv",
            output_path=tmp_path / "out.csv",
            output_df=sample_df,
        )
        result = meta.to_dict()

        assert "Recency" in result
        assert isinstance(result["Recency"], list)
        assert len(result["Recency"]) == 1
        rec = result["Recency"][0]
        assert "DatasetInstanceId" in rec
        assert "RecencyLastUpdated" in rec
        assert "DatasetInstanceLastUpdated" in rec

    def test_v1_3_metadata_has_schema_as_list(
        self, v1_3_mapping, v1_3_spec, sample_df, tmp_path
    ) -> None:
        """Test v1.3 metadata contains Schema as collection."""
        meta = build_sidecar_metadata(
            spec=v1_3_spec,
            mapping=v1_3_mapping,
            generator_name="test",
            generator_version="0.1.0",
            input_path=tmp_path / "in.csv",
            output_path=tmp_path / "out.csv",
            output_df=sample_df,
        )
        result = meta.to_dict()

        assert "Schema" in result
        assert isinstance(result["Schema"], list)
        assert len(result["Schema"]) == 1
        schema = result["Schema"][0]
        assert schema["FocusVersion"] == "1.3"
        assert "SchemaId" in schema
        assert "DatasetInstanceId" in schema
        assert "CreationDate" in schema
        assert schema["CreationDate"] == "2026-02-07T10:00:00Z"

    def test_v1_2_metadata_uses_object_structure(self, tmp_path) -> None:
        """Test v1.2 metadata uses object-based structure, not collections."""
        mapping = load_mapping_config(Path("tests/fixtures/mapping_v1_2.yaml"))
        spec = load_focus_spec("v1.2")
        df = pd.DataFrame({"BilledCost": [100.00], "BillingCurrency": ["USD"]})

        meta = build_sidecar_metadata(
            spec=spec,
            mapping=mapping,
            generator_name="test",
            generator_version="0.1.0",
            input_path=tmp_path / "in.csv",
            output_path=tmp_path / "out.csv",
            output_df=df,
        )
        result = meta.to_dict()

        # v1.2 should NOT have DatasetInstance or Recency
        assert "DatasetInstance" not in result
        assert "Recency" not in result
        # Schema should be object, not list
        assert "Schema" in result
        assert isinstance(result["Schema"], dict)


class TestTimeSectorExtraction:
    """Tests for TimeSector extraction from data."""

    def test_extract_time_sectors_from_df(self) -> None:
        """Test extracting distinct time sectors from ChargePeriodStart/End."""
        df = pd.DataFrame({
            "ChargePeriodStart": [
                "2026-01-01T00:00:00Z",
                "2026-01-01T01:00:00Z",
                "2026-01-01T00:00:00Z",  # Duplicate
            ],
            "ChargePeriodEnd": [
                "2026-01-01T01:00:00Z",
                "2026-01-01T02:00:00Z",
                "2026-01-01T01:00:00Z",  # Duplicate
            ],
        })

        sectors = extract_time_sectors(df, dataset_complete=True)

        assert len(sectors) == 2  # Deduplicated
        assert all(s["TimeSectorComplete"] is True for s in sectors)
        starts = {s["TimeSectorStart"] for s in sectors}
        assert "2026-01-01T00:00:00Z" in starts
        assert "2026-01-01T01:00:00Z" in starts

    def test_extract_time_sectors_with_incomplete_dataset(self) -> None:
        """Test time sectors inherit complete=False when dataset is incomplete."""
        df = pd.DataFrame({
            "ChargePeriodStart": ["2026-01-01T00:00:00Z"],
            "ChargePeriodEnd": ["2026-01-01T01:00:00Z"],
        })

        sectors = extract_time_sectors(df, dataset_complete=False)

        assert len(sectors) == 1
        assert sectors[0]["TimeSectorComplete"] is False

    def test_extract_time_sectors_with_sector_map(self) -> None:
        """Test time sectors use per-sector complete flags from map."""
        df = pd.DataFrame({
            "ChargePeriodStart": [
                "2026-01-01T00:00:00Z",
                "2026-01-01T01:00:00Z",
            ],
            "ChargePeriodEnd": [
                "2026-01-01T01:00:00Z",
                "2026-01-01T02:00:00Z",
            ],
        })

        sector_map = {
            ("2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"): True,
            ("2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"): False,
        }

        sectors = extract_time_sectors(
            df, dataset_complete=False, sector_complete_map=sector_map
        )

        assert len(sectors) == 2
        by_start = {s["TimeSectorStart"]: s for s in sectors}
        assert by_start["2026-01-01T00:00:00Z"]["TimeSectorComplete"] is True
        assert by_start["2026-01-01T01:00:00Z"]["TimeSectorComplete"] is False

    def test_extract_time_sectors_empty_without_columns(self) -> None:
        """Test returns empty list if ChargePeriod columns missing."""
        df = pd.DataFrame({"BilledCost": [100.00]})

        sectors = extract_time_sectors(df, dataset_complete=True)

        assert sectors == []


class TestDatasetInstanceId:
    """Tests for DatasetInstanceId UUID5 generation."""

    def test_dataset_instance_id_is_deterministic(self) -> None:
        """Test same inputs produce same UUID."""
        df = pd.DataFrame({"value": [1, 2, 3]})

        id1 = _dataset_instance_id(
            dataset_type="CostAndUsage",
            dataset_instance_name="Test",
            schema_id="abc123",
            output_df=df,
        )
        id2 = _dataset_instance_id(
            dataset_type="CostAndUsage",
            dataset_instance_name="Test",
            schema_id="abc123",
            output_df=df,
        )

        assert id1 == id2

    def test_dataset_instance_id_differs_with_content(self) -> None:
        """Test different data produces different UUID."""
        df1 = pd.DataFrame({"value": [1, 2, 3]})
        df2 = pd.DataFrame({"value": [4, 5, 6]})

        id1 = _dataset_instance_id(
            dataset_type="CostAndUsage",
            dataset_instance_name="Test",
            schema_id="abc123",
            output_df=df1,
        )
        id2 = _dataset_instance_id(
            dataset_type="CostAndUsage",
            dataset_instance_name="Test",
            schema_id="abc123",
            output_df=df2,
        )

        assert id1 != id2

    def test_dataset_instance_id_differs_with_name(self) -> None:
        """Test different instance name produces different UUID."""
        df = pd.DataFrame({"value": [1, 2, 3]})

        id1 = _dataset_instance_id(
            dataset_type="CostAndUsage",
            dataset_instance_name="Instance A",
            schema_id="abc123",
            output_df=df,
        )
        id2 = _dataset_instance_id(
            dataset_type="CostAndUsage",
            dataset_instance_name="Instance B",
            schema_id="abc123",
            output_df=df,
        )

        assert id1 != id2

    def test_dataset_instance_id_handles_none_name(self) -> None:
        """Test None instance name uses 'default' placeholder."""
        df = pd.DataFrame({"value": [1]})

        result = _dataset_instance_id(
            dataset_type="CostAndUsage",
            dataset_instance_name=None,
            schema_id="abc",
            output_df=df,
        )

        assert result  # Valid UUID string
        assert len(result) == 36  # UUID format
