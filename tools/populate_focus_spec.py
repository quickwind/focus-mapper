from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen


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
    description: str | None


BASE = "https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec"
API_BASE = "https://api.github.com/repos/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec"


def fetch_text(url: str) -> str:
    try:
        with urlopen(url) as r:
            return r.read().decode("utf-8")
    except HTTPError as e:
        raise RuntimeError(f"Failed to fetch {url} (HTTP {e.code})") from e


def fetch_json(url: str) -> dict:
    try:
        with urlopen(url) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        raise RuntimeError(f"Failed to fetch {url} (HTTP {e.code})") from e


def _parse_mdpp_includes(text: str) -> list[str]:
    """Parse !INCLUDE directives from MDPP files."""
    files = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^!INCLUDE \"([^\"]+)\",", line)
        if not m:
            continue
        files.append(m.group(1))
    return files


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
    if not cells:
        return False
    for c in cells:
        c2 = c.replace(":", "").replace("-", "").strip()
        if c2:
            return False
    return True


def _parse_key_value_table(rows: list[list[str]]) -> dict[str, str]:
    if not rows:
        return {}
    if len(rows) >= 2 and _is_separator_row(rows[1]):
        data_rows = rows[2:]
    else:
        data_rows = rows[1:]
    out: dict[str, str] = {}
    for cells in data_rows:
        if _is_separator_row(cells):
            continue
        if len(cells) < 2:
            continue
        key = cells[0].strip()
        value = cells[1].strip()
        if not key:
            continue
        out[key] = value
    return out


def _canonical_constraints(raw: dict[str, str]) -> dict[str, str]:
    def norm(k: str) -> str:
        return re.sub(r"\s+", " ", k.strip().lower())

    mapping = {
        "feature level": "Feature level",
        "allows nulls": "Allows nulls",
        "data type": "Data type",
        "value format": "Value format",
        "numeric precision": "Numeric precision",
        "number scale": "Number scale",
        "numeric scale": "Number scale",
    }

    out: dict[str, str] = {}
    for k, v in raw.items():
        nk = norm(k)
        if nk in mapping:
            out[mapping[nk]] = v
    return out


def parse_allowed_values(
    md: str, *, column_id: str, display_name: str | None
) -> list[str] | None:
    rows = _parse_table_after_marker(md, "Allowed values:")
    if not rows:
        rows = _parse_table_after_marker(md, "Allowed Values")
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
    
    # Try multiple strategies to find the right column
    if "value" in header_norm:
        target_idx = header_norm.index("value")
    elif display_name and norm(display_name) in header_norm:
        target_idx = header_norm.index(norm(display_name))
    elif column_id and norm(column_id) in header_norm:
        target_idx = header_norm.index(norm(column_id))
    else:
        # Fallback: look for a column that contains the column_id or display_name
        for idx, h in enumerate(header_norm):
            if column_id and norm(column_id) in h:
                target_idx = idx
                break
            if display_name and norm(display_name) in h:
                target_idx = idx
                break

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


def join_repo_path(base_dir: str, rel: str) -> str:
    base_dir = base_dir.strip("/")
    rel = rel.strip("/")
    if not rel:
        return base_dir
    return f"{base_dir}/{rel}" if base_dir else rel


def _tree_for_ref(ref: str) -> dict:
    tree_url = f"{API_BASE}/git/trees/{ref}?recursive=1"
    try:
        return fetch_json(tree_url)
    except RuntimeError:
        ref_url = f"{API_BASE}/git/refs/tags/{ref}"
        ref_json = fetch_json(ref_url)
        sha = ref_json.get("object", {}).get("sha")
        if not sha:
            raise RuntimeError(f"Missing SHA for ref {ref}")
        return fetch_json(f"{API_BASE}/git/trees/{sha}?recursive=1")


