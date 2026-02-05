from __future__ import annotations

import pandas as pd
import pytest

from focus_mapper.errors import MappingExecutionError
from focus_mapper.mapping.ops import apply_steps


def test_apply_steps_invalid_op() -> None:
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(MappingExecutionError, match="Invalid op"):
        apply_steps(df, steps=[{"op": ""}], target="X")


def test_apply_steps_cast_invalid_to() -> None:
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(MappingExecutionError, match="Unsupported cast"):
        apply_steps(
            df,
            steps=[{"op": "from_column", "column": "a"}, {"op": "cast", "to": "weird"}],
            target="X",
        )


def test_apply_steps_round_invalid_ndigits() -> None:
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(MappingExecutionError, match="round.ndigits"):
        apply_steps(
            df,
            steps=[
                {"op": "from_column", "column": "a"},
                {"op": "round", "ndigits": "nope"},
            ],
            target="X",
        )


def test_apply_steps_math_operator_errors() -> None:
    df = pd.DataFrame({"a": [1], "b": [2]})
    with pytest.raises(MappingExecutionError, match="math.operator"):
        apply_steps(
            df,
            steps=[{"op": "math", "operator": "pow", "operands": [{"column": "a"}]}],
            target="X",
        )

    with pytest.raises(MappingExecutionError, match="requires exactly 2 operands"):
        apply_steps(
            df,
            steps=[
                {
                    "op": "math",
                    "operator": "sub",
                    "operands": [{"column": "a"}, {"column": "b"}, {"const": 1}],
                }
            ],
            target="X",
        )

    with pytest.raises(MappingExecutionError, match="current but no prior series"):
        apply_steps(
            df,
            steps=[
                {"op": "math", "operator": "add", "operands": [{"current": True}]}
            ],
            target="X",
        )


def test_apply_steps_concat_invalid_sep() -> None:
    df = pd.DataFrame({"a": ["x"], "b": ["y"]})
    with pytest.raises(MappingExecutionError, match="concat sep"):
        apply_steps(
            df,
            steps=[{"op": "concat", "columns": ["a", "b"], "sep": 1}],
            target="X",
        )


def test_apply_steps_when_missing_column_defaults() -> None:
    df = pd.DataFrame({"a": [1, 2]})
    out = apply_steps(
        df,
        steps=[
            {"op": "when", "column": "missing", "value": "x", "then": "Y", "else": "N"}
        ],
        target="X",
    )
    assert out.tolist() == ["N", "N"]


def test_apply_steps_pandas_expr_invalid_cases() -> None:
    df = pd.DataFrame({"a": [1, 2]})

    with pytest.raises(MappingExecutionError, match="Invalid pandas_expr syntax"):
        apply_steps(
            df,
            steps=[{"op": "pandas_expr", "expr": "df["}],
            target="X",
        )

    with pytest.raises(MappingExecutionError, match="disallowed method"):
        apply_steps(
            df,
            steps=[{"op": "pandas_expr", "expr": "os.system('ls')"}],
            target="X",
        )

    with pytest.raises(MappingExecutionError, match="Series or scalar"):
        apply_steps(
            df,
            steps=[{"op": "pandas_expr", "expr": "df"}],
            target="X",
        )

    with pytest.raises(MappingExecutionError, match="length mismatch"):
        apply_steps(
            df,
            steps=[{"op": "pandas_expr", "expr": "[1,2,3]"}],
            target="X",
        )
