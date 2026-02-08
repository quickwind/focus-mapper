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
    # 2. Mandatory (Add Step) -> "done"
    # 3. Optional (Init) -> "skip"
    # 4. Extension (Type) -> "string"  <-- NEW
    # 5. Extension (Init) -> "const"
    # 6. Extension (Add Step) -> "done"
    menu_choices = ["const", "done", "skip", "string", "const", "done"]
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
    # 1. Dataset
    # 2. Defaults
    # 3. Mand -> const
    # 4. Mand Valid
    # 5. Add ext? y
    # 6. suffix
    # 7. desc
    # 8. type
    # 9. const
    # 10. valid
    # 11. Add ext? n
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
    # 2. Mandatory (Add Step) -> "done"
    # 3. Optional (Init) -> "skip"
    # 4. Extension (Type) -> "string"  <-- NEW
    # 5. Extension (Init) -> "const"
    # 6. Extension (Add Step) -> "done"
    menu_choices = ["const", "done", "skip", "string", "const", "done"]
    menu_iter = iter(menu_choices)
    def menu_side_effect(prompt, header, options, default=None):
        try:
            return next(menu_iter)
        except StopIteration:
            return default

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
    # 1. Dataset
    # 2. Defaults
    # 3. Global Valid? n
    # 4. Mand -> const
    # 5. Add ext? y
    # 6. suffix: "uniq"
    # 7. desc
    # 8. type: string (via menu)
    # 9. const
    # 10. Add ext? y
    # 11. suffix: "uniq" (DUPLICATE - should reject and loop)
    # 12. suffix: "uniq2" (valid)
    # 13. desc
    # 14. type: string
    # 15. const
    # 16. Add ext? n
    
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
    # 2. Mandatory (Add Step) -> "done"
    # 3. Optional (Init) -> "skip"
    # 4. Ext 1 (Type) -> "string"
    # 5. Ext 1 (Init) -> "const"
    # 6. Ext 1 (Add Step) -> "done"
    # 7. Ext 2 (Type) -> "string"
    # 8. Ext 2 (Init) -> "const"
    # 9. Ext 2 (Add Step) -> "done"
    menu_choices = [
        "const", "done", "skip", 
        "string", "const", "done", 
        "string", "const", "done"
    ]
    menu_iter = iter(menu_choices)
    
    def menu_side_effect(prompt, header, options, default=None):
        try:
            return next(menu_iter)
        except StopIteration:
            return default

    # Mock prompt_bool to return True for "Add ext?" and False for others/end
    # Inputs list for prompt_bool:
    # 1. Global Valid? -> False (handled by inputs list usually? No prompt_bool handles its own)
    # Wait, prompt_bool uses `prompt` fixture if not mocked separately.
    # In my tests usually `prompt` function handles string inputs.
    # But `prompt_bool` calls `prompt`. 
    # Let's verify `run_wizard` usage. 
    # `ask_validation_overrides` uses prompt_bool.
    # `add` (extension) uses prompt_bool (changed by user).
    
    # If `prompt_bool` uses `prompt` (the fixture), then my inputs list should contain "y" or "n".
    # User changed `add = prompt_bool(...)`.
    # `prompt_bool` implementation calls `prompt(...)`.
    
    # So my inputs list MUST contain "y"/"n" strings for boolean prompts.
    
    # Inputs re-verified:
    # prompt("Dataset") -> "TestDS"
    # prompt_bool("Defaults") -> "y" (via prompt)
    # prompt_bool("Global Valid") -> "n"
    # prompt("Mandatory") -> "A" (via const loop logic)
    # prompt_bool("Add ext?") -> "y"
    # prompt("Suffix") -> "uniq"
    # prompt("Desc") -> "desc1"
    # prompt_menu("Type") -> (handled by side_effect)
    # prompt("Const") -> "B"
    # prompt_bool("Add ext?") -> "y"
    # prompt("Suffix") -> "uniq" (Duplicate test)
    # prompt("Suffix") -> "uniq2"
    # prompt("Desc") -> "desc2"
    # prompt_menu("Type") -> (handled by side_effect)
    # prompt("Const") -> "C"
    # prompt_bool("Add ext?") -> "n"
    
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
