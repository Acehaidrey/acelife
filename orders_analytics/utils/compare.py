from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


def _normalize_blank(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() == "nan":
        return ""
    if text == "-":
        return ""
    return text


def _coalesce(row: Dict[str, Any], columns: Sequence[str]) -> str:
    for col in columns:
        value = _normalize_blank(row.get(col, ""))
        if value != "":
            return value
    return ""


def _parse_decimal(value: str) -> Optional[Decimal]:
    text = _normalize_blank(value)
    if not text:
        return None
    try:
        return Decimal(text.replace("$", "").replace(",", ""))
    except InvalidOperation:
        return None


def _is_zeroish(value: str) -> bool:
    text = _normalize_blank(value)
    if not text:
        return False
    dec = _parse_decimal(text)
    if dec is None:
        return False
    return dec == Decimal("0.00")


def _apply_transforms(value: str, transforms: Sequence[str]) -> str:
    current = _normalize_blank(value)
    for transform in transforms:
        if transform == "strip":
            current = current.strip()
        elif transform == "lower":
            current = current.lower()
        elif transform == "upper":
            current = current.upper()
        elif transform == "money":
            dec = _parse_decimal(current)
            current = "" if dec is None else f"{dec:.2f}"
        elif transform == "abs":
            dec = _parse_decimal(current)
            current = "" if dec is None else f"{abs(dec):.2f}"
        elif transform == "round_2":
            dec = _parse_decimal(current)
            current = "" if dec is None else f"{dec:.2f}"
        else:
            raise ValueError(f"Unknown transform: {transform}")
    return current


def _normalize_transforms(transforms: Any) -> List[str]:
    if transforms is None:
        return []
    if isinstance(transforms, str):
        return [transforms]
    return list(transforms)


def _normalize_key_spec(keys: Any) -> Dict[str, str]:
    if isinstance(keys, dict):
        return {str(k): str(v) for k, v in keys.items()}
    if isinstance(keys, list):
        return {str(k): str(k) for k in keys}
    raise ValueError("keys must be a list or mapping")


def _build_key(row: Dict[str, Any], keys: Dict[str, str]) -> Tuple[str, ...]:
    parts = []
    for _, column in keys.items():
        parts.append(_normalize_blank(row.get(column, "")))
    return tuple(parts)


def _key_columns(keys: Dict[str, str]) -> List[str]:
    return [f"key_{name}" for name in keys.keys()]


def _key_values(keys: Dict[str, str], row: Dict[str, Any]) -> List[str]:
    return [_normalize_blank(row.get(column, "")) for column in keys.values()]


def _passes_excludes(row: Dict[str, Any], excludes: List[Dict[str, Any]]) -> bool:
    for rule in excludes:
        column = str(rule.get("column", "")).strip()
        if not column:
            continue
        value = _normalize_blank(row.get(column, ""))
        if "equals" in rule and value == _normalize_blank(rule["equals"]):
            return False
        if "in" in rule and value in {str(v) for v in rule["in"]}:
            return False
        if "starts_with" in rule and value.startswith(str(rule["starts_with"])):
            return False
        if "contains" in rule:
            needle = str(rule["contains"])
            if needle and needle.lower() in value.lower():
                return False
    return True


@dataclass
class FieldConfig:
    name: str
    left: List[str]
    right: List[str]
    transforms: List[str]
    tolerance: Optional[Decimal]


def load_csv(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    df = pd.read_csv(path, dtype=str).fillna("")
    return df.to_dict("records")


def build_field_configs(fields: Iterable[Dict[str, Any]]) -> List[FieldConfig]:
    configs: List[FieldConfig] = []
    for field in fields:
        name = str(field.get("name", "")).strip()
        if not name:
            raise ValueError("field name is required")
        left = field.get("left", name)
        right = field.get("right", name)
        left_cols = [left] if isinstance(left, str) else list(left)
        right_cols = [right] if isinstance(right, str) else list(right)
        transforms = _normalize_transforms(field.get("transforms") or field.get("transform"))
        tol_value = field.get("tolerance")
        tolerance = None
        if tol_value is not None and str(tol_value).strip() != "":
            try:
                tolerance = Decimal(str(tol_value))
            except InvalidOperation:
                tolerance = None
        configs.append(FieldConfig(name=name, left=left_cols, right=right_cols, transforms=transforms, tolerance=tolerance))
    return configs


def build_exclusion_keys(exclusions: Iterable[Dict[str, Any]]) -> set[Tuple[str, ...]]:
    keys: set[Tuple[str, ...]] = set()
    for entry in exclusions:
        path = entry.get("path")
        if not path:
            continue
        key_spec = _normalize_key_spec(entry.get("keys", {}))
        rows = load_csv(path)
        for row in rows:
            keys.add(_build_key(row, key_spec))
    return keys


def compare_datasets(
    left_rows: List[Dict[str, Any]],
    right_rows: List[Dict[str, Any]],
    left_keys: Dict[str, str],
    right_keys: Dict[str, str],
    fields: List[FieldConfig],
    left_label: str = "left",
    right_label: str = "right",
    excludes: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    exclusion_keys: Optional[set[Tuple[str, ...]]] = None,
) -> List[Dict[str, Any]]:
    left_excludes = (excludes or {}).get("left", [])
    right_excludes = (excludes or {}).get("right", [])

    left_filtered = [row for row in left_rows if _passes_excludes(row, left_excludes)]
    right_filtered = [row for row in right_rows if _passes_excludes(row, right_excludes)]

    left_map: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for row in left_filtered:
        key = _build_key(row, left_keys)
        if not any(key):
            continue
        left_map[key] = row

    right_map: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for row in right_filtered:
        key = _build_key(row, right_keys)
        if not any(key):
            continue
        right_map[key] = row

    exclusion_keys = exclusion_keys or set()
    all_keys = set(left_map.keys()) | set(right_map.keys())

    output: List[Dict[str, Any]] = []
    key_columns = _key_columns(left_keys)

    for key in sorted(all_keys):
        if key in exclusion_keys:
            continue
        left_row = left_map.get(key)
        right_row = right_map.get(key)
        key_values = _key_values(left_keys, left_row or right_row or {})
        key_payload = dict(zip(key_columns, key_values))

        if left_row is None:
            payload = {
                **key_payload,
                "status": f"missing_{left_label}",
                "field": "",
                "left_value": "",
                "right_value": "",
                "diff": "",
                "diff_abs": "",
                "notes": f"missing_{left_label}",
            }
            output.append(payload)
            continue
        if right_row is None:
            payload = {
                **key_payload,
                "status": f"missing_{right_label}",
                "field": "",
                "left_value": "",
                "right_value": "",
                "diff": "",
                "diff_abs": "",
                "notes": f"missing_{right_label}",
            }
            output.append(payload)
            continue

        for field in fields:
            left_value = _coalesce(left_row, field.left)
            right_value = _coalesce(right_row, field.right)
            left_value = _apply_transforms(left_value, field.transforms)
            right_value = _apply_transforms(right_value, field.transforms)

            if left_value == "" and right_value == "":
                continue
            if left_value == "" and _is_zeroish(right_value):
                continue
            if right_value == "" and _is_zeroish(left_value):
                continue

            if field.tolerance is not None:
                left_num = _parse_decimal(left_value)
                right_num = _parse_decimal(right_value)
                if left_num is None or right_num is None:
                    if left_value == right_value:
                        continue
                    diff = ""
                    diff_abs = ""
                else:
                    diff = left_num - right_num
                    diff_abs = abs(diff)
                    if diff_abs <= field.tolerance:
                        continue
            else:
                if left_value == right_value:
                    continue
                diff = ""
                diff_abs = ""

            payload = {
                **key_payload,
                "status": "mismatch",
                "field": field.name,
                "left_value": left_value,
                "right_value": right_value,
                "diff": f"{diff:.2f}" if isinstance(diff, Decimal) else "",
                "diff_abs": f"{diff_abs:.2f}" if isinstance(diff_abs, Decimal) else "",
                "notes": "",
            }
            output.append(payload)
    return output


def write_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not rows:
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["status", "field"])
        return
    columns = list(rows[0].keys())
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
