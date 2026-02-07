import logging
import pytest
import pandas as pd
from focus_mapper.mapping.executor import generate_focus_dataframe
from focus_mapper.mapping.config import MappingConfig, MappingRule
from focus_mapper.spec import FocusSpec, FocusColumnSpec

def test_warning_on_unmapped_column(caplog):
    # Setup simple data and spec
    df = pd.DataFrame({"col1": [1, 2]})
    spec = FocusSpec(
        version="1.0",
        columns=[
            FocusColumnSpec(name="ValidColumn", feature_level="Mandatory", allows_nulls=True, data_type="string")
        ],
        source={},
        metadata={}
    )
    
    # Create mapping with one valid and one invalid column
    mapping = MappingConfig(
        spec_version="1.0",
        rules=[
            MappingRule(target="ValidColumn", steps=[{"op": "const", "value": "test"}]),
            MappingRule(target="InvalidColumn", steps=[{"op": "const", "value": "test"}]),
            MappingRule(target="x_Extension", steps=[{"op": "const", "value": "test"}])
        ],
        validation_defaults={}
    )

    # Capture logs
    with caplog.at_level(logging.WARNING):
        generate_focus_dataframe(df, mapping=mapping, spec=spec)

    # Allow for some flexibility in the exact log message, but ensure key parts are there
    assert "InvalidColumn" in caplog.text
    assert "Generic or 'x_' prefix" not in caplog.text # Should not warn about x_Extension
    assert "Validation" not in caplog.text # It's an execution warning, not validation (unless validation also warns)
    
    # Verify x_Extension did NOT trigger a warning
    # We loop through records to be precise
    invalid_warnings = [
        r.message for r in caplog.records 
        if "InvalidColumn" in r.message and "ignored" in r.message
    ]
    assert len(invalid_warnings) == 1
    
    extension_warnings = [r.message for r in caplog.records if "x_Extension" in r.message]
    assert len(extension_warnings) == 0
