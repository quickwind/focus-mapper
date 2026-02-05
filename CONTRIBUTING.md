# Contributing

Thanks for contributing to **focus-mapper**.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

## Run tests

```bash
pytest
```

## Code style
- Keep changes focused and minimal.
- Prefer explicit behavior over implicit magic.
- Update or add tests for any functional change.
