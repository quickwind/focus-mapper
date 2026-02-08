from __future__ import annotations

import argparse
import os
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
from .metadata import build_sidecar_metadata, write_sidecar_metadata, extract_time_sectors
from .spec import load_focus_spec, list_available_spec_versions
from .validate import validate_focus_dataframe, write_validation_report
from .wizard_lib import prompt_menu

logger = logging.getLogger("focus_mapper")


def _path(p: str) -> Path:
    return Path(p).expanduser()


def _eprint(message: str) -> None:
    print(message, file=sys.stderr)


def _prompt(text: str) -> str:
    return input(text)


def _prompt_bool(text: str, default: bool = True) -> bool:
    """Prompt for a yes/no answer with strict validation."""
    valid_true = {"y", "yes"}
    valid_false = {"n", "no"}

    while True:
        val = _prompt(text).strip().lower()
        if not val:
            return default
        if val in valid_true:
            return True
        if val in valid_false:
            return False
        _eprint("Please enter 'y' or 'n'.")


def _setup_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="focus-mapper")
    p.add_argument("--version", action="version", version=f"focus-mapper {__version__}")
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )

    sub = p.add_subparsers(dest="cmd")

    gen = sub.add_parser("generate", help="Generate FOCUS report")
    gen.add_argument("--spec", help="FOCUS spec version (default: v1.3)")
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
        "--data-generator", help="Data generator name (overrides ENV: FOCUS_DATA_GENERATOR_NAME)"
    )
    gen.add_argument(
        "--data-generator-version", help="Data generator version (overrides ENV: FOCUS_DATA_GENERATOR_VERSION)"
    )
    gen.add_argument(
        "--spec-dir",
        type=_path,
        help="Directory containing spec JSON files (overrides bundled specs). "
             "Also reads from FOCUS_SPEC_DIR env var if not set.",
    )

    # Dataset completion flags
    comp_group = gen.add_mutually_exclusive_group()
    comp_group.add_argument(
        "--dataset-complete",
        action="store_true",
        default=None,
        help="Mark dataset instance as complete (skip prompt)",
    )
    comp_group.add_argument(
        "--dataset-incomplete",
        action="store_true",
        default=None,
        help="Mark dataset instance as incomplete (skip prompt)",
    )

    val = sub.add_parser("validate", help="Validate an existing FOCUS dataset")
    val.add_argument("--spec", help="FOCUS spec version (default: v1.3)")
    val.add_argument("--input", type=_path, help="Input CSV or Parquet")
    val.add_argument("--out", type=_path, help="Validation report JSON output path")
    val.add_argument(
        "--report-format", default="json", choices=["json"], help="Report format"
    )
    val.add_argument(
        "--spec-dir",
        type=_path,
        help="Directory containing spec JSON files (overrides bundled specs). "
             "Also reads from FOCUS_SPEC_DIR env var if not set.",
    )

    return p


def _cmd_generate(args: argparse.Namespace) -> int:
    mapping_path = getattr(args, "mapping", None)
    while mapping_path is None:
        with path_completion():
            val = _prompt("Mapping YAML path: ").strip()
        if val:
            mapping_path = _path(val)
    logger.debug("Loading mapping configuration from: %s", mapping_path)
    mapping = load_mapping_config(mapping_path)

    spec_version = getattr(args, "spec", None) or mapping.spec_version
    spec_dir = getattr(args, "spec_dir", None)
    logger.debug("Loading FOCUS spec version: %s", spec_version)
    spec = load_focus_spec(spec_version, spec_dir=spec_dir)

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
    validation = validate_focus_dataframe(out_df, spec=spec, mapping=mapping)
    logger.info(
        "Validation finished with %d errors and %d warnings",
        validation.summary.errors,
        validation.summary.warnings,
    )

    # v1.3+ CostAndUsage: Prompt for TimeSector completeness
    time_sectors: list[dict] | None = None
    dataset_instance_complete: bool | None = None
    version = spec.version.lstrip("v")

    if version >= "1.3" and mapping.dataset_type == "CostAndUsage":
        # Resolve completeness from args or prompt
        if args.dataset_complete:
            dataset_instance_complete = True
        elif args.dataset_incomplete:
            dataset_instance_complete = False
        else:
            # First prompt: Is the dataset instance complete?
            dataset_instance_complete = _prompt_bool("Is the dataset instance complete? [Y/n]: ", default=True)

        # Extract distinct time sectors
        if dataset_instance_complete:
            time_sectors = extract_time_sectors(
                out_df, dataset_complete=True
            )
        else:
            # Need to prompt for each sector
            if "ChargePeriodStart" in out_df.columns and "ChargePeriodEnd" in out_df.columns:
                pairs = out_df[["ChargePeriodStart", "ChargePeriodEnd"]].drop_duplicates()
                sector_map: dict[tuple[str, str], bool] = {}
                for _, row in pairs.iterrows():
                    start = str(row["ChargePeriodStart"])
                    end = str(row["ChargePeriodEnd"])
                    
                    if args.dataset_incomplete:
                        # If forcing incomplete via CLI, assume sectors are incomplete unless we build a complex arg parser.
                        # For now, this lets users bypass the prompts.
                        ans = False
                    else:
                        ans = _prompt_bool(f"Is time sector {start} to {end} complete? [Y/n]: ", default=True)
                    
                    sector_map[(start, end)] = ans
                time_sectors = extract_time_sectors(
                    out_df, dataset_complete=False, sector_complete_map=sector_map
                )
            else:
                time_sectors = []

    sidecar = build_sidecar_metadata(
        spec=spec,
        mapping=mapping,
        generator_name=args.data_generator or os.environ.get("FOCUS_DATA_GENERATOR_NAME", "focus-mapper"),
        generator_version=args.data_generator_version or os.environ.get("FOCUS_DATA_GENERATOR_VERSION", __version__),
        input_path=input_path,
        output_path=output_path,
        output_df=out_df,
        time_sectors=time_sectors,
        dataset_instance_complete=dataset_instance_complete,
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
    available = list_available_spec_versions()
    default_spec = "v1.3"
    if available and default_spec not in available:
        default_spec = available[-1]
    spec_version = getattr(args, "spec", None)
    if not spec_version:
        if available:
            options = [(v, v) for v in available]
            spec_version = prompt_menu(
                _prompt,
                "Select FOCUS spec version:",
                options,
                default=default_spec,
            )
        else:
            spec_version = (
                _prompt(f"FOCUS spec version [{default_spec}]: ").strip() or default_spec
            )
    logger.debug("Loading FOCUS spec version: %s", spec_version)
    spec_dir = getattr(args, "spec_dir", None)
    spec = load_focus_spec(spec_version, spec_dir=spec_dir)

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
