"""
focus-mapper: FOCUS data generation and validation library.

Main API:
- generate(): Generate FOCUS-compliant data from input + mapping
- validate(): Validate FOCUS data against specification
- validate_mapping(): Validate mapping YAML configuration
"""

# Define version first to avoid circular imports
__version__ = "0.7.0"

# Import API after version is defined
from .api import (
    generate,
    validate,
    validate_mapping,
    GenerationResult,
    MappingValidationResult,
)
from .validate import ValidationReport, ValidationFinding, ValidationSummary
from .metadata import SidecarMetadata
from .mapping.config import MappingConfig, load_mapping_config
from .datetime_utils import (
    ensure_utc_datetime,
    format_datetime_iso8601,
    ensure_utc_and_format_datetime,
)
from .spec import FocusSpec, load_focus_spec

__all__ = [
    "__version__",
    # Main API functions
    "generate",
    "validate",
    "validate_mapping",
    # Result types
    "GenerationResult",
    "MappingValidationResult",
    "ValidationReport",
    "ValidationFinding",
    "ValidationSummary",
    "SidecarMetadata",
    # Config types
    "MappingConfig",
    "FocusSpec",
    # Loaders
    "load_mapping_config",
    "load_focus_spec",
    # Datetime utilities
    "ensure_utc_datetime",
    "format_datetime_iso8601",
    "ensure_utc_and_format_datetime",
]
