"""Custom exception hierarchy for focus-mapper runtime and validation errors."""

class FocusReportError(Exception):
    """Base exception for focus-mapper domain errors."""
    pass


class SpecError(FocusReportError):
    """Raised when loading/using FOCUS spec artifacts fails."""
    pass


class MappingConfigError(FocusReportError):
    """Raised for invalid mapping YAML structure or content."""
    pass


class MappingExecutionError(FocusReportError):
    """Raised when executing mapping steps fails."""
    pass


class ValidationError(FocusReportError):
    """Raised for validation pipeline failures."""
    pass


class ParquetUnavailableError(FocusReportError):
    """Raised when Parquet functionality requires unavailable dependencies."""
    pass
