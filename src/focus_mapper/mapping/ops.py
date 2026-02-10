from __future__ import annotations

import ast
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd

from ..datetime_utils import ensure_utc_datetime
from ..errors import MappingExecutionError


_ALLOWED_PANDAS_NAMES = {"df", "pd", "current", "str", "int", "float"}
_ALLOWED_PANDAS_CALLS = {
    # pandas top-level helpers
    "to_datetime",
    "to_numeric",
    "to_timedelta",
    # DataFrame/Series ops
    "groupby",
    "agg",
    "aggregate",
    "transform",
    "sum",
    "mean",
    "min",
    "max",
    "count",
    "nunique",
    "astype",
    "fillna",
    "where",
    "map",
    "combine_first",
    "replace",
    "round",
    "clip",
    "abs",
    "add",
    "sub",
    "mul",
    "div",
    "pow",
    "shift",
    "diff",
    "cumsum",
    "cummax",
    "cummin",
    "cumprod",
    # str/dt accessors
    "lower",
    "upper",
    "strip",
    "replace",
    "contains",
    "startswith",
    "endswith",
    "slice",
    "len",
    "year",
    "month",
    "day",
    "date",
    "floor",
    "ceil",
}
_DISALLOWED_PANDAS_NODES = (
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
    ast.NamedExpr,
    ast.JoinedStr,
    ast.FormattedValue,
)


def _validate_pandas_expr(expr: str) -> None:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise MappingExecutionError(f"Invalid pandas_expr syntax: {e.msg}") from e

    for node in ast.walk(tree):
        if isinstance(node, _DISALLOWED_PANDAS_NODES):
            raise MappingExecutionError("pandas_expr contains disallowed syntax")

        if isinstance(node, ast.Name):
            if node.id not in _ALLOWED_PANDAS_NAMES:
                raise MappingExecutionError(
                    f"pandas_expr uses disallowed name: {node.id}"
                )

        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise MappingExecutionError("pandas_expr uses private attribute access")

        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id not in _ALLOWED_PANDAS_CALLS:
                    raise MappingExecutionError(
                        f"pandas_expr calls disallowed function: {func.id}"
                    )
            elif isinstance(func, ast.Attribute):
                if func.attr not in _ALLOWED_PANDAS_CALLS:
                    raise MappingExecutionError(
                        f"pandas_expr calls disallowed method: {func.attr}"
                    )
            else:
                raise MappingExecutionError("pandas_expr uses disallowed call target")

            for kw in node.keywords:
                if kw.arg is None:
                    raise MappingExecutionError("pandas_expr disallows **kwargs")


def _eval_pandas_expr(
    expr: str, *, df: pd.DataFrame, current: pd.Series | None, target: str
) -> pd.Series:
    _validate_pandas_expr(expr)

    try:
        result = eval(  # noqa: S307 - guarded by AST validation and no builtins
            compile(expr, "<pandas_expr>", "eval"),
            {"__builtins__": {}},
            {"df": df, "pd": pd, "current": current, "str": str, "int": int, "float": float},
        )
    except Exception as e:
        raise MappingExecutionError(
            f"pandas_expr failed for target {target}: {e}"
        ) from e

    if isinstance(result, pd.Series):
        return result
    if isinstance(result, pd.DataFrame):
        raise MappingExecutionError(
            f"pandas_expr must return a Series or scalar for target {target}"
        )
    if isinstance(result, (list, tuple)):
        if len(result) != len(df):
            raise MappingExecutionError(
                f"pandas_expr result length mismatch for target {target}"
            )
        return pd.Series(result, index=df.index)

    # scalar or None
    return pd.Series([result] * len(df), index=df.index)


