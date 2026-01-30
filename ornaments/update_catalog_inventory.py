#!/usr/bin/env python3
"""Update catalog inventory quantities using ornament intake counts."""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence


CATALOG_NEW_COLUMNS = (
    "New Quantity Mission Viejo",
    "New Quantity Cerritos",
    "New Quantity Storage",
)
CATALOG_CURRENT_COLUMNS = (
    "Current Quantity Mission Viejo",
    "Current Quantity Cerritos",
    "Current Quantity Storage",
)

SUMMARY_COLUMNS = (
    "Item Name",
    "Style",
    "UPC",
    "Prev Quantity Mission Viejo",
    "Prev Quantity Cerritos",
    "Prev Quantity Storage",
    "New Quantity Mission Viejo",
    "New Quantity Cerritos",
    "New Quantity Storage",
    "Quantity Received",
)


@dataclass(frozen=True)
class IntakeRecord:
    """Normalized intake row from ORNAMENTS_2025_COUNT.csv."""

    style: str
    upc: str
    quantity_received: int
    source_row: dict = field(compare=False, repr=False)


def _value_is_digit_string(value: str) -> bool:
    return bool(value) and value.isdigit()


def _possible_sku_keys(value: str) -> Sequence[str]:
    """Generate possible lookup keys for SKU/UPC style fields."""
    keys = []
    raw = value.strip()
    if not raw:
        return keys
    keys.append(raw)
    if raw.upper() != raw:
        keys.append(raw.upper())
    if _value_is_digit_string(raw):
        numeric = str(int(raw))
        if numeric not in keys:
            keys.append(numeric)
        stripped = raw.lstrip("0")
        if stripped and stripped not in keys:
            keys.append(stripped)
    return keys


def _normalize_style(style: str) -> str:
    return style.strip().upper()


def _extract_style_from_item_name(name: str) -> Optional[str]:
    """Pull the trailing parenthetical style from the item name if present."""
    if not name:
        return None
    match = re.search(r"\(([^()]+)\)\s*$", name)
    if not match:
        return None
    return match.group(1).strip()


def _find_quantity_field(fieldnames: Sequence[str]) -> str:
    for field in fieldnames:
        normalized = field.lower().replace(" ", "").replace("_", "")
        if normalized == "quantityreceived":
            return field
    raise ValueError("Unable to locate quantity_received column in intake file.")


def _parse_int(value: Optional[str]) -> int:
    if value is None:
        return 0
    stripped = value.strip()
    if not stripped:
        return 0
    try:
        return int(stripped)
    except ValueError:
        return int(float(stripped))


def _load_intake_records(
    path: Path,
) -> tuple[list[IntakeRecord], dict[str, dict[str, IntakeRecord]]]:
    by_style: Dict[str, IntakeRecord] = {}
    by_upc: Dict[str, IntakeRecord] = {}
    records: List[IntakeRecord] = []

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        quantity_field = _find_quantity_field(reader.fieldnames or [])
        for row in reader:
            style = row.get("STYLE", "").strip()
            upc = row.get("UPC", "").strip()
            qty_value = row.get(quantity_field, "")
            quantity_received = _parse_int(qty_value)
            record = IntakeRecord(
                style=style,
                upc=upc,
                quantity_received=quantity_received,
                source_row=row,
            )
            records.append(record)
            if style:
                style_key = _normalize_style(style)
                by_style[style_key] = record
            if upc:
                for key in _possible_sku_keys(upc):
                    by_upc[key] = record
    return records, {"style": by_style, "upc": by_upc}


def _current_quantity(row: dict, column: str) -> int:
    return max(0, _parse_int(row.get(column, "0")))


def _distribute_for_pbs(quantity: int) -> Sequence[int]:
    if quantity <= 0:
        return (0, 0, 0)
    mission = math.ceil(quantity * 2 / 3)
    cerritos = quantity - mission
    storage = 0
    return mission, cerritos, storage


def _distribute_for_boxes(boxes: int) -> Sequence[int]:
    if boxes <= 0:
        return (0, 0, 0)
    if boxes == 1:
        return (6, 6, 0)
    # Reserve one box for each store, remainder to storage.
    mission = 12
    cerritos = 12
    storage = max(0, boxes - 2) * 12
    return mission, cerritos, storage


def _compute_distribution(record: IntakeRecord) -> Sequence[int]:
    style_key = _normalize_style(record.style)
    if style_key.startswith("PBS"):
        return _distribute_for_pbs(record.quantity_received)
    return _distribute_for_boxes(record.quantity_received)


