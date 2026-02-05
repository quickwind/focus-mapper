from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

from .spec import FocusSpec
from .mapping.config import MappingConfig


@dataclass(frozen=True)
class ValidationSummary:
    errors: int
    warnings: int


@dataclass(frozen=True)
class ValidationFinding:
    check_id: str
    severity: str  # INFO/WARN/ERROR
    message: str
    column: str | None = None
    failing_rows: int | None = None
    sample_values: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "severity": self.severity,
            "message": self.message,
            "column": self.column,
            "failing_rows": self.failing_rows,
            "sample_values": self.sample_values,
        }


@dataclass(frozen=True)
class ValidationReport:
    summary: ValidationSummary
    findings: list[ValidationFinding]
    spec_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_version": self.spec_version,
            "summary": {
                "errors": self.summary.errors,
                "warnings": self.summary.warnings,
            },
            "findings": [f.to_dict() for f in self.findings],
        }


def validate_focus_dataframe(
    df: pd.DataFrame, *, spec: FocusSpec, mapping: MappingConfig | None = None
) -> ValidationReport:
    """
    Validates a DataFrame against the FinOps FOCUS specification rules.

    Checks performed:
    1. Presence: Mandatory columns must exist (ERROR), Conditional columns (WARN).
    2. Nullability: Mandatory columns must not contain nulls.
    3. Enumerations: Columns with 'allowed_values' are checked for compliance.
    4. Type Integrity: Values must be parseable as Date/Time, Decimal, or JSON.
    5. Extensions: Custom columns must use the 'x_' prefix.
    6. Formats: Basic checks for standard formats (e.g., ISO 4217 currency codes).
    """
    findings: list[ValidationFinding] = []
    default_validation = mapping.validation_defaults if mapping else {}

    def effective_validation(col_name: str) -> dict[str, Any]:
        base = _deep_merge({}, default_validation)
        if mapping:
            rule = mapping.rule_for_target(col_name)
            if rule and rule.validation:
                base = _deep_merge(base, rule.validation)
        return base

    # 1) Presence by feature level
    for col in spec.columns:
        eff = effective_validation(col.name)
        enforce_presence = (
            eff.get("presence", {}).get("enforce")
            if isinstance(eff.get("presence"), dict)
            else None
        )
        if enforce_presence is False:
            continue
        if col.name in df.columns:
            continue

        level = col.feature_level.strip().lower()
        if level == "mandatory":
            severity = "ERROR"
        elif level == "conditional":
            severity = "WARN"
        else:
            severity = "INFO"

        findings.append(
            ValidationFinding(
                check_id="focus.column_present",
                severity=severity,
                message="FOCUS column is missing from dataset",
                column=col.name,
            )
        )

    # 2) Nullability when present
    for col in spec.columns:
        if col.name not in df.columns:
            continue
        eff = effective_validation(col.name)
        allow_nulls_override = (
            eff.get("nullable", {}).get("allow_nulls")
            if isinstance(eff.get("nullable"), dict)
            else None
        )
        if col.allows_nulls:
            if allow_nulls_override is None or allow_nulls_override is True:
                continue
        if allow_nulls_override is True:
            continue

        s = df[col.name]
        if not isinstance(s, pd.Series):
            continue
        failing = int(s.isna().sum())
        if failing:
            findings.append(
                ValidationFinding(
                    check_id="focus.not_null",
                    severity="ERROR",
                    message="Column disallows nulls but contains null values",
                    column=col.name,
                    failing_rows=failing,
                    sample_values=_sample_values(s),
                )
            )

    # 3) Allowed values
    for col in spec.columns:
        if not col.allowed_values:
            continue
        if col.name not in df.columns:
            continue
        eff = effective_validation(col.name)
        mode = eff.get("mode", "permissive")
        case_insensitive = (
            eff.get("allowed_values", {}).get("case_insensitive")
            if isinstance(eff.get("allowed_values"), dict)
            else None
        )
        if case_insensitive is None:
            case_insensitive = False
        s = df[col.name]
        if not isinstance(s, pd.Series):
            continue
        if case_insensitive:
            allowed = {v.lower() for v in col.allowed_values}
            mask = (~s.isna()) & (~s.astype("string").str.lower().isin(allowed))
        else:
            mask = (~s.isna()) & (~s.astype("string").isin(col.allowed_values))
        failing = int(mask.sum())
        if failing:
            findings.append(
                ValidationFinding(
                    check_id="focus.allowed_values",
                    severity="ERROR",
                    message="Column contains values outside allowed set",
                    column=col.name,
                    failing_rows=failing,
                    sample_values=_sample_values(s[mask]),
                )
            )

    # 4) Type-specific validations (format/parseability)
    for col in spec.columns:
        if col.name not in df.columns:
            continue
        s = df[col.name]
        if not isinstance(s, pd.Series):
            continue
        eff = effective_validation(col.name)
        mode = eff.get("mode", "permissive")
        dtype = col.data_type.strip().lower()
        if dtype == "date/time":
            fmt = None
            if isinstance(eff.get("datetime"), dict):
                fmt = eff.get("datetime", {}).get("format")
            _validate_datetime(findings, s, col.name, mode=mode, fmt=fmt)
        elif dtype == "decimal":
            dec = eff.get("decimal") if isinstance(eff.get("decimal"), dict) else {}
            precision = (
                dec.get("precision")
                if dec and dec.get("precision") is not None
                else col.numeric_precision
            )
            scale = (
                dec.get("scale")
                if dec and dec.get("scale") is not None
                else col.numeric_scale
            )
            _validate_decimal(
                findings,
                s,
                col.name,
                precision=precision,
                scale=scale,
                integer_only=dec.get("integer_only") if dec else None,
                min_value=dec.get("min") if dec else None,
                max_value=dec.get("max") if dec else None,
                mode=mode,
            )
        elif dtype == "string":
            s_cfg = eff.get("string") if isinstance(eff.get("string"), dict) else {}
            _validate_string(
                findings,
                s,
                col.name,
                min_length=s_cfg.get("min_length"),
                max_length=s_cfg.get("max_length"),
                allow_empty=s_cfg.get("allow_empty"),
                trim=s_cfg.get("trim"),
            )
        elif dtype == "json":
            obj_only = False
            if isinstance(eff.get("json"), dict):
                obj_only = bool(eff.get("json", {}).get("object_only"))
            _validate_json(findings, s, col.name, object_only=obj_only)

    # 5) Extension columns: must start with x_
    for name in df.columns:
        if not isinstance(name, str):
            continue
        if name.startswith("x_"):
            continue
        if name in spec.column_names:
            continue
        # Unknown non-extension column
        findings.append(
            ValidationFinding(
                check_id="focus.unknown_column",
                severity="WARN",
                message="Column is not in FOCUS schema and does not use x_ extension prefix",
                column=name,
            )
        )

    # 6) Basic currency code format check (ISO4217-like)
    if "BillingCurrency" in df.columns:
        s = df["BillingCurrency"]
        if isinstance(s, pd.Series):
            s_str = s.astype("string")
            mask = (~s_str.isna()) & (~s_str.str.fullmatch(r"[A-Z]{3}"))
            failing = int(mask.sum())
            if failing:
                findings.append(
                    ValidationFinding(
                        check_id="focus.currency_format",
                        severity="ERROR",
                        message="BillingCurrency must be a 3-letter uppercase ISO 4217 code",
                        column="BillingCurrency",
                        failing_rows=failing,
                        sample_values=_sample_values(s[mask]),
                    )
                )

    errors = sum(1 for f in findings if f.severity == "ERROR")
    warnings = sum(1 for f in findings if f.severity == "WARN")
    return ValidationReport(
        summary=ValidationSummary(errors=errors, warnings=warnings),
        findings=findings,
        spec_version=spec.version,
    )


