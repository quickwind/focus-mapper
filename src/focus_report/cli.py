from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .io import read_table, write_table
from .mapping.config import load_mapping_config
from .mapping.executor import generate_focus_dataframe
from .metadata import build_sidecar_metadata, write_sidecar_metadata
from .spec import load_focus_spec
from .validate import validate_focus_dataframe, write_validation_report


def _path(p: str) -> Path:
    return Path(p).expanduser()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="focus_report")
    p.add_argument("--version", action="version", version=f"focus-report {__version__}")

    sub = p.add_subparsers(dest="cmd", required=True)

    gen = sub.add_parser("generate", help="Generate FOCUS report")
    gen.add_argument(
        "--spec", default="v1.2", help="FOCUS spec version (default: v1.2)"
    )
    gen.add_argument("--input", required=True, type=_path, help="Input CSV or Parquet")
    gen.add_argument("--mapping", required=True, type=_path, help="Mapping YAML")
    gen.add_argument(
        "--output", required=True, type=_path, help="Output CSV or Parquet"
    )
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
    val.add_argument(
        "--spec", default="v1.2", help="FOCUS spec version (default: v1.2)"
    )
    val.add_argument("--input", required=True, type=_path, help="Input CSV or Parquet")
    val.add_argument("--out", type=_path, help="Validation report JSON output path")
    val.add_argument(
        "--report-format", default="json", choices=["json"], help="Report format"
    )

    return p


def _cmd_generate(args: argparse.Namespace) -> int:
    spec = load_focus_spec(args.spec)
    mapping = load_mapping_config(args.mapping)
    in_df = read_table(args.input)

    out_df = generate_focus_dataframe(in_df, mapping=mapping, spec=spec)

    validation = validate_focus_dataframe(out_df, spec=spec)

    sidecar = build_sidecar_metadata(
        spec=spec,
        mapping=mapping,
        generator_name=args.data_generator,
        generator_version=args.data_generator_version,
        validation=validation,
        input_path=args.input,
        output_path=args.output,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)

    metadata_out = args.metadata_out or args.output.with_name(
        args.output.name + ".focus-metadata.json"
    )
    validation_out = args.validation_out or args.output.with_name(
        args.output.name + ".validation.json"
    )

    # Always write dataset.
    write_table(out_df, args.output, parquet_metadata=sidecar.parquet_kv_metadata())

    write_sidecar_metadata(sidecar, metadata_out)
    write_validation_report(validation, validation_out)

    return 2 if validation.summary.errors else 0


def _cmd_validate(args: argparse.Namespace) -> int:
    spec = load_focus_spec(args.spec)
    df = read_table(args.input)
    report = validate_focus_dataframe(df, spec=spec)

    if args.out:
        write_validation_report(report, args.out)
    else:
        json.dump(
            report.to_dict(),
            fp=getattr(__import__("sys"), "stdout"),
            indent=2,
            sort_keys=True,
        )

    return 2 if report.summary.errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "generate":
        return _cmd_generate(args)
    if args.cmd == "validate":
        return _cmd_validate(args)

    raise AssertionError(f"Unhandled cmd: {args.cmd}")
