import pandas as pd

import pytest

from focus_mapper.mapping.ops import apply_steps
from focus_mapper.errors import MappingExecutionError


def test_pandas_expr_basic_math() -> None:
    df = pd.DataFrame({"a": [1, 2], "b": [10, 20]})
    steps = [{"op": "pandas_expr", "expr": "df['a'] + df['b']"}]

    out = apply_steps(df, steps=steps, target="x_sum")
    assert out.tolist() == [11, 22]


def test_pandas_expr_groupby_transform() -> None:
    df = pd.DataFrame({"g": ["x", "x", "y"], "v": [1, 2, 5]})
    steps = [{"op": "pandas_expr", "expr": "df.groupby('g')['v'].transform('sum')"}]

    out = apply_steps(df, steps=steps, target="x_gsum")
    assert out.tolist() == [3, 3, 5]


def test_pandas_expr_blocks_unsafe_code() -> None:
    df = pd.DataFrame({"a": [1]})
    steps = [{"op": "pandas_expr", "expr": "__import__('os').system('echo nope')"}]

    with pytest.raises(MappingExecutionError):
        apply_steps(df, steps=steps, target="x_bad")
