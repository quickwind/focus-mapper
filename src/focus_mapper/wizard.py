from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Callable

import pandas as pd

from .mapping.config import MappingConfig, MappingRule
from .spec import FocusSpec, FocusColumnSpec
from .wizard_lib import (
    PromptFunc,
    column_completion,
    value_completion,
    prompt_menu,
    prompt_int,
    prompt_decimal,
    prompt_bool,
    prompt_choice,
    prompt_datetime_format,
)
from .format_validators import (
    validate_key_value_format,
    validate_json_object_format,
    validate_currency_format,
    validate_datetime_format,
    validate_numeric_format,
    validate_integer,
    validate_boolean,
    validate_collection_of_strings,
)


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
    sample_df: pd.DataFrame | None = None,
    resume_config: MappingConfig | None = None,
    save_callback: Callable[[MappingConfig], None] | None = None,
) -> WizardResult:
    columns = list(input_df.columns)
    normalized = {_norm(c): c for c in columns}

    # -- Initialization Logic --
    if resume_config:
        print(f"Resuming configuration with {len(resume_config.rules)} existing rules.")
        default_validation = resume_config.validation_defaults
        dataset_type = resume_config.dataset_type
        dataset_instance_name = resume_config.dataset_instance_name
        creation_date = resume_config.creation_date
        
        # We need to construct the *initial* list of rules from resume_config
        rules = list(resume_config.rules)
        existing_targets = {r.target for r in rules}
        skipped_targets = set(resume_config.skipped_columns or [])
    else:
        # Prompt for dataset details EARLY (v1.3+)
        dataset_type = "CostAndUsage"
        dataset_instance_name = None
        if spec.version >= "1.3":
            # For now, hardcode CostAndUsage as per requirement
            # dataset_type = prompt_menu(...)
            print(f"Using Dataset Type: {dataset_type}")
            dataset_instance_name = prompt("Dataset Instance Name: ").strip() or None

        default_validation = _prompt_validation_defaults(prompt=prompt)
        creation_date = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        rules = []
        existing_targets = set()
        skipped_targets = set()

    # Ask validation overrides for BOTH new and resume flows
    ask_validation_overrides = prompt_bool(
        prompt, 
        "Do you want to ever override validation for specific columns? [y/N] ", 
        default=False
    )
    if ask_validation_overrides is None:
         ask_validation_overrides = False

    # Define helper to build current config for saving
    def build_current_config() -> MappingConfig:
        return MappingConfig(
            spec_version=f"v{spec.version}",
            rules=rules,
            validation_defaults=default_validation,
            creation_date=creation_date,
            dataset_type=dataset_type,
            dataset_instance_name=dataset_instance_name,
            skipped_columns=sorted(list(skipped_targets)),
        )

    targets = _select_targets(
        spec,
        include_optional=include_optional,
        include_recommended=include_recommended,
        include_conditional=include_conditional,
    )

    for target in targets:
        if target.name in existing_targets:
            continue
        if target.name in skipped_targets:
            continue

        suggested = _suggest_column(target.name, normalized)
        steps = _prompt_for_steps(
            target=target, 
            columns=columns, 
            suggested=suggested, 
            prompt=prompt,
            sample_df=sample_df,
        )
        if steps:
            steps = _maybe_append_cast(
                steps=steps,
                data_type=target.data_type,
                numeric_scale=target.numeric_scale,
            )
            
            validation = None
            if ask_validation_overrides:
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
                    data_type=target.data_type,
                    validation=validation,
                )
            )
            # If it was previously skipped (edge case if logic changes), unskip it
            skipped_targets.discard(target.name)
            
            # Incremental Save
            if save_callback:
                save_callback(build_current_config())
        else:
             # User skipped (or provided no steps)
             # We record this as explicitly skipped so we don't prompt again on resume
             skipped_targets.add(target.name)
             if save_callback:
                 save_callback(build_current_config())

    # Extension columns (always append to end if not present? Or allow adding more?)
    # For resume, we usually assume existing ones are done. We can prompt for *new* ones.
    # But usually extension columns are added at end.
    # The simple resume logic is: replay what we have, then continue with standard targets, then ask for extensions.
    # Issues: if user resumed, they might want to add MORE extensions.
    # The current `ext_rules` logic loops until user says no.
    current_ext_targets = {r.target for r in rules if r.target.startswith("x_")}
    
    def on_ext_rule(rule: MappingRule):
        # We append to the main rules list so it's included in the config
        # Note: _prompt_extension_columns also maintains a local list but we ignore its return value
        # to avoid duplication or need for merging.
        # Actually, to be safe against double-adding if we used the return value,
        # we should just trust the callback.
        
        # But wait, `rules` is a local variable in run_wizard. 
        # Python closures format: `rules` is captured.
        rules.append(rule)
        if save_callback:
             save_callback(build_current_config())

    _ = _prompt_extension_columns(
        columns=columns, 
        normalized=normalized,
        prompt=prompt, 
        existing_targets=current_ext_targets,
        on_rule_added=on_ext_rule,
        ask_validation_overrides=ask_validation_overrides,
        sample_df=sample_df,
    )
    # We ignore the returned rules list because on_ext_rule handles appending and saving.

    return WizardResult(
        mapping=build_current_config(),
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
    sample_df: pd.DataFrame | None = None,
) -> list[dict]:
    header = f"{'=' * 50}\nTarget column: \n\t{target.name} ({target.feature_level})"
    if target.data_type:
        header += f"\n\n\tData Type: {target.data_type}"
    if target.value_format:
        header += f" ({target.value_format})"
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
    allow_null = bool(target.allows_nulls)
    data_type = target.data_type.strip().lower() if target.data_type else ""
    is_string = data_type == "string"
    
    while True:
        choice = ""
        step_config: dict | None = None
        op_type = ""

        if not has_series:
            # Build menu options based on column properties
            init_options: list[tuple[str, str]] = [
                ("from_column", "from_column"),
                ("const", "const"),
            ]
            if allow_null:
                init_options.append(("null", "null"))
            init_options.extend([
                ("coalesce", "coalesce"),
                ("map_values", "map_values"),
                ("concat", "concat"),
                ("math", "math"),
                ("sql", "sql"),
                ("pandas_expr", "pandas_expr"),
            ])
            if allow_skip:
                init_options.append(("skip", "skip"))
            
            choice = prompt_menu(prompt, "Choose mapping (init):", init_options)
            if choice == "skip":
                return []
        else:
            # Build add-step options
            add_options: list[tuple[str, str]] = [("map_values", "map_values")]
            if allow_cast:
                add_options.append(("cast", "cast"))
            add_options.extend([
                ("round", "round"),
                ("math", "math"),
                ("when", "when"),
                ("sql", "sql"),
                ("pandas_expr", "pandas_expr"),
                ("done", "done"),
            ])
            
            choice = prompt_menu(prompt, "Add additional step (if needed): ", add_options, default="done")
            if choice == "done":
                return steps

        # --- Gather Step Inputs ---
        if choice == "from_column":
            col = _pick_column(columns, prompt=prompt, suggested=suggested)
            op_type = "from_column"
            step_config = {"column": col}
        elif choice == "const":
            # ... existing const logic ...
            # To keep diff clean, we will reuse existing logic flow but wrapped
            # actually we need to refactor slightly to separate input gathering from appending
            # for preview support.
            # But the existing code has complex logic inside the ifs (like loop for allowed values).
            # We can just copy the logic or refactor.
            # Given the constraints, let's keep it inline but assign to `step_config`.
            
            allowed = target.allowed_values or []
            if allowed:
                print(
                    "Allowed values:\n"
                    + "\n".join(f"- {v}" for v in allowed)
                    + "\n"
                )
                while True:
                    with value_completion(allowed):
                        value = prompt("Choose allowed value: ").strip()
                    if value in allowed:
                        op_type = "const"
                        step_config = {"value": value}
                        break
                    print(f"Value must be one of: {', '.join(allowed)}\n")
            else:
                while True:
                    vf_hint = ""
                    if target.value_format:
                        vf_hint = f" (Format: {target.value_format})"
                    elif data_type and not is_string:
                        vf_hint = f" (Type: {data_type})"

                    value = prompt(f"Enter constant value{vf_hint}: ")
                    
                    if is_string and not allow_null:
                        if value == "" or value.strip() == "":
                            print(
                                "Error: Empty strings and whitespace-only strings are not allowed "
                                "for non-nullable string columns (per FOCUS spec).\n"
                            )
                            continue
                    
                    should_validate = (
                        (value and not is_string and data_type) or 
                        (value and target.value_format)
                    )
                    
                    if should_validate:
                        is_valid, error_msg = _validate_const_value(
                            value, data_type, target.value_format
                        )
                        if not is_valid:
                            print(f"Error: {error_msg}\n")
                            continue
                    
                    op_type = "const"
                    step_config = {"value": value}
                    break

        elif choice == "null":
            op_type = "null"
            step_config = {}
        elif choice == "coalesce":
            cols = _pick_columns(columns, prompt=prompt, suggested=suggested)
            op_type = "coalesce"
            step_config = {"columns": cols}
        elif choice == "map_values":
            col = None
            if not has_series:
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
            op_type = "map_values"
            step_config = {"mapping": mapping}
            if col:
                step_config["column"] = col
            if default != "":
                step_config["default"] = default

        elif choice == "concat":
            cols = _pick_columns(columns, prompt=prompt, suggested=suggested)
            sep = prompt("Separator (empty for none): ").strip()
            op_type = "concat"
            step_config = {"columns": cols, "sep": sep}
        elif choice == "math":
            operator = prompt("Operator [add|sub|mul|div]: ").strip()
            operands: list[dict] = []
            while True:
                kind_prompt = "Add operand type [column|const] (empty to finish): "
                if has_series:
                     kind_prompt = "Add operand type [current|column|const] (empty to finish): "
                
                kind = prompt(kind_prompt).strip()
                if not kind:
                    break
                if kind == "current" and has_series:
                    operands.append({"current": True})
                elif kind == "column":
                    col = _pick_column(columns, prompt=prompt, suggested=suggested)
                    operands.append({"column": col})
                elif kind == "const":
                    val = prompt("Constant value: ").strip()
                    operands.append({"const": val})
            op_type = "math"
            step_config = {"operator": operator, "operands": operands}

        elif choice == "pandas_expr":
            expr = prompt(
                "Enter pandas expression (use df, pd, and/or current): "
            ).strip()
            op_type = "pandas_expr"
            step_config = {"expr": expr}

        elif choice == "sql":
            mode = prompt_menu(prompt, "SQL mode:", [("expr", "Expression (simple)"), ("query", "Query (full SQL)")])
            op_type = "sql"
            if mode == "expr":
                print("Enter a DuckDB SQL expression using column names directly.")
                print("Examples: 'a + b', 'CASE WHEN x = 1 THEN y ELSE z END', 'UPPER(name)'")
                expr = prompt("SQL expression: ").strip()
                step_config = {"expr": expr}
            else:
                print("Enter a full DuckDB SQL query. Use table name 'src'. Must return one column.")
                print("Example: 'SELECT a + b FROM src'")
                query = prompt("SQL query: ").strip()
                step_config = {"query": query}

        elif choice == "cast":
             to = prompt(
                "Cast to type [string|float|int|datetime|decimal]: "
            ).strip()
             op_type = "cast"
             step_config = {"to": to}
             if to == "decimal":
                scale = prompt("Decimal scale (int, empty for none): ").strip()
                if scale != "":
                    step_config["scale"] = int(scale)
                precision = prompt(
                    "Decimal precision (int, empty for none): "
                ).strip()
                if precision != "":
                    step_config["precision"] = int(precision)

        elif choice == "round":
            ndigits = prompt_int(prompt, "Round ndigits (int, default 0): ", default=0)
            op_type = "round"
            step_config = {"ndigits": ndigits if ndigits is not None else 0}

        elif choice == "when":
             col = _pick_column(columns, prompt=prompt, suggested=suggested)
             value = prompt("If value equals: ").strip()
             then_value = prompt("Then value: ").strip()
             else_value = prompt("Else value (empty for null): ").strip()
             op_type = "when"
             step_config = {
                "column": col,
                "value": value,
                "then": then_value,
             }
             if else_value != "":
                step_config["else"] = else_value

        # --- Preview & Validation ---
        # --- Preview & Validation ---
        if step_config is not None:
            if sample_df is not None and op_type in {"sql", "pandas_expr"}:
                try:
                    from .mapping.ops import apply_steps
                    
                    preview_steps = steps + [{"op": op_type, **step_config}]
                    
                    print(f"Running validation on {len(sample_df)} rows...")
                    # We use a dummy target name for preview
                    preview_series = apply_steps(
                        sample_df, 
                        steps=preview_steps, 
                        target=target.name
                    )
                    
                    # Enhanced Validation: Check Nulls & Types
                    validation_errors = []
                    
                    # 1. Nullability Check
                    if not allow_null and preview_series.hasnans:
                         validation_errors.append("Result contains nulls but column is Mandatory (not nullable).")
                    
                    # 2. Basic Type Compatibility (soft warning)
                    if not preview_series.empty:
                         dtype = preview_series.dtype
                         if data_type == "decimal" and not pd.api.types.is_numeric_dtype(dtype):
                              validation_errors.append(f"Expected decimal/numeric type, got {dtype}.")
                         elif data_type == "datetime" and not pd.api.types.is_datetime64_any_dtype(dtype):
                              validation_errors.append(f"Expected datetime type, got {dtype}.")

                    print("\nPreview results (first 5):")
                    print(preview_series.head(5).to_string())
                    
                    if validation_errors:
                        print("\n⚠️  Validation Issues:")
                        for err in validation_errors:
                            print(f"  - {err}")
                        if not prompt_bool(prompt, "\nDo you want to keep this step despite issues? [y/N] ", default=False):
                            continue
                    else:
                        print("\n✅ Step validation successful.")
                    
                except Exception as e:
                    print(f"\n❌ Validation failed: {e}")
                    # For sql/pandas_expr, we often want to fix the query immediately
                    if not prompt_bool(prompt, "Do you want to keep this step despite the error? [y/N] ", default=False):
                        continue

            steps.append({"op": op_type, **step_config})
            has_series = True



