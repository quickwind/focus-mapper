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
        "focus_report",
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
        "focus_report",
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
        "focus_report",
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

    from focus_report.spec import load_focus_spec

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
    ]
    for _ in range(mandatory_count):
        inputs_list.extend(["", "4"])
    inputs_list.append("n")
    inputs = iter(inputs_list)

    def fake_input(text: str) -> str:
        return next(inputs)

    monkeypatch.setattr("builtins.input", fake_input)

    from focus_report.wizard_cli import main

    rc = main([])
    assert rc == 0
    assert out.exists()