def write_validation_report(report: ValidationReport, path: Path) -> None:
    """Writes the validation result to a JSON file."""
    path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )


def _sample_values(s: pd.Series, limit: int = 5) -> list[str]:
    """Extracts a few sample failing values for the validation report."""
    vals = []
    for v in s.dropna().astype(str).head(limit).tolist():
        vals.append(v)
    return vals


def _validate_datetime(
    findings: list[ValidationFinding],
    s: pd.Series,
    col: str,
    *,
    mode: str,
    fmt: str | None,
) -> None:
    """Checks if a column contains valid ISO8601/parseable dates."""
    if pd.api.types.is_datetime64_any_dtype(s.dtype):
        return
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Could not infer format.*",
            category=UserWarning,
        )
        if fmt:
            parsed = pd.to_datetime(s, utc=True, errors="coerce", format=fmt)
        else:
            parsed = pd.to_datetime(s, utc=True, errors="coerce")

    if mode == "strict" and fmt is None:
        s_str = s.astype("string")
        iso_mask = s_str.str.fullmatch(r"\d{4}-\d{2}-\d{2}([T ][0-9:.+-Z]+)?")
        iso_mask = iso_mask.fillna(False)
        bad_iso = (~s.isna()) & (~iso_mask)
        failing_iso = int(bad_iso.sum())
        if failing_iso:
            findings.append(
                ValidationFinding(
                    check_id="focus.datetime_format",
                    severity="ERROR",
                    message="Date/Time column does not match ISO-8601 format",
                    column=col,
                    failing_rows=failing_iso,
                    sample_values=_sample_values(s[bad_iso]),
                )
            )
    mask = (~s.isna()) & (pd.isna(parsed))
    failing = int(mask.sum())
    if failing:
        findings.append(
            ValidationFinding(
                check_id="focus.datetime_parse",
                severity="ERROR",
                message="Date/Time column contains values that cannot be parsed",
                column=col,
                failing_rows=failing,
                sample_values=_sample_values(s[mask]),
            )
        )


