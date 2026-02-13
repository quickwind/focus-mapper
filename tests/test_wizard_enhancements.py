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
        "n",            # 3. Global Validation Overrides? n (NEW)
        "X",            # 4. MandatoryCol const value (prompted inside const block)
        # "n",          # 5. MandatoryCol validation override? (SKIPPED due to global=n)
        "n"             # 5. Add extension? n
    ]
    
    # Menu choices calls:
    # 1. MandatoryCol (Init) -> "const"
    # 2. OptionalCol (Init) -> "skip"
    menu_choices = ["const", "skip"]
    menu_iter = iter(menu_choices)
    
    def menu_side_effect(prompt, header, options, default=None):
        try:
            val = next(menu_iter)
            return val
        except StopIteration:
            raise StopIteration("Menu choices exhausted")

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
        "n",            # 3. Global Validation Overrides? n (NEW)
        "A",            # 4. Man Val
        # "n",          # (Skipped Man Valid)
        "y",            # 5. Add extension?
        "test",         # 6. Suffix
        "desc",         # 7. Desc
        # "string",     # (Skipped Type - mock)
        "B",            # 8. Ext Val
        # "n",          # (Skipped Ext Valid)
        "n"             # 9. Add another extension?
    ]
    
    # Menu choices:
    # 1. Mandatory (Init) -> "const"
    # 2. Optional (Init) -> "skip"
    # 3. Extension (Type) -> "string"
    # 4. Extension (Init) -> "const"
    menu_choices = ["const", "skip", "string", "const"]
    menu_iter = iter(menu_choices)

    def menu_side_effect(prompt, header, options, default=None):
        try:
            return next(menu_iter)
        except StopIteration:
            raise StopIteration("Menu choices exhausted")

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
    # 1. Validation overrides? n (NEW)
    # 2. Add extension? n
    inputs = ["n", "n"]
    
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


def test_extension_autosave(mock_spec, sample_df):
    """Test that extension columns trigger save_callback immediately."""
    
    # Inputs:
    inputs = [
        "TestDS", "y", 
        "y", # Global valid? y
        "A", "n", 
        "y", "ext1", "desc1", 
        # "string",  <-- handled by prompt_menu mock
        "B", "n", 
        "n"
    ]
    
    # Menu choices:
    # 1. Mandatory (Init) -> "const"
    # 2. Optional (Init) -> "skip"
    # 3. Extension (Type) -> "string"
    # 4. Extension (Init) -> "const"
    menu_choices = ["const", "skip", "string", "const"]
    menu_iter = iter(menu_choices)
    def menu_side_effect(prompt, header, options, default=None):
        try:
            return next(menu_iter)
        except StopIteration:
            raise StopIteration("Menu choices exhausted")

    save_callback = MagicMock()
    
    with patch("focus_mapper.wizard.prompt_menu", side_effect=menu_side_effect):
        run_wizard(
            spec=mock_spec,
            input_df=sample_df,
            prompt=create_mock_prompt(inputs),
            include_optional=True,
            include_recommended=True,
            include_conditional=True,
            save_callback=save_callback
        )
    
    # Check save calls
    # Call 1: OptionalCol skipped
    # Call 2: MandatoryCol mapped
    # Call 3: Extension x_ext1 mapped
    assert save_callback.call_count >= 3
    
    # Get the last call arg
    last_config = save_callback.call_args[0][0]
    assert isinstance(last_config, MappingConfig)
    
    # Verify x_ext1 is in the rules of the saved config
    targets = [r.target for r in last_config.rules]
    assert "x_ext1" in targets


def test_wizard_extension_prevent_duplicates(mock_spec, sample_df):
    """Test that wizard prevents adding duplicate extension columns."""
    
    # Inputs:
    inputs = [
        "TestDS", "y", "n", 
        "A", 
        "y",             # Add ext 1
        "uniq", "desc1", 
        # "string", 
        "B", 
        "y",             # Add ext 2 (attempt duplicate)
        "uniq",          # DUPLICATE -> Wizard loops back
        "y",             # Retry Add ext
        "uniq2",         # Valid
        "desc2", 
        # "string", 
        "C", 
        "n"              # Finish
    ]
    
    # Menu choices:
    # 1. Mandatory (Init) -> "const"
    # 2. Optional (Init) -> "skip"
    # 3. Ext 1 (Type) -> "string"
    # 4. Ext 1 (Init) -> "const"
    # 5. Ext 2 (Type) -> "string"
    # 6. Ext 2 (Init) -> "const"
    menu_choices = [
        "const", "skip", 
        "string", "const", 
        "string", "const"
    ]
    menu_iter = iter(menu_choices)
    
    def menu_side_effect(prompt, header, options, default=None):
        try:
            return next(menu_iter)
        except StopIteration:
            raise StopIteration("Menu choices exhausted")

    with patch("focus_mapper.wizard.prompt_menu", side_effect=menu_side_effect):
        result = run_wizard(
            spec=mock_spec,
            input_df=sample_df,
            prompt=create_mock_prompt(inputs),
            include_optional=True,
            include_recommended=True,
            include_conditional=True,
        )
        
    ext_rules = [r for r in result.mapping.rules if r.target.startswith("x_")]
    targets = {r.target for r in ext_rules}
    assert "x_uniq" in targets
    assert "x_uniq2" in targets
    assert len(targets) == 2


def test_wizard_extension_suggestion(mock_spec, sample_df):
    """Test extension suggestion logic."""
    # input_df has "source_col".
    # We will add extension with suffix "source_col".
    # This should trigger suggestion logic.
    
    # Inputs:
    inputs = [
        "TestDS", "y", "n", 
        "A",             # Mandatory -> const "A"
        "y",             # Add ext
        "source_col",    # Suffix matching input
        "desc", 
        # "string",      # Type (menu)
        # "from_column", # Menu
        "y",             # Use suggested column?
        "n"              # Finish
    ]
    
    # Menu choices:
    # 1. Mandatory (Init) -> "const"
    # 2. Optional (Init) -> "skip"
    # 3. Extension (Type) -> "string"
    # 4. Extension (Init) -> "from_column"
    menu_choices = ["const", "skip", "string", "from_column"]
    menu_iter = iter(menu_choices)
    
    def menu_side_effect(prompt, header, options, default=None):
        try:
            return next(menu_iter)
        except StopIteration:
            raise StopIteration("Menu choices exhausted")

    with patch("focus_mapper.wizard.prompt_menu", side_effect=menu_side_effect):
        result = run_wizard(
            spec=mock_spec,
            input_df=sample_df,
            prompt=create_mock_prompt(inputs),
            include_optional=True,
            include_recommended=True,
            include_conditional=True,
            sample_df=sample_df # Must pass sample_df for inference
        )
        
    ext_rules = [r for r in result.mapping.rules if r.target == "x_source_col"]
    assert len(ext_rules) == 1
    # Verify it mapped from "source_col"
    assert ext_rules[0].steps[0]["op"] == "from_column"
    assert ext_rules[0].steps[0]["column"] == "source_col"
