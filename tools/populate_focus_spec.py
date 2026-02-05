from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError


@dataclass(frozen=True)
class Column:
    name: str
    feature_level: str
    allows_nulls: bool
    data_type: str
    value_format: str | None
    allowed_values: list[str] | None
    numeric_precision: int | None
    numeric_scale: int | None


BASE = "https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec"


def fetch_text(url: str) -> str:
    try:
        with urlopen(url) as r:
            return r.read().decode("utf-8")
    except HTTPError as e:
        raise RuntimeError(f"Failed to fetch {url} (HTTP {e.code})") from e


def parse_columns_mdpp(text: str) -> list[str]:
    files = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^!INCLUDE \"([^\"]+)\",", line)
        if not m:
            continue
        files.append(m.group(1))
    return files


def parse_constraints(md: str) -> dict[str, str]:
    # Extract the first markdown table that contains a "Feature level" row.
    lines = md.splitlines()
    start = None
    for i, line in enumerate(lines):
        if "| Feature level" in line:
            # Find header row start by scanning backwards to previous line that starts with |
            j = i
            while j >= 0 and not lines[j].lstrip().startswith("|"):
                j -= 1
            # back up a bit to include header
            start = max(0, j - 2)
            break

    if start is None:
        return {}

    table_lines = []
    for line in lines[start:]:
        if not line.lstrip().startswith("|"):
            if table_lines:
                break
            continue
        table_lines.append(line)

    out: dict[str, str] = {}
    for line in table_lines:
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) != 2:
            continue
        key, value = parts
        if key.lower() in {"constraint", ":--------------", ":----------------"}:
            continue
        if key.startswith(":"):
            continue
        if key and value and key.lower() != "constraint":
            out[key] = value
    return out


def _parse_table_after_marker(md: str, marker: str) -> list[list[str]]:
    if marker not in md:
        return []
    after = md.split(marker, 1)[1]
    rows: list[list[str]] = []
    started = False
    for raw_line in after.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            if started:
                break
            continue
        started = True
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    return rows


def _is_separator_row(cells: list[str]) -> bool:
    # Markdown separator rows are like: | --- | :---: |
    if not cells:
        return False
    for c in cells:
        c2 = c.replace(":", "").replace("-", "").strip()
        if c2:
            return False
    return True


def parse_allowed_values(
    md: str, *, column_id: str, display_name: str | None
) -> list[str] | None:
    rows = _parse_table_after_marker(md, "Allowed values:")
    if len(rows) < 3:
        return None

    header = rows[0]
    if _is_separator_row(rows[1]):
        data_rows = rows[2:]
    else:
        data_rows = rows[1:]

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip().lower())

    header_norm = [norm(h) for h in header]
    target_idx = 0
    if "value" in header_norm:
        target_idx = header_norm.index("value")
    elif display_name and norm(display_name) in header_norm:
        target_idx = header_norm.index(norm(display_name))
    elif column_id and norm(column_id) in header_norm:
        target_idx = header_norm.index(norm(column_id))

    values: list[str] = []
    seen = set()
    for cells in data_rows:
        if _is_separator_row(cells):
            continue
        if target_idx >= len(cells):
            continue
        v = cells[target_idx].strip()
        if not v:
            continue
        if v.startswith(":"):
            continue
        if v.lower() == "value":
            continue
        if v not in seen:
            seen.add(v)
            values.append(v)
    return values or None


def _dest_dir(version: str) -> Path:
    normalized = version.lower().removeprefix("v").replace(".", "_")
    return Path(f"src/focus_mapper/specs/v{normalized}")


def _dest_file(version: str) -> Path:
    normalized = version.lower().removeprefix("v").replace(".", "_")
    return _dest_dir(version) / f"focus_v{normalized}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="populate_focus_spec")
    parser.add_argument(
        "--version",
        default="1.2",
        help="FOCUS spec version to vendor (e.g., 1.0, 1.1, 1.2, 1.3)",
    )
    parser.add_argument(
        "--ref",
        default=None,
        help="Git ref or tag to fetch from (defaults to v<version>, e.g. v1.2)",
    )
    parser.add_argument(
        "--path",
        default="specification/columns",
        help="Path to spec columns in the repo (default: specification/columns)",
    )
    args = parser.parse_args(argv)
    version = args.version
    ref = args.ref or f"v{version}"
    path = args.path

    print(f"Populating FOCUS spec v{version} (ref={ref}, path={path})")
    base = f"{BASE}/{ref}/{path}"

    try:
        print(f"Fetching index: {base}/columns.mdpp")
        cols_mdpp = fetch_text(f"{base}/columns.mdpp")
    except RuntimeError as e:
        raise RuntimeError(
            f"{e}\nCheck that the version tag exists. You can override with "
            f"--ref (e.g., --ref main or --ref v{version}.0)."
        ) from e
    files = parse_columns_mdpp(cols_mdpp)

    columns: list[Column] = []
    for i, filename in enumerate(files, start=1):
        print(f"[{i}/{len(files)}] Fetching {filename}")
        md = fetch_text(f"{base}/{filename}")
        constraints = parse_constraints(md)

        # Column ID is in a section:
        #   ## Column ID
        #   BilledCost
        m = re.search(
            r"^## Column ID\s*\n\s*([A-Za-z0-9_]+)\s*$", md, flags=re.MULTILINE
        )
        if not m:
            raise RuntimeError(f"Failed to find Column ID in {filename}")
        name = m.group(1)

        display = None
        dm = re.search(r"^## Display Name\s*\n\s*(.+?)\s*$", md, flags=re.MULTILINE)
        if dm:
            display = dm.group(1).strip()

        allowed_values = parse_allowed_values(md, column_id=name, display_name=display)

        feature_level = constraints.get("Feature level", "Unknown")
        allows_nulls_str = constraints.get("Allows nulls", "True")
        allows_nulls = allows_nulls_str.strip().lower() == "true"
        data_type = constraints.get("Data type", "String")
        value_format = constraints.get("Value format")

        numeric_precision = None
        numeric_scale = None
        if data_type.lower() == "decimal":
            if "Numeric precision" in constraints:
                try:
                    numeric_precision = int(constraints["Numeric precision"])
                except ValueError:
                    numeric_precision = None
            if "Number scale" in constraints:
                try:
                    numeric_scale = int(constraints["Number scale"])
                except ValueError:
                    numeric_scale = None

        columns.append(
            Column(
                name=name,
                feature_level=feature_level,
                allows_nulls=allows_nulls,
                data_type=data_type,
                value_format=value_format,
                allowed_values=allowed_values,
                numeric_precision=numeric_precision,
                numeric_scale=numeric_scale,
            )
        )

    out = {
        "version": version,
        "source": {
            "repo": "https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec",
            "ref": f"v{version}",
            "path": "specification/columns",
        },
        "columns": [
            {
                "name": c.name,
                "feature_level": c.feature_level,
                "allows_nulls": c.allows_nulls,
                "data_type": c.data_type,
                "value_format": c.value_format,
                "allowed_values": c.allowed_values,
                "numeric_precision": c.numeric_precision,
                "numeric_scale": c.numeric_scale,
            }
            for c in columns
        ],
    }

    dest_dir = _dest_dir(version)
    dest_dir.mkdir(parents=True, exist_ok=True)
    init_py = dest_dir / "__init__.py"
    if not init_py.exists():
        init_py.write_text("", encoding="utf-8")
    dest = _dest_file(version)
    dest.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