def _discover_index_path(ref: str, path_hint: str | None) -> tuple[str, str, list[str]]:
    tree = _tree_for_ref(ref)
    blobs = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]

    def candidates(suffix: str) -> list[str]:
        return [p for p in blobs if p.endswith(suffix)]

    index_candidates = candidates("columns.mdpp") + candidates("columns.md")
    if path_hint:
        path_hint = path_hint.strip("/")
        index_candidates = [p for p in index_candidates if path_hint in p]
    index_candidates = sorted(index_candidates, key=lambda p: len(p))
    if index_candidates:
        index_path = index_candidates[0]
        base_dir = index_path.rsplit("/", 1)[0]
        return base_dir, index_path, blobs

    column_md = [p for p in blobs if p.endswith(".mdpp") or p.endswith(".md")]
    column_json = [p for p in blobs if p.endswith(".json")]
    if not column_md and not column_json:
        raise RuntimeError(
            "Unable to locate columns index or column files via GitHub API"
        )

    scored: dict[str, int] = {}
    for p in column_md + column_json:
        if "columns" not in p:
            continue
        base_dir = p.rsplit("/", 1)[0]
        scored[base_dir] = scored.get(base_dir, 0) + 1
    if not scored:
        candidate = column_md[0] if column_md else column_json[0]
        base_dir = candidate.rsplit("/", 1)[0]
    else:
        base_dir = max(scored.items(), key=lambda kv: kv[1])[0]
    return base_dir, "", blobs


def _discover_metadata_path(ref: str, path_hint: str | None) -> str:
    tree = _tree_for_ref(ref)
    blobs = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]
    candidates = [
        p for p in blobs if p.endswith("metadata.mdpp") or p.endswith("metadata.md")
    ]
    if path_hint:
        path_hint = path_hint.strip("/")
        candidates = [p for p in candidates if path_hint in p]
    candidates = sorted(candidates, key=lambda p: len(p))
    return candidates[0] if candidates else ""


def _split_column_blocks(md: str) -> list[str]:
    pattern = re.compile(r"^##### .*?Column ID\s*$", flags=re.MULTILINE)
    matches = list(pattern.finditer(md))
    if not matches:
        pattern = re.compile(r"^## Column ID\s*$", flags=re.MULTILINE)
        matches = list(pattern.finditer(md))
    if not matches:
        return []
    blocks: list[str] = []
    for idx, m in enumerate(matches):
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(md)
        blocks.append(md[start:end])
    return blocks


def _extract_first_nonempty_line(block: str) -> str | None:
    for line in block.splitlines():
        line = line.strip()
        if line:
            return line
    return None


def _parse_constraints_from_block(md: str) -> dict[str, str]:
    rows = _parse_table_after_marker(md, "Content constraints")
    if not rows:
        rows = _parse_table_after_marker(md, "Content Constraints")
    if rows:
        return _canonical_constraints(_parse_key_value_table(rows))
    return _canonical_constraints({})


def _parse_columns_from_markdown(md: str) -> list[Column]:
    blocks = _split_column_blocks(md)
    if not blocks:
        return []

    columns: list[Column] = []
    for block in blocks:
        name = _extract_first_nonempty_line(block)
        if not name:
            continue

        display = None
        # Match "##### Display Name" header followed by content on next line(s)
        dm = re.search(
            r"^#+ .*?Display Name\s*$.*?^([^#\n]+)",
            block,
            flags=re.MULTILINE | re.DOTALL,
        )
        if dm:
            display = dm.group(1).strip()

        description = None
        desc_m = re.search(
            r"^(?:#####|##) Description\s*\n(.*?)(?=\n^#|\Z)",
            block,
            flags=re.MULTILINE | re.DOTALL,
        )
        if desc_m:
            d = desc_m.group(1).strip()
            if d:
                description = d

        constraints = _parse_constraints_from_block(block)
        allowed_values = parse_allowed_values(
            block, column_id=name, display_name=display
        )

        feature_level = constraints.get("Feature level", "Unknown")
        allows_nulls_str = constraints.get("Allows nulls", "True")
        allows_nulls = allows_nulls_str.strip().lower() == "true"
        data_type = constraints.get("Data type", "String")
        value_format = constraints.get("Value format")

        if value_format:
            value_format = _clean_value_format(value_format)

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
                description=description,
            )
        )

    return columns


def _split_metadata_blocks(md: str) -> list[str]:
    pattern = re.compile(r"Metadata ID\s*$", flags=re.MULTILINE | re.IGNORECASE)
    matches = list(pattern.finditer(md))
    if not matches:
        return []
    blocks: list[str] = []
    for idx, m in enumerate(matches):
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(md)
        blocks.append(md[start:end])
    return blocks


def _parse_metadata_entries(md: str) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    blocks = _split_metadata_blocks(md)
    for block in blocks:
        meta_id = _extract_first_nonempty_line(block)
        if not meta_id:
            continue
        constraints = _parse_constraints_from_block(block)
        entries[meta_id] = constraints
    return entries


