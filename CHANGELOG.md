# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-02-07

### 🎉 Library API & v1.3 Support

This release introduces a stable Python library API, full support for FOCUS v1.3, and flexible external spec management.

### Features

#### Library API
- New `focus_mapper.api` module with high-level entrypoints:
  - **`generate()`**: Generate FOCUS reports programmatically
  - **`validate()`**: Validate existing datasets
  - **`validate_mapping()`**: Check mapping configuration validity
- Exported type definitions for better IDE support/type hinting

#### FOCUS v1.3 Support
- Full support for **FOCUS v1.3** specification
- **Default Version Change**: `v1.3` is now the default version for CLI and library (previously `v1.2`)
- **Metadata**: Support for v1.3 metadata collections (`DatasetInstance`, `Recency`, `Schema`, `DataGenerator`)
- **DataGenerator Customization**: usage of `FOCUS_DATA_GENERATOR_NAME` and `FOCUS_DATA_GENERATOR_VERSION` environment variables
- **Validation**: Updated validation rules for v1.3 columns and constraints

#### External Spec Management
- **Overrides**: Load custom/development specs from external directory using:
  - CLI: `--spec-dir /path/to/specs`
  - Env Var: `FOCUS_SPEC_DIR=/path/to/specs`
  - API parameter: `generate(..., spec_dir="/path/to/specs")`
- **Naming Convention**: Spec files now use `focus_spec_vX.Y.json` format
- **Populate Tool**: Defaults to `specification/datasets/cost_and_usage/columns` for v1.3+

### Changed
- **Defaults**: All tools now default to FOCUS `v1.3`
- **CLI**: Added `--spec-dir` flag to `generate` and `validate` commands
- **File Naming**: Renamed internal spec files from `focus_vX_Y.json` to `focus_spec_vX.Y.json`
- **Validation**: Improved severity handling (Mandatory/Recommended/Conditional/Optional)

## [0.1.0] - 2026-02-07

### 🎉 Initial Release

**focus-mapper** is a Python library and CLI tool for generating FinOps FOCUS-compliant reports from tabular billing/telemetry data.

### Features

#### Library API
- **`generate()`** - Full FOCUS generation pipeline from input data + mapping YAML
- **`validate()`** - Validate FOCUS datasets against specification
- **`validate_mapping()`** - Validate mapping YAML configuration before use

#### CLI Tools
- **`focus-mapper generate`** - Generate FOCUS reports with metadata and validation
- **`focus-mapper validate`** - Validate existing FOCUS datasets
- **`focus-mapper-wizard`** - Interactive wizard to create mapping YAML files

#### Spec Population Tool
- **`tools/populate_focus_spec.py`** - Download and store FOCUS spec versions from upstream repository
- Supports custom git refs for unreleased spec versions
- Automatically extracts column definitions and constraints

#### FOCUS Specification Support
- **v1.1**, **v1.2**, **v1.3** specification versions supported
- Automatic type coercion to spec-defined data types
- Column presence validation with feature-level severity:
  - Mandatory → ERROR
  - Recommended → WARN
  - Conditional → INFO
  - Optional → No finding

#### Mapping Operations
11 mapping operations for transforming input data:
- `from_column` - Map from source column
- `const` - Static value for all rows
- `null` - Null value for all rows
- `coalesce` - First non-null from multiple columns
- `map_values` - Dictionary-based value mapping
- `concat` - Join multiple columns
- `cast` - Type conversion (string, int, float, decimal, datetime)
- `round` - Numeric rounding
- `math` - Arithmetic operations (add, sub, mul, div)
- `when` - Conditional value assignment
- `pandas_expr` - Custom pandas expressions (sandboxed)

#### Metadata Generation
- **v1.2**: Object-based metadata structure
- **v1.3**: Collection-based metadata with:
  - `DatasetInstance` - Dataset identification
  - `Recency` - TimeSectors and completeness tracking
  - `Schema` - Column definitions with FOCUS version
  - `DataGenerator` - Tool identification

#### Validation
- Column presence by feature level
- Nullability enforcement
- Allowed values with optional case-insensitivity
- Type validation (decimal, datetime, string, JSON)
- Per-column validation overrides in mapping YAML
- JSON validation report output

#### Output Formats
- CSV and Parquet output
- Parquet metadata embedding
- Sidecar JSON metadata files

### Installation

```bash
pip install focus-mapper

# With Parquet support
pip install focus-mapper[parquet]
```

### Quick Example

```python
from focus_mapper import generate

result = generate(
    input_data="billing.csv",
    mapping="mapping.yaml",
    output_path="focus.parquet",
)

if result.is_valid:
    print(f"Generated {len(result.output_df)} FOCUS-compliant rows")
```

### Links

- [Documentation](https://github.com/quickwind/focus-mapper#readme)
- [PyPI](https://pypi.org/project/focus-mapper/)
- [GitHub](https://github.com/quickwind/focus-mapper)
