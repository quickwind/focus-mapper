from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Callable

import pandas as pd

from .mapping.config import MappingConfig, MappingRule
from .completer import column_completion, value_completion
from .spec import FocusSpec, FocusColumnSpec


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
    include_conditional: bool,
) -> WizardResult:
    columns = list(input_df.columns)
    normalized = {_norm(c): c for c in columns}

    default_validation = _prompt_validation_defaults(prompt=prompt)

    targets = _select_targets(
        spec,
        include_optional=include_optional,
        include_recommended=include_recommended,
        include_conditional=include_conditional,
    )
    rules: list[MappingRule] = []

    for target in targets:
        suggested = _suggest_column(target.name, normalized)
        steps = _prompt_for_steps(
            target=target, columns=columns, suggested=suggested, prompt=prompt
        )
        if steps:
            steps = _maybe_append_cast(
                steps=steps,
                data_type=target.data_type,
                numeric_scale=target.numeric_scale,
            )
            validation = _prompt_column_validation(
                target_name=target.name,
                data_type=target.data_type,
                prompt=prompt,
            )
            rules.append(
                MappingRule(
                    target=target.name,
                    steps=steps,
                    description=None,
                    validation=validation,
                )
            )

    # Extension columns
    ext_rules = _prompt_extension_columns(columns=columns, prompt=prompt)
    rules.extend(ext_rules)

    return WizardResult(
        mapping=MappingConfig(
            spec_version=f"v{spec.version}",
            rules=rules,
            validation_defaults=default_validation,
        ),
        selected_targets=[t.name for t in targets],
    )


def _select_targets(
    spec: FocusSpec,
    *,
    include_optional: bool,
    include_recommended: bool,
    include_conditional: bool,
) -> list[FocusColumnSpec]:
    targets: list[FocusColumnSpec] = []
    for col in spec.columns:
        level = col.feature_level.strip().lower()
        if level == "mandatory":
            targets.append(col)
        elif level == "recommended" and include_recommended:
            targets.append(col)
        elif level == "optional" and include_optional:
            targets.append(col)
        elif level == "conditional" and include_conditional:
            targets.append(col)
    return targets