def update_catalog_quantities(
    catalog_path: Path,
    intake_path: Path,
    output_path: Optional[Path] = None,
) -> Path:
    catalog_path = Path(catalog_path)
    intake_path = Path(intake_path)
    intake_records, intake_maps = _load_intake_records(intake_path)
    by_style: Dict[str, IntakeRecord] = intake_maps["style"]
    by_upc: Dict[str, IntakeRecord] = intake_maps["upc"]

    matched_styles: Dict[str, int] = defaultdict(int)
    matched_rows: List[dict] = []
    matched_records: set[IntakeRecord] = set()
    summary_rows: List[dict] = []

    with catalog_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        for row in reader:
            record = None
            sku_value = row.get("SKU", "")
            for key in _possible_sku_keys(sku_value):
                record = by_upc.get(key)
                if record:
                    break
            if record is None:
                style_token = _extract_style_from_item_name(row.get("Item Name", ""))
                if style_token:
                    normalized = _normalize_style(style_token)
                    record = by_style.get(normalized)
                    if record is None:
                        # Try removing trailing descriptors (e.g. "- BROWN")
                        simplified = normalized.split("-")[0].strip()
                        record = by_style.get(simplified)
            if record is None:
                continue

            mission_add, cerritos_add, storage_add = _compute_distribution(record)
            additions = {
                "Mission Viejo": mission_add,
                "Cerritos": cerritos_add,
                "Storage": storage_add,
            }
            prev_totals = {}
            for current_col, new_col, location in zip(
                    CATALOG_CURRENT_COLUMNS,
                    CATALOG_NEW_COLUMNS,
                    ("Mission Viejo", "Cerritos", "Storage"),
                ):
                current_value = _current_quantity(row, current_col)
                new_quantity = current_value + additions[location]
                row[new_col] = str(new_quantity)
                prev_totals[location] = current_value
            matched_rows.append(row)
            matched_styles[_normalize_style(record.style)] += 1
            matched_records.add(record)
            summary_rows.append(
                {
                    "Item Name": row.get("Item Name", ""),
                    "Style": record.style,
                    "UPC": record.upc,
                    "Prev Quantity Mission Viejo": prev_totals["Mission Viejo"],
                    "Prev Quantity Cerritos": prev_totals["Cerritos"],
                    "Prev Quantity Storage": prev_totals["Storage"],
                    "New Quantity Mission Viejo": _parse_int(row["New Quantity Mission Viejo"]),
                    "New Quantity Cerritos": _parse_int(row["New Quantity Cerritos"]),
                    "New Quantity Storage": _parse_int(row["New Quantity Storage"]),
                    "Quantity Received": record.quantity_received,
                }
            )

    if output_path is None:
        suffix = catalog_path.suffix
        output_path = catalog_path.with_name(f"{catalog_path.stem}_updated{suffix}")

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matched_rows)

    summary_path = output_path.with_name(
        f"{output_path.stem}_summary{output_path.suffix}"
    )
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(summary_rows)

    unmatched_styles = set(by_style) - set(matched_styles)
    unmatched_records = [
        record for record in intake_records if record not in matched_records
    ]
    print(
        f"Updated {len(matched_styles)} intake styles across "
        f"{len(matched_rows)} catalog rows."
    )
    if unmatched_styles:
        print(f"Intake styles without catalog match: {len(unmatched_styles)}")
    if unmatched_records:
        print("Unmatched intake entries (STYLE / UPC / qty):")
        for record in unmatched_records:
            style = record.style or "<none>"
            upc = record.upc or "<none>"
            print(f"  - {style} / {upc} / {record.quantity_received}")
    else:
        print("All intake entries matched to catalog rows.")
    print(f"Wrote updated catalog to {output_path}")
    print(f"Wrote match summary to {summary_path}")
    return output_path


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update Square catalog inventory using intake counts."
    )
    parser.add_argument(
        "catalog",
        help="Path to the Square catalog CSV (e.g. KX6Y24PVNYR04_catalog-*.csv)",
    )
    parser.add_argument(
        "intake",
        help="Path to the intake counts CSV (e.g. ORNAMENTS_2025_COUNT.csv)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional output path. Defaults to <catalog> with _updated suffix.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    catalog_path = Path(args.catalog)
    intake_path = Path(args.intake)
    output_path = Path(args.output) if args.output else None
    update_catalog_quantities(catalog_path, intake_path, output_path)


if __name__ == "__main__":
    main()
