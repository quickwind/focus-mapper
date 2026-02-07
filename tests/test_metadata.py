from __future__ import annotations

from pathlib import Path

import pandas as pd

from focus_mapper.mapping.config import load_mapping_config
from focus_mapper.metadata import build_sidecar_metadata, mapping_yaml_canonical
from focus_mapper.spec import load_focus_spec


def test_build_sidecar_metadata_tags_and_extensions(tmp_path: Path) -> None:
    spec = load_focus_spec("v1.2")
    mapping = load_mapping_config(Path("tests/fixtures/mapping_v1_2.yaml"))

    output_df = pd.DataFrame(
        {
            "BillingCurrency": ["USD"],
            "BilledCost": [12.34],
            "Tags": [{"env": "prod"}],
            "x_CustomJson": [{"k": "v"}],
        }
    )

    meta = build_sidecar_metadata(
        spec=spec,
        mapping=mapping,
        generator_name="tester",
        generator_version="0.0.1",
        input_path=tmp_path / "input.csv",
        output_path=tmp_path / "out.csv",
        output_df=output_df,
        provider_tag_prefixes=["aws:"],
    )

    data = meta.to_dict()
    assert data["DataGenerator"]["DataGenerator"] == "tester"
    assert data["Schema"]["FocusVersion"] == spec.version

    by_name = {c["ColumnName"]: c for c in data["Schema"]["ColumnDefinition"]}
    assert by_name["Tags"]["ProviderTagPrefixes"] == ["aws:"]
    assert by_name["BillingCurrency"]["DataType"] == "STRING"
    assert by_name["x_CustomJson"]["DataType"] == "JSON"


def test_mapping_yaml_canonical_stable() -> None:
    mapping = load_mapping_config(Path("tests/fixtures/mapping_v1_2.yaml"))
    first = mapping_yaml_canonical(mapping)
    second = mapping_yaml_canonical(mapping)
    assert first == second
