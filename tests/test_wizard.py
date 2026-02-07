from __future__ import annotations

import pandas as pd

from focus_mapper.spec import load_focus_spec
from focus_mapper.wizard import run_wizard


def test_wizard_generates_mapping_with_defaults(monkeypatch) -> None:
    spec = load_focus_spec("v1.2")
    df = pd.read_csv("tests/fixtures/telemetry_small.csv")

    # Minimal inputs: use const for all targets.
    inputs_list = [
        "",  # use default validation settings
    ]
    mandatory_cols = [c for c in spec.columns if c.feature_level.lower() == "mandatory"]
    for col in mandatory_cols:
        inputs_list.append("2")  # const
        if col.allowed_values:
            inputs_list.append(col.allowed_values[0])
        elif col.allows_nulls:
            inputs_list.append("")
        else:
            # Provide type-appropriate values for non-nullable columns
            data_type = (col.data_type or "").strip().lower()
            if data_type == "decimal":
                inputs_list.append("0")
            elif data_type in ("date/time", "datetime"):
                inputs_list.append("2024-01-01T00:00:00Z")
            else:
                inputs_list.append("X")
        inputs_list.append("done")  # finish steps
        inputs_list.append("n")  # no per-column validation override
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
        include_conditional=False,
    )

    assert result.mapping.spec_version == "v1.2"
    assert len(result.mapping.rules) >= 1
