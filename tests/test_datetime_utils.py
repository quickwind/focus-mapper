"""
Unit tests for datetime utility functions.

Tests cover various timezone scenarios and edge cases to ensure
proper UTC conversion and ISO8601 formatting.
"""

import pandas as pd
import pytest
from datetime import datetime, timezone, timedelta

from focus_mapper.datetime_utils import (
    ensure_utc_datetime,
    format_datetime_iso8601,
    ensure_utc_and_format_datetime,
)


class TestEnsureUtcDatetime:
    """Test the ensure_utc_datetime function."""

    def test_timezone_naive_datetime(self):
        """Test timezone-naive datetimes are treated as UTC."""
        # Create timezone-naive datetime series
        series = pd.Series([
            '2024-01-01 12:00:00',
            '2024-01-02 15:30:00',
            '2024-01-03 00:00:00'
        ])
        dt_series = pd.to_datetime(series)
        
        result = ensure_utc_datetime(dt_series)
        
        # Should have UTC timezone
        assert result.dt.tz is not None
        assert str(result.dt.tz) == 'UTC'
        
        # Values should remain the same (treated as UTC)
        expected = pd.to_datetime(series).dt.tz_localize('UTC')
        pd.testing.assert_series_equal(result, expected)

    def test_timezone_aware_datetime_utc(self):
        """Test timezone-aware datetimes already in UTC."""
        # Create UTC timezone-aware datetime series
        series = pd.Series([
            '2024-01-01 12:00:00+00:00',
            '2024-01-02 15:30:00+00:00',
            '2024-01-03 00:00:00+00:00'
        ])
        dt_series = pd.to_datetime(series)
        
        result = ensure_utc_datetime(dt_series)
        
        # Should still have UTC timezone
        assert result.dt.tz is not None
        assert str(result.dt.tz) == 'UTC'
        
        # Values should remain the same
        pd.testing.assert_series_equal(result, dt_series)

    def test_timezone_aware_datetime_non_utc(self):
        """Test timezone-aware datetimes in other timezones are converted to UTC."""
        # Create timezone-aware datetime series in different timezones
        # Use individual timestamps to avoid mixed timezone parsing issues
        ist_dt = pd.Timestamp('2024-01-01 12:00:00+05:30')
        pst_dt = pd.Timestamp('2024-01-02 15:30:00-08:00')
        cet_dt = pd.Timestamp('2024-01-03 00:00:00+02:00')
        
        series = pd.Series([ist_dt, pst_dt, cet_dt])
        
        result = ensure_utc_datetime(series)
        
        # Should have UTC timezone
        assert result.dt.tz is not None
        assert str(result.dt.tz) == 'UTC'
        
        # Values should be converted to UTC
        expected_values = [
            pd.Timestamp('2024-01-01 06:30:00+00:00'),  # IST -> UTC
            pd.Timestamp('2024-01-02 23:30:00+00:00'),  # PST -> UTC  
            pd.Timestamp('2024-01-02 22:00:00+00:00'),  # CET -> UTC
        ]
        expected = pd.Series(expected_values)
        pd.testing.assert_series_equal(result, expected)

    def test_mixed_timezone_scenarios(self):
        """Test mixed timezone-naive and timezone-aware values."""
        # Create series with mixed timezone scenarios using individual timestamps
        naive_dt = pd.Timestamp('2024-01-01 12:00:00')
        utc_dt = pd.Timestamp('2024-01-01 12:00:00+00:00')
        ist_dt = pd.Timestamp('2024-01-01 17:30:00+05:30')
        
        series = pd.Series([naive_dt, utc_dt, ist_dt])
        
        result = ensure_utc_datetime(series)
        
        # All should be UTC
        assert result.dt.tz is not None
        assert str(result.dt.tz) == 'UTC'
        
        # Values should be correct
        expected = pd.Series([
            pd.Timestamp('2024-01-01 12:00:00+00:00'),  # naive -> UTC
            pd.Timestamp('2024-01-01 12:00:00+00:00'),  # UTC stays UTC
            pd.Timestamp('2024-01-01 12:00:00+00:00'),  # IST -> UTC
        ])
        pd.testing.assert_series_equal(result, expected)

    def test_null_and_na_values(self):
        """Test handling of null/NaT values."""
        series = pd.Series([
            '2024-01-01 12:00:00',
            None,
            pd.NaT,
            '2024-01-02 15:30:00'
        ])
        dt_series = pd.to_datetime(series)
        
        result = ensure_utc_datetime(dt_series)
        
        # Should have UTC timezone for non-null values
        assert result.dt.tz is not None
        assert str(result.dt.tz) == 'UTC'
        
        # Null values should be preserved
        assert pd.isna(result.iloc[1])
        assert pd.isna(result.iloc[2])
        
        # Non-null values should be UTC
        assert not pd.isna(result.iloc[0])
        assert not pd.isna(result.iloc[3])

    def test_empty_series(self):
        """Test handling of empty series."""
        series = pd.Series([], dtype='datetime64[ns]')
        
        result = ensure_utc_datetime(series)
        
        # Should return empty series with same dtype
        assert len(result) == 0
        assert result.dtype == 'datetime64[ns, UTC]'

    def test_non_datetime_series_raises_error(self):
        """Test that non-datetime series raise appropriate error."""
        series = pd.Series([1, 2, 3])
        
        with pytest.raises(ValueError, match="Series must contain datetime values"):
            ensure_utc_datetime(series)

    def test_original_series_not_modified(self):
        """Test that the original series is not modified."""
        original = pd.Series(['2024-01-01 12:00:00'])
        dt_series = pd.to_datetime(original)
        
        result = ensure_utc_datetime(dt_series)
        
        # Original should be unchanged
        assert dt_series.dt.tz is None
        
        # Result should have UTC timezone
        assert result.dt.tz is not None


