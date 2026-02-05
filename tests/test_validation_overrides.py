from __future__ import annotations

import pandas as pd

from focus_report.mapping.config import MappingConfig, MappingRule
from focus_report.spec import load_focus_spec
from focus_report.validate import validate_focus_dataframe


def test_validation_defaults_permissive_datetime() -> None:
    spec = load_focus_spec("v1.2")
    df = pd.DataFrame(
        {
            "BillingPeriodStart": ["01/31/2026"],
        }
    )
    mapping = MappingConfig(
        spec_version="v1.2",
        rules=[],
        validation_defaults={},
    )

    report = validate_focus_dataframe(df, spec=spec, mapping=mapping)
    assert not any(f.check_id == "focus.datetime_format" for f in report.findings)


def test_validation_strict_datetime_format_rejects_non_iso() -> None:
    spec = load_focus_spec("v1.2")
    df = pd.DataFrame(
        {
            "BillingPeriodStart": ["01/31/2026"],
        }
    )
    mapping = MappingConfig(
        spec_version="v1.2",
        rules=[
            MappingRule(
                target="BillingPeriodStart",
                steps=[{"op": "const", "value": None}],
                description=None,
                validation={"mode": "strict"},
            )
        ],
        validation_defaults={},
    )

    report = validate_focus_dataframe(df, spec=spec, mapping=mapping)
    assert any(f.check_id == "focus.datetime_format" for f in report.findings)


def test_validation_allowed_values_case_sensitive_override() -> None:
    spec = load_focus_spec("v1.2")
    df = pd.DataFrame(
        {
            "ChargeCategory": ["usage"],
        }
    )
    mapping = MappingConfig(
        spec_version="v1.2",
        rules=[
            MappingRule(
                target="ChargeCategory",
                steps=[{"op": "const", "value": None}],
                description=None,
                validation={"allowed_values": {"case_insensitive": False}},
            )
        ],
        validation_defaults={},
    )

    report = validate_focus_dataframe(df, spec=spec, mapping=mapping)
    assert any(f.check_id == "focus.allowed_values" for f in report.findings)
