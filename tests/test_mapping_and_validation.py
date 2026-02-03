import pandas as pd

from focus_report.mapping.config import load_mapping_config
from focus_report.mapping.executor import generate_focus_dataframe
from focus_report.spec import load_focus_spec
from focus_report.validate import validate_focus_dataframe


def test_generate_and_validate_focus_dataset_from_fixtures() -> None:
    spec = load_focus_spec("v1.2")
    mapping = load_mapping_config(
        __import__("pathlib").Path("tests/fixtures/mapping_basic.yaml")
    )
    df = pd.read_csv("tests/fixtures/telemetry_small.csv")

    out = generate_focus_dataframe(df, mapping=mapping, spec=spec)
    assert set(spec.column_names).issubset(set(out.columns))
    assert "x_CostCenter" in out.columns
    assert len(out) == len(df)

    report = validate_focus_dataframe(out, spec=spec)
    assert report.summary.errors == 0