class TestFormatDatetimeIso8601:
    """Test the format_datetime_iso8601 function."""

    def test_format_utc_datetime(self):
        """Test formatting UTC datetime to ISO8601."""
        series = pd.Series([
            '2024-01-01 12:00:00+00:00',
            '2024-01-02 15:30:00+00:00',
        ])
        dt_series = pd.to_datetime(series)
        
        result = format_datetime_iso8601(dt_series)
        
        # Should be string type
        assert result.dtype == 'object'
        assert all(isinstance(x, str) for x in result.dropna())
        
        # Should have Z suffix
        assert result.iloc[0] == '2024-01-01T12:00:00Z'
        assert result.iloc[1] == '2024-01-02T15:30:00Z'

    def test_format_non_utc_datetime_converts_first(self):
        """Test that non-UTC datetimes are converted to UTC before formatting."""
        # Use individual timestamps to avoid mixed timezone parsing issues
        ist_dt = pd.Timestamp('2024-01-01 12:00:00+05:30')  # IST
        pst_dt = pd.Timestamp('2024-01-02 15:30:00-08:00')  # PST
        
        series = pd.Series([ist_dt, pst_dt])
        
        result = format_datetime_iso8601(series)
        
        # Should be converted to UTC and formatted
        assert result.iloc[0] == '2024-01-01T06:30:00Z'  # IST -> UTC
        assert result.iloc[1] == '2024-01-02T23:30:00Z'  # PST -> UTC

    def test_format_naive_datetime_treats_as_utc(self):
        """Test that timezone-naive datetimes are treated as UTC."""
        series = pd.Series([
            '2024-01-01 12:00:00',
            '2024-01-02 15:30:00',
        ])
        dt_series = pd.to_datetime(series)
        
        result = format_datetime_iso8601(dt_series)
        
        # Should be formatted as if UTC
        assert result.iloc[0] == '2024-01-01T12:00:00Z'
        assert result.iloc[1] == '2024-01-02T15:30:00Z'

    def test_format_with_nulls(self):
        """Test formatting with null values."""
        series = pd.Series([
            '2024-01-01 12:00:00',
            None,
            pd.NaT,
            '2024-01-02 15:30:00'
        ])
        dt_series = pd.to_datetime(series)
        
        result = format_datetime_iso8601(dt_series)
        
        # Non-null values should be formatted
        assert result.iloc[0] == '2024-01-01T12:00:00Z'
        assert result.iloc[3] == '2024-01-02T15:30:00Z'
        
        # Null values should be preserved as NaN
        assert pd.isna(result.iloc[1])
        assert pd.isna(result.iloc[2])

    def test_non_datetime_series_raises_error(self):
        """Test that non-datetime series raise appropriate error."""
        series = pd.Series([1, 2, 3])
        
        with pytest.raises(ValueError, match="Series must contain datetime values"):
            format_datetime_iso8601(series)


