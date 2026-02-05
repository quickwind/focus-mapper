from __future__ import annotations

import pandas as pd

from ..errors import MappingExecutionError
from ..spec import FocusSpec, coerce_dataframe_to_spec
from .config import MappingConfig
from .ops import apply_steps


def generate_focus_dataframe(
    df: pd.DataFrame, *, mapping: MappingConfig, spec: FocusSpec
) -> pd.DataFrame:
    """
    Orchestrates the conversion of an input DataFrame to a FOCUS-compliant DataFrame.

    This function:
    1. Validates that the mapping config version matches the spec version.
    2. Initializes a new DataFrame with standard FOCUS columns in canonical order.
    3. Populates columns using the rules defined in the mapping configuration.
    4. Appends custom extension columns (x_ prefix).
    5. Coerces all columns to the data types required by the FOCUS specification.
    """
    if mapping.spec_version.lower().removeprefix(
        "v"
    ) != spec.version.lower().removeprefix("v"):
        raise MappingExecutionError(
            f"Mapping spec_version {mapping.spec_version!r} does not match spec {spec.version!r}"
        )

    out = pd.DataFrame(index=df.index)

    # Standard columns in canonical order
    for col in spec.column_names:
        rule = mapping.rule_for_target(col)
        if rule:
            out[col] = pd.Series([pd.NA] * len(df))
            out[col] = apply_steps(df, steps=rule.steps, target=col)

    # Append extension columns from mapping (order as provided).
    for rule in mapping.rules:
        if not rule.target.startswith("x_"):
            continue
        if rule.target in out.columns:
            raise MappingExecutionError(
                f"Extension column collides with standard column: {rule.target}"
            )
        out[rule.target] = apply_steps(df, steps=rule.steps, target=rule.target)

    return coerce_dataframe_to_spec(out, spec=spec)
