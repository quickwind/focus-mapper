from __future__ import annotations

import pandas as pd

from focus_report.spec import FocusColumnSpec, FocusSpec, load_focus_spec
from focus_report.validate import validate_focus_dataframe


def _has_finding(report, check_id: str, column: str | None = None) -> bool:
    for f in report.findings:
        if f.check_id != check_id:
            continue
        if column is not None and f.column != column:
            continue
        return True
    return False


def test_validation_missing_mandatory_columns() -> None:
    spec = load_focus_spec("v1.2")
    df = pd.read_csv("tests/fixtures/focus_invalid_required_missing.csv")

    report = validate_focus_dataframe(df, spec=spec)
    assert report.summary.errors > 0
    assert _has_finding(report, "focus.column_present")


def test_validation_invalid_datetime() -> None:
    spec = load_focus_spec("v1.2")
    df = pd.read_csv("tests/fixtures/focus_invalid_datetime.csv")

    report = validate_focus_dataframe(df, spec=spec)
    assert _has_finding(report, "focus.datetime_parse", "BillingPeriodStart")


def test_validation_invalid_decimal_parse() -> None:
    spec = load_focus_spec("v1.2")
    df = pd.read_csv("tests/fixtures/focus_invalid_decimal.csv")

    report = validate_focus_dataframe(df, spec=spec)
    assert _has_finding(report, "focus.decimal_parse", "BilledCost")


def test_validation_invalid_allowed_values() -> None:
    spec = load_focus_spec("v1.2")
    df = pd.read_csv("tests/fixtures/focus_invalid_allowed_values.csv")

    report = validate_focus_dataframe(df, spec=spec)
    assert _has_finding(report, "focus.allowed_values", "ChargeCategory")


def test_validation_unknown_non_extension_column() -> None:
    spec = load_focus_spec("v1.2")
    df = pd.read_csv("tests/fixtures/focus_invalid_unknown_column.csv")

    report = validate_focus_dataframe(df, spec=spec)
    assert _has_finding(report, "focus.unknown_column", "CustomField")


def test_validation_invalid_json_object() -> None:
    spec = load_focus_spec("v1.2")
    df = pd.read_csv("tests/fixtures/focus_invalid_json.csv")

    report = validate_focus_dataframe(df, spec=spec)
    assert _has_finding(report, "focus.json_object", "Tags")


def test_validation_decimal_precision_scale() -> None:
    spec = load_focus_spec("v1.2")
    cols: list[FocusColumnSpec] = []
    for c in spec.columns:
        if c.name == "BilledCost":
            cols.append(
                FocusColumnSpec(
                    name=c.name,
                    feature_level=c.feature_level,
                    allows_nulls=c.allows_nulls,
                    data_type=c.data_type,
                    value_format=c.value_format,
                    allowed_values=c.allowed_values,
                    numeric_precision=5,
                    numeric_scale=2,
                )
            )
        else:
            cols.append(c)
    spec_with_limits = FocusSpec(
        version=spec.version,
        source=spec.source,
        columns=cols,
    )

    df = pd.read_csv("tests/fixtures/focus_invalid_decimal_precision.csv")
    report = validate_focus_dataframe(df, spec=spec_with_limits)
    assert _has_finding(report, "focus.decimal_precision_scale", "BilledCost")
