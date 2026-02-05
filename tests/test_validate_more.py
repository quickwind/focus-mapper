from __future__ import annotations

import pandas as pd

from focus_mapper.mapping.config import MappingConfig, MappingRule
from focus_mapper.spec import FocusColumnSpec, FocusSpec
from focus_mapper.validate import validate_focus_dataframe


def _spec(cols: list[FocusColumnSpec]) -> FocusSpec:
    return FocusSpec(version="1.2", source=None, columns=cols)


def test_allowed_values_case_sensitive_default() -> None:
    spec = _spec(
        [
            FocusColumnSpec(
                name="ChargeCategory",
                feature_level="mandatory",
                allows_nulls=False,
                data_type="String",
                allowed_values=["Usage", "Tax"],
            )
        ]
    )
    df = pd.DataFrame({"ChargeCategory": ["usage"]})
    report = validate_focus_dataframe(df, spec=spec)
    assert report.summary.errors == 1


def test_allowed_values_case_insensitive_override() -> None:
    spec = _spec(
        [
            FocusColumnSpec(
                name="ChargeCategory",
                feature_level="mandatory",
                allows_nulls=False,
                data_type="String",
                allowed_values=["Usage", "Tax"],
            )
        ]
    )
    mapping = MappingConfig(
        spec_version="v1.2",
        rules=[
            MappingRule(
                target="ChargeCategory",
                steps=[{"op": "from_column", "column": "ChargeCategory"}],
                validation={"allowed_values": {"case_insensitive": True}},
            )
        ],
        validation_defaults={},
    )
    df = pd.DataFrame({"ChargeCategory": ["usage"]})
    report = validate_focus_dataframe(df, spec=spec, mapping=mapping)
    assert report.summary.errors == 0


def test_decimal_permissive_parsing_currency() -> None:
    spec = _spec(
        [
            FocusColumnSpec(
                name="BilledCost",
                feature_level="mandatory",
                allows_nulls=False,
                data_type="Decimal",
            )
        ]
    )
    df = pd.DataFrame({"BilledCost": ["$1,234.50"]})
    report = validate_focus_dataframe(df, spec=spec)
    assert report.summary.errors == 0


def test_decimal_limits_integer_min_max() -> None:
    spec = _spec(
        [
            FocusColumnSpec(
                name="BilledCost",
                feature_level="mandatory",
                allows_nulls=False,
                data_type="Decimal",
            )
        ]
    )
    mapping = MappingConfig(
        spec_version="v1.2",
        rules=[
            MappingRule(
                target="BilledCost",
                steps=[{"op": "from_column", "column": "BilledCost"}],
                validation={
                    "decimal": {
                        "precision": 3,
                        "scale": 0,
                        "integer_only": True,
                        "min": "0",
                        "max": "10",
                    }
                },
            )
        ],
        validation_defaults={},
    )
    df = pd.DataFrame({"BilledCost": ["12.34", "-1", "1000"]})
    report = validate_focus_dataframe(df, spec=spec, mapping=mapping)
    # multiple errors for parse/limits/integer_only
    assert report.summary.errors >= 1


def test_datetime_strict_format_and_parse() -> None:
    spec = _spec(
        [
            FocusColumnSpec(
                name="BillingPeriodStart",
                feature_level="mandatory",
                allows_nulls=False,
                data_type="Date/Time",
            )
        ]
    )
    mapping = MappingConfig(
        spec_version="v1.2",
        rules=[
            MappingRule(
                target="BillingPeriodStart",
                steps=[{"op": "from_column", "column": "BillingPeriodStart"}],
                validation={"mode": "strict"},
            )
        ],
        validation_defaults={},
    )
    df = pd.DataFrame({"BillingPeriodStart": ["01/02/2026"]})
    report = validate_focus_dataframe(df, spec=spec, mapping=mapping)
    assert report.summary.errors >= 1


def test_string_validation_trim_and_length() -> None:
    spec = _spec(
        [
            FocusColumnSpec(
                name="ChargeDescription",
                feature_level="mandatory",
                allows_nulls=False,
                data_type="String",
            )
        ]
    )
    mapping = MappingConfig(
        spec_version="v1.2",
        rules=[
            MappingRule(
                target="ChargeDescription",
                steps=[{"op": "from_column", "column": "ChargeDescription"}],
                validation={
                    "string": {"min_length": 2, "max_length": 4, "allow_empty": False, "trim": True}
                },
            )
        ],
        validation_defaults={},
    )
    df = pd.DataFrame({"ChargeDescription": ["  ", "abcdef"]})
    report = validate_focus_dataframe(df, spec=spec, mapping=mapping)
    assert report.summary.errors >= 1


def test_json_object_only_validation() -> None:
    spec = _spec(
        [
            FocusColumnSpec(
                name="Tags",
                feature_level="optional",
                allows_nulls=True,
                data_type="JSON",
            )
        ]
    )
    mapping = MappingConfig(
        spec_version="v1.2",
        rules=[
            MappingRule(
                target="Tags",
                steps=[{"op": "from_column", "column": "Tags"}],
                validation={"json": {"object_only": True}},
            )
        ],
        validation_defaults={},
    )
    df = pd.DataFrame({"Tags": ["[]"]})
    report = validate_focus_dataframe(df, spec=spec, mapping=mapping)
    assert report.summary.errors == 1


def test_unknown_column_warning_and_currency_format() -> None:
    spec = _spec(
        [
            FocusColumnSpec(
                name="BillingCurrency",
                feature_level="mandatory",
                allows_nulls=False,
                data_type="String",
            )
        ]
    )
    df = pd.DataFrame({"BillingCurrency": ["usd"], "Weird": [1]})
    report = validate_focus_dataframe(df, spec=spec)
    # one error for currency format + one warn for unknown column
    assert report.summary.errors == 1
    assert report.summary.warnings == 1
