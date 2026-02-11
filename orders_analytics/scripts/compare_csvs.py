#!/usr/bin/env python3
import argparse
from typing import Any, Dict

from orders_analytics.utils.compare import (
    build_exclusion_keys,
    build_field_configs,
    compare_datasets,
    load_csv,
    write_csv,
    _normalize_key_spec,
)


def _strip_comments(line: str) -> str:
    if "#" not in line:
        return line
    idx = line.find("#")
    return line[:idx]


def _parse_scalar(text: str) -> Any:
    value = text.strip()
    if value == "":
        return ""
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value


def _parse_block(lines: list[tuple[int, str]], start: int, indent: int) -> tuple[Any, int]:
    if start >= len(lines):
        return {}, start
    _, first = lines[start]
    is_list = first.lstrip().startswith("- ")
    if is_list:
        items: list[Any] = []
        idx = start
        while idx < len(lines):
            cur_indent, content = lines[idx]
            if cur_indent < indent:
                break
            if cur_indent > indent:
                raise ValueError("Invalid indentation in YAML")
            item_text = content.strip()[2:].strip()
            if item_text == "":
                nested, idx = _parse_block(lines, idx + 1, indent + 2)
                items.append(nested)
                continue
            if ":" in item_text:
                key, value = item_text.split(":", 1)
                key = key.strip()
                value = value.strip()
                item_dict: Dict[str, Any] = {}
                if value == "":
                    nested, idx = _parse_block(lines, idx + 1, indent + 2)
                    item_dict[key] = nested
                else:
                    item_dict[key] = _parse_scalar(value)
                    idx += 1
                if idx < len(lines) and lines[idx][0] > indent:
                    nested, idx = _parse_block(lines, idx, indent + 2)
                    if isinstance(nested, dict):
                        item_dict.update(nested)
                    else:
                        raise ValueError("List item with mapping cannot contain non-mapping block")
                items.append(item_dict)
            else:
                items.append(_parse_scalar(item_text))
                idx += 1
        return items, idx
    data: Dict[str, Any] = {}
    idx = start
    while idx < len(lines):
        cur_indent, content = lines[idx]
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise ValueError("Invalid indentation in YAML")
        if ":" not in content:
            raise ValueError(f"Invalid YAML line: {content}")
        key, value = content.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            nested, idx = _parse_block(lines, idx + 1, indent + 2)
            data[key] = nested
        else:
            data[key] = _parse_scalar(value)
            idx += 1
    return data, idx


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        raw_lines = [_strip_comments(line.rstrip("\n")) for line in handle]
    lines: list[tuple[int, str]] = []
    for line in raw_lines:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent % 2 != 0:
            raise ValueError("YAML indentation must be multiples of 2 spaces")
        lines.append((indent, line.lstrip()))
    data, _ = _parse_block(lines, 0, 0)
    if not isinstance(data, dict):
        raise ValueError("Top-level YAML must be a mapping")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two CSV files based on a YAML config.")
    parser.add_argument("--config", required=True, help="Path to YAML config.")
    args = parser.parse_args()

    config = load_config(args.config)
    left = config.get("left", {})
    right = config.get("right", {})
    output_path = config.get("output")
    if not output_path:
        raise ValueError("Config must include output path")

    left_path = left.get("path")
    right_path = right.get("path")
    if not left_path or not right_path:
        raise ValueError("Config must include left.path and right.path")

    left_keys = _normalize_key_spec(left.get("keys"))
    right_keys = _normalize_key_spec(right.get("keys"))
    left_label = str(left.get("name") or "left")
    right_label = str(right.get("name") or "right")
    fields = build_field_configs(config.get("fields", []))
    excludes = config.get("excludes", {})
    exclusions = build_exclusion_keys(config.get("exclude_keys", []))

    left_rows = load_csv(left_path)
    right_rows = load_csv(right_path)
    left_columns = set(left_rows[0].keys()) if left_rows else set()
    right_columns = set(right_rows[0].keys()) if right_rows else set()
    for field in fields:
        for col in field.left:
            if col not in left_columns:
                raise ValueError(f"Missing left column for field '{field.name}': {col}")
        for col in field.right:
            if col not in right_columns:
                raise ValueError(f"Missing right column for field '{field.name}': {col}")
    rows = compare_datasets(
        left_rows,
        right_rows,
        left_keys,
        right_keys,
        fields,
        left_label=left_label,
        right_label=right_label,
        excludes=excludes,
        exclusion_keys=exclusions,
    )
    write_csv(output_path, rows)
    print(f"Wrote {len(rows)} difference row(s) -> {output_path}")


if __name__ == "__main__":
    main()