def _prompt_extension_columns(
    *, 
    columns: list[str], 
    normalized: dict[str, str],
    prompt: PromptFunc, 
    existing_targets: set[str] | None = None,
    on_rule_added: Callable[[MappingRule], None] | None = None,
    ask_validation_overrides: bool = True,
    sample_df: pd.DataFrame | None = None,
) -> list[MappingRule]:
    # If existing_targets provided, we assume we might be resuming.
    # Spec says: "ask for extensions".
    
    rules: list[MappingRule] = []
    # Track locally added targets to prevent duplicates within this session
    full_existing_targets = set(existing_targets) if existing_targets else set()

    while True:
        add = prompt_bool(prompt, "Add x_ extension column? [Y/n] ", default=True)
        if not add:
            return rules

        with column_completion(columns):
            suffix = prompt("Extension column suffix (appended to x_): ").strip()
        
        if not suffix:
             print("Suffix cannot be empty.\n")
             continue
             
        # Auto-prefix x_ if not present
        if suffix.startswith("x_"):
            name = suffix
            # For suggestions, we strip x_ to see if there is a match in input cols
            candidate_base = suffix[2:]
        else:
            name = f"x_{suffix}"
            candidate_base = suffix

        if name in full_existing_targets:
            print(f"Extension '{name}' is already defined. Skipping.\n")
            continue

        # Check for suggested column from input data
        suggested_col = _suggest_column(candidate_base, normalized)
        inferred_type = "string"
        
        if suggested_col and sample_df is not None:
             if suggested_col in sample_df.columns:
                 # Infer type
                 try:
                     dtype = sample_df[suggested_col].dtype
                     if pd.api.types.is_float_dtype(dtype) or pd.api.types.is_integer_dtype(dtype):
                         inferred_type = "decimal"
                     elif pd.api.types.is_datetime64_any_dtype(dtype):
                         inferred_type = "datetime"
                     # Check for collection? Hard without inspecting values
                     # Check for boolean?
                     elif pd.api.types.is_bool_dtype(dtype):
                         inferred_type = "string" # FOCUS extensions usually string or specific types, boolean supported?
                         # The menu below has string, decimal, datetime, json. 
                         # User requested: "inferred type ... would be default for menu"
                         # Menu choices: string, decimal, datetime, json.
                         # If bool, maybe string? Or add boolean to menu?
                         # _prompt_column_validation supports boolean. 
                         # But FOCUS spec for extension types? 
                         # Usually string, decimal, datetime.
                         pass
                 except Exception:
                     pass
        
        desc = prompt("Description (optional): ").strip() or None
        
        # Prompt for data type
        data_type = prompt_menu(
             prompt,
             "Column type:",
             [
                 ("string", "String"),
                 ("decimal", "Decimal"),
                 ("datetime", "DateTime"),
                 ("json", "JSON"),
             ],
             default=inferred_type,
        )
        if not data_type:
            data_type = "string"

        # Create a temporary FocusColumnSpec to reuse _prompt_for_steps
        # Extensions are always Optional level essentially
        temp_spec = FocusColumnSpec(
             name=name,
             feature_level="Optional",
             allows_nulls=True, # Extensions are usually nullable
             data_type=data_type,
             description=desc,
        )
        
        print(f"Configuring extension column: {name} ({data_type})")
        steps = _prompt_for_steps(
             target=temp_spec,
             columns=columns,
             suggested=suggested_col,
             prompt=prompt,
             sample_df=sample_df,
        )

        if steps:
            steps = _maybe_append_cast(
                steps=steps,
                data_type=data_type,
                numeric_scale=None, # Prompt for scale? defaulting to None for now
            )
            
            validation = None
            if ask_validation_overrides:
                validation = _prompt_column_validation(
                    target_name=name,
                    data_type=data_type,
                    prompt=prompt,
                )

            rule = MappingRule(
                target=name,
                steps=steps,
                description=desc,
                data_type=data_type,
                validation=validation,
            )
            rules.append(rule)
            full_existing_targets.add(name)
            if on_rule_added:
                on_rule_added(rule)
        else:
            print("No steps configured. Skipping extension column.\n")


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
                    "Column type [string|decimal|datetime|json|boolean]: ",
                    {"string", "decimal", "datetime", "json", "boolean"},
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


