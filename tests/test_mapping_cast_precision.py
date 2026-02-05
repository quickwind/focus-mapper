from decimal import Decimal

import pandas as pd

from focus_report.mapping.ops import apply_steps


def test_cast_decimal_precision_enforced() -> None:
    df = pd.DataFrame({"cost": ["123456.78", "12.34"]})
    steps = [
        {"op": "from_column", "column": "cost"},
        {"op": "cast", "to": "decimal", "precision": 5, "scale": 2},
    ]

    out = apply_steps(df, steps=steps, target="BilledCost")
    assert out.tolist() == [None, Decimal("12.34")]
