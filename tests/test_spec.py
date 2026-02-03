from focus_report.spec import load_focus_spec


def test_load_focus_spec_v1_2() -> None:
    spec = load_focus_spec("v1.2")
    assert spec.version == "1.2"
    assert "BilledCost" in spec.column_names
