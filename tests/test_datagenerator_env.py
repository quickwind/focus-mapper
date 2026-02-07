"""Tests for DataGenerator customization via environment variables."""

import os
from pathlib import Path
from unittest import mock

from focus_mapper import generate


def test_generate_uses_env_vars_for_datagenerator(tmp_path: Path) -> None:
    """Test that generate() uses environment variables for DataGenerator info."""
    
    # Mock environment variables
    with mock.patch.dict(os.environ, {
        "FOCUS_DATA_GENERATOR_NAME": "test-generator-env",
        "FOCUS_DATA_GENERATOR_VERSION": "9.9.9-env"
    }):
        result = generate(
            input_data="tests/fixtures/telemetry_small.csv",
            mapping="tests/fixtures/mapping_v1_3.yaml",
            output_path=tmp_path / "focus_env.csv",
            spec_version="v1.3",
            dataset_instance_complete=True,
        )
        
        assert result.metadata.generator_name == "test-generator-env"
        # The schema might use the generator version
        assert result.metadata.generator_version == "9.9.9-env"


def test_generate_args_override_env_vars(tmp_path: Path) -> None:
    """Test that explicit arguments override environment variables."""
    
    with mock.patch.dict(os.environ, {
        "FOCUS_DATA_GENERATOR_NAME": "test-generator-env",
        "FOCUS_DATA_GENERATOR_VERSION": "9.9.9-env"
    }):
        result = generate(
            input_data="tests/fixtures/telemetry_small.csv",
            mapping="tests/fixtures/mapping_v1_3.yaml",
            output_path=tmp_path / "focus_override.csv",
            spec_version="v1.3",
            dataset_instance_complete=True,
            generator_name="explicit-name",
            generator_version="1.0.0-explicit",
        )
        
        assert result.metadata.generator_name == "explicit-name"
        assert result.metadata.generator_version == "1.0.0-explicit"


def test_generate_defaults_fallback(tmp_path: Path) -> None:
    """Test that defaults are used when no env vars or args are provided."""
    
    # Ensure no env vars set (though they shouldn't be by default in test env, better safe)
    with mock.patch.dict(os.environ, {}, clear=True):
        # Restore PATH/PYTHONPATH if needed by other things, but here we just need to clear FOCUS_ vars
        # Actually mock.patch.dict with clear=True clears everything. 
        # Safer to just unset specific vars if they exist
        pass
        
    # We can just rely on the fact that these vars are likely not set in the test environment
    # But to be robust, we can map over os.environ excluding our target vars
    
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("FOCUS_DATA_GENERATOR_")}
    
    with mock.patch.dict(os.environ, clean_env, clear=True):
        from focus_mapper import __version__
        
        result = generate(
            input_data="tests/fixtures/telemetry_small.csv",
            mapping="tests/fixtures/mapping_v1_3.yaml",
            output_path=tmp_path / "focus_default.csv",
            spec_version="v1.3",
            dataset_instance_complete=True,
        )
        
        assert result.metadata.generator_name == "focus-mapper"
        assert result.metadata.generator_version == __version__


def test_env_overrides_default_arg(tmp_path: Path) -> None:
    """Test that environment variables override the default argument value 'focus-mapper'."""
    
    with mock.patch.dict(os.environ, {
        "FOCUS_DATA_GENERATOR_NAME": "env-generator"
    }):
        # Calling without generator_name uses default="focus-mapper"
        result = generate(
            input_data="tests/fixtures/telemetry_small.csv",
            mapping="tests/fixtures/mapping_v1_3.yaml",
            output_path=tmp_path / "focus_env_override.csv",
            spec_version="v1.3",
            dataset_instance_complete=True,
        )
        
        # Should detect "focus-mapper" (default) and use ENV instead
        assert result.metadata.generator_name == "env-generator"

