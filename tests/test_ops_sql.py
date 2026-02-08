import pandas as pd
import pytest
from focus_mapper.mapping.ops import apply_steps
from focus_mapper.errors import MappingExecutionError

def test_ops_sql_basic():
    """Test basic SQL expression evaluation."""
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    steps = [{"op": "sql", "expr": "a + b"}]
    result = apply_steps(df, steps=steps, target="Total")
    # DuckDB return type might depend on column types, but values should match
    expected = pd.Series([5, 7, 9], name="result")
    pd.testing.assert_series_equal(result, expected, check_names=False, check_dtype=False)

def test_ops_sql_query():
    """Test full SQL query mode."""
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    steps = [{"op": "sql", "query": "SELECT a * b FROM src"}]
    result = apply_steps(df, steps=steps, target="Product")
    expected = pd.Series([4, 10, 18], name="a * b")
    pd.testing.assert_series_equal(result, expected, check_names=False, check_dtype=False)

def test_ops_sql_missing_args():
    """Test error when expr and query are missing."""
    df = pd.DataFrame({"a": [1]})
    steps = [{"op": "sql"}]
    with pytest.raises(MappingExecutionError, match="sql requires 'expr' or 'query'"):
        apply_steps(df, steps=steps, target="Bad")

def test_ops_sql_invalid_syntax():
    """Test error on invalid SQL syntax."""
    df = pd.DataFrame({"a": [1]})
    steps = [{"op": "sql", "expr": "a +"}] # Syntax error
    with pytest.raises(MappingExecutionError, match="sql failed"):
        apply_steps(df, steps=steps, target="BadSyntax")

def test_ops_sql_date():
    """Test DuckDB date functions."""
    df = pd.DataFrame({
        "d": ["2023-01-01", "2023-01-02"]
    })
    # DuckDB date function
    steps = [{"op": "sql", "expr": "CAST(d AS DATE) + INTERVAL 1 DAY"}]
    result = apply_steps(df, steps=steps, target="NextDay")
    
    # Check values
    assert result.iloc[0].year == 2023
    assert result.iloc[0].month == 1
    assert result.iloc[0].day == 2

def test_ops_sql_safety_check():
    """Test that non-SELECT/WITH queries are rejected."""
    df = pd.DataFrame({"a": [1]})
    steps = [{"op": "sql", "query": "DROP TABLE src"}]
    with pytest.raises(MappingExecutionError, match="must start with SELECT or WITH"):
        apply_steps(df, steps=steps, target="BadQuery")