def apply_steps(
    df: pd.DataFrame, *, steps: list[dict[str, Any]], target: str
) -> pd.Series:
    """
    Executes a sequence of mapping operations on a DataFrame to produce a single Series.

    Each step in 'steps' is an operation (e.g., 'from_column', 'math', 'cast') that
    either initializes or transforms the current working series.
    """
    series: pd.Series | None = None

    for step in steps:
        op = step.get("op")
        if not isinstance(op, str) or not op:
            raise MappingExecutionError(f"Invalid op for target {target}")

        if op == "from_column":
            # Initialize series from a raw input column
            col = step.get("column")
            if not isinstance(col, str) or not col:
                raise MappingExecutionError(
                    f"from_column requires 'column' for target {target}"
                )
            if col not in df.columns:
                series = pd.Series([pd.NA] * len(df))
            else:
                series = df[col]
            continue

        if op == "const":
            # Initialize series with a static value
            value = step.get("value")
            series = pd.Series([value] * len(df))
            continue

        if op == "null":
            # Initialize series with all null values
            series = pd.Series([pd.NA] * len(df))
            continue

        if op == "coalesce":
            # Take the first non-null value from a list of input columns
            cols = step.get("columns")
            if not isinstance(cols, list) or not cols:
                raise MappingExecutionError(
                    f"coalesce requires 'columns' for target {target}"
                )
            coalesced: pd.Series | None = None
            for col in cols:
                if not isinstance(col, str) or not col:
                    raise MappingExecutionError(
                        f"coalesce columns must be strings for target {target}"
                    )
                s = df[col] if col in df.columns else pd.Series([pd.NA] * len(df))
                coalesced = s if coalesced is None else coalesced.combine_first(s)
            series = (
                coalesced if coalesced is not None else pd.Series([pd.NA] * len(df))
            )
            continue

        if op == "map_values":
            # Transform values using a lookup dictionary
            if series is None:
                src = step.get("column")
                if not isinstance(src, str) or not src:
                    raise MappingExecutionError(
                        f"map_values requires prior series or 'column' for target {target}"
                    )
                series = df[src] if src in df.columns else pd.Series([pd.NA] * len(df))

            assert series is not None

            mapping = step.get("mapping")
            if not isinstance(mapping, dict) or not mapping:
                raise MappingExecutionError(
                    f"map_values requires 'mapping' for target {target}"
                )
            default = step.get("default", pd.NA)
            series = series.map(mapping).fillna(default)
            continue

        if op == "concat":
            # Join multiple columns into a single string column
            cols = step.get("columns")
            sep = step.get("sep", "")
            if not isinstance(cols, list) or not cols:
                raise MappingExecutionError(
                    f"concat requires 'columns' for target {target}"
                )
            if not isinstance(sep, str):
                raise MappingExecutionError(
                    f"concat sep must be string for target {target}"
                )
            parts: list[pd.Series] = []
            for col in cols:
                if not isinstance(col, str) or not col:
                    raise MappingExecutionError(
                        f"concat columns must be strings for target {target}"
                    )
                s = df[col] if col in df.columns else pd.Series([pd.NA] * len(df))
                parts.append(s.astype("string"))
            out: pd.Series = parts[0]
            for s in parts[1:]:
                out = out.fillna("") + sep + s.fillna("")
            series = out
            continue

        if op == "cast":
            # Convert the working series to a specific data type
            if series is None:
                raise MappingExecutionError(
                    f"cast requires a prior series for target {target}"
                )
            to = step.get("to")
            if to == "string":
                series = series.astype("string")
                continue
            if to == "json":
                series = series.astype("string")
                continue
            if to == "float":
                series = pd.to_numeric(series, errors="coerce")
                continue
            if to == "int":
                series = pd.to_numeric(series, errors="coerce").astype("Int64")
                continue
            if to == "datetime":
                dt_series = pd.to_datetime(series, errors="coerce")
                series = ensure_utc_datetime(dt_series)
                continue
            if to == "decimal":
                scale = step.get("scale")
                if scale is not None and not isinstance(scale, int):
                    raise MappingExecutionError(
                        f"cast decimal scale must be int for target {target}"
                    )
                precision = step.get("precision")
                if precision is not None and not isinstance(precision, int):
                    raise MappingExecutionError(
                        f"cast decimal precision must be int for target {target}"
                    )
                series = _cast_decimal(series, scale=scale, precision=precision)
                continue

            raise MappingExecutionError(
                f"Unsupported cast.to={to!r} for target {target}"
            )

        if op == "round":
            # Round numeric values in the series
            if series is None:
                raise MappingExecutionError(
                    f"round requires a prior series for target {target}"
                )
            ndigits = step.get("ndigits", 0)
            if not isinstance(ndigits, int):
                raise MappingExecutionError(
                    f"round.ndigits must be int for target {target}"
                )
            series = pd.to_numeric(series, errors="coerce").round(ndigits)
            continue

        if op == "math":
            # Perform row-wise arithmetic calculations
            operator = step.get("operator")
            operands = step.get("operands")
            if not isinstance(operator, str) or operator not in {
                "add",
                "sub",
                "mul",
                "div",
            }:
                raise MappingExecutionError(
                    f"math.operator must be one of add/sub/mul/div for target {target}"
                )
            if not isinstance(operands, list) or not operands:
                raise MappingExecutionError(
                    f"math.operands must be a non-empty list for target {target}"
                )

            resolved: list[pd.Series] = []
            for operand in operands:
                if not isinstance(operand, dict) or not operand:
                    raise MappingExecutionError(
                        f"math operand must be a mapping for target {target}"
                    )
                if operand.get("current") is True:
                    if series is None:
                        raise MappingExecutionError(
                            f"math operand uses current but no prior series for target {target}"
                        )
                    resolved.append(pd.to_numeric(series, errors="coerce"))
                    continue
                if "column" in operand:
                    col = operand.get("column")
                    if not isinstance(col, str) or not col:
                        raise MappingExecutionError(
                            f"math operand.column must be string for target {target}"
                        )
                    s = df[col] if col in df.columns else pd.Series([pd.NA] * len(df))
                    resolved.append(pd.to_numeric(s, errors="coerce"))
                    continue
                if "const" in operand:
                    value = operand.get("const")
                    resolved.append(pd.Series([value] * len(df)))
                    continue
                raise MappingExecutionError(
                    f"math operand must include one of: current=true, column, const for target {target}"
                )

            if operator == "add":
                out = resolved[0]
                for s in resolved[1:]:
                    out = out + s
                series = out
                continue
            if operator == "mul":
                out = resolved[0]
                for s in resolved[1:]:
                    out = out * s
                series = out
                continue
            if operator in {"sub", "div"}:
                if len(resolved) != 2:
                    raise MappingExecutionError(
                        f"math operator {operator} requires exactly 2 operands for target {target}"
                    )
                a, b = resolved
                series = a - b if operator == "sub" else a / b
                continue

        if op == "when":
            # Basic conditional assignment
            col = step.get("column")
            value = step.get("value")
            then_value = step.get("then")
            else_value = step.get("else", pd.NA)
            if not isinstance(col, str) or not col:
                raise MappingExecutionError(
                    f"when requires 'column' for target {target}"
                )
            src = df[col] if col in df.columns else pd.Series([pd.NA] * len(df))
            mask = src == value
            series = pd.Series([else_value] * len(df))
            series = series.where(~mask, other=then_value)
            continue

        if op == "pandas_expr":
            expr = step.get("expr")
            if not isinstance(expr, str) or not expr:
                raise MappingExecutionError(
                    f"pandas_expr requires non-empty 'expr' for target {target}"
                )
            series = _eval_pandas_expr(expr, df=df, current=series, target=target)
            continue

        if op == "sql":
            # DuckDB SQL expression (recommended over pandas_expr)
            import duckdb

            expr = step.get("expr")
            query = step.get("query")
            if not expr and not query:
                raise MappingExecutionError(
                    f"sql requires 'expr' or 'query' for target {target}"
                )
            try:
                conn = duckdb.connect(":memory:")
                conn.register("src", df)
                if expr:
                    result = conn.execute(f"SELECT {expr} AS result FROM src").df()["result"]
                else:
                    # Basic safety check
                    query_upper = query.strip().upper()
                    if not (query_upper.startswith("SELECT") or query_upper.startswith("WITH")):
                         raise MappingExecutionError(
                            f"sql query for target {target} must start with SELECT or WITH"
                        )
                    result = conn.execute(query).df().iloc[:, 0]
                series = result
                
                # If the result is datetime-like, ensure it's converted to UTC
                if pd.api.types.is_datetime64_any_dtype(series):
                    series = ensure_utc_datetime(series)
                        
            except Exception as e:
                raise MappingExecutionError(
                    f"sql failed for target {target}: {e}"
                ) from e
            continue

        raise MappingExecutionError(f"Unknown op '{op}' for target {target}")

    if series is None:
        return pd.Series([pd.NA] * len(df))
    return series


def _cast_decimal(
    series: pd.Series, *, scale: int | None, precision: int | None
) -> pd.Series:
    """Safely converts a series to Decimal objects with optional scaling/precision."""

    def conv(v: Any) -> Any:
        if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA:
            return None
        try:
            d = Decimal(str(v))
            if scale is not None:
                q = Decimal(1).scaleb(-scale)
                d = d.quantize(q)
            if precision is not None:
                tup = d.as_tuple()
                digits = len(tup.digits)
                exp = tup.exponent
                actual_precision = digits + exp if exp >= 0 else digits
                if actual_precision > precision:
                    return None
            return d
        except (InvalidOperation, ValueError):
            return None

    return series.map(conv)
