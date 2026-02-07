from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

from .completer import path_completion
from .io import read_table
from .mapping.config import MappingConfig
from .spec import load_focus_spec, list_available_spec_versions
from .wizard import run_wizard, PromptFunc
from .wizard_lib import prompt_menu

logger = logging.getLogger("focus_mapper.wizard")


def _path(p: str) -> Path:
    return Path(p).expanduser()


def _prompt_input_path(prompt: PromptFunc) -> Path:
    """Prompt user for input file path with path completion."""
    while True:
        with path_completion():
            val = prompt("Input file (CSV/Parquet): ").strip()
        if val:
            return _path(val)


def _eprint(message: str) -> None:
    print(message, file=sys.stderr)


def _setup_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="focus-mapper-wizard")
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )
    p.add_argument("--spec", help="FOCUS spec version (default: v1.2)")
    p.add_argument("--input", type=_path, help="Input CSV or Parquet")
    p.add_argument("--output", type=_path, help="Output mapping YAML path")
    p.add_argument(
        "--include-recommended",
        action="store_true",
        help="Include Recommended columns in the wizard",
    )
    p.add_argument(
        "--include-conditional",
        action="store_true",
        help="Include Conditional columns in the wizard",
    )
    p.add_argument(
        "--include-optional",
        action="store_true",
        help="Include Optional columns in the wizard",
    )
    return p


def _write_mapping(path: Path, mapping: MappingConfig) -> None:
    data: dict[str, object] = {
        "spec_version": mapping.spec_version,
        "mappings": {},
    }
    # New v1.3+ metadata fields
    if mapping.creation_date:
        data["creation_date"] = mapping.creation_date
    if mapping.dataset_type:
        data["dataset_type"] = mapping.dataset_type
    if mapping.dataset_instance_name:
        data["dataset_instance_name"] = mapping.dataset_instance_name

    if mapping.validation_defaults:
        data["validation"] = {"default": mapping.validation_defaults}

    mappings: dict[str, object] = {}
    for rule in mapping.rules:
        body: dict[str, object] = {"steps": rule.steps}
        if rule.description:
            body["description"] = rule.description
        if rule.validation:
            body["validation"] = rule.validation
        mappings[rule.target] = body

    data["mappings"] = mappings

    path.write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    _setup_logging(args.log_level)

    def prompt(text: str) -> str:
        return input(text)

    try:
        while True:
            available = list_available_spec_versions()
            default_spec = "v1.2"
            if available and default_spec not in available:
                default_spec = available[-1]
            spec_version = args.spec
            if not spec_version:
                 if available:
                     options = [(v, v) for v in available]
                     spec_version = prompt_menu(
                         prompt,
                         "Select FOCUS spec version:",
                         options,
                         default=default_spec,
                     )
                 else:
                     spec_version = (
                         prompt(f"FOCUS spec version [{default_spec}]: ").strip()
                         or default_spec
                     )
            try:
                logger.debug("Loading FOCUS spec version: %s", spec_version)
                spec = load_focus_spec(spec_version)
                break
            except Exception as e:
                _eprint(f"Error: {e}")
                if args.spec:
                    return 2

        input_path = args.input or _prompt_input_path(prompt)

        # Read and validate input file
        df = None
        while df is None:
            if not input_path.exists():
                _eprint(f"Error: input file not found: {input_path}")
                if args.input:
                    return 2
                input_path = _prompt_input_path(prompt)
                continue

            try:
                logger.debug("Reading input dataset: %s", input_path)
                df = read_table(input_path)
            except Exception as e:
                _eprint(f"Error: failed to read input file: {e}")
                if args.input:
                    return 2
                input_path = _prompt_input_path(prompt)

        output_path = args.output
        while output_path is None:
            with path_completion():
                val = prompt("Output mapping YAML path [mapping.yaml]: ").strip()
            output_path = _path(val or "mapping.yaml")

        include_recommended = args.include_recommended
        if not include_recommended:
            answer = prompt("Include Recommended columns? [y/N] ").strip().lower()
            include_recommended = answer in {"y", "yes"}

        include_conditional = args.include_conditional
        if not include_conditional:
            answer = prompt("Include Conditional columns? [y/N] ").strip().lower()
            include_conditional = answer in {"y", "yes"}

        include_optional = args.include_optional
        if not include_optional:
            answer = prompt("Include Optional columns? [y/N] ").strip().lower()
            include_optional = answer in {"y", "yes"}

        logger.debug("Starting interactive wizard...")
        result = run_wizard(
            spec=spec,
            input_df=df,
            prompt=prompt,
            include_optional=include_optional,
            include_recommended=include_recommended,
            include_conditional=include_conditional,
        )

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Writing mapping configuration to: %s", output_path)
            _write_mapping(output_path, result.mapping)
            print(f"Wrote mapping to {output_path}")
            return 0
        except Exception as e:
            logger.exception(f"Failed to write mapping file: {e}")
            return 2
    except KeyboardInterrupt:
        print("\n\nWizard interrupted by user. Exiting...")
        return 130  # Standard exit code for Ctrl+C


if __name__ == "__main__":
    raise SystemExit(main())
