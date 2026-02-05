class FocusReportError(Exception):
    pass


class SpecError(FocusReportError):
    pass


class MappingConfigError(FocusReportError):
    pass


class MappingExecutionError(FocusReportError):
    pass


class ValidationError(FocusReportError):
    pass


class ParquetUnavailableError(FocusReportError):
    pass
