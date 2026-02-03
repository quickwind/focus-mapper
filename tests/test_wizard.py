from __future__ import annotations

import pandas as pd

from focus_report.spec import load_focus_spec
from focus_report.wizard import run_wizard


def test_wizard_generates_mapping_with_defaults(monkeypatch) -> None:
    spec = load_focus_spec("v1.2")
    df = pd.read_csv("tests/fixtures/telemetry_small.csv")

    # Minimal inputs: accept suggested columns and skip extras.
    inputs_list = [
        "",  # header prompt for first target
        "1",  # from_column
        "",  # use suggested
    ]
    for _ in range(len(spec.columns) - 1):
        inputs_list.extend(["", "4"])  # header + skip
    inputs_list.append("n")  # no extension
    inputs = iter(inputs_list)

    def fake_input(text: str) -> str:
        return next(inputs)

    result = run_wizard(
        spec=spec,
        input_df=df,
        prompt=fake_input,
        include_optional=False,
        include_recommended=False,
    )

    assert result.mapping.spec_version == "v1.2"
    assert len(result.mapping.rules) >= 1
