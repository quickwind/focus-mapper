# focus-report

Generate FinOps FOCUS v1.2 compliant reports from a pre-flattened telemetry/billing table.

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install -e ".[dev]"

python -m focus_report --help
pytest -q
```

## Generate

```bash
python -m focus_report generate \
  --spec v1.2 \
  --input telemetry.csv \
  --mapping mapping.yaml \
  --output focus.csv \
  --metadata-out focus.focus-metadata.json \
  --validation-out focus.validation.json
```

## Mapping Wizard

Interactive wizard to create a mapping YAML based on a sample input file:

```bash
focus-report-wizard \
  --spec v1.2 \
  --input telemetry.csv \
  --output mapping.yaml
```

You can also run the wizard with no arguments and it will prompt for values:

```bash
focus-report-wizard
```

Optional flags:
- `--include-recommended` to include Recommended columns
- `--include-optional` to include Optional columns

## Mapping YAML Specification

The mapping file is a YAML document that defines how input columns are transformed into FOCUS spec columns.

### Top-level Structure
```yaml
spec_version: "1.2"
mappings:
  # Standard FOCUS columns or extension columns (x_ prefix)
  BilledCost:
    description: "Optional description for metadata"
    steps:
      - op: from_column
        column: "raw_cost"
      - op: cast
        to: "decimal"
        scale: 2
```

### Supported Operations (`op`)

| Operation | Description | Parameters |
|-----------|-------------|------------|
| `from_column` | Load value from an input column | `column` (string) |
| `const` | Set a constant value | `value` (any) |
| `coalesce` | Take the first non-null value from a list of columns | `columns` (list) |
| `map_values` | Map input values to new values using a dictionary | `mapping` (dict), `default` (optional), `column` (optional if piped) |
| `concat` | Concatenate multiple columns into a string | `columns` (list), `sep` (string, default "") |
| `cast` | Convert value type | `to` ("string", "float", "int", "datetime", "decimal"), `scale` (int, for decimal) |
| `round` | Round numeric values | `ndigits` (int, default 0) |
| `math` | Perform arithmetic | `operator` ("add", "sub", "mul", "div"), `operands` (list of `{current: true}`, `{column: name}`, or `{const: value}`) |
| `when` | Simple conditional (if column == value then X else Y) | `column`, `value`, `then`, `else` |

### Extension Columns
Custom columns MUST start with `x_` prefix. They will be appended to the output dataset and documented in the generated metadata if a `description` is provided.

## Validate

```bash
python -m focus_report validate \
  --spec v1.2 \
  --input focus.csv \
  --out focus.validation.json
```
