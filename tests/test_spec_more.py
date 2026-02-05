from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from focus_mapper.errors import SpecError
from focus_mapper.spec import (
    FocusColumnSpec,
    coerce_dataframe_to_spec,
    coerce_series_to_type,
    list_available_spec_versions,
)


def test_coerce_series_to_decimal_and_json() -> None:
    dec_col = FocusColumnSpec(
        name="Cost",
        feature_level="mandatory",
        allows_nulls=False,
        data_type="Decimal",
    )
    series = pd.Series(["1.25", "bad", None])
    out = coerce_series_to_type(series, dec_col)
    assert out.iloc[0] == Decimal("1.25")
    assert out.iloc[1] is None
    assert out.iloc[2] is None

    json_col = FocusColumnSpec(
        name="Tags",
        feature_level="optional",
        allows_nulls=True,
        data_type="JSON",
    )
    series = pd.Series(['{"a": 1}', '{"a": 1}', "[]", "", None, {"k": "v"}])
    out = coerce_series_to_type(series, json_col)
    assert out.iloc[0] == {"a": 1}
    assert out.iloc[2] is None
    assert out.iloc[3] is None
    assert out.iloc[5] == {"k": "v"}


def test_coerce_series_unsupported_type_raises() -> None:
    col = FocusColumnSpec(
        name="Weird",
        feature_level="optional",
        allows_nulls=True,
        data_type="Number",
    )
    with pytest.raises(SpecError, match="Unsupported data type"):
        coerce_series_to_type(pd.Series([1, 2]), col)


def test_coerce_dataframe_to_spec_casts_columns() -> None:
    spec = [
        FocusColumnSpec(
            name="BillingPeriodStart",
            feature_level="mandatory",
            allows_nulls=False,
            data_type="Date/Time",
        ),
        FocusColumnSpec(
            name="BillingCurrency",
            feature_level="mandatory",
            allows_nulls=False,
            data_type="String",
        ),
    ]
    df = pd.DataFrame(
        {
            "BillingPeriodStart": ["2026-01-01T00:00:00Z"],
            "BillingCurrency": ["USD"],
        }
    )
    out = coerce_dataframe_to_spec(df, spec=type("Spec", (), {"columns": spec})())
    assert str(out["BillingPeriodStart"].dtype).startswith("datetime64")
    assert str(out["BillingCurrency"].dtype) == "string"


def test_list_available_spec_versions_includes_v1_2() -> None:
    versions = list_available_spec_versions()
    assert "v1.2" in versions
