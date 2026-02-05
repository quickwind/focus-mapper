# focus-mapper

![CI](https://github.com/quickwind/focus-mapping/actions/workflows/ci.yml/badge.svg)

Generate FinOps FOCUS compliant reports from a pre-flattened telemetry/billing table.

This project takes any tabular data (CSV/Parquet) and converts it to a FOCUS compliant report using a YAML mapping. Use the interactive wizard to build the mapping, or hand‑author it.

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install -e ".[dev]"

python -m focus_mapper --help
pytest -q
```

## Supported Spec Versions

Default spec version is `v1.2`. The CLI and wizard will detect any versions available under `src/focus_mapper/specs`.

## Populate Spec Versions

Use the tool below to download and store a specific spec version from the upstream repository:

```bash
python tools/populate_focus_spec.py --version 1.0
python tools/populate_focus_spec.py --version 1.1
python tools/populate_focus_spec.py --version 1.2
python tools/populate_focus_spec.py --version 1.3
```

If a version tag doesn’t exist, override the git ref:

```bash
python tools/populate_focus_spec.py --version 1.3 --ref main
```

Then use `--spec v1.0` (or `v1.1`, `v1.3`) in the CLI.

## What You Need

- A flat input table (CSV or Parquet).
- A mapping YAML that tells the tool how to create each FOCUS column.

If you don’t have a mapping yet, start with the wizard.

## Generate

```bash
python -m focus_mapper generate \
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

## Use As A Library

You can install and call `focus-mapper` from another Python project.

Install from a local checkout:

```bash
pip install -e /path/to/focus-mapper
```

Example usage:

```python
from pathlib import Path

import pandas as pd

from focus_mapper.mapping.config import load_mapping_config
from focus_mapper.mapping.executor import generate_focus_dataframe
from focus_mapper.spec import load_focus_spec
from focus_mapper.validate import validate_focus_dataframe

df = pd.read_csv("input.csv")
mapping = load_mapping_config(Path("mapping.yaml"))
spec = load_focus_spec("v1.2")

out = generate_focus_dataframe(df, mapping=mapping, spec=spec)
report = validate_focus_dataframe(out, spec=spec, mapping=mapping)
```

Notes:
- Parquet support requires `pyarrow` (`pip install -e ".[parquet]"`).
- Only `v1.2` is supported right now.
- Validation overrides require passing `mapping` to `validate_focus_dataframe`.

## Mapping Wizard

Interactive wizard to create a mapping YAML based on a sample input file:

```bash
focus-mapper-wizard \
  --spec v1.2 \
  --input telemetry.csv \
  --output mapping.yaml
```

You can also run the wizard with no arguments and it will prompt for values:

```bash
focus-mapper-wizard
```

Optional flags:
- `--include-recommended` to include Recommended columns
- `--include-conditional` to include Conditional columns
- `--include-optional` to include Optional columns

Tip: column name prompts support tab‑completion (case‑insensitive).
The wizard will also show a summary of default validation settings and let you override them globally or per column.
For standard FOCUS columns, the wizard does not offer a `cast` option because the generator will coerce to the spec type automatically.

## Mapping YAML Specification

The mapping file is a YAML document that defines how your input columns are transformed into FinOps FOCUS compliant columns.

### Core Concept: The Pipeline
Each column in the `mappings` section is defined as a series of **steps**. Steps are executed in order, and the output of one step is passed as the input to the next.

### Top-level Structure
```yaml
spec_version: "1.2"
validation:
  default:
    mode: permissive
    datetime:
      format: null
    decimal:
      precision: null
      scale: null
      integer_only: false
      min: null
      max: null
    string:
      min_length: null
      max_length: null
      allow_empty: true
      trim: true
    json:
      object_only: false
    allowed_values:
      case_insensitive: false
    nullable:
      allow_nulls: null
    presence:
      enforce: true
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
    validation:
      decimal:
        precision: 12
        scale: 2
        min: 0
```

### Validation Overrides (Optional)

Validation is **permissive by default** unless you define `validation.default`. You can override validation for individual columns inside each mapping:

```yaml
spec_version: "1.2"
validation:
  default:
    mode: permissive
    datetime:
      format: null
    decimal:
      precision: null
      scale: null
      integer_only: false
      min: 0
      max: null
    string:
      min_length: null
      max_length: 120
      allow_empty: true
      trim: true
    json:
      object_only: false
    allowed_values:
      case_insensitive: false
    nullable:
      allow_nulls: null
    presence:
      enforce: true
mappings:
  BillingPeriodStart:
    steps:
      - op: pandas_expr
        expr: 'pd.to_datetime(df["billing_period"] + "-01", utc=True)'
    validation:
      mode: strict
      datetime:
        format: "%Y-%m-%dT%H:%M:%SZ"
  BilledCost:
    steps:
      - op: from_column
        column: billed_cost
    validation:
      decimal:
        precision: 12
        scale: 2
        min: 0
  Tags:
    steps:
      - op: from_column
        column: tags_json
    validation:
      json:
        object_only: true
```

Validation override keys:
- `mode`: `permissive` or `strict`
- `datetime.format`: strftime format; if omitted, permissive uses inference
- `decimal`: `precision`, `scale`, `integer_only`, `min`, `max`
- `string`: `min_length`, `max_length`, `allow_empty`, `trim`
- `json.object_only`: require JSON objects only
- `allowed_values.case_insensitive`: case‑insensitive matching (default: false)
- `nullable.allow_nulls`: override spec nullability
- `presence.enforce`: skip “missing column” checks

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
| `from_column` | Initialize the pipeline from a source column. Use this as the first step when you want to transform an input field. | `column` (string; input column name) | `- op: from_column`<br>`  column: "cost"` |
| `const` | Create a column with the same value for every row (including `null`). Useful for static metadata. | `value` (any) | `- op: const`<br>`  value: "Acme"` |
| `coalesce` | Pick the first non-null value across multiple columns, left to right. | `columns` (list of strings) | `- op: coalesce`<br>`  columns: ["a", "b"]` |
| `map_values` | Replace values using a lookup dictionary. If a value is missing, use `default` (or null if not set). Can start from `column` or the current series. | `mapping` (dict), `default` (optional), `column` (optional) | `- op: map_values`<br>`  column: "charge_category"`<br>`  mapping: {"Usage": "U", "Tax": "T"}` |
| `concat` | Join multiple columns into a single string. Nulls are treated as empty strings. | `columns` (list), `sep` (string, default "") | `- op: concat`<br>`  columns: ["tag_a", "tag_b"]`<br>`  sep: "-"` |
| `cast` | Convert the current series to a specific type. Use `decimal` for money and `datetime` for timestamps. | `to` (string: `string|float|int|datetime|decimal`), `scale` (int, decimal only), `precision` (int, decimal only) | `- op: cast`<br>`  to: "decimal"`<br>`  scale: 2`<br>`  precision: 12` |
| `round` | Round the current numeric series to `ndigits`. | `ndigits` (int, default 0) | `- op: round`<br>`  ndigits: 2` |
| `math` | Row-wise arithmetic across columns or constants. Supports `add`, `sub`, `mul`, `div`. Use `operands` to list inputs. | `operator` (string), `operands` (list of `{column}` or `{const}`) | `- op: math`<br>`  operator: add`<br>`  operands: [{column: "cost"}, {column: "tax"}]` |
| `when` | Conditional assignment: if `column == value` then `then`, else `else`. | `column`, `value`, `then`, `else` (optional) | `- op: when`<br>`  column: "charge_category"`<br>`  value: "Tax"`<br>`  then: "Y"`<br>`  else: "N"` |
| `pandas_expr` | Evaluate a safe pandas expression. Use `df` for the input DataFrame, `current` for the prior series, and `pd` for pandas helpers. Must return a Series or scalar. | `expr` (string) | `- op: pandas_expr`<br>`  expr: "df['a'] + df['b']"` |

### pandas_expr Safety Notes

`pandas_expr` is evaluated in a restricted environment:
- Available names: `df`, `pd`, `current`, `str`, `int`, `float`
- No builtins, no private/dunder attribute access
- Only a safe allowlist of pandas methods is permitted

If you need more pandas methods, add them to the allowlist in `src/focus_mapper/mapping/ops.py`.

### Extension Columns
Custom columns MUST start with the `x_` prefix. They will be appended to the output dataset and documented in the generated metadata if a `description` is provided.

### Skip a Column
If you skip a column in the wizard, it will not be mapped and will remain null in the output.

## Validate

```bash
python -m focus_mapper validate \
  --spec v1.2 \
  --input focus.csv \
  --out focus.validation.json
```

## Tests

```bash
pytest
```

Coverage is enabled by default. HTML report is written to `htmlcov/index.html`.
