"""Format validators for FOCUS spec value_format rules.

This module provides validators for all FOCUS specification value_format types:
- Key-Value Format (JSON with primitives only)
- JSON Object Format (JSON with nesting, arrays, max 3 levels)
- Currency Format (ISO 4217)
- Numeric Format (no commas, currency symbols, or units)
- Date/Time Format (UTC ISO8601)
- Allowed Values (enum matching)
- Unit Format (soft validation - warnings only)

All validators return a tuple of (is_valid, error_message).
For soft validators, is_valid may be True with a warning message.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

try:
    import iso4217parse
    HAS_ISO4217 = True
except ImportError:
    HAS_ISO4217 = False


__all__ = [
    # Strict validators (ERROR on failure)
    "validate_key_value_format",
    "validate_json_object_format",
    "validate_currency_format",
    "validate_datetime_format",
    "validate_numeric_format",
    "validate_allowed_values",
    # Soft validators (WARN on failure)
    "validate_unit_format",
    # Data type validators
    "validate_integer",
    "validate_boolean",
    "validate_collection_of_strings",
]


# =============================================================================
# KEY-VALUE FORMAT (Strict)
# =============================================================================

def validate_key_value_format(value: str) -> tuple[bool, str | None]:
    """Validate JSON Key-Value format (primitives only, no arrays/objects).
    
    Per FOCUS spec:
    - MUST be valid JSON object
    - Values MUST be: number, string, true, false, or null
    - Values MUST NOT be an object or an array
    
    Args:
        value: JSON string to validate
        
    Returns:
        (is_valid, error_message or None)
    """
    if not value or not value.strip():
        return True, None  # Empty is valid (nullable columns)
    
    try:
        obj = json.loads(value)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"
    
    if not isinstance(obj, dict):
        return False, "Key-Value format must be a JSON object"
    
    for key, val in obj.items():
        if isinstance(val, (dict, list)):
            return False, f"Key-Value format does not allow nested objects or arrays (key: '{key}')"
    
    return True, None


# =============================================================================
# JSON OBJECT FORMAT (Strict with soft depth warning)
# =============================================================================

def _check_json_depth(obj: Any, current_depth: int = 0) -> int:
    """Calculate the maximum nesting depth of a JSON object.
    
    Depth 0 = root object itself
    Depth 1 = first level of nested objects/arrays inside root
    etc.
    
    Per FOCUS spec: "SHOULD NOT exceed 3 levels of nesting"
    So {"a": {"b": {"c": {"d": 1}}}} = depth 4, exceeds 3.
    """
    if isinstance(obj, dict):
        if not obj:
            return current_depth
        return max(_check_json_depth(v, current_depth + 1) for v in obj.values())
    elif isinstance(obj, list):
        if not obj:
            return current_depth
        return max(_check_json_depth(item, current_depth + 1) for item in obj)
    return current_depth


def _validate_array_elements(arr: list, path: str) -> tuple[bool, str | None]:
    """Validate array elements per JSON Object Format rules.
    
    - Elements must all be the same type
    - Elements must not be repeated
    - Elements must not be null
    """
    if not arr:
        return True, None
    
    # Check for null elements
    for i, elem in enumerate(arr):
        if elem is None:
            return False, f"Array at '{path}' contains null element at index {i}"
    
    # Check same type
    first_type = type(arr[0])
    for i, elem in enumerate(arr):
        if type(elem) != first_type:
            return False, f"Array at '{path}' has mixed types: {first_type.__name__} and {type(elem).__name__}"
    
    # Check for duplicates (only for hashable types)
    if all(isinstance(e, (str, int, float, bool)) for e in arr):
        if len(arr) != len(set(arr)):
            return False, f"Array at '{path}' contains duplicate elements"
    
    return True, None


def _validate_json_object_recursive(
    obj: Any, path: str = "root"
) -> tuple[bool, str | None]:
    """Recursively validate JSON object structure."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            valid, err = _validate_json_object_recursive(val, f"{path}.{key}")
            if not valid:
                return False, err
    elif isinstance(obj, list):
        valid, err = _validate_array_elements(obj, path)
        if not valid:
            return False, err
        for i, item in enumerate(obj):
            valid, err = _validate_json_object_recursive(item, f"{path}[{i}]")
            if not valid:
                return False, err
    return True, None