def _prompt_for_steps(
    *,
    target: FocusColumnSpec,
    columns: list[str],
    suggested: str | None,
    prompt: PromptFunc,
) -> list[dict]:
    header = f"{'=' * 50}\nTarget column: \n\t{target.name} ({target.feature_level})"
    if target.description:
        header += f"\n\n\tDescription: {target.description}"
    if suggested:
        header += f"\n\n\t(suggested input: {suggested})"
    _ = print(f"{header}\n")

    allow_cast = target.data_type.strip().lower() not in {
        "string",
        "decimal",
        "date/time",
        "json",
    }
    allow_skip = target.feature_level.strip().lower() != "mandatory"
    steps: list[dict] = []
    has_series = False
    while True:
        if not has_series:
            if allow_cast:
                choice = prompt(
                    "Choose mapping (init): [1] from_column [2] const [3] coalesce "
                    "[4] map_values [5] concat [6] math [7] pandas_expr"
                    + (" [8] skip" if allow_skip else "")
                    + "\n> "
                ).strip()
            else:
                choice = prompt(
                    "Choose mapping (init): [1] from_column [2] const [3] coalesce "
                    "[4] map_values [5] concat [6] math [7] pandas_expr"
                    + (" [8] skip" if allow_skip else "")
                    + "\n> "
                ).strip()
            if allow_skip and choice in {"8", "skip"}:
                return []
        else:
            if allow_cast:
                choice = prompt(
                    "Add step: [1] map_values [2] cast [3] round [4] math "
                    '[5] when [6] pandas_expr [7] done\n(Default is "done") > '
                ).strip()
            else:
                choice = prompt(
                    "Add step: [1] map_values [2] round [3] math "
                    '[4] when [5] pandas_expr [6] done\n(Default is "done") > '
                ).strip()
            if (
                not choice
                or choice in {"7", "done"}
                or (not allow_cast and choice in {"6", "done"})
            ):
                return steps

        if not has_series:
            if choice in {"1", "from_column"}:
                col = _pick_column(columns, prompt=prompt, suggested=suggested)
                steps.append({"op": "from_column", "column": col})
                has_series = True
            elif choice in {"2", "const"}:
                allowed = target.allowed_values or []
                allow_null = bool(target.allows_nulls)
                if allowed:
                    print(
                        "Allowed values:\n"
                        + "\n".join(f"- {v}" for v in allowed)
                        + "\n"
                    )
                    while True:
                        with value_completion(allowed):
                            value = prompt(
                                "Choose allowed value"
                                + (" (empty for null)" if allow_null else "")
                                + ": "
                            ).strip()
                        if (allow_null and value == "") or value in allowed:
                            steps.append(
                                {"op": "const", "value": value if value != "" else None}
                            )
                            break
                else:
                    value = prompt(
                        "Enter constant value"
                        + (" (empty for null)" if allow_null else "")
                        + ": "
                    )
                    if value == "" and not allow_null:
                        print("Null is not allowed for this column.\n")
                        continue
                    steps.append(
                        {"op": "const", "value": value if value != "" else None}
                    )
                has_series = True
            elif choice in {"3", "coalesce"}:
                cols = _pick_columns(columns, prompt=prompt, suggested=suggested)
                steps.append({"op": "coalesce", "columns": cols})
                has_series = True
            elif choice in {"4", "map_values"}:
                col = _pick_column(columns, prompt=prompt, suggested=suggested)
                mapping: dict[str, str] = {}
                print("Enter mapping pairs (empty key to finish).")
                while True:
                    key = prompt("  from: ").strip()
                    if not key:
                        break
                    val = prompt("  to: ").strip()
                    mapping[key] = val
                default = prompt("Default value (empty for null): ").strip()
                step = {"op": "map_values", "column": col, "mapping": mapping}
                if default != "":
                    step["default"] = default
                steps.append(step)
                has_series = True
            elif choice in {"5", "concat"}:
                cols = _pick_columns(columns, prompt=prompt, suggested=suggested)
                sep = prompt("Separator (empty for none): ").strip()
                steps.append({"op": "concat", "columns": cols, "sep": sep})
                has_series = True
            elif choice in {"6", "math"}:
                operator = prompt("Operator [add|sub|mul|div]: ").strip()
                operands: list[dict] = []
                while True:
                    kind = prompt(
                        "Add operand type [column|const] (empty to finish): "
                    ).strip()
                    if not kind:
                        break
                    if kind == "column":
                        col = _pick_column(columns, prompt=prompt, suggested=suggested)
                        operands.append({"column": col})
                    elif kind == "const":
                        val = prompt("Constant value: ").strip()
                        operands.append({"const": val})
                steps.append({"op": "math", "operator": operator, "operands": operands})
                has_series = True
            elif choice in {"7", "pandas_expr"}:
                expr = prompt(
                    "Enter pandas expression (use df, pd, and/or current): "
                ).strip()
                steps.append({"op": "pandas_expr", "expr": expr})
                has_series = True
        else:
            if choice in {"1", "map_values"}:
                mapping: dict[str, str] = {}
                print("Enter mapping pairs (empty key to finish).")
                while True:
                    key = prompt("  from: ").strip()
                    if not key:
                        break
                    val = prompt("  to: ").strip()
                    mapping[key] = val
                default = prompt("Default value (empty for null): ").strip()
                step = {"op": "map_values", "mapping": mapping}
                if default != "":
                    step["default"] = default
                steps.append(step)
            elif allow_cast and choice in {"2", "cast"}:
                to = prompt(
                    "Cast to type [string|float|int|datetime|decimal]: "
                ).strip()
                step: dict = {"op": "cast", "to": to}
                if to == "decimal":
                    scale = prompt("Decimal scale (int, empty for none): ").strip()
                    if scale != "":
                        step["scale"] = int(scale)
                    precision = prompt(
                        "Decimal precision (int, empty for none): "
                    ).strip()
                    if precision != "":
                        step["precision"] = int(precision)
                steps.append(step)
            elif (allow_cast and choice in {"3", "round"}) or (
                not allow_cast and choice in {"2", "round"}
            ):
                ndigits = _prompt_int(prompt, "Round ndigits (int, default 0): ")
                steps.append({"op": "round", "ndigits": ndigits if ndigits is not None else 0})
            elif (allow_cast and choice in {"4", "math"}) or (
                not allow_cast and choice in {"3", "math"}
            ):
                operator = prompt("Operator [add|sub|mul|div]: ").strip()
                operands: list[dict] = []
                while True:
                    kind = prompt(
                        "Add operand type [current|column|const] (empty to finish): "
                    ).strip()
                    if not kind:
                        break
                    if kind == "current":
                        operands.append({"current": True})
                    elif kind == "column":
                        col = _pick_column(columns, prompt=prompt, suggested=suggested)
                        operands.append({"column": col})
                    elif kind == "const":
                        val = prompt("Constant value: ").strip()
                        operands.append({"const": val})
                steps.append({"op": "math", "operator": operator, "operands": operands})
            elif (allow_cast and choice in {"5", "when"}) or (
                not allow_cast and choice in {"4", "when"}
            ):
                col = _pick_column(columns, prompt=prompt, suggested=suggested)
                value = prompt("If value equals: ").strip()
                then_value = prompt("Then value: ").strip()
                else_value = prompt("Else value (empty for null): ").strip()
                step: dict = {
                    "op": "when",
                    "column": col,
                    "value": value,
                    "then": then_value,
                }
                if else_value != "":
                    step["else"] = else_value
                steps.append(step)
            elif (allow_cast and choice in {"6", "pandas_expr"}) or (
                not allow_cast and choice in {"5", "pandas_expr"}
            ):
                expr = prompt(
                    "Enter pandas expression (use df, pd, and/or current): "
                ).strip()
                steps.append({"op": "pandas_expr", "expr": expr})


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
            print("Name must start with x_. Skipping.\n")
            continue
        desc = prompt("Description (optional): ").strip() or None
        col = _pick_column(columns, prompt=prompt, suggested=None)
        validation = _prompt_column_validation(
            target_name=name,
            data_type=None,
            prompt=prompt,
        )
        rules.append(
            MappingRule(
                target=name,
                steps=[{"op": "from_column", "column": col}],
                description=desc,
                validation=validation,
            )
        )


