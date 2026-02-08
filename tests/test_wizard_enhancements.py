from unittest.mock import MagicMock, patch, ANY
import pytest
import pandas as pd
from focus_mapper.wizard import run_wizard
from focus_mapper.mapping.config import MappingConfig, MappingRule

@pytest.fixture
def mock_spec():
    from focus_mapper.spec import FocusSpec, FocusColumnSpec
    return FocusSpec(
        version="1.3",
        source={"version": "1.3"},
        columns=[
            FocusColumnSpec(
                name="MandatoryCol",
                feature_level="Mandatory",
                allows_nulls=False,
                data_type="string",
            ),
            FocusColumnSpec(
                name="OptionalCol",
                feature_level="Optional",
                allows_nulls=True,
                data_type="string",
            ),
        ],
    )

@pytest.fixture
def sample_df():
    return pd.DataFrame({"source_col": ["a", "b", "c"]})

def create_mock_prompt(inputs):
    """Creates a mock prompt function that yields from inputs."""
    iterator = iter(inputs)
    def prompt(text):
        try:
            val = next(iterator)
            return val
        except StopIteration:
            return ""
    return prompt

def test_wizard_records_skipped_columns(mock_spec, sample_df):
    """Test that skipped columns are recorded in the result mapping."""
    
    # Inputs list for `prompt` calls:
    inputs = [
        "TestDataset",  # 1. Dataset Instance Name
        "y",            # 2. Validation defaults? Y
        "X",            # 3. MandatoryCol const value (prompted inside const block)
        "n",            # 4. MandatoryCol validation override? n
        "n"             # 5. Add extension? n
    ]
    
    # Menu choices calls:
    # 1. MandatoryCol (Init) -> "const"
    # 2. MandatoryCol (Add Step) -> "done"
    # 3. OptionalCol (Init) -> "skip"
    menu_choices = ["const", "done", "skip"]
    menu_iter = iter(menu_choices)
    
    def menu_side_effect(prompt, header, options, default=None):
        try:
            val = next(menu_iter)
            return val
        except StopIteration:
            return default

    with patch("focus_mapper.wizard.prompt_menu", side_effect=menu_side_effect):
        result = run_wizard(
            spec=mock_spec,
            input_df=sample_df,
            prompt=create_mock_prompt(inputs),
            include_optional=True,
            include_recommended=True,
            include_conditional=True,
        )

    # Verification
    assert "OptionalCol" in result.mapping.skipped_columns
    assert "MandatoryCol" not in result.mapping.skipped_columns
    assert len(result.mapping.rules) == 1
    assert result.mapping.rules[0].target == "MandatoryCol"


def test_wizard_extension_enhancements(mock_spec, sample_df):
    """Test validation of extension auto-prefix and full ops."""
    
    # Inputs:
    inputs = [
        "TestDS",       # 1. Dataset
        "y",            # 2. Defaults
        "A",            # 3. Man Val
        "n",            # 4. Man Valid
        "y",            # 5. Add extension?
        "test",         # 6. Suffix
        "desc",         # 7. Desc
        "string",       # 8. Type
        "B",            # 9. Ext Val
        "n",            # 10. Ext Valid
        "n"             # 11. Add another extension?
    ]
    
    # Menu choices:
    # 1. Mandatory (Init) -> "const"
    # 2. Mandatory (Add Step) -> "done"
    # 3. Optional (Init) -> "skip"
    # 4. Extension (Init) -> "const"
    # 5. Extension (Add Step) -> "done"
    menu_choices = ["const", "done", "skip", "const", "done"]
    menu_iter = iter(menu_choices)

    def menu_side_effect(prompt, header, options, default=None):
        try:
            return next(menu_iter)
        except StopIteration:
            return default

    with patch("focus_mapper.wizard.prompt_menu", side_effect=menu_side_effect):
        result = run_wizard(
            spec=mock_spec,
            input_df=sample_df,
            prompt=create_mock_prompt(inputs),
            include_optional=True,
            include_recommended=True,
            include_conditional=True,
        )

    # Verification
    assert "OptionalCol" in result.mapping.skipped_columns
    
    ext_rules = [r for r in result.mapping.rules if r.target == "x_test"]
    assert len(ext_rules) == 1
    rule = ext_rules[0]
    assert rule.description == "desc"
    # Verify it used the "const" op (full op support)
    assert rule.steps[0]["op"] == "const"
    assert rule.steps[0]["value"] == "B"


def test_resume_skips_columns(mock_spec, sample_df):
    """Test that resuming skips columns present in skipped_columns."""
    
    # Setup resume config
    # MandatoryCol is mapped.
    # OptionalCol is skipped.
    resume_config = MappingConfig(
        spec_version="v1.3",
        rules=[
            MappingRule(target="MandatoryCol", steps=[{"op": "const", "value": "A"}])
        ],
        validation_defaults={},
        skipped_columns=["OptionalCol"],
        creation_date="2023-01-01T00:00:00Z",
        dataset_type="CostAndUsage",
        dataset_instance_name="ResumedDS"
    )

    # Inputs:
    # 1. Add extension? n
    inputs = ["n"]
    
    with patch("focus_mapper.wizard.prompt_menu") as mock_menu:
        # Should not be called
        mock_menu.side_effect = Exception("prompt_menu should not be called")
        
        result = run_wizard(
            spec=mock_spec,
            input_df=sample_df,
            prompt=create_mock_prompt(inputs),
            include_optional=True,
            include_recommended=True,
            include_conditional=True,
            resume_config=resume_config,
        )
    
    # Verify mapping remains consistent
    assert len(result.mapping.rules) == 1
    assert result.mapping.rules[0].target == "MandatoryCol"
    # Skipped columns should be preserved
    assert "OptionalCol" in result.mapping.skipped_columns
