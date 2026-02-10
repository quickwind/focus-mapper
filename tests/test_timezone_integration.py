"""
Integration test to verify timezone fix works end-to-end.
"""

import pandas as pd
import tempfile
import pytest
from pathlib import Path

from focus_mapper.api import generate
from focus_mapper.mapping.config import MappingConfig, MappingRule


def test_timezone_integration_end_to_end():
    """Test that timezone handling works end-to-end with actual CSV output."""
    
    # Create test input data with different timezone scenarios
    input_data = pd.DataFrame({
        'BillingPeriod': ['2024-01', '2024-02', '2024-03'],
        'RateAmount': [100.0, 200.0, 300.0],
        'BillingDate': ['2024-01-15', '2024-02-15', '2024-03-15'],
        'BillingHour': ['12', '15', '08']
    })
    
    # Create mapping config that generates datetime columns
    mapping_config = MappingConfig(
        spec_version="v1.3",
        dataset_type="CostAndUsage",
        creation_date="2024-01-01T00:00:00Z",
        validation_defaults={},  # Use empty defaults for simplicity
        rules=[
            # Test SQL expression with timezone handling using valid FOCUS column  
            MappingRule(
                target="ChargePeriodStart",
                steps=[
                    {
                        "op": "sql",
                        "expr": "TRY_CAST(BillingDate || 'T' || LPAD(CAST(BillingHour AS VARCHAR), 2, '0') || ':00:00' AS TIMESTAMP)"
                    },
                    {
                        "op": "cast", 
                        "to": "datetime"
                    }
                ],
                data_type="date/time"
            ),
            # Simple numeric column using valid FOCUS column
            MappingRule(
                target="Cost",
                steps=[
                    {
                        "op": "from_column",
                        "column": "RateAmount"
                    }
                ],
                data_type="decimal"
            )
        ]
    )
    
    # Create temporary output file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp:
        output_path = Path(tmp.name)
    
    try:
        # Generate FOCUS data
        result = generate(
            input_data=input_data,
            mapping=mapping_config,
            output_path=output_path,
            write_validation=False,
            write_metadata=False
        )
        
        # Read the generated CSV and verify timezone formatting
        with open(output_path, 'r') as f:
            csv_content = f.read()
        
        # Verify datetime columns are properly formatted with Z suffix
        lines = csv_content.strip().split('\n')
        header = lines[0]
        data_lines = lines[1:]
        
        # Find datetime column indices
        headers = header.strip('"').split('","')
        charge_period_start_idx = headers.index('ChargePeriodStart')
        
        # Check each data row
        for i, line in enumerate(data_lines):
            parts = line.split(',')
            charge_period_start = parts[charge_period_start_idx].strip('"')
            
            # Verify Z suffix format
            assert charge_period_start.endswith('Z'), f"ChargePeriodStart missing Z suffix: {charge_period_start}"
            
            # Verify ISO8601 format
            assert 'T' in charge_period_start, f"ChargePeriodStart not in ISO8601 format: {charge_period_start}"
        
        # Verify the DataFrame also has proper UTC timezone
        col = 'ChargePeriodStart'
        if col in result.output_df.columns:
            dt_col = result.output_df[col]
            if pd.api.types.is_datetime64_any_dtype(dt_col):
                assert str(dt_col.dt.tz) == 'UTC', f"{col} not in UTC timezone"
        
    finally:
        # Cleanup
        if output_path.exists():
            output_path.unlink()


def test_timezone_integration_with_mixed_timezones():
    """Test timezone handling with mixed timezone-aware timestamps."""
    
    # Create test input data that will generate mixed timezone scenarios
    input_data = pd.DataFrame({
        'BillingPeriod': ['2024-01', '2024-02'],
        'RateAmount': [100.0, 200.0]
    })
    
    # Create mapping with timezone-aware SQL expressions
    mapping_config = MappingConfig(
        spec_version="v1.3",
        dataset_type="CostAndUsage",
        creation_date="2024-01-01T00:00:00Z",
        validation_defaults={},
        rules=[
            MappingRule(
                target="ChargePeriodStart",
                steps=[
                    {
                        "op": "sql",
                        "expr": "TRY_CAST(BillingPeriod || '-01T00:00:00+05:30' AS TIMESTAMPTZ)"  # IST timezone
                    },
                    {
                        "op": "cast", 
                        "to": "datetime"
                    }
                ],
                data_type="date/time"
            )
        ]
    )
    
    # Create temporary output file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp:
        output_path = Path(tmp.name)
    
    try:
        # Generate FOCUS data
        result = generate(
            input_data=input_data,
            mapping=mapping_config,
            output_path=output_path,
            write_validation=False,
            write_metadata=False
        )
        
        # Read the generated CSV and verify timezone conversion
        with open(output_path, 'r') as f:
            csv_content = f.read()
        
        lines = csv_content.strip().split('\n')
        data_lines = lines[1:]
        
        # Check that IST times are converted to UTC
        # 2024-01-01T00:00:00+05:30 should become 2023-12-31T18:30:00Z
        expected_utc_times = ['2023-12-31T18:30:00Z', '2024-01-31T18:30:00Z']
        
        for i, line in enumerate(data_lines):
            parts = line.split(',')
            charge_period_start = parts[0].strip('"')
            
            assert charge_period_start == expected_utc_times[i], f"Expected {expected_utc_times[i]}, got {charge_period_start}"
        
        # Verify DataFrame timezone
        dt_col = result.output_df['ChargePeriodStart']
        assert str(dt_col.dt.tz) == 'UTC', "DataFrame column not in UTC timezone"
        
    finally:
        # Cleanup
        if output_path.exists():
            output_path.unlink()
