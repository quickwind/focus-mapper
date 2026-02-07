"""Tests for format_validators module."""
from __future__ import annotations

import pytest

from focus_mapper.format_validators import (
    validate_key_value_format,
    validate_json_object_format,
    validate_currency_format,
    validate_datetime_format,
    validate_numeric_format,
    validate_allowed_values,
    validate_unit_format,
    validate_integer,
    validate_boolean,
    validate_collection_of_strings,
)


class TestKeyValueFormat:
    """Tests for Key-Value format validation."""

    def test_valid_primitives(self):
        """Valid primitives are accepted."""
        valid, err = validate_key_value_format('{"a": 1, "b": "str", "c": true, "d": null}')
        assert valid is True
        assert err is None

    def test_empty_object(self):
        """Empty object is valid."""
        valid, err = validate_key_value_format("{}")
        assert valid is True

    def test_empty_string(self):
        """Empty string is valid (nullable)."""
        valid, err = validate_key_value_format("")
        assert valid is True

    def test_rejects_arrays(self):
        """Arrays in values are rejected."""
        valid, err = validate_key_value_format('{"a": [1, 2, 3]}')
        assert valid is False
        assert "array" in err.lower()

    def test_rejects_nested_objects(self):
        """Nested objects are rejected."""
        valid, err = validate_key_value_format('{"a": {"b": 1}}')
        assert valid is False
        assert "nested" in err.lower()

    def test_invalid_json(self):
        """Invalid JSON is rejected."""
        valid, err = validate_key_value_format("{not valid json}")
        assert valid is False
        assert "Invalid JSON" in err


class TestJsonObjectFormat:
    """Tests for JSON Object format validation."""

    def test_allows_arrays(self):
        """Arrays are allowed."""
        valid, err = validate_json_object_format('{"a": [1, 2, 3]}')
        assert valid is True
        assert err is None

    def test_allows_nesting_within_limit(self):
        """Nesting within 3 levels is allowed."""
        # Depth: root=0, a=1, b=2, c=3 -> exactly 3 levels, OK
        valid, err = validate_json_object_format('{"a": {"b": {"c": 1}}}')
        assert valid is True
        assert err is None

    def test_warns_on_exceeding_3_levels(self):
        """Warns when nesting exceeds 3 levels."""
        # Depth: root=0, a=1, b=2, c=3, d=4 -> 4 levels, warning
        deep = '{"a": {"b": {"c": {"d": 1}}}}'
        valid, err = validate_json_object_format(deep)
        assert valid is True  # Still valid, just warning
        assert "Warning" in err
        assert "4" in err

    def test_array_same_type(self):
        """Arrays must have same type."""
        valid, err = validate_json_object_format('{"a": [1, "two"]}')
        assert valid is False
        assert "mixed types" in err.lower()

    def test_array_no_null(self):
        """Arrays must not contain null."""
        valid, err = validate_json_object_format('{"a": [1, null, 3]}')
        assert valid is False
        assert "null" in err.lower()

    def test_array_no_duplicates(self):
        """Arrays must not have duplicate elements."""
        valid, err = validate_json_object_format('{"a": [1, 2, 1]}')
        assert valid is False
        assert "duplicate" in err.lower()

    def test_empty_array(self):
        """Empty arrays are valid."""
        valid, err = validate_json_object_format('{"a": []}')
        assert valid is True


class TestCurrencyFormat:
    """Tests for Currency format validation."""

    def test_valid_iso_codes(self):
        """Valid ISO 4217 codes are accepted."""
        for code in ["USD", "EUR", "GBP", "JPY", "CNY"]:
            valid, err = validate_currency_format(code)
            assert valid is True, f"Failed for {code}"

    def test_lowercase_rejected(self):
        """Lowercase codes are rejected."""
        valid, err = validate_currency_format("usd")
        assert valid is False
        assert "uppercase" in err

    def test_virtual_currency(self):
        """Virtual currency strings are accepted."""
        valid, err = validate_currency_format("Credits")
        assert valid is True

    def test_empty_valid(self):
        """Empty string is valid."""
        valid, err = validate_currency_format("")
        assert valid is True


class TestDatetimeFormat:
    """Tests for Date/Time format validation."""

    def test_valid_utc(self):
        """Valid UTC datetime is accepted."""
        valid, err = validate_datetime_format("2024-01-15T10:30:00Z")
        assert valid is True
        assert err is None

    def test_rejects_non_utc(self):
        """Non-UTC datetime is rejected."""
        valid, err = validate_datetime_format("2024-01-15T10:30:00")
        assert valid is False
        assert "UTC format" in err

    def test_rejects_date_only(self):
        """Date-only format is rejected."""
        valid, err = validate_datetime_format("2024-01-15")
        assert valid is False

    def test_rejects_offset(self):
        """Offset timezone is rejected (must be Z)."""
        valid, err = validate_datetime_format("2024-01-15T10:30:00+00:00")
        assert valid is False

    def test_empty_valid(self):
        """Empty string is valid."""
        valid, err = validate_datetime_format("")
        assert valid is True


