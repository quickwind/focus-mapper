from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .completer import path_completion
from .io import read_table
from .mapping.config import MappingConfig
from .spec import load_focus_spec
from .wizard import run_wizard

logger = logging.getLogger("focus_report.wizard")


def _path(p: str) -> Path:
    return Path(p).expanduser()


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
    p = argparse.ArgumentParser(prog="focus_report_wizard")
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
    lines: list[str] = []
    lines.append(f'spec_version: "{mapping.spec_version}"\n')
    lines.append("mappings:\n")
    for rule in mapping.rules:
        lines.append(f"  {rule.target}:\n")
        if rule.description:
            lines.append(f'    description: "{rule.description}"\n')
        lines.append("    steps:\n")
        for step in rule.steps:
            lines.append(f"      - op: {step['op']}\n")
            for k, v in step.items():
                if k == "op":
                    continue
                if v is None:
                    lines.append(f"        {k}: null\n")
                elif isinstance(v, str):
                    lines.append(f'        {k}: "{v}"\n')
                elif isinstance(v, list):
                    lines.append(f"        {k}:\n")
                    for item in v:
                        lines.append(f'          - "{item}"\n')
                else:
                    lines.append(f"        {k}: {v}\n")
        lines.append("\n")
    path.write_text("".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    _setup_logging(args.log_level)

    def prompt(text: str) -> str:
        return input(text)

    while True:
        spec_version = (
            args.spec or prompt("FOCUS spec version [v1.2]: ").strip() or "v1.2"
        )
        try:
            logger.debug("Loading FOCUS spec version: %s", spec_version)
            spec = load_focus_spec(spec_version)
            break
        except Exception as e:
            _eprint(f"Error: {e}")
            if args.spec:
                return 2

    input_path = args.input
    while input_path is None:
        with path_completion():
            val = prompt("Input file (CSV/Parquet): ").strip()
        if val:
            input_path = _path(val)

    df = None
    while df is None:
        if not input_path.exists():
            _eprint(f"Error: input file not found: {input_path}")
            if args.input:
                return 2
            input_path = None
            while input_path is None:
                with path_completion():
                    val = prompt("Input file (CSV/Parquet): ").strip()
                if val:
                    input_path = _path(val)
            continue

        try:
            logger.debug("Reading input dataset: %s", input_path)
            df = read_table(input_path)
        except Exception as e:
            _eprint(f"Error: failed to read input file: {e}")
            if args.input:
                return 2
            input_path = None
            while input_path is None:
                with path_completion():
                    val = prompt("Input file (CSV/Parquet): ").strip()
                if val:
                    input_path = _path(val)

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
        logger.exception("Failed to write mapping file")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