def _pick_column(
    columns: list[str], *, prompt: PromptFunc, suggested: str | None
) -> str:
    if suggested and suggested in columns:
        use = prompt(f"Use suggested column '{suggested}'? [Y/n] ").strip().lower()
        if use in {"", "y", "yes"}:
            return suggested

    print("Available columns:\n" + "\n".join(f"- {c}" for c in columns) + "\n")
    while True:
        with column_completion(columns):
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

    print("Available columns:\n" + "\n".join(f"- {c}" for c in columns) + "\n")
    while True:
        with column_completion(columns):
            col = prompt("Add column (empty to finish): ").strip()
        if not col:
            break
        if col in columns and col not in picked:
            picked.append(col)
    return picked


def _suggest_column(target: str, normalized: dict[str, str]) -> str | None:
    key = _norm(target)
    if key in normalized:
        return normalized[key]
    alt = key.replace("_", "")
    for n, original in normalized.items():
        if n.replace("_", "") == alt:
            return original
    return None


def _prompt_validation_defaults(*, prompt: PromptFunc) -> dict:
    defaults = _default_validation_settings()
    summary = (
        "Default validation settings:\n"
        "- mode: permissive\n"
        "- datetime: infer format\n"
        "- decimal: no precision/scale limits\n"
        "- string: no length limits, trim=true, allow_empty=true\n"
        "- json: allow any JSON type\n"
        "- allowed values: case-sensitive\n"
        "- nullable: follow spec\n"
    )
    print(summary)
    use = prompt("Use these defaults? [Y/n] ").strip().lower()
    if use in {"", "y", "yes"}:
        return {}

    mode = _prompt_choice(
        prompt,
        "Default mode [permissive/strict] (permissive): ",
        {"permissive", "strict"},
        default="permissive",
    )
    if mode:
        defaults["mode"] = mode

    dt_format = _prompt_datetime_format(
        prompt, "Default datetime format (empty = infer): "
    )
    if dt_format:
        defaults["datetime"]["format"] = dt_format

    dec_precision = _prompt_int(prompt, "Default decimal precision (empty = none): ")
    if dec_precision is not None:
        defaults["decimal"]["precision"] = dec_precision
    dec_scale = _prompt_int(prompt, "Default decimal scale (empty = none): ")
    if dec_scale is not None:
        defaults["decimal"]["scale"] = dec_scale
    defaults["decimal"]["integer_only"] = _prompt_bool(
        prompt, "Default decimal integer_only? [y/N] ", default=False
    )

    s_max = _prompt_int(prompt, "Default string max length (empty = none): ")
    if s_max is not None:
        defaults["string"]["max_length"] = s_max
    s_min = _prompt_int(prompt, "Default string min length (empty = none): ")
    if s_min is not None:
        defaults["string"]["min_length"] = s_min
    defaults["string"]["trim"] = _prompt_bool(
        prompt, "Default string trim? [Y/n] ", default=True
    )
    defaults["string"]["allow_empty"] = _prompt_bool(
        prompt, "Default string allow empty? [Y/n] ", default=True
    )

    defaults["json"]["object_only"] = _prompt_bool(
        prompt, "Default JSON object_only? [y/N] ", default=False
    )

    defaults["allowed_values"]["case_insensitive"] = _prompt_bool(
        prompt, "Allowed values case-insensitive? [Y/n] ", default=True
    )

    nullable = _prompt_bool(
        prompt,
        "Override nullable? [y/n/empty for spec]: ",
        default=None,
    )
    if nullable is not None:
        defaults["nullable"]["allow_nulls"] = nullable

    return defaults


