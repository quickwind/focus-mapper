from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

from .spec import FocusSpec


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


def validate_focus_dataframe(df: pd.DataFrame, *, spec: FocusSpec) -> ValidationReport:
    findings: list[ValidationFinding] = []

    # 1) Presence by feature level
    for col in spec.columns:
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
        if col.allows_nulls:
            continue

        s = df[col.name]
        failing = int(pd.isna(s).sum())
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
        s = df[col.name]
        mask = (~pd.isna(s)) & (~s.astype("string").isin(col.allowed_values))
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
        dtype = col.data_type.strip().lower()
        if dtype == "date/time":
            _validate_datetime(findings, s, col.name)
        elif dtype == "decimal":
            _validate_decimal(findings, s, col.name)
        elif dtype == "json":
            _validate_json_object(findings, s, col.name)

    # 5) Extension columns: must start with x_
    for name in df.columns:
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
        s = df["BillingCurrency"].astype("string")
        mask = (~pd.isna(s)) & (~s.str.fullmatch(r"[A-Z]{3}"))
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
    path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )


def _sample_values(s: pd.Series, limit: int = 5) -> list[str]:
    vals = []
    for v in s.dropna().astype(str).head(limit).tolist():
        vals.append(v)
    return vals


def _validate_datetime(
    findings: list[ValidationFinding], s: pd.Series, col: str
) -> None:
    if pd.api.types.is_datetime64_any_dtype(s.dtype):
        return
    parsed = pd.to_datetime(s, utc=True, errors="coerce")
    mask = (~pd.isna(s)) & (pd.isna(parsed))
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
    findings: list[ValidationFinding], s: pd.Series, col: str
) -> None:
    def ok(v: Any) -> bool:
        if v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)):
            return True
        if isinstance(v, Decimal):
            return True
        try:
            Decimal(str(v))
            return True
        except (InvalidOperation, ValueError):
            return False

    mask = ~s.map(ok)
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


def _validate_json_object(
    findings: list[ValidationFinding], s: pd.Series, col: str
) -> None:
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
                return isinstance(parsed, dict)
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
                message="JSON column contains values that are not JSON objects",
                column=col,
                failing_rows=failing,
                sample_values=_sample_values(s[mask]),
            )
        )