def validate_json_object_format(value: str) -> tuple[bool, str | None]:
    """Validate JSON Object format (allows nesting and arrays).
    
    Per FOCUS spec:
    - MUST be valid JSON object
    - Array elements MUST all use the same type
    - Array elements MUST NOT be repeated
    - Array elements MUST NOT be null
    - SHOULD NOT exceed 3 levels of nesting (warning)
    
    Args:
        value: JSON string to validate
        
    Returns:
        (is_valid, error_message or warning or None)
    """
    if not value or not value.strip():
        return True, None
    
    try:
        obj = json.loads(value)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"
    
    if not isinstance(obj, dict):
        return False, "JSON Object format must be a JSON object"
    
    # Validate structure (arrays, types)
    valid, err = _validate_json_object_recursive(obj)
    if not valid:
        return False, err
    
    # Check depth (soft warning)
    depth = _check_json_depth(obj)
    if depth > 3:
        # Return True but with warning message
        return True, f"Warning: JSON object exceeds recommended 3 levels (has {depth} levels)"
    
    return True, None


# =============================================================================
# CURRENCY FORMAT (Strict)
# =============================================================================

def validate_currency_format(value: str) -> tuple[bool, str | None]:
    """Validate ISO 4217 currency code format.
    
    Per FOCUS spec:
    - MUST be three-letter alphabetic code per ISO 4217
    - OR virtual currency string for non-ISO currencies
    
    Args:
        value: Currency code to validate
        
    Returns:
        (is_valid, error_message or None)
    """
    if not value or not value.strip():
        return True, None
    
    code = value.strip().upper()
    # Enforce uppercase only for 3-letter codes (ISO 4217 style)
    # Virtual currencies like 'Credits' or 'Points' can be mixed case
    if len(value.strip()) == 3 and value.strip() != code:
        return False, f"Currency code must be uppercase: {value}"
    
    # Check if it's a valid ISO 4217 code
    if HAS_ISO4217:
        try:
            currency = iso4217parse.parse(code)
            if currency:
                return True, None
        except (ValueError, KeyError):
            pass
    else:
        # Fallback: check if it's a 3-letter alphabetic code
        if len(code) == 3 and code.isalpha():
            return True, None
    
    # Allow virtual currencies (any string that follows string handling rules)
    # Per spec: "MUST conform to StringHandling when value is virtual currency"
    if value.strip():
        return True, None  # Virtual currency allowed
    
    return False, f"Invalid currency code: '{value}'"


# =============================================================================
# DATE/TIME FORMAT (Strict)
# =============================================================================

# ISO 8601 UTC format: YYYY-MM-DDTHH:mm:ssZ
_DATETIME_UTC_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
)


def validate_datetime_format(value: str) -> tuple[bool, str | None]:
    """Validate ISO 8601 UTC datetime format.
    
    Per FOCUS spec:
    - MUST be in UTC
    - MUST be format: YYYY-MM-DDTHH:mm:ssZ
    
    Args:
        value: Datetime string to validate
        
    Returns:
        (is_valid, error_message or None)
    """
    if not value or not value.strip():
        return True, None
    
    v = value.strip()
    
    # Check format pattern
    if not _DATETIME_UTC_PATTERN.match(v):
        return False, f"DateTime must be UTC format YYYY-MM-DDTHH:mm:ssZ, got: '{v}'"
    
    # Verify it's a valid datetime
    try:
        datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as e:
        return False, f"Invalid datetime: {e}"
    
    return True, None


# =============================================================================
# NUMERIC FORMAT (Strict)
# =============================================================================

# Pattern to detect invalid numeric characters
_INVALID_NUMERIC_CHARS = re.compile(r"[,$£€¥₹%]")
_VALID_NUMERIC_PATTERN = re.compile(
    r"^-?(\d+\.?\d*|\d*\.?\d+)([Ee]-?\d+)?$"
)


def validate_numeric_format(value: str) -> tuple[bool, str | None]:
    """Validate numeric format per FOCUS spec.
    
    Per FOCUS spec:
    - MUST be integer, decimal, or E notation
    - MUST NOT contain commas, currency symbols, or units
    - MUST NOT contain math symbols, functions, or operators
    - Positive sign (+) MUST NOT be used
    
    Args:
        value: Numeric string to validate
        
    Returns:
        (is_valid, error_message or None)
    """
    if not value or not value.strip():
        return True, None
    
    v = value.strip()
    
    # Check for invalid characters
    if _INVALID_NUMERIC_CHARS.search(v):
        return False, f"Numeric value contains invalid characters (commas, currency symbols): '{v}'"
    
    # Check for positive sign
    if v.startswith("+"):
        return False, f"Numeric value must not have positive sign: '{v}'"
    
    # Check valid pattern
    if not _VALID_NUMERIC_PATTERN.match(v):
        return False, f"Invalid numeric format: '{v}'"
    
    # Verify it can be parsed as a number
    try:
        Decimal(v.replace("E", "e"))
    except InvalidOperation:
        return False, f"Cannot parse as number: '{v}'"
    
    return True, None