def _default_validation_settings() -> dict:
    return {
        "mode": "permissive",
        "datetime": {"format": None},
        "decimal": {
            "precision": None,
            "scale": None,
            "integer_only": False,
            "min": None,
            "max": None,
        },
        "string": {
            "min_length": None,
            "max_length": None,
            "allow_empty": True,
            "trim": True,
        },
        "json": {"object_only": False},
        "allowed_values": {"case_insensitive": False},
        "nullable": {"allow_nulls": None},
        "presence": {"enforce": True},
    }


def _prompt_column_validation(
    *, target_name: str, data_type: str | None, prompt: PromptFunc
) -> dict | None:
    use = prompt(f"Override validation for {target_name}? [y/N] ").strip().lower()
    if use not in {"y", "yes"}:
        return None

    if data_type is None:
        data_type = (
            _prompt_choice(
                prompt,
                "Column type [string|decimal|datetime|json]: ",
                {"string", "decimal", "datetime", "json"},
                default="string",
            )
            or "string"
        )
    else:
        data_type = data_type.strip().lower()

    out: dict = {}
    mode = _prompt_choice(
        prompt,
        "Mode override [permissive/strict/empty]: ",
        {"permissive", "strict"},
        default=None,
        allow_empty=True,
    )
    if mode:
        out["mode"] = mode

    nullable = _prompt_bool(prompt, "Override nullable? [y/n/empty]: ", default=None)
    if nullable is not None:
        out.setdefault("nullable", {})["allow_nulls"] = nullable

    if data_type in {"datetime", "date/time"}:
        fmt = _prompt_datetime_format(
            prompt, "Datetime format override (empty = infer): "
        )
        if fmt:
            out.setdefault("datetime", {})["format"] = fmt
    elif data_type == "decimal":
        prec = _prompt_int(prompt, "Decimal precision override (empty = none): ")
        if prec is not None:
            out.setdefault("decimal", {})["precision"] = prec
        scale = _prompt_int(prompt, "Decimal scale override (empty = none): ")
        if scale is not None:
            out.setdefault("decimal", {})["scale"] = scale
        integer_only = _prompt_bool(
            prompt, "Decimal integer_only? [y/N] ", default=False
        )
        out.setdefault("decimal", {})["integer_only"] = integer_only
        min_val = _prompt_decimal(prompt, "Decimal min (empty = none): ")
        if min_val is not None:
            out.setdefault("decimal", {})["min"] = str(min_val)
        max_val = _prompt_decimal(prompt, "Decimal max (empty = none): ")
        if max_val is not None:
            out.setdefault("decimal", {})["max"] = str(max_val)
    elif data_type == "string":
        min_len = _prompt_int(prompt, "String min length (empty = none): ")
        if min_len is not None:
            out.setdefault("string", {})["min_length"] = min_len
        max_len = _prompt_int(prompt, "String max length (empty = none): ")
        if max_len is not None:
            out.setdefault("string", {})["max_length"] = max_len
        out.setdefault("string", {})["allow_empty"] = _prompt_bool(
            prompt, "Allow empty string? [Y/n] ", default=True
        )
        out.setdefault("string", {})["trim"] = _prompt_bool(
            prompt, "Trim strings before checks? [Y/n] ", default=True
        )
    elif data_type == "json":
        out.setdefault("json", {})["object_only"] = _prompt_bool(
            prompt, "Require JSON object only? [y/N] ", default=False
        )

    allowed_ci = _prompt_bool(
        prompt, "Allowed values case-insensitive? [Y/n/empty]: ", default=None
    )
    if allowed_ci is not None:
        out.setdefault("allowed_values", {})["case_insensitive"] = allowed_ci

    presence = _prompt_bool(
        prompt, "Enforce presence for this column? [Y/n/empty]: ", default=None
    )
    if presence is not None:
        out.setdefault("presence", {})["enforce"] = presence

    return out or None


