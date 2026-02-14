"""Utilities for normalizing and formatting timezone-aware datetime series."""

from __future__ import annotations

import pandas as pd


def ensure_utc_datetime(series: pd.Series) -> pd.Series:
    """
    Convert a pandas Series to UTC timezone.
    
    This function handles both timezone-naive and timezone-aware datetime series:
    - Timezone-naive: treated as UTC (no conversion, just add UTC timezone)
    - Timezone-aware: converted to UTC
    
    Args:
        series: pandas Series with datetime values
        
    Returns:
        pandas Series with datetime values in UTC timezone
        
    Example:
        >>> import pandas as pd
        >>> # Timezone-naive (treated as UTC)
        >>> naive = pd.Series(['2024-01-01 12:00:00'])
        >>> naive_dt = pd.to_datetime(naive)
        >>> utc_series = ensure_utc_datetime(naive_dt)
        >>> print(utc_series.dt.tz)  # UTC
        
        >>> # Timezone-aware (converted to UTC)
        >>> aware = pd.Series(['2024-01-01 12:00:00+05:30'])
        >>> aware_dt = pd.to_datetime(aware)
        >>> utc_series = ensure_utc_datetime(aware_dt)
        >>> print(utc_series.dt.tz)  # UTC
    """
    # Handle mixed timezone series (object dtype with Timestamp objects)
    if series.dtype == 'object':
        # Convert each timestamp individually to ensure consistent timezone handling
        converted_values = []
        for item in series:
            if pd.isna(item):
                converted_values.append(pd.NaT)
            elif isinstance(item, pd.Timestamp):
                if item.tz is None:
                    # Treat timezone-naive as UTC
                    converted_values.append(item.tz_localize('UTC'))
                else:
                    # Convert timezone-aware to UTC
                    converted_values.append(item.tz_convert('UTC'))
            else:
                # Try to parse as datetime if it's a string
                try:
                    dt = pd.to_datetime(item)
                    if dt.tz is None:
                        converted_values.append(dt.tz_localize('UTC'))
                    else:
                        converted_values.append(dt.tz_convert('UTC'))
                except Exception:
                    converted_values.append(pd.NaT)
        return pd.Series(converted_values)
    
    # Handle regular datetime64 series
    if not pd.api.types.is_datetime64_any_dtype(series):
        raise ValueError("Series must contain datetime values")
    
    # Create a copy to avoid modifying the original series
    result = series.copy()
    
    if result.dt.tz is None:
        # Treat timezone-naive datetimes as UTC
        result = result.dt.tz_localize('UTC')
    else:
        # Convert timezone-aware datetimes to UTC
        result = result.dt.tz_convert('UTC')
    
    return result


def format_datetime_iso8601(series: pd.Series) -> pd.Series:
    """
    Format a UTC datetime Series as ISO8601 strings with Z suffix.
    
    Args:
        series: pandas Series with datetime values in UTC timezone
        
    Returns:
        pandas Series with ISO8601 formatted strings (e.g., "2024-01-01T12:00:00Z")
        
    Example:
        >>> import pandas as pd
        >>> dt_series = pd.Series(['2024-01-01 12:00:00'])
        >>> dt_series = pd.to_datetime(dt_series).dt.tz_localize('UTC')
        >>> formatted = format_datetime_iso8601(dt_series)
        >>> print(formatted.iloc[0])  # "2024-01-01T12:00:00Z"
    """
    # Handle object dtype series (mixed timezone timestamps)
    if series.dtype == 'object':
        # First ensure UTC conversion
        utc_series = ensure_utc_datetime(series)
        # Then format each timestamp
        formatted_values = []
        for item in utc_series:
            if pd.isna(item):
                formatted_values.append(pd.NA)
            elif isinstance(item, pd.Timestamp):
                # Include microseconds if present
                if item.microsecond > 0:
                    formatted_values.append(item.strftime('%Y-%m-%dT%H:%M:%S.%fZ'))
                else:
                    formatted_values.append(item.strftime('%Y-%m-%dT%H:%M:%SZ'))
            else:
                formatted_values.append(pd.NA)
        return pd.Series(formatted_values)
    
    # Handle regular datetime64 series
    if not pd.api.types.is_datetime64_any_dtype(series):
        raise ValueError("Series must contain datetime values")
    
    # Ensure UTC first
    utc_series = ensure_utc_datetime(series)
    
    # Format as ISO8601 with Z suffix, include microseconds if present
    if utc_series.dt.microsecond.any():
        return utc_series.dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    else:
        return utc_series.dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def ensure_utc_and_format_datetime(series: pd.Series) -> pd.Series:
    """
    Convert a datetime Series to UTC and format as ISO8601 with Z suffix.
    
    This is a convenience function that combines ensure_utc_datetime and 
    format_datetime_iso8601 for the most common use case.
    
    Args:
        series: pandas Series with datetime values
        
    Returns:
        pandas Series with ISO8601 formatted strings in UTC
        
    Example:
        >>> import pandas as pd
        >>> dt_series = pd.Series(['2024-01-01 12:00:00'])
        >>> dt_series = pd.to_datetime(dt_series)
        >>> formatted = ensure_utc_and_format_datetime(dt_series)
        >>> print(formatted.iloc[0])  # "2024-01-01T12:00:00Z"
    """
    return format_datetime_iso8601(series)
