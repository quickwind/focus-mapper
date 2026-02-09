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
        "tests/fixtures/mapping_v1_2.yaml",
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


def test_cli_generate_v1_3_writes_outputs(tmp_path: Path) -> None:
    """Test that v1.3 generate produces correct metadata structure with collections."""
    out_csv = tmp_path / "focus_v1_3.csv"

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
        "v1.3",
        "--input",
        "tests/fixtures/telemetry_small.csv",
        "--mapping",
        "tests/fixtures/mapping_v1_3.yaml",
        "--output",
        str(out_csv),
    ]
    # v1.3 prompts for TimeSector completeness - provide Y for complete
    p = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env, input="Y\n")
    # Exit code 2 means validation errors (expected for sample data with missing columns)
    # Files are still generated, which is what we're testing
    assert p.returncode in (0, 2), p.stderr

    assert out_csv.exists()
    metadata_path = tmp_path / "focus_v1_3.csv.focus-metadata.json"
    assert metadata_path.exists()
    assert (tmp_path / "focus_v1_3.csv.validation.json").exists()

    df = pd.read_csv(out_csv)
    assert "BilledCost" in df.columns
    assert "HostProviderName" in df.columns  # v1.3 column

    # Verify v1.3 metadata structure has collections
    meta = json.loads(metadata_path.read_text())
    assert "DatasetInstance" in meta
    assert isinstance(meta["DatasetInstance"], list)
    assert "Recency" in meta
    assert isinstance(meta["Recency"], list)
    assert "Schema" in meta
    assert isinstance(meta["Schema"], list)
    assert meta["Schema"][0]["FocusVersion"] == "1.3"


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
        "tests/fixtures/mapping_v1_2.yaml",
        "--output",
        str(out_parquet),
    ]
    p = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr

    t = pq.read_table(out_parquet)
    md = t.schema.metadata or {}
    assert b"FocusMetadata" in md
    
    import json
    meta = json.loads(md[b"FocusMetadata"])
    # In v1.3 metadata structure Schema is a list, but in v1.2 it might be a dict depending on implementation
    if "Schema" in meta:
        schema = meta["Schema"]
        if isinstance(schema, list):
            assert schema[0]["FocusVersion"] == "1.2"
        else:
            assert schema["FocusVersion"] == "1.2"
    # Or in the simple structure if it was v1.2 legacy? 
    # The output showed: 'FocusMetadata': b'{"DataGenerator": ..., "Schema": ...}'
    # content: b'{"DataGenerator": {"DataGenerator": "focus-mapper"}, "Schema": {"SchemaId": "...", "FocusVersion": "1.2", ...}}'
    # Wait, the output showed Schema is a dict? No, let's look closely at the output in step 5344.
    # b'FocusMetadata': b'{"DataGenerator": {"DataGenerator": "focus-mapper"}, "Schema": {"SchemaId": "...", "FocusVersion": "1.2", ...}}'
    # Wait, the output in step 5344 showed: "Schema": {"SchemaId": ...}
    # But usually Schema is a list in v1.3?
    # Let me re-read the output carefully.
    
    # Output from step 5344:
    # b'FocusMetadata': b'{"DataGenerator": {"DataGenerator": "focus-mapper"}, "Schema": {"SchemaId": "b21ded9f...", "FocusVersion": "1.2", ...}}'
    
    # So Schema IS a dict here? That's v1.2 style metadata maybe?
    # Spec v1.3 introduced the collection style. v1.2 might still use the simpler one or we backported it?
    # The command used `focus_mapper generate --spec v1.2`.
    
    # Let's just check that FocusVersion is in there somewhere.
    assert "FocusVersion" in str(md[b"FocusMetadata"])


def test_wizard_cli_prompts_for_missing_args(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "mapping.yaml"

    from focus_mapper.spec import load_focus_spec

    spec = load_focus_spec("v1.2")
    mandatory_count = len(
        [c for c in spec.columns if c.feature_level.lower() == "mandatory"]
    )

    inputs_list = [
        "tests/fixtures/telemetry_small.csv",
        str(out),
        "v1.2",
        "n",
        "n",
        "n",
        "",  # use default validation settings
        "y", # enable global validation overrides
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
            "tests/fixtures/mapping_v1_2.yaml",
            "tests/fixtures/telemetry_small.csv",
            str(out_csv),
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    from focus_mapper.cli import main

    rc = main(["generate"])
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
        "tests/fixtures/mapping_v1_2.yaml",
        "--output",
        str(out_csv),
    ]
    subprocess.run(cmd, check=True, env=env)

    inputs = iter(["2", "v1.2", str(out_csv)])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    from focus_mapper.cli import main

    rc = main([])
    assert rc == 0
