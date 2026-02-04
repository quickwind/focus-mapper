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

The mapping file is a YAML document that defines how your input columns are transformed into FinOps FOCUS compliant columns.

### Core Concept: The Pipeline
Each column in the `mappings` section is defined as a series of **steps**. Steps are executed in order, and the output of one step is passed as the input to the next.

### Top-level Structure
```yaml
spec_version: "1.2"
mappings:
  # Standard FOCUS column name
  BilledCost:
    description: "Optional documentation for metadata"
    steps:
      - op: from_column
        column: "raw_cost"
      - op: cast
        to: "decimal"
        scale: 2
```

### Operation Reference

| Operation | Description | Parameters | Example |
|-----------|-------------|------------|---------|
| `from_column` | Load value from an input column | `column` (string) | `- op: from_column`<br>`  column: "cost"` |
| `const` | Set a constant value for every row | `value` (any) | `- op: const`<br>`  value: "Acme"` |
| `coalesce` | Take the first non-null value from a list of columns | `columns` (list) | `- op: coalesce`<br>`  columns: ["a", "b"]` |
| `map_values` | Map values using a lookup dictionary | `mapping` (dict), `default` (opt), `column` (opt) | `- op: map_values`<br>`  mapping: {"U": "Usage"}` |
| `concat` | Concatenate multiple columns into a string | `columns` (list), `sep` (string, default "") | `- op: concat`<br>`  columns: ["p", "s"]`<br>`  sep: "-"` |
| `cast` | Convert the data type of the current value | `to` (string), `scale` (int, for decimal) | `- op: cast`<br>`  to: "decimal"`<br>`  scale: 2` |
| `round` | Round the current numeric value | `ndigits` (int, default 0) | `- op: round`<br>`  ndigits: 2` |
| `math` | Perform arithmetic (+, -, *, /) | `operator` (string), `operands` (list) | `- op: math`<br>`  operator: add`<br>`  operands: [{column: "tax"}]` |
| `when` | Simple `if column == value then X else Y` logic | `column`, `value`, `then`, `else` | `- op: when`<br>`  column: "id"`<br>`  value: 0`<br>`  then: "N/A"` |
| `pandas_expr` | Evaluate a safe pandas expression to produce a column | `expr` (string) | `- op: pandas_expr`<br>`  expr: "df['a'] + df['b']"` |

### Extension Columns
Custom columns MUST start with the `x_` prefix. They will be appended to the output dataset and documented in the generated metadata if a `description` is provided.

## Validate

```bash
python -m focus_report validate \
  --spec v1.2 \
  --input focus.csv \
  --out focus.validation.json
```