def _maybe_append_cast(
    *, steps: list[dict], data_type: str | None, numeric_scale: int | None
) -> list[dict]:
    if not data_type or not steps:
        return steps
    if steps[-1].get("op") == "cast":
        return steps

    t = data_type.strip().lower()
    to = None
    if t == "string":
        to = "string"
    elif t == "decimal":
        to = "decimal"
    elif t == "date/time":
        to = "datetime"

    if to is None:
        return steps

    cast_step: dict = {"op": "cast", "to": to}
    if to == "decimal" and numeric_scale is not None:
        cast_step["scale"] = int(numeric_scale)
    return [*steps, cast_step]


def _prompt_int(prompt: PromptFunc, text: str) -> int | None:
    while True:
        value = prompt(text).strip()
        if value == "":
            return None
        try:
            return int(value)
        except ValueError:
            print("Invalid integer. Try again.\n")


def _prompt_bool(prompt: PromptFunc, text: str, *, default: bool | None) -> bool | None:
    while True:
        value = prompt(text).strip().lower()
        if value == "":
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Invalid choice. Enter y or n.\n")


def _prompt_choice(
    prompt: PromptFunc,
    text: str,
    choices: set[str],
    *,
    default: str | None,
    allow_empty: bool = False,
) -> str | None:
    while True:
        value = prompt(text).strip().lower()
        if value == "":
            if allow_empty:
                return default
            # If empty not allowed and there's a default, use it
            if default is not None:
                return default
            print("Empty input not allowed. Please enter a value.\n")
            continue
        if value in choices:
            return value
        print(f"Invalid choice. Options: {', '.join(sorted(choices))}\n")


def _prompt_decimal(prompt: PromptFunc, text: str) -> Decimal | None:
    while True:
        value = prompt(text).strip()
        if value == "":
            return None
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError):
            print("Invalid number. Try again.\n")


def _prompt_datetime_format(prompt: PromptFunc, text: str) -> str | None:
    while True:
        value = prompt(text).strip()
        if value == "":
            return None
        if "%" not in value or not any(
            token in value for token in ("%Y", "%y", "%m", "%d", "%H", "%M", "%S")
        ):
            print("Invalid format. Include datetime directives like %Y-%m-%d.\n")
            continue
        try:
            now = datetime.now(timezone.utc)
            _ = now.strftime(value)
        except Exception:
            print("Invalid datetime format string. Try again.\n")
            continue
        return value


def _norm(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum() or ch == "_")
