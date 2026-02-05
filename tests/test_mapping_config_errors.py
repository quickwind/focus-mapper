from __future__ import annotations

from pathlib import Path

import pytest

from focus_mapper.errors import MappingConfigError
from focus_mapper.mapping.config import load_mapping_config


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "mapping.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_mapping_config_requires_top_level_mapping(tmp_path: Path) -> None:
    path = _write(tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(MappingConfigError, match="top level"):
        load_mapping_config(path)


def test_mapping_config_requires_spec_version(tmp_path: Path) -> None:
    path = _write(tmp_path, "mappings: {}\n")
    with pytest.raises(MappingConfigError, match="spec_version"):
        load_mapping_config(path)


def test_mapping_config_requires_mappings(tmp_path: Path) -> None:
    path = _write(tmp_path, "spec_version: '1.2'\n")
    with pytest.raises(MappingConfigError, match="mapping.mappings"):
        load_mapping_config(path)


def test_mapping_config_requires_steps_with_op(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """spec_version: "1.2"
mappings:
  BilledCost:
    steps:
      - value: 1
""",
    )
    with pytest.raises(MappingConfigError, match="must include 'op'"):
        load_mapping_config(path)
