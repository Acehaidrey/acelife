#!/usr/bin/env python3
"""Compare RM inventory against Square catalog entries tagged in Item Name.

This script looks for a trailing parenthetical code in the catalog Item Name,
normalizes it, and compares against rm2025.csv SKUs with an "RM" prefix.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import re
from typing import Dict, Iterable, List, Tuple

PAREN_PATTERN = re.compile(r"\(([^()]*)\)\s*$")


def normalize_code(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip()).upper()


def clean_description(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    cleaned = re.sub(r"\s+ea\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def build_item_name(description: str, rm_sku: str) -> str:
    description = clean_description(description)
    if description:
        return f"{description} ({rm_sku})"
    return rm_sku


def detect_name_column(fieldnames: Iterable[str]) -> str:
    for candidate in ("Item Name", "Name"):
        if candidate in fieldnames:
            return candidate
    raise KeyError("Expected an 'Item Name' or 'Name' column in the catalog CSV header.")


def load_rm_inventory(rm_path: pathlib.Path) -> Tuple[Dict[str, dict], List[str]]:
    with rm_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"No header found in {rm_path}")

        rows_by_code: Dict[str, dict] = {}
        for row in reader:
            raw_sku = normalize_code(row.get("SKU", ""))
            if not raw_sku:
                continue
            code = raw_sku if raw_sku.startswith("RM") else f"RM{raw_sku}"
            row["RM_SKU"] = code
            rows_by_code[code] = row

    return rows_by_code, list(reader.fieldnames) + ["RM_SKU"]


def load_catalog_rows(catalog_path: pathlib.Path) -> Tuple[Dict[str, List[dict]], List[str]]:
    with catalog_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"No header found in {catalog_path}")

        name_column = detect_name_column(reader.fieldnames)
        rows_by_code: Dict[str, List[dict]] = {}
        for row in reader:
            raw_name = (row.get(name_column) or "").strip()
            match = PAREN_PATTERN.search(raw_name)
            if not match:
                continue
            code = normalize_code(match.group(1))
            if not code:
                continue
            rows_by_code.setdefault(code, []).append(row)

    return rows_by_code, list(reader.fieldnames)


def write_rows(path: pathlib.Path, fieldnames: List[str], rows: List[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        required=True,
        type=pathlib.Path,
        help="Path to the Square catalog export CSV.",
    )
    parser.add_argument(
        "--rm",
        required=True,
        type=pathlib.Path,
        help="Path to rm2025.csv (or similar RM inventory CSV).",
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=pathlib.Path("."),
        help="Directory to write output CSVs (default: current directory).",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print found/missing matches to stdout instead of writing CSVs.",
    )
    parser.add_argument(
        "--missing-catalog",
        type=pathlib.Path,
        help="Write a CSV of missing items formatted for Square import.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    rm_rows_by_code, rm_fieldnames = load_rm_inventory(args.rm)
    catalog_rows_by_code, catalog_fieldnames = load_catalog_rows(args.catalog)

    rm_codes = set(rm_rows_by_code)
    catalog_codes = set(catalog_rows_by_code)

    found_codes = rm_codes & catalog_codes
    missing_codes = rm_codes - catalog_codes
    extra_codes = catalog_codes - rm_codes

    found_rows: List[dict] = []
    for code in sorted(found_codes):
        for row in catalog_rows_by_code.get(code, []):
            row = dict(row)
            row["Matched RM SKU"] = code
            found_rows.append(row)

    missing_rows = [rm_rows_by_code[code] for code in sorted(missing_codes)]

    if args.missing_catalog:
        missing_catalog_rows = []
        for row in missing_rows:
            rm_sku = row["RM_SKU"]
            description = clean_description(row.get("Description", ""))
            missing_catalog_rows.append({
                "Item Name": build_item_name(description, rm_sku),
                "SKU": rm_sku,
                "Description": description,
            })

        write_rows(
            args.missing_catalog,
            ["Item Name", "SKU", "Description"],
            missing_catalog_rows,
        )
        print(f"Wrote missing catalog rows: {args.missing_catalog}")

    if args.print_only:
        name_column = detect_name_column(catalog_fieldnames)
        print(f"Found matches: {len(found_rows)} rows (codes: {len(found_codes)})")
        for row in found_rows:
            item_name = (row.get(name_column) or "").strip()
            sku = (row.get("SKU") or "").strip()
            print(f"FOUND\t{row['Matched RM SKU']}\t{item_name}\t{sku}")
        print(f"Missing from catalog: {len(missing_rows)} rows (codes: {len(missing_codes)})")
        for row in missing_rows:
            description = clean_description(row.get("Description", ""))
            print(f"MISSING\t{row['RM_SKU']}\t{description}")
        return

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    extra_rows: List[dict] = []
    for code in sorted(extra_codes):
        for row in catalog_rows_by_code.get(code, []):
            row = dict(row)
            row["Catalog Code"] = code
            extra_rows.append(row)

    found_path = output_dir / "rm2025_catalog_found.csv"
    missing_path = output_dir / "rm2025_catalog_missing.csv"
    extra_path = output_dir / "rm2025_catalog_extra.csv"

    write_rows(found_path, catalog_fieldnames + ["Matched RM SKU"], found_rows)
    write_rows(missing_path, rm_fieldnames, missing_rows)
    write_rows(extra_path, catalog_fieldnames + ["Catalog Code"], extra_rows)

    print(f"Found matches: {len(found_rows)} rows (codes: {len(found_codes)})")
    print(f"Missing from catalog: {len(missing_rows)} rows (codes: {len(missing_codes)})")
    print(f"Catalog codes not in RM inventory: {len(extra_rows)} rows (codes: {len(extra_codes)})")
    print(f"Wrote: {found_path}")
    print(f"Wrote: {missing_path}")
    print(f"Wrote: {extra_path}")


if __name__ == "__main__":
    main()