def _validate_decimal(
    findings: list[ValidationFinding],
    s: pd.Series,
    col: str,
    *,
    precision: int | None,
    scale: int | None,
    integer_only: bool | None,
    min_value: Any | None,
    max_value: Any | None,
    mode: str,
) -> None:
    """Checks if a column contains valid decimal-compatible values."""

    def normalize(v: Any) -> Any:
        if isinstance(v, str) and mode == "permissive":
            v = v.strip()
            v = v.replace(",", "")
            v = v.lstrip("$€£")
        return v

    def to_decimal(v: Any) -> Decimal | None:
        v = normalize(v)
        if v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)):
            return None
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError):
            return None

    def within_limits(d: Decimal) -> bool:
        tup = d.as_tuple()
        digits = len(tup.digits)
        exp = tup.exponent
        if exp >= 0:
            actual_scale = 0
            actual_precision = digits + exp
        else:
            actual_scale = -exp
            actual_precision = digits

        if precision is not None and actual_precision > precision:
            return False
        if scale is not None and actual_scale > scale:
            return False
        return True

    parsed = s.map(to_decimal)
    parse_fail = parsed.isna() & ~s.isna()
    mask = parse_fail
    failing = int(mask.sum())
    if failing:
        findings.append(
            ValidationFinding(
                check_id="focus.decimal_parse",
                severity="ERROR",
                message="Decimal column contains values that cannot be parsed as decimals",
                column=col,
                failing_rows=failing,
                sample_values=_sample_values(s[mask]),
            )
        )

    if integer_only:
        int_fail = parsed.map(lambda d: d is not None and d.as_tuple().exponent < 0)
        failing_int = int(int_fail.sum())
        if failing_int:
            findings.append(
                ValidationFinding(
                    check_id="focus.decimal_integer_only",
                    severity="ERROR",
                    message="Decimal column contains non-integer values",
                    column=col,
                    failing_rows=failing_int,
                    sample_values=_sample_values(s[int_fail]),
                )
            )

    if min_value is not None:
        try:
            min_d = Decimal(str(min_value))
            min_fail = parsed.map(lambda d: d is not None and d < min_d)
            failing_min = int(min_fail.sum())
            if failing_min:
                findings.append(
                    ValidationFinding(
                        check_id="focus.decimal_min",
                        severity="ERROR",
                        message="Decimal column contains values below minimum",
                        column=col,
                        failing_rows=failing_min,
                        sample_values=_sample_values(s[min_fail]),
                    )
                )
        except Exception:
            pass

    if max_value is not None:
        try:
            max_d = Decimal(str(max_value))
            max_fail = parsed.map(lambda d: d is not None and d > max_d)
            failing_max = int(max_fail.sum())
            if failing_max:
                findings.append(
                    ValidationFinding(
                        check_id="focus.decimal_max",
                        severity="ERROR",
                        message="Decimal column contains values above maximum",
                        column=col,
                        failing_rows=failing_max,
                        sample_values=_sample_values(s[max_fail]),
                    )
                )
        except Exception:
            pass

    if precision is None and scale is None:
        return

    limit_mask = parsed.map(lambda d: True if d is None else within_limits(d)) == False  # noqa: E712
    failing_limits = int(limit_mask.sum())
    if failing_limits:
        findings.append(
            ValidationFinding(
                check_id="focus.decimal_precision_scale",
                severity="ERROR",
                message="Decimal column exceeds defined precision/scale limits",
                column=col,
                failing_rows=failing_limits,
                sample_values=_sample_values(s[limit_mask]),
            )
        )


