import pandas as pd
import numpy as np
import pytest

from focus_mapper.mapping.config import load_mapping_config
from focus_mapper.mapping.executor import generate_focus_dataframe
from focus_mapper.spec import load_focus_spec
from focus_mapper.validate import validate_focus_dataframe


def test_generate_and_validate_focus_dataset_from_fixtures() -> None:
    spec = load_focus_spec("v1.2")
    mapping = load_mapping_config(
        __import__("pathlib").Path("tests/fixtures/mapping_v1_2.yaml")
    )
    df = pd.read_csv("tests/fixtures/telemetry_small.csv")

    out = generate_focus_dataframe(df, mapping=mapping, spec=spec)
    mapped_targets = {r.target for r in mapping.rules}
    assert mapped_targets.issubset(set(out.columns))
    
    # Verify expected extension columns exist
    expected_cols = [
        "x_CostCenter", "x_CoalescedDescription", "x_MappedCategory",
        "x_TagConcat", "x_RoundedTax", "x_MathTotal", "x_WhenTax",
        "x_QueryTotal", "x_DailyTotalCost"
    ]
    for col in expected_cols:
        assert col in out.columns

    assert len(out) == len(df)

    # Verify logic correctness instead of hardcoded values
    
    # x_CoalescedDescription: coalesce(alt_description, charge_description)
    expected_desc = df["alt_description"].combine_first(df["charge_description"])
    pd.testing.assert_series_equal(out["x_CoalescedDescription"], expected_desc.rename("x_CoalescedDescription"), check_names=False, check_dtype=False)

    # x_MappedCategory: Usage->U, Tax->T
    category_map = {"Usage": "U", "Tax": "T"}
    expected_cat = df["charge_category"].map(category_map).fillna("Other")
    pd.testing.assert_series_equal(out["x_MappedCategory"], expected_cat.rename("x_MappedCategory"), check_names=False, check_dtype=False)

    # x_TagConcat: tag_a + "-" + tag_b
    expected_concat = df["tag_a"] + "-" + df["tag_b"]
    pd.testing.assert_series_equal(out["x_TagConcat"], expected_concat.rename("x_TagConcat"), check_names=False, check_dtype=False)

    # x_RoundedTax: round(tax_amount, 0)
    expected_rounded = df["tax_amount"].round(1)
    pd.testing.assert_series_equal(out["x_RoundedTax"], expected_rounded.rename("x_RoundedTax"), check_names=False, check_dtype=False)

    # x_MathTotal: billed_cost + tax_amount
    expected_math = df["billed_cost"] + df["tax_amount"]
    # Float precision might vary slightly, use close match
    pd.testing.assert_series_equal(out["x_MathTotal"], expected_math.rename("x_MathTotal"), check_names=False, check_dtype=False)

    # x_WhenTax: "Y" if Tax else "N"
    expected_when = np.where(df["charge_category"] == "Tax", "Y", "N")
    pd.testing.assert_series_equal(out["x_WhenTax"], pd.Series(expected_when, name="x_WhenTax"), check_names=False, check_dtype=False)

    # x_QueryTotal: SELECT billed_cost + tax_amount FROM src
    # Should match x_MathTotal logic
    pd.testing.assert_series_equal(out["x_QueryTotal"], expected_math.rename("x_QueryTotal"), check_names=False, check_dtype=False)
    
    # x_DailyTotalCost: Window function SUM(billed_cost) PARTITION BY billing_resource_id, billing_date
    # Calculate expected using pandas groupby transform
    expected_daily = df.groupby(["billing_resource_id", "billing_date"])["billed_cost"].transform("sum")
    # Sort output to match input order for comparison if needed, but indices should align
    # DuckDB window function preserves input row count/order usually (pandas wrapper might reset index?)
    # Focus dataframe generation preserves index
    pd.testing.assert_series_equal(out["x_DailyTotalCost"], expected_daily.rename("x_DailyTotalCost"), check_names=False, check_dtype=False)

    report = validate_focus_dataframe(out, spec=spec, mapping=mapping)
    assert report.summary.errors == 0
