# Changelog

## 0.1.0
- Initial public release of focus-mapper.
- YAML-driven mapping from arbitrary tabular data to FOCUS-compliant reports.
- Interactive wizard for building mappings and validation defaults.
- Safe `pandas_expr` support for calculated columns.
- Validation engine with per-column overrides (type, precision/scale, string length, nullable, allowed values).
- Multi-spec support (v1.0–v1.3) with spec populate tool.
- Metadata sidecar generation following FOCUS schema.
- CLI + library usage support.
- Windows path and column name autocomplete improvements.
- CI with pandas 1.5/2.x compatibility and coverage reporting.
