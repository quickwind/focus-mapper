from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .completer import path_completion
from .errors import FocusReportError
from .io import read_table, write_table
from .mapping.config import load_mapping_config
from .mapping.executor import generate_focus_dataframe
from .metadata import build_sidecar_metadata, write_sidecar_metadata
from .spec import load_focus_spec
from .validate import validate_focus_dataframe, write_validation_report

logger = logging.getLogger("focus_report")


def _path(p: str) -> Path:
    return Path(p).expanduser()


def _eprint(message: str) -> None:
    print(message, file=sys.stderr)


def _prompt(text: str) -> str:
    return input(text)


def _setup_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="focus_report")
    p.add_argument("--version", action="version", version=f"focus-report {__version__}")
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )

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
    logger.debug("Loading FOCUS spec version: %s", spec_version)
    spec = load_focus_spec(spec_version)

    mapping_path = getattr(args, "mapping", None)
    while mapping_path is None:
        with path_completion():
            val = _prompt("Mapping YAML path: ").strip()
        if val:
            mapping_path = _path(val)
    logger.debug("Loading mapping configuration from: %s", mapping_path)
    mapping = load_mapping_config(mapping_path)

    input_path = getattr(args, "input", None)
    while input_path is None:
        with path_completion():
            val = _prompt("Input file (CSV/Parquet): ").strip()
        if val:
            input_path = _path(val)
    logger.debug("Reading input dataset: %s", input_path)
    in_df = read_table(input_path)

    output_path = getattr(args, "output", None)
    while output_path is None:
        with path_completion():
            val = _prompt("Output report path [focus.parquet]: ").strip()
        output_path = _path(val or "focus.parquet")

    logger.info("Generating FOCUS dataframe...")
    out_df = generate_focus_dataframe(in_df, mapping=mapping, spec=spec)
    logger.info("Generation complete. Rows: %d", len(out_df))

    logger.info("Running compliance validation...")
    validation = validate_focus_dataframe(out_df, spec=spec)
    logger.info(
        "Validation finished with %d errors and %d warnings",
        validation.summary.errors,
        validation.summary.warnings,
    )

    sidecar = build_sidecar_metadata(
        spec=spec,
        mapping=mapping,
        generator_name=getattr(args, "data_generator", "focus-report"),
        generator_version=getattr(args, "data_generator_version", __version__),
        input_path=input_path,
        output_path=output_path,
        output_df=out_df,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata_out = getattr(args, "metadata_out", None) or output_path.with_name(
        output_path.name + ".focus-metadata.json"
    )
    validation_out = getattr(args, "validation_out", None) or output_path.with_name(
        output_path.name + ".validation.json"
    )

    logger.info("Writing output dataset to: %s", output_path)
    write_table(out_df, output_path, parquet_metadata=sidecar.parquet_kv_metadata())

    logger.info("Writing sidecar metadata to: %s", metadata_out)
    write_sidecar_metadata(sidecar, metadata_out)

    logger.info("Writing validation report to: %s", validation_out)
    write_validation_report(validation, validation_out)

    if validation.summary.errors:
        logger.error("Dataset generated but failed FOCUS compliance validation.")
        return 2

    logger.info("Successfully generated FOCUS compliant report.")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    spec_version = (
        getattr(args, "spec", None)
        or _prompt("FOCUS spec version [v1.2]: ").strip()
        or "v1.2"
    )
    logger.debug("Loading FOCUS spec version: %s", spec_version)
    spec = load_focus_spec(spec_version)

    input_path = getattr(args, "input", None)
    while input_path is None:
        with path_completion():
            val = _prompt("Dataset to validate (CSV/Parquet): ").strip()
        if val:
            input_path = _path(val)
    logger.debug("Reading dataset for validation: %s", input_path)
    df = read_table(input_path)

    logger.info("Validating FOCUS dataframe...")
    report = validate_focus_dataframe(df, spec=spec)
    logger.info(
        "Validation finished with %d errors and %d warnings",
        report.summary.errors,
        report.summary.warnings,
    )

    out_path = getattr(args, "out", None)
    if out_path:
        logger.info("Writing validation report to: %s", out_path)
        write_validation_report(report, out_path)
    else:
        json.dump(
            report.to_dict(),
            fp=sys.stdout,
            indent=2,
            sort_keys=True,
        )

    if report.summary.errors:
        logger.error("Validation failed: dataset is not FOCUS compliant.")
        return 2

    logger.info("Validation successful: dataset is FOCUS compliant.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    _setup_logging(args.log_level)

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
        logger.error("%s", e)
        return 1
    except Exception as e:
        logger.exception("Unexpected error occurred")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
