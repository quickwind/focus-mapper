from __future__ import annotations

from focus_mapper.wizard import (
    _maybe_append_cast,
    _norm,
    _prompt_bool,
    _prompt_choice,
    _prompt_datetime_format,
    _prompt_decimal,
    _prompt_int,
    _select_targets,
    _suggest_column,
)
from focus_mapper.spec import FocusColumnSpec, FocusSpec


def test_prompt_helpers_validation() -> None:
    inputs = iter(["nope", "5"])
    assert _prompt_int(lambda _: next(inputs), "n") == 5

    inputs = iter(["x", "y"])
    assert _prompt_bool(lambda _: next(inputs), "b", default=None) is True

    inputs = iter(["wrong", "permissive"])
    assert _prompt_choice(
        lambda _: next(inputs), "c", {"permissive", "strict"}, default=None
    ) == "permissive"

    inputs = iter(["bad", "1.5"])
    assert _prompt_decimal(lambda _: next(inputs), "d") is not None

    inputs = iter(["bad", "%Y-%m-%d"])
    assert _prompt_datetime_format(lambda _: next(inputs), "dt") == "%Y-%m-%d"


def test_suggest_and_norm() -> None:
    normalized = {"billingperiodstart": "Billing_Period_Start"}
    assert _suggest_column("BillingPeriodStart", normalized) == "Billing_Period_Start"
    assert _norm("Billing-Period Start") == "billingperiodstart"


def test_select_targets_and_append_cast() -> None:
    spec = FocusSpec(
        version="1.2",
        source=None,
        columns=[
            FocusColumnSpec(
                name="BillingCurrency",
                feature_level="mandatory",
                allows_nulls=False,
                data_type="String",
            ),
            FocusColumnSpec(
                name="OptionalCol",
                feature_level="optional",
                allows_nulls=True,
                data_type="Decimal",
                numeric_scale=2,
            ),
        ],
    )
    targets = _select_targets(
        spec, include_optional=True, include_recommended=False, include_conditional=False
    )
    assert {t.name for t in targets} == {"BillingCurrency", "OptionalCol"}

    steps = [{"op": "from_column", "column": "billing_currency"}]
    out = _maybe_append_cast(steps=steps, data_type="String", numeric_scale=None)
    assert out[-1]["op"] == "cast"