def _validate_const_value(
    value: str, data_type: str, value_format: str | None = None
) -> tuple[bool, str | None]:
    """
    Validate a const value against its data type and optional value format.
    
    Returns (is_valid, error_message).
    """
    dt = data_type.strip().lower()
    vf = value_format.strip().lower() if value_format else None
    
    # Check value_format specific validators first
    if vf:
        if "key-value" in vf or "keyvalue" in vf:
            return validate_key_value_format(value)
        elif "json object" in vf or "jsonobject" in vf:
            valid, err = validate_json_object_format(value)
            if valid and err and "Warning" in err:
                return True, None  # Treat warnings as valid for wizard input
            return valid, err
        elif "currency" in vf:
            return validate_currency_format(value)
        elif "date/time" in vf or "datetime" in vf:
            return validate_datetime_format(value)
        elif "numeric" in vf:
            return validate_numeric_format(value)
    
    # Check data_type validators
    if dt == "integer":
        return validate_integer(value)
    elif dt == "boolean":
        return validate_boolean(value)
    elif dt == "decimal":
        # Use numeric validator if strict format wasn't checked above,
        # but basic decimal check is safer for general input unless strict format required
        try:
            Decimal(value)
            return True, None
        except (InvalidOperation, ValueError):
            return False, "Value must be a valid number"
    elif dt in ("date/time", "datetime"):
        # If not covered by specific format above, require strict UTC anyway for FOCUS
        return validate_datetime_format(value)
    elif dt == "collection of strings":
        return validate_collection_of_strings(value)
    elif dt == "json":
        # Generic JSON validation if no specific format
        try:
            json.loads(value)
            return True, None
        except json.JSONDecodeError:
            return False, "Value must be valid JSON"
            
    # For string and other types, accept any value
    return True, None


def _norm(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum() or ch == "_")
