#!/usr/bin/env python3
"""Compare Square inventory against new ornaments data and mark existing styles.

Usage:
    python compare_inventory.py --inventory KX6Y24PVNYR04_catalog-2025-10-17-1706.csv \
        --new-items new_ornaments_2025.csv [--output updated_ornaments.csv]

If no --output path is supplied, the script updates the new-items file in place.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import re
from typing import Iterable, Set

PAREN_PATTERN = re.compile(r"\(([^()]*)\)\s*$")


def extract_style_codes(rows: Iterable[dict], name_column: str) -> Set[str]:
    """Pull the trailing parenthetical code from each inventory item name."""
    extracted: Set[str] = set()
    for row in rows:
        raw_name = (row.get(name_column) or "").strip()
        match = PAREN_PATTERN.search(raw_name)
        if match:
            extracted.add(match.group(1).strip().lower())
    return extracted


def detect_name_column(fieldnames: Iterable[str]) -> str:
    """Find the column that stores the Square item name."""
    for candidate in ("Item Name", "Name"):
        if candidate in fieldnames:
            return candidate
    raise KeyError(
        "Expected an 'Item Name' or 'Name' column in the inventory CSV header."
    )


def load_inventory_codes(inventory_path: pathlib.Path) -> Set[str]:
    with inventory_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"No header found in {inventory_path}")
        name_column = detect_name_column(reader.fieldnames)
        return extract_style_codes(reader, name_column)


def annotate_new_items(
    new_items_path: pathlib.Path,
    codes: Set[str],
    output_path: pathlib.Path,
) -> None:
    with new_items_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"No header found in {new_items_path}")

        fieldnames = list(reader.fieldnames)
        if "already_exists" not in fieldnames:
            fieldnames.append("already_exists")

        rows = []
        for row in reader:
            style_value = (row.get("STYLE") or "").strip().lower()
            row["already_exists"] = "true" if style_value in codes else "false"
            rows.append(row)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        required=True,
        type=pathlib.Path,
        help="Path to the Square inventory export CSV.",
    )
    parser.add_argument(
        "--new-items",
        required=True,
        type=pathlib.Path,
        help="Path to the CSV that should receive the already_exists column.",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        help="Optional output path; defaults to overwriting the new-items file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inventory_path = args.inventory
    new_items_path = args.new_items
    output_path = args.output or new_items_path

    codes = load_inventory_codes(inventory_path)
    annotate_new_items(new_items_path, codes, output_path)


if __name__ == "__main__":
    main()