# =============================================================================
# ALLOWED VALUES (Strict)
# =============================================================================

def validate_allowed_values(
    value: str, allowed: list[str], *, case_sensitive: bool = True
) -> tuple[bool, str | None]:
    """Validate value is in allowed values list.
    
    Args:
        value: Value to validate
        allowed: List of allowed values
        case_sensitive: Whether to match case-sensitively
        
    Returns:
        (is_valid, error_message or None)
    """
    if not value or not value.strip():
        return True, None
    
    v = value.strip()
    
    if case_sensitive:
        if v in allowed:
            return True, None
    else:
        if v.lower() in {a.lower() for a in allowed}:
            return True, None
    
    return False, f"Value '{v}' not in allowed values: {allowed}"


# =============================================================================
# UNIT FORMAT (Soft - warning only)
# =============================================================================

# Recommended data size units
_DATA_SIZE_UNITS = {
    "b", "B", "Kb", "KB", "Mb", "MB", "Gb", "GB", "Tb", "TB", "Pb", "PB", "Eb", "EB",
    "Kib", "KiB", "Mib", "MiB", "Gib", "GiB", "Tib", "TiB", "Pib", "PiB", "Eib", "EiB",
}

# Recommended time units
_TIME_UNITS = {"Year", "Month", "Day", "Hour", "Minute", "Second"}

# Recommended count units
_COUNT_UNITS = {"Count", "Unit", "Request", "Token", "Connection", "Certificate", "Domain", "Core"}


def validate_unit_format(value: str) -> tuple[bool, str | None]:
    """Validate unit format per FOCUS spec (soft validation - warnings only).
    
    Per FOCUS spec (SHOULD rules, not MUST):
    - Units should be expressed in specific formats
    - This is a recommendation, not a hard requirement
    
    Args:
        value: Unit string to validate
        
    Returns:
        (True, warning_message or None) - always True, may include warning
    """
    if not value or not value.strip():
        return True, None
    
    # Unit format is recommendations only, so always return True
    # but optionally provide a warning
    v = value.strip()
    
    # Check for common invalid patterns
    warnings = []
    
    # Check for lowercase data units (should be abbreviated)
    lower_data_units = {"gigabyte", "megabyte", "kilobyte", "terabyte", "petabyte"}
    if v.lower() in lower_data_units:
        warnings.append(f"Consider using abbreviated form (e.g., GB instead of gigabyte)")
    
    if warnings:
        return True, f"Warning: {'; '.join(warnings)}"
    
    return True, None


# =============================================================================
# DATA TYPE VALIDATORS
# =============================================================================

def validate_integer(value: str) -> tuple[bool, str | None]:
    """Validate value is a valid integer.
    
    Args:
        value: String to validate as integer
        
    Returns:
        (is_valid, error_message or None)
    """
    if not value or not value.strip():
        return True, None
    
    v = value.strip()
    
    # Check if it can be parsed as int
    try:
        int(v)
    except ValueError:
        return False, f"Invalid integer: '{v}'"
    
    # Check for decimal point (not allowed in integers)
    if "." in v:
        return False, f"Integer must not contain decimal point: '{v}'"
    
    return True, None


def validate_boolean(value: str) -> tuple[bool, str | None]:
    """Validate value is a valid boolean.
    
    Args:
        value: String to validate as boolean
        
    Returns:
        (is_valid, error_message or None)
    """
    if not value or not value.strip():
        return True, None
    
    v = value.strip().lower()
    
    if v in {"true", "false"}:
        return True, None
    
    return False, f"Boolean must be 'true' or 'false', got: '{value}'"


def validate_collection_of_strings(value: str) -> tuple[bool, str | None]:
    """Validate value is a valid collection (array) of strings.
    
    Args:
        value: JSON array string to validate
        
    Returns:
        (is_valid, error_message or None)
    """
    if not value or not value.strip():
        return True, None
    
    try:
        arr = json.loads(value)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"
    
    if not isinstance(arr, list):
        return False, "Collection of Strings must be a JSON array"
    
    for i, item in enumerate(arr):
        if not isinstance(item, str):
            return False, f"Collection of Strings must only contain strings, found {type(item).__name__} at index {i}"
    
    return True, None
