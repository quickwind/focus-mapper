# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-02-09

### Added
- **Windows Build Support**: Added tooling to build standalone Windows executables (`focus-mapper.exe` and `focus-mapper-wizard.exe`) using PyInstaller.
  - Included `tools/windows/build.bat` and `tools/windows/build.ps1` scripts for easy building.
  - Configured `tools/windows/focus_mapper.spec` for correct packaging.
- **Spec Version Merging**: The wizard and CLI now merge custom spec versions (from `--spec-dir`) with built-in versions, allowing users to select either from a single list.
- **Extension Column Persistence**:
  - The wizard now persists the `Data Type` and `Description` of extension columns to the mapping YAML and sidecar metadata.
  - Added global prompt for validation overrides to streamline the wizard experience.
  - Improved column header display in the wizard to show data type and value format.

## [0.5.0] - 2026-02-08

### Added
- **Resumable Wizard**: The wizard now prompts for an output path early and can resume from an existing mapping file, skipping already configured columns.
- **Incremental Saving**: The wizard saves the mapping file after every successful column definition to prevent data loss.
- **CLI**: Added `--spec-dir` argument to `focus-mapper-wizard` to consistent with other tools.
- **Skipped Columns Persistence**: The wizard now remembers which columns you explicitly skipped, preventing re-prompting when resuming a mapping session.
- **Enhanced Extension Columns**:
  - **Auto-Prefix**: Automatically appends `x_` to extension column names if omitted.
  - **Full Mapping Support**: Extension columns now support all mapping operations (SQL, Pandas, Const, etc.) and data type selection.

### Fixed
- **Null Operation**: Fixed a bug where selecting the `null` operation had no effect when `allow_nulls: true`.
- **Live Preview Validation**: The wizard's "Live Preview" now validates results against column constraints (e.g., checks for nulls in mandatory columns) and warns on type mismatches.
- **Prompt Ordering**: Moved Dataset Instance Name prompt to the start of the wizard for v1.3+ specs.

### Refactored
- **Spec Resolution**: Consolidated logic for resolving external spec directories into a reusable helper `_resolve_spec_search_paths`, eliminating code duplication in `focus_mapper/spec.py`.

## [0.4.0] - 2026-02-08

### New Feature: Wizard Live Preview

The interactive mapping wizard (`focus-mapper-wizard`) now provides **real-time feedback** when defining complex transformation steps.

- **Live Dry-Run**: When you add a `sql` or `pandas_expr` step, the wizard automatically executes it against a sample of your input data (first 100 rows).
- **Instant Result Preview**: Successfully validated steps show the first 5 result values immediately (e.g., `0 123.45`, `1 67.89`), giving you confidence that your expression is correct.
- **Error Reporting**: Syntax errors or invalid column references are caught instantly, allowing you to retry without restarting the wizard.

### Improvements

- **Performance**: Optimized sample data loading using `nrows` for instant feedback even on large datasets.

## [0.3.0] - 2026-02-08

### New Feature: SQL Operation (DuckDB Support)

We are excited to introduce the `sql` operation, powered by DuckDB. This is now the **recommended** method for complex transformations, offering better performance and standard SQL syntax compared to `pandas_expr`.

#### Key Capabilities
- **Expression Mode (`expr`)**: Simple column arithmetic or SQL functions.
  ```yaml
  - op: sql
    expr: "billed_cost + tax_amount"
  ```
- **Query Mode (`query`)**: Full SQL power, including window functions and aggregations.
  ```yaml
  - op: sql
    query: "SELECT SUM(billed_cost) OVER (PARTITION BY billing_account_id ORDER BY billing_date) FROM src"
  ```
  *(Note: Queries must select from the `src` table and return a single column.)*

### Improvements

#### CLI & API
- **Strict Prompt Validation**: Interactive prompts now rigidly require "y/n" or "yes/no" inputs.
- **Automation Flags**: New CLI flags `--dataset-complete` and `--dataset-incomplete` allow skipping interactive prompts for CostAndUsage datasets.
- **API Enhancement**: The `generate()` function now accepts a `sector_complete_map` parameter for granular programmatic control over TimeSector completeness.

#### Documentation & Templates
- **Updated Wizard**: The mapping wizard now includes the `sql` operation as a standard option.
- **Enhanced Examples**: `README.md` and test fixtures now demonstrate best practices for using SQL in your mappings.

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
- **Dependencies**: Relaxed pandas requirement to `>=1.5`. Added `pandas15` optional extra.
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