class TestEnsureUtcAndFormatDatetime:
    """Test the ensure_utc_and_format_datetime convenience function."""

    def test_convenience_function(self):
        """Test the convenience function combines both operations."""
        # Use individual timestamps to avoid mixed timezone parsing issues
        naive_dt = pd.Timestamp('2024-01-01 12:00:00')        # naive
        ist_dt = pd.Timestamp('2024-01-02 15:30:00+05:30')  # IST
        pst_dt = pd.Timestamp('2024-01-03 08:00:00-08:00')  # PST
        
        series = pd.Series([naive_dt, ist_dt, pst_dt])
        
        result = ensure_utc_and_format_datetime(series)
        
        # Should be string type with Z suffix
        assert result.dtype == 'object'
        assert all(isinstance(x, str) for x in result.dropna())
        
        # Should be properly converted and formatted
        assert result.iloc[0] == '2024-01-01T12:00:00Z'  # naive -> UTC
        assert result.iloc[1] == '2024-01-02T10:00:00Z'  # IST -> UTC
        assert result.iloc[2] == '2024-01-03T16:00:00Z'  # PST -> UTC

    def test_with_nulls(self):
        """Test convenience function with null values."""
        naive_dt = pd.Timestamp('2024-01-01 12:00:00')
        ist_dt = pd.Timestamp('2024-01-02 15:30:00+05:30')
        
        series = pd.Series([naive_dt, None, ist_dt])
        
        result = ensure_utc_and_format_datetime(series)
        
        # Should handle nulls properly
        assert result.iloc[0] == '2024-01-01T12:00:00Z'
        assert pd.isna(result.iloc[1])
        assert result.iloc[2] == '2024-01-02T10:00:00Z'


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_microseconds_precision(self):
        """Test handling of microseconds precision."""
        # Use individual timestamps to avoid parsing issues
        naive_dt = pd.Timestamp('2024-01-01 12:00:00.123456')
        ist_dt = pd.Timestamp('2024-01-02 15:30:00.789012+05:30')
        
        series = pd.Series([naive_dt, ist_dt])
        
        result = ensure_utc_and_format_datetime(series)
        
        # Should preserve microseconds
        assert result.iloc[0] == '2024-01-01T12:00:00.123456Z'
        assert result.iloc[1] == '2024-01-02T10:00:00.789012Z'

    def test_leap_second_handling(self):
        """Test handling of leap seconds (if supported)."""
        # Note: pandas may not fully support leap seconds
        series = pd.Series(['2016-12-31 23:59:60'])  # Leap second
        dt_series = pd.to_datetime(series, errors='coerce')
        
        if not pd.isna(dt_series.iloc[0]):
            result = ensure_utc_and_format_datetime(dt_series)
            # Should handle gracefully
            assert isinstance(result.iloc[0], str)

    def test_very_large_dates(self):
        """Test handling of very large dates."""
        series = pd.Series(['2099-12-31 23:59:59'])
        dt_series = pd.to_datetime(series)
        
        result = ensure_utc_and_format_datetime(dt_series)
        
        assert result.iloc[0] == '2099-12-31T23:59:59Z'

    def test_very_small_dates(self):
        """Test handling of very small dates."""
        series = pd.Series(['1900-01-01 00:00:00'])
        dt_series = pd.to_datetime(series)
        
        result = ensure_utc_and_format_datetime(dt_series)
        
        assert result.iloc[0] == '1900-01-01T00:00:00Z'

    def test_dst_transitions(self):
        """Test handling of daylight saving time transitions."""
        # Use individual timestamps to avoid mixed timezone parsing issues
        # This might behave differently based on the system timezone
        # but our function should normalize everything to UTC
        dt1 = pd.Timestamp('2024-03-10 02:30:00-05:00')  # During DST transition (US)
        dt2 = pd.Timestamp('2024-11-03 01:30:00-04:00')  # During DST transition (US)
        
        series = pd.Series([dt1, dt2])
        
        result = ensure_utc_and_format_datetime(series)
        
        # Should convert to UTC properly regardless of DST
        assert result.iloc[0] == '2024-03-10T07:30:00Z'
        assert result.iloc[1] == '2024-11-03T05:30:00Z'


if __name__ == "__main__":
    pytest.main([__file__])