def _validate_json_object(
    findings: list[ValidationFinding], s: pd.Series, col: str
) -> None:
    """Checks if a column contains valid JSON object strings or dictionaries."""
    _validate_json(findings, s, col, object_only=True)


def _validate_json(
    findings: list[ValidationFinding],
    s: pd.Series,
    col: str,
    *,
    object_only: bool,
) -> None:
    """Checks if a column contains valid JSON (object only if configured)."""

    def ok(v: Any) -> bool:
        if v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)):
            return True
        if isinstance(v, dict):
            return True
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return True
            try:
                parsed = json.loads(v)
                if object_only:
                    return isinstance(parsed, dict)
                return True
            except Exception:
                return False
        return False

    mask = ~s.map(ok)
    failing = int(mask.sum())
    if failing:
        findings.append(
            ValidationFinding(
                check_id="focus.json_object",
                severity="ERROR",
                message="JSON column contains values that are not valid JSON objects"
                if object_only
                else "JSON column contains values that are not valid JSON",
                column=col,
                failing_rows=failing,
                sample_values=_sample_values(s[mask]),
            )
        )


def _validate_string(
    findings: list[ValidationFinding],
    s: pd.Series,
    col: str,
    *,
    min_length: int | None,
    max_length: int | None,
    allow_empty: bool | None,
    trim: bool | None,
) -> None:
    if (
        min_length is None
        and max_length is None
        and allow_empty is None
        and trim is None
    ):
        return

    s_str = s.astype("string")
    if trim is None:
        trim = True
    if trim:
        s_str = s_str.str.strip()

    if allow_empty is False:
        empty_mask = (~s_str.isna()) & (s_str == "")
        failing = int(empty_mask.sum())
        if failing:
            findings.append(
                ValidationFinding(
                    check_id="focus.string_empty",
                    severity="ERROR",
                    message="String column contains empty values",
                    column=col,
                    failing_rows=failing,
                    sample_values=_sample_values(s[empty_mask]),
                )
            )

    if min_length is not None:
        short_mask = (~s_str.isna()) & (s_str.str.len() < int(min_length))
        failing = int(short_mask.sum())
        if failing:
            findings.append(
                ValidationFinding(
                    check_id="focus.string_min_length",
                    severity="ERROR",
                    message="String column contains values shorter than minimum length",
                    column=col,
                    failing_rows=failing,
                    sample_values=_sample_values(s[short_mask]),
                )
            )

    if max_length is not None:
        long_mask = (~s_str.isna()) & (s_str.str.len() > int(max_length))
        failing = int(long_mask.sum())
        if failing:
            findings.append(
                ValidationFinding(
                    check_id="focus.string_max_length",
                    severity="ERROR",
                    message="String column contains values longer than maximum length",
                    column=col,
                    failing_rows=failing,
                    sample_values=_sample_values(s[long_mask]),
                )
            )


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out.get(k), dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
