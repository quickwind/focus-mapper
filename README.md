# focus-report

Generate FinOps FOCUS v1.2 compliant reports from a pre-flattened telemetry/billing table.

This project takes any tabular data (CSV/Parquet) and converts it to a FOCUS v1.2 report using a YAML mapping. Use the interactive wizard to build the mapping, or hand‑author it.

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install -e ".[dev]"

python -m focus_report --help
pytest -q
```

## What You Need

- A flat input table (CSV or Parquet).
- A mapping YAML that tells the tool how to create each FOCUS column.

If you don’t have a mapping yet, start with the wizard.

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

Outputs:
- `focus.csv` (FOCUS report)
- `focus.focus-metadata.json` (metadata)
- `focus.validation.json` (validation report)

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
- `--include-conditional` to include Conditional columns
- `--include-optional` to include Optional columns

Tip: column name prompts support tab‑completion (case‑insensitive).

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

### Example Input (CSV)

```csv
billing_period,billing_date,billing_hour,billing_currency,billed_cost,tax_amount,charge_category,charge_class,charge_description,alt_description,tag_a,tag_b,pricing_quantity,pricing_unit
2026-01,2026-01-30,4,USD,12.34,1.23,Usage,Normal,Compute usage,,core,vm,1,Hours
2026-01,2026-01-30,5,USD,5.00,0.50,Tax,Normal,Sales tax,Alt tax desc,billing,tax,1,Hours
```

### Example Mapping (YAML)

```yaml
spec_version: "1.2"
mappings:
  BillingPeriodStart:
    steps:
      - op: pandas_expr
        expr: 'pd.to_datetime(df["billing_period"] + "-01", utc=True)'
      - op: cast
        to: datetime

  BillingPeriodEnd:
    steps:
      - op: pandas_expr
        expr: 'pd.to_datetime((df["billing_period"].str.slice(0,4).astype(int) + ((df["billing_period"].str.slice(5,7).astype(int) + 1) > 12).astype(int)).astype(str) + "-" + (((df["billing_period"].str.slice(5,7).astype(int) + 1 - 1) % 12) + 1).astype(str).str.replace(r"^(\\d)$", r"0\\1", regex=True) + "-01", utc=True)'
      - op: cast
        to: datetime

  ChargePeriodStart:
    steps:
      - op: pandas_expr
        expr: 'pd.to_datetime(df["billing_date"] + "T" + df["billing_hour"].astype(int).astype(str).str.replace(r"^(\\d)$", r"0\\1", regex=True) + ":00:00Z", utc=True)'
      - op: cast
        to: datetime

  ChargePeriodEnd:
    steps:
      - op: pandas_expr
        expr: 'pd.to_datetime(df["billing_date"] + "T" + df["billing_hour"].astype(int).astype(str).str.replace(r"^(\\d)$", r"0\\1", regex=True) + ":00:00Z", utc=True) + pd.to_timedelta(1, unit="h")'
      - op: cast
        to: datetime

  EffectiveCost:
    steps:
      - op: pandas_expr
        expr: "df['billed_cost'] + df['tax_amount']"
      - op: cast
        to: decimal
        scale: 2

  x_TagConcat:
    description: "Concat tag_a and tag_b"
    steps:
      - op: concat
        columns: ["tag_a", "tag_b"]
        sep: "-"
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

### pandas_expr Safety Notes

`pandas_expr` is evaluated in a restricted environment:
- Available names: `df`, `pd`, `current`, `str`, `int`, `float`
- No builtins, no private/dunder attribute access
- Only a safe allowlist of pandas methods is permitted

If you need more pandas methods, add them to the allowlist in `src/focus_report/mapping/ops.py`.

### Extension Columns
Custom columns MUST start with the `x_` prefix. They will be appended to the output dataset and documented in the generated metadata if a `description` is provided.

### Skip a Column
If you skip a column in the wizard, it will not be mapped and will remain null in the output.

## Validate

```bash
python -m focus_report validate \
  --spec v1.2 \
  --input focus.csv \
  --out focus.validation.json
```

## Tests

```bash
pytest
```

Coverage is enabled by default. HTML report is written to `htmlcov/index.html`.
