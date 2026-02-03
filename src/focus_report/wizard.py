from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

from .mapping.config import MappingConfig, MappingRule
from .spec import FocusSpec


PromptFunc = Callable[[str], str]


@dataclass(frozen=True)
class WizardResult:
    mapping: MappingConfig
    selected_targets: list[str]


def run_wizard(
    *,
    spec: FocusSpec,
    input_df: pd.DataFrame,
    prompt: PromptFunc,
    include_optional: bool,
    include_recommended: bool,
) -> WizardResult:
    columns = list(input_df.columns)
    normalized = {_norm(c): c for c in columns}

    targets = _select_targets(
        spec, include_optional=include_optional, include_recommended=include_recommended
    )
    rules: list[MappingRule] = []

    for target in targets:
        suggested = _suggest_column(target, normalized)
        steps = _prompt_for_steps(
            target=target, columns=columns, suggested=suggested, prompt=prompt
        )
        rules.append(MappingRule(target=target, steps=steps, description=None))

    # Extension columns
    ext_rules = _prompt_extension_columns(columns=columns, prompt=prompt)
    rules.extend(ext_rules)

    return WizardResult(
        mapping=MappingConfig(spec_version=f"v{spec.version}", rules=rules),
        selected_targets=targets,
    )


def _select_targets(
    spec: FocusSpec, *, include_optional: bool, include_recommended: bool
) -> list[str]:
    targets: list[str] = []
    for col in spec.columns:
        level = col.feature_level.strip().lower()
        if level == "mandatory":
            targets.append(col.name)
        elif level == "recommended" and include_recommended:
            targets.append(col.name)
        elif level == "optional" and include_optional:
            targets.append(col.name)
        elif level == "conditional":
            # conditional columns are not automatically selected
            continue
    return targets


def _prompt_for_steps(
    *,
    target: str,
    columns: list[str],
    suggested: str | None,
    prompt: PromptFunc,
) -> list[dict]:
    header = f"Target: {target}"
    if suggested:
        header += f" (suggested input: {suggested})"
    _ = prompt(f"{header}\n")

    while True:
        choice = prompt(
            "Choose mapping: [1] from_column [2] const [3] coalesce [4] skip\n> "
        ).strip()
        if choice in {"1", "from_column"}:
            col = _pick_column(columns, prompt=prompt, suggested=suggested)
            return [{"op": "from_column", "column": col}]
        if choice in {"2", "const"}:
            value = prompt("Enter constant value (empty for null): ")
            return [{"op": "const", "value": value if value != "" else None}]
        if choice in {"3", "coalesce"}:
            cols = _pick_columns(columns, prompt=prompt, suggested=suggested)
            return [{"op": "coalesce", "columns": cols}]
        if choice in {"4", "skip"}:
            return [{"op": "const", "value": None}]


def _prompt_extension_columns(
    *, columns: list[str], prompt: PromptFunc
) -> list[MappingRule]:
    rules: list[MappingRule] = []
    while True:
        add = prompt("Add x_ extension column? [y/N] ").strip().lower()
        if add not in {"y", "yes"}:
            return rules

        name = prompt("Extension column name (must start with x_): ").strip()
        if not name.startswith("x_"):
            prompt("Name must start with x_. Skipping.\n")
            continue
        desc = prompt("Description (optional): ").strip() or None
        col = _pick_column(columns, prompt=prompt, suggested=None)
        rules.append(
            MappingRule(
                target=name,
                steps=[{"op": "from_column", "column": col}],
                description=desc,
            )
        )


def _pick_column(
    columns: list[str], *, prompt: PromptFunc, suggested: str | None
) -> str:
    if suggested and suggested in columns:
        use = prompt(f"Use suggested column '{suggested}'? [Y/n] ").strip().lower()
        if use in {"", "y", "yes"}:
            return suggested

    prompt("Available columns:\n" + "\n".join(f"- {c}" for c in columns) + "\n")
    while True:
        col = prompt("Enter column name: ").strip()
        if col in columns:
            return col


def _pick_columns(
    columns: list[str], *, prompt: PromptFunc, suggested: str | None
) -> list[str]:
    if suggested and suggested in columns:
        use = (
            prompt(f"Use suggested column '{suggested}' as first? [Y/n] ")
            .strip()
            .lower()
        )
        if use in {"", "y", "yes"}:
            picked = [suggested]
        else:
            picked = []
    else:
        picked = []

    prompt("Available columns:\n" + "\n".join(f"- {c}" for c in columns) + "\n")
    while True:
        col = prompt("Add column (empty to finish): ").strip()
        if not col:
            break
        if col in columns and col not in picked:
            picked.append(col)
    return picked or [suggested] if suggested else picked


def _suggest_column(target: str, normalized: dict[str, str]) -> str | None:
    key = _norm(target)
    if key in normalized:
        return normalized[key]
    alt = key.replace("_", "")
    for n, original in normalized.items():
        if n.replace("_", "") == alt:
            return original
    return None


def _norm(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum() or ch == "_")
