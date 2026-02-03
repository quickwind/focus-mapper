from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .errors import FocusReportError
from .io import read_table, write_table
from .mapping.config import load_mapping_config
from .mapping.executor import generate_focus_dataframe
from .metadata import build_sidecar_metadata, write_sidecar_metadata
from .spec import load_focus_spec
from .validate import validate_focus_dataframe, write_validation_report


def _path(p: str) -> Path:
    return Path(p).expanduser()


def _eprint(message: str) -> None:
    print(message, file=sys.stderr)


def _prompt(text: str) -> str:
    return input(text)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="focus_report")
    p.add_argument("--version", action="version", version=f"focus-report {__version__}")

    sub = p.add_subparsers(dest="cmd")

    gen = sub.add_parser("generate", help="Generate FOCUS report")
    gen.add_argument("--spec", help="FOCUS spec version (default: v1.2)")
    gen.add_argument("--input", type=_path, help="Input CSV or Parquet")
    gen.add_argument("--mapping", type=_path, help="Mapping YAML")
    gen.add_argument("--output", type=_path, help="Output CSV or Parquet")
    gen.add_argument(
        "--metadata-out",
        type=_path,
        help="Sidecar metadata JSON output path (default: <output>.focus-metadata.json)",
    )
    gen.add_argument(
        "--validation-out",
        type=_path,
        help="Validation report JSON output path (default: <output>.validation.json)",
    )
    gen.add_argument(
        "--data-generator", default="focus-report", help="Data generator name"
    )
    gen.add_argument(
        "--data-generator-version", default=__version__, help="Data generator version"
    )

    val = sub.add_parser("validate", help="Validate an existing FOCUS dataset")
    val.add_argument("--spec", help="FOCUS spec version (default: v1.2)")
    val.add_argument("--input", type=_path, help="Input CSV or Parquet")
    val.add_argument("--out", type=_path, help="Validation report JSON output path")
    val.add_argument(
        "--report-format", default="json", choices=["json"], help="Report format"
    )

    return p


def _cmd_generate(args: argparse.Namespace) -> int:
    spec_version = (
        getattr(args, "spec", None)
        or _prompt("FOCUS spec version [v1.2]: ").strip()
        or "v1.2"
    )
    spec = load_focus_spec(spec_version)

    mapping_path = getattr(args, "mapping", None)
    while mapping_path is None:
        val = _prompt("Mapping YAML path: ").strip()
        if val:
            mapping_path = _path(val)
    mapping = load_mapping_config(mapping_path)

    input_path = getattr(args, "input", None)
    while input_path is None:
        val = _prompt("Input file (CSV/Parquet): ").strip()
        if val:
            input_path = _path(val)
    in_df = read_table(input_path)

    output_path = getattr(args, "output", None)
    while output_path is None:
        val = _prompt("Output report path [focus.parquet]: ").strip()
        output_path = _path(val or "focus.parquet")

    out_df = generate_focus_dataframe(in_df, mapping=mapping, spec=spec)

    validation = validate_focus_dataframe(out_df, spec=spec)

    sidecar = build_sidecar_metadata(
        spec=spec,
        mapping=mapping,
        generator_name=getattr(args, "data_generator", "focus-report"),
        generator_version=getattr(args, "data_generator_version", __version__),
        validation=validation,
        input_path=input_path,
        output_path=output_path,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata_out = getattr(args, "metadata_out", None) or output_path.with_name(
        output_path.name + ".focus-metadata.json"
    )
    validation_out = getattr(args, "validation_out", None) or output_path.with_name(
        output_path.name + ".validation.json"
    )

    # Always write dataset.
    write_table(out_df, output_path, parquet_metadata=sidecar.parquet_kv_metadata())

    write_sidecar_metadata(sidecar, metadata_out)
    write_validation_report(validation, validation_out)

    return 2 if validation.summary.errors else 0


def _cmd_validate(args: argparse.Namespace) -> int:
    spec_version = (
        getattr(args, "spec", None)
        or _prompt("FOCUS spec version [v1.2]: ").strip()
        or "v1.2"
    )
    spec = load_focus_spec(spec_version)

    input_path = getattr(args, "input", None)
    while input_path is None:
        val = _prompt("Dataset to validate (CSV/Parquet): ").strip()
        if val:
            input_path = _path(val)
    df = read_table(input_path)

    report = validate_focus_dataframe(df, spec=spec)

    out_path = getattr(args, "out", None)
    if out_path:
        write_validation_report(report, out_path)
    else:
        json.dump(
            report.to_dict(),
            fp=sys.stdout,
            indent=2,
            sort_keys=True,
        )

    return 2 if report.summary.errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd is None:
        while True:
            choice = (
                _prompt("Choose command: [1] generate [2] validate [q] quit\n> ")
                .strip()
                .lower()
            )
            if choice in {"1", "generate"}:
                args.cmd = "generate"
                break
            if choice in {"2", "validate"}:
                args.cmd = "validate"
                break
            if choice in {"q", "quit"}:
                return 0

    try:
        if args.cmd == "generate":
            return _cmd_generate(args)
        if args.cmd == "validate":
            return _cmd_validate(args)
    except FocusReportError as e:
        _eprint(f"Error: {e}")
        return 1
    except Exception as e:
        _eprint(f"Unexpected error: {e}")
        return 1

    return 0