class TestNumericFormat:
    """Tests for Numeric format validation."""

    def test_valid_integer(self):
        """Valid integers are accepted."""
        valid, err = validate_numeric_format("42")
        assert valid is True

    def test_valid_negative(self):
        """Negative numbers are accepted."""
        valid, err = validate_numeric_format("-100.5")
        assert valid is True

    def test_valid_decimal(self):
        """Valid decimals are accepted."""
        valid, err = validate_numeric_format("3.14159")
        assert valid is True

    def test_valid_scientific(self):
        """Scientific notation is accepted."""
        valid, err = validate_numeric_format("35.2E-7")
        assert valid is True

    def test_rejects_comma(self):
        """Commas are rejected."""
        valid, err = validate_numeric_format("1,234")
        assert valid is False
        assert "comma" in err.lower() or "invalid" in err.lower()

    def test_rejects_currency_symbol(self):
        """Currency symbols are rejected."""
        valid, err = validate_numeric_format("$100")
        assert valid is False

    def test_rejects_positive_sign(self):
        """Positive sign is rejected."""
        valid, err = validate_numeric_format("+333")
        assert valid is False
        assert "positive sign" in err.lower()

    def test_empty_valid(self):
        """Empty string is valid."""
        valid, err = validate_numeric_format("")
        assert valid is True


class TestAllowedValues:
    """Tests for Allowed Values validation."""

    def test_valid_match(self):
        """Matching value is accepted."""
        valid, err = validate_allowed_values("Usage", ["Usage", "Purchase", "Tax"])
        assert valid is True

    def test_case_sensitive_by_default(self):
        """Case-sensitive matching by default."""
        valid, err = validate_allowed_values("usage", ["Usage", "Purchase"])
        assert valid is False

    def test_case_insensitive(self):
        """Case-insensitive matching when specified."""
        valid, err = validate_allowed_values("usage", ["Usage", "Purchase"], case_sensitive=False)
        assert valid is True

    def test_invalid_value(self):
        """Invalid value is rejected."""
        valid, err = validate_allowed_values("Invalid", ["Usage", "Purchase"])
        assert valid is False
        assert "not in allowed" in err.lower()


class TestUnitFormat:
    """Tests for Unit format validation (soft warnings only)."""

    def test_always_valid(self):
        """Unit format always returns True (soft validation)."""
        valid, err = validate_unit_format("anything")
        assert valid is True

    def test_warns_on_lowercase_unit(self):
        """Warns on lowercase data unit names."""
        valid, err = validate_unit_format("gigabyte")
        assert valid is True
        assert err is not None
        assert "Warning" in err


class TestInteger:
    """Tests for Integer validation."""

    def test_valid_integer(self):
        """Valid integers are accepted."""
        valid, err = validate_integer("42")
        assert valid is True

    def test_valid_negative(self):
        """Negative integers are accepted."""
        valid, err = validate_integer("-100")
        assert valid is True

    def test_rejects_decimal(self):
        """Decimal numbers are rejected."""
        valid, err = validate_integer("3.14")
        assert valid is False
        assert "integer" in err.lower() or "decimal" in err.lower()

    def test_rejects_text(self):
        """Non-numeric text is rejected."""
        valid, err = validate_integer("abc")
        assert valid is False


class TestBoolean:
    """Tests for Boolean validation."""

    def test_true(self):
        """'true' is accepted."""
        valid, err = validate_boolean("true")
        assert valid is True

    def test_false(self):
        """'false' is accepted."""
        valid, err = validate_boolean("false")
        assert valid is True

    def test_case_insensitive(self):
        """Case-insensitive matching."""
        valid, err = validate_boolean("TRUE")
        assert valid is True

    def test_rejects_yes(self):
        """'yes' is not accepted."""
        valid, err = validate_boolean("yes")
        assert valid is False

    def test_rejects_1(self):
        """'1' is not accepted."""
        valid, err = validate_boolean("1")
        assert valid is False


class TestCollectionOfStrings:
    """Tests for Collection of Strings validation."""

    def test_valid_array(self):
        """Valid string array is accepted."""
        valid, err = validate_collection_of_strings('["a", "b", "c"]')
        assert valid is True

    def test_empty_array(self):
        """Empty array is valid."""
        valid, err = validate_collection_of_strings("[]")
        assert valid is True

    def test_rejects_numbers(self):
        """Numbers in array are rejected."""
        valid, err = validate_collection_of_strings('[1, 2, 3]')
        assert valid is False
        assert "strings" in err.lower()

    def test_rejects_mixed(self):
        """Mixed types are rejected."""
        valid, err = validate_collection_of_strings('["a", 1]')
        assert valid is False

    def test_rejects_non_array(self):
        """Non-array is rejected."""
        valid, err = validate_collection_of_strings('{"a": "b"}')
        assert valid is False
        assert "array" in err.lower()
