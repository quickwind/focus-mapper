import pandas as pd

from focus_mapper.mapping.config import load_mapping_config
from focus_mapper.mapping.executor import generate_focus_dataframe
from focus_mapper.spec import load_focus_spec
from focus_mapper.validate import validate_focus_dataframe


def test_generate_and_validate_focus_dataset_from_fixtures() -> None:
    spec = load_focus_spec("v1.2")
    mapping = load_mapping_config(
        __import__("pathlib").Path("tests/fixtures/mapping_basic.yaml")
    )
    df = pd.read_csv("tests/fixtures/telemetry_small.csv")

    out = generate_focus_dataframe(df, mapping=mapping, spec=spec)
    assert set(spec.column_names).issubset(set(out.columns))
    assert "x_CostCenter" in out.columns
    assert "x_CoalescedDescription" in out.columns
    assert "x_MappedCategory" in out.columns
    assert "x_TagConcat" in out.columns
    assert "x_RoundedTax" in out.columns
    assert "x_MathTotal" in out.columns
    assert "x_WhenTax" in out.columns
    assert len(out) == len(df)

    assert out["x_CoalescedDescription"].tolist() == [
        "Compute usage",
        "Alt tax desc",
    ]
    assert out["x_MappedCategory"].tolist() == ["U", "T"]
    assert out["x_TagConcat"].tolist() == ["core-vm", "billing-tax"]
    assert out["x_RoundedTax"].tolist() == [1.0, 0.0]
    assert out["x_MathTotal"].tolist() == [13.57, 5.5]
    assert out["x_WhenTax"].tolist() == ["N", "Y"]

    report = validate_focus_dataframe(out, spec=spec, mapping=mapping)
    assert report.summary.errors == 0
