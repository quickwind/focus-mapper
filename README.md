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

## Validate

```bash
python -m focus_report validate \
  --spec v1.2 \
  --input focus.csv \
  --out focus.validation.json
```
