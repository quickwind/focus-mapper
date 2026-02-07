import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_cli_generate_writes_outputs(tmp_path: Path) -> None:
    out_csv = tmp_path / "focus.csv"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src")) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    cmd = [
        sys.executable,
        "-m",
        "focus_mapper",
        "generate",
        "--spec",
        "v1.2",
        "--input",
        "tests/fixtures/telemetry_small.csv",
        "--mapping",
        "tests/fixtures/mapping_basic.yaml",
        "--output",
        str(out_csv),
    ]
    p = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr

    assert out_csv.exists()
    assert (tmp_path / "focus.csv.focus-metadata.json").exists()
    assert (tmp_path / "focus.csv.validation.json").exists()

    df = pd.read_csv(out_csv)
    assert "BilledCost" in df.columns


def test_cli_validate_exit_code_on_errors(tmp_path: Path) -> None:
    out = tmp_path / "validate.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src")) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    cmd = [
        sys.executable,
        "-m",
        "focus_mapper",
        "validate",
        "--spec",
        "v1.2",
        "--input",
        "tests/fixtures/focus_invalid_required_missing.csv",
        "--out",
        str(out),
    ]
    p = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
    assert p.returncode == 2

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["summary"]["errors"] >= 1


def test_cli_generate_parquet_embeds_metadata(tmp_path: Path) -> None:
    import pyarrow.parquet as pq

    in_parquet = tmp_path / "telemetry.parquet"
    out_parquet = tmp_path / "focus.parquet"

    df = pd.read_csv("tests/fixtures/telemetry_small.csv")
    df.to_parquet(in_parquet, index=False)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src")) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    cmd = [
        sys.executable,
        "-m",
        "focus_mapper",
        "generate",
        "--spec",
        "v1.2",
        "--input",
        str(in_parquet),
        "--mapping",
        "tests/fixtures/mapping_basic.yaml",
        "--output",
        str(out_parquet),
    ]
    p = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr

    t = pq.read_table(out_parquet)
    md = t.schema.metadata or {}
    assert b"FocusVersion" in md


def test_wizard_cli_prompts_for_missing_args(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "mapping.yaml"

    from focus_mapper.spec import load_focus_spec

    spec = load_focus_spec("v1.2")
    mandatory_count = len(
        [c for c in spec.columns if c.feature_level.lower() == "mandatory"]
    )

    inputs_list = [
        "v1.2",
        "tests/fixtures/telemetry_small.csv",
        str(out),
        "n",
        "n",
        "n",
        "",  # use default validation settings
    ]

    mandatory_cols = [c for c in spec.columns if c.feature_level.lower() == "mandatory"]
    for col in mandatory_cols:
        inputs_list.append("2")  # const
        if col.allowed_values:
            inputs_list.append(col.allowed_values[0])
        elif col.allows_nulls:
            inputs_list.append("")
        else:
            # Provide type-appropriate values for non-nullable columns
            data_type = (col.data_type or "").strip().lower()
            if data_type == "decimal":
                inputs_list.append("0")
            elif data_type in ("date/time", "datetime"):
                inputs_list.append("2024-01-01T00:00:00Z")
            else:
                inputs_list.append("X")
        inputs_list.append("done")  # finish steps
        inputs_list.append("n")  # no per-column validation override
    inputs_list.append("n")
    inputs = iter(inputs_list)

    def fake_input(text: str) -> str:
        return next(inputs)

    monkeypatch.setattr("builtins.input", fake_input)

    from focus_mapper.wizard_cli import main

    rc = main([])
    assert rc == 0
    assert out.exists()


def test_cli_generate_interactive(tmp_path: Path, monkeypatch) -> None:
    out_csv = tmp_path / "focus_interactive.csv"

    inputs = iter(
        [
            "1",
            "v1.2",
            "tests/fixtures/mapping_basic.yaml",
            "tests/fixtures/telemetry_small.csv",
            str(out_csv),
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    from focus_mapper.cli import main

    rc = main([])
    assert rc == 0
    assert out_csv.exists()


def test_cli_validate_interactive(tmp_path: Path, monkeypatch) -> None:
    out_csv = tmp_path / "valid_focus.csv"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src")) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    cmd = [
        sys.executable,
        "-m",
        "focus_mapper",
        "generate",
        "--spec",
        "v1.2",
        "--input",
        "tests/fixtures/telemetry_small.csv",
        "--mapping",
        "tests/fixtures/mapping_basic.yaml",
        "--output",
        str(out_csv),
    ]
    subprocess.run(cmd, check=True, env=env)

    inputs = iter(["2", "v1.2", str(out_csv)])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    from focus_mapper.cli import main

    rc = main([])
    assert rc == 0