def _collect_metadata_entries(
    ref: str, metadata_path: str
) -> dict[str, dict[str, str]]:
    def fetch_and_parse(path: str, seen: set[str]) -> dict[str, dict[str, str]]:
        if path in seen:
            return {}
        seen.add(path)
        print(f"[metadata] Fetching {path}")
        text = fetch_text(f"{BASE}/{ref}/{path}")
        entries = _parse_metadata_entries(text)
        includes = _parse_mdpp_includes(text)
        if not includes:
            return entries
        base_dir = path.rsplit("/", 1)[0]
        for inc in includes:
            child = join_repo_path(base_dir, inc)
            entries.update(fetch_and_parse(child, seen))
        return entries

    return fetch_and_parse(metadata_path, set())


def _clean_value_format(value_format: str | None) -> str | None:
    if not value_format:
        return None
    # Clean up markdown links: [Numeric Format](#numericformat) -> Numeric Format
    # Also handle <not specified>
    if "<not specified>" in value_format.lower():
        return None
    
    # Remove markdown link syntax [text](url) -> text
    vf_match = re.match(r"\[(.*?)\].*", value_format)
    if vf_match:
        value_format = vf_match.group(1)
    return value_format.strip()


def _build_metadata_schema(entries: dict[str, dict[str, str]]) -> dict[str, dict]:
    def field(meta_id: str) -> dict | None:
        constraints = entries.get(meta_id)
        if not constraints:
            return None
        return {
            "feature_level": constraints.get("Feature level"),
            "allows_nulls": constraints.get("Allows nulls"),
            "data_type": constraints.get("Data type"),
            "value_format": _clean_value_format(constraints.get("Value format")),
        }

    def collect(ids: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for meta_id in ids:
            entry = field(meta_id)
            if entry:
                out[meta_id] = entry
        return out

    data_generator_fields = collect(["DataGenerator"])
    dataset_instance_fields = collect(
        ["DatasetInstanceId", "DatasetInstanceName", "FocusDatasetId"]
    )
    schema_fields = collect(
        [
            "SchemaId",
            "CreationDate",
            "FocusVersion",
            "DataGeneratorVersion",
            "DatasetInstanceId",
        ]
    )
    column_definition_fields = collect(
        [
            "ColumnName",
            "DataType",
            "Deprecated",
            "NumericPrecision",
            "NumberScale",
            "PreviousColumnName",
            "ProviderTagPrefixes",
            "StringEncoding",
            "StringMaxLength",
        ]
    )
    column_definition_self = field("ColumnDefinition")

    metadata: dict[str, dict] = {}
    if data_generator_fields:
        metadata["DataGenerator"] = data_generator_fields
        if field("DataGenerator"):
            metadata["DataGenerator"]["__self__"] = field("DataGenerator")

    if dataset_instance_fields:
        metadata["DatasetInstance"] = {
            **(
                {"__self__": field("DatasetInstance")}
                if field("DatasetInstance")
                else {}
            ),
            **dataset_instance_fields,
        }

    time_sector_fields = collect(
        [
            "TimeSectorComplete",
            "TimeSectorLastUpdated",
            "TimeSectorStart",
            "TimeSectorEnd",
        ]
    )
    if time_sector_fields:
        time_sectors = {
            **({"__self__": field("TimeSectors")} if field("TimeSectors") else {}),
            **time_sector_fields,
        }
    else:
        time_sectors = {}

    recency_fields = collect(
        [
            "DatasetInstanceId",
            "DatasetInstanceComplete",
            "DatasetInstanceLastUpdated",
            "RecencyLastUpdated",
        ]
    )
    if recency_fields or time_sectors:
        metadata["Recency"] = {
            **({"__self__": field("Recency")} if field("Recency") else {}),
            **recency_fields,
        }
        if time_sectors:
            metadata["Recency"]["TimeSectors"] = time_sectors

    if schema_fields or column_definition_fields:
        schema_obj: dict[str, dict] = {}
        if field("Schema"):
            schema_obj["__self__"] = field("Schema")
        schema_obj.update(schema_fields)
        if column_definition_fields or column_definition_self:
            schema_obj["ColumnDefinition"] = {
                **(
                    {"__self__": column_definition_self}
                    if column_definition_self
                    else {}
                ),
                **column_definition_fields,
            }
        metadata["Schema"] = schema_obj
    return metadata


def _parse_allowed_values_json(val: object) -> list[str] | None:
    if val is None:
        return None
    if isinstance(val, list):
        out: list[str] = []
        for item in val:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                for key in ("value", "Value", "name", "Name"):
                    if key in item and isinstance(item[key], str):
                        out.append(item[key])
                        break
        return out or None
    if isinstance(val, dict):
        for key in ("values", "Values", "allowed", "Allowed"):
            if key in val:
                return _parse_allowed_values_json(val[key])
    return None


def _parse_column_from_json(data: dict) -> Column | None:
    if not data:
        return None

    rules = list(data.values())
    if not rules or not isinstance(rules[0], dict):
        return None

    reference = None

    def collect_allowed_values(req_obj: dict) -> list[str]:
        values: list[str] = []
        if not isinstance(req_obj, dict):
            return values
        fn = req_obj.get("CheckFunction")
        if fn == "CheckValue" and isinstance(req_obj.get("Value"), str):
            values.append(req_obj["Value"])
        if fn in {"OR", "AND"} and isinstance(req_obj.get("Items"), list):
            for item in req_obj["Items"]:
                if isinstance(item, dict):
                    values.extend(collect_allowed_values(item))
        return values

    for rule in rules:
        if isinstance(rule, dict) and isinstance(rule.get("Reference"), str):
            reference = rule["Reference"]
            break
    if not reference:
        return None

    feature_level = "Unknown"
    allows_nulls = True
    data_type = "String"
    value_format = None
    allowed_values: list[str] | None = None
    numeric_precision = None
    numeric_scale = None

    for key in data.keys():
        if not isinstance(key, str):
            continue
        suffix = key.split("-")[-1]
        if suffix == "M":
            feature_level = "Mandatory"
            break
        if suffix == "C":
            feature_level = "Conditional"
        if suffix == "R" and feature_level == "Unknown":
            feature_level = "Recommended"
        if suffix == "O" and feature_level == "Unknown":
            feature_level = "Optional"

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if rule.get("Reference") != reference:
            continue
        vc = rule.get("ValidationCriteria", {})
        if not isinstance(vc, dict):
            continue
        req = vc.get("Requirement", {})
        if not isinstance(req, dict):
            continue
        check_fn = req.get("CheckFunction")

        if check_fn in {"TypeDecimal", "TypeNumeric"}:
            data_type = "Decimal"
        elif check_fn in {"TypeString"}:
            data_type = "String"
        elif check_fn in {"TypeDateTime", "TypeDatetime"}:
            data_type = "Date/Time"
        elif check_fn in {"TypeJson", "TypeJSON"}:
            data_type = "JSON"

        if check_fn in {"CheckNotValue", "CheckNotNull"} and req.get("Value") is None:
            allows_nulls = False

        if check_fn in {"FormatNumeric"}:
            value_format = "NumericFormat"
        if check_fn in {"FormatDateTime"}:
            value_format = "Date/Time Format"
        if check_fn in {"FormatCurrency"}:
            value_format = "Currency Format"

        if check_fn in {"CheckValueIn", "CheckAllowedValue", "CheckValueInList"}:
            allowed_values = _parse_allowed_values_json(
                req.get("Values") or req.get("AllowedValues") or req.get("ValueSet")
            )
        if check_fn in {"OR", "AND"} and isinstance(req.get("Items"), list):
            vals = collect_allowed_values(req)
            if vals:
                allowed_values = vals

    return Column(
        name=reference,
        feature_level=feature_level,
        allows_nulls=allows_nulls,
        data_type=data_type,
        value_format=value_format,
        allowed_values=allowed_values,
        numeric_precision=numeric_precision,
        numeric_scale=numeric_scale,
        description=None,
    )


def _dest_dir(version: str) -> Path:
    normalized = version.lower().removeprefix("v").replace(".", "_")
    return Path(f"src/focus_mapper/specs/v{normalized}")


def _dest_file(version: str) -> Path:
    normalized = version.lower().removeprefix("v")
    normalized_dir = normalized.replace(".", "_")
    return _dest_dir(version) / f"focus_spec_v{normalized}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="populate_focus_spec")
    parser.add_argument(
        "--version",
        default="1.3",
        help="FOCUS spec version to vendor (e.g., 1.0, 1.1, 1.2, 1.3)",
    )
    parser.add_argument(
        "--ref",
        default=None,
        help="Git ref or tag to fetch from (defaults to v<version>, e.g. v1.2)",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="Path to spec columns in the repo (default: specification/columns for < 1.3, specification/datasets/cost_and_usage/columns for >= 1.3)",
    )
    args = parser.parse_args(argv)
    version = args.version
    ref = args.ref or f"v{version}"
    
    path = args.path
    if path is None:
        if version >= "1.3":
            path = "specification/datasets/cost_and_usage/columns"
        else:
            path = "specification/columns"

    print(f"Populating FOCUS spec v{version} (ref={ref}, path={path})")
    base = f"{BASE}/{ref}/{path}"

    files: list[str] = []
    blobs: list[str] = []
    index_path = ""
    try:
        print(f"Fetching index: {base}/columns.mdpp")
        cols_mdpp = fetch_text(f"{base}/columns.mdpp")
        files = _parse_mdpp_includes(cols_mdpp)
        index_path = f"{path.strip('/')}/columns.mdpp"
    except RuntimeError:
        try:
            print("Index not found at default path. Discovering via GitHub API...")
            base_dir, index_path, blobs = _discover_index_path(ref, path)
            if index_path:
                print(f"Discovered index: {index_path}")
                cols_mdpp = fetch_text(f"{BASE}/{ref}/{index_path}")
                files = _parse_mdpp_includes(cols_mdpp)
            else:
                print(f"No index file found. Using column files under {base_dir}")
        except RuntimeError as e:
            raise RuntimeError(
                f"{e}\nCheck that the version tag exists or override with "
                f"--ref (e.g., --ref main or --ref v{version}.0)."
            ) from e

    if index_path:
        base_dir = index_path.rsplit("/", 1)[0] if "/" in index_path else ""
        file_paths = [join_repo_path(base_dir, f) for f in files]
    else:
        if not blobs:
            base_dir, _, blobs = _discover_index_path(ref, path)
        if path:
            base_dir = path.strip("/")
        file_paths = [
            p
            for p in blobs
            if p.startswith(base_dir + "/")
            and (p.endswith(".mdpp") or p.endswith(".md") or p.endswith(".json"))
            and not p.endswith("columns.mdpp")
            and not p.endswith("columns.md")
        ]

    columns: list[Column] = []
    for i, filename in enumerate(file_paths, start=1):
        print(f"[{i}/{len(file_paths)}] Fetching {filename}")
        if filename.endswith(".json"):
            data = fetch_json(f"{BASE}/{ref}/{filename}")
            col = _parse_column_from_json(data if isinstance(data, dict) else {})
            if col:
                columns.append(col)
            else:
                print(f"Skipping {filename}: unrecognized JSON structure")
            continue

        md = fetch_text(f"{BASE}/{ref}/{filename}")
        parsed = _parse_columns_from_markdown(md)
        if parsed:
            columns.extend(parsed)
            continue

    metadata: dict[str, dict] = {}
    try:
        metadata_path = "specification/metadata/metadata.mdpp"
        print(f"Fetching metadata schema: {BASE}/{ref}/{metadata_path}")
        entries = _collect_metadata_entries(ref, metadata_path)
        metadata = _build_metadata_schema(entries)
    except RuntimeError:
        try:
            print(
                "Metadata index not found at default path. Discovering via GitHub API..."
            )
            meta_path = _discover_metadata_path(ref, "specification/metadata")
            if meta_path:
                print(f"Discovered metadata schema: {meta_path}")
                entries = _collect_metadata_entries(ref, meta_path)
                metadata = _build_metadata_schema(entries)
            else:
                print("No metadata schema found in repo.")
        except RuntimeError as e:
            print(f"Metadata schema not found or unreadable: {e}")

    if not columns:
        raise RuntimeError(
            "No columns parsed. The spec structure may have changed. "
            "Try providing --path or check the upstream layout."
        )

    out = {
        "version": version,
        "source": {
            "repo": "https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec",
            "ref": ref,
            "path": path,
        },
        "metadata": metadata,
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
                "description": c.description,
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
    try:
        dest.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Wrote {dest}")
    except (OSError, IOError) as e:
        raise RuntimeError(f"Failed to write spec file to {dest}: {e}") from e
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
