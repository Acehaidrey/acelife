#!/usr/bin/env python3
"""Make a catalog-ready CSV for newly ordered ornaments/stockings.

Steps:
1. Normalize the source order sheet (STYLE/DESCRIPTION) via format_invoice_received.
2. Push names/prices/configuration into a Square catalog export via rename_items_in_catalog.
3. Extract just the newly added rows so they can be imported separately.
"""

from __future__ import annotations

import argparse
import pathlib

import pandas as pd

from polarx_invoice_inventory import (
    extract_item_number,
    format_invoice_received,
    rename_items_in_catalog,
    update_missing_items_to_catalog,
)


def normalize_text(value: str) -> str:
    return (value or "").upper()


def infer_categories(item_number: str, item_name: str) -> str:
    """Infer category hierarchy based on item number and name keywords."""
    number = normalize_text(item_number)
    name = normalize_text(item_name)

    categories: list[str] = []

    def add(category: str) -> None:
        if category and category not in categories:
            categories.append(category)

    if number.startswith("PBS"):
        add("Stocking (W3LQNKF77II35AUEVYTGCLXZ)")
        if "BABY" in name:
            add("Ornament > Baby")
            if number.endswith("-P") or "PINK" in name:
                add("Ornament > Baby > Baby Girl (Pink)")
            elif number.endswith("-B") or "BLUE" in name:
                add("Ornament > Baby > Baby Boy (Blue)")
            else:
                add("Ornament > Baby > Baby Neutral")
        return ", ".join(categories)

    if number.startswith("PF"):
        add("Ornament")
        add("Ornament > Picture Frame")
    else:
        add("Ornament")

    if "EXPECTING" in name or "PREGNANT" in name:
        add("Ornament > We're Expecting (Pregnancy)")

    if number.startswith("DECO") or "DECO" in name:
        add("Ornament > Personalization Supplies")

    if any(number.startswith(prefix) for prefix in ("NFL", "NBA", "MLB", "NHL", "NCAA", "MLS")):
        add("Ornament > Sports")

    if "COUPLE" in name or "COUPLES" in name:
        add("Ornament > Family of 2 (Couples)")

    if "BABY" in name:
        add("Ornament > Baby")
        if number.endswith("-P") or "PINK" in name:
            add("Ornament > Baby > Baby Girl (Pink)")
        elif number.endswith("-B") or "BLUE" in name:
            add("Ornament > Baby > Baby Boy (Blue)")
        elif any(suffix in number for suffix in ("-RG", "-GN", "-GR")) or any(
            keyword in name for keyword in ("NEUTRAL", "RED & GREEN", "TEAL")
        ):
            add("Ornament > Baby > Baby Neutral")
        else:
            add("Ornament > Baby > Baby Neutral")

    if "CHILD" in name or "KID" in name:
        add("Ornament > Child")

    if any(keyword in name for keyword in ("DOG", "CAT", "PET", "PAW", "ANIMAL", "WOOF", "WHO SAVED WHO")):
        add("Ornament > Pets/Animals")

    if any(
        keyword in name
        for keyword in (
            "SOCCER",
            "BASEBALL",
            "FOOTBALL",
            "BASKETBALL",
            "HOCKEY",
            "GOLF",
            "CHEER",
            "SPORT",
            "NFL",
            "NBA",
            "MLB",
            "NHL",
            "KARATE",
            "JOGGER"
        )
    ):
        add("Ornament > Sports")

    if any(
        keyword in name
        for keyword in (
            "NURSE",
            "DOCTOR",
            "TEACHER",
            "POLICE",
            "OFFICER",
            "FIREFIGHTER",
            "FIREMAN",
            "DENTIST",
            "CHEF",
            "ENGINEER",
            "ARMY",
            "NAVY",
            "MARINE",
            "PILOT",
            "MILITARY",
            "OCCUPATION",
        )
    ):
        add("Ornament > Occupation")

    if any(
        keyword in name
        for keyword in (
            "BIKE",
            "CAMP",
            "FISH",
            "FISHING",
            "CAMPER",
            "CAMPING",
            "HUNT",
            "HUNTING",
            "SKI",
            "SNOWBOARD",
            "DANCE",
            "MUSIC",
            "GUITAR",
            "ORCHESTRA",
            "MOTORCYCLE",
            "MOTORBIKE",
            "ESPRESSO",
            "COFFEE",
            "CAMERA",
            "PHONE",
            "TECH",
            "GAMER",
        )
    ):
        add("Ornament > Hobbies/Activities")

    if "GENERAL" in name:
        add("Ornament > General")

    if "HOLIDAY" in name or "CHRISTMAS" in name or "XMAS" in name:
        add("Ornament > Holiday Themed")

    if any(
        keyword in name
        for keyword in (
            "TRAVEL",
            "POSTCARD",
            "SUITCASE",
            "VACATION",
            "ROAD TRIP",
            "ROADTRIP",
            "CAMPER",
            "RV",
        )
    ):
        add("Ornament > Travel")

    if any(keyword in name for keyword in ("HOUSE", "HOME", "DOOR", "FRONT DOOR")):
        add("Ornament > House/Door")

    family_size = None
    if "-" in number:
        suffix = number.split("-")[-1]
        if suffix.isdigit():
            family_size = int(suffix)
    if family_size is None and "FAMILY OF" in name:
        parts = name.split("FAMILY OF", 1)[-1].strip().split()
        if parts and parts[0].isdigit():
            family_size = int(parts[0])

    if family_size:
        if family_size == 2:
            add("Ornament > Family of 2 (Couples)")
        else:
            add(f"Ornament > Family of {family_size}")

    return ", ".join(categories)


def default_formatted_path(source: pathlib.Path) -> pathlib.Path:
    return source.with_name(f"{source.stem}_OUTPUT.csv")


def run_pipeline(
    catalog_path: pathlib.Path,
    source_path: pathlib.Path,
    formatted_path: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path]:
    formatted_invoice_path = pathlib.Path(
        format_invoice_received(str(source_path), str(formatted_path))
    )
    catalog_with_missing_path = pathlib.Path(
        update_missing_items_to_catalog(str(catalog_path), str(formatted_invoice_path))
    )
    cleaned_catalog_path = pathlib.Path(
        rename_items_in_catalog(
            str(catalog_with_missing_path), str(formatted_invoice_path)
        )
    )
    return formatted_invoice_path, cleaned_catalog_path


def extract_new_rows(
    cleaned_catalog_path: pathlib.Path,
    formatted_invoice_path: pathlib.Path,
    output_path: pathlib.Path,
) -> None:
    invoice_df = pd.read_csv(formatted_invoice_path)
    numbers = set(invoice_df["Number"])

    catalog_df = pd.read_csv(cleaned_catalog_path)
    catalog_df["ItemNumber"] = catalog_df["Item Name"].apply(extract_item_number)

    new_rows_df = catalog_df[catalog_df["ItemNumber"].isin(numbers)].copy()
    new_rows_df["Categories"] = new_rows_df.apply(
        lambda row: infer_categories(row["ItemNumber"], row["Item Name"]), axis=1
    )
    catalog_df.loc[
        catalog_df["ItemNumber"].isin(numbers), "Categories"
    ] = new_rows_df["Categories"].values

    new_rows_df = new_rows_df.drop(columns=["ItemNumber"])
    new_rows_df.to_csv(output_path, index=False)
    catalog_df = catalog_df.drop(columns=["ItemNumber"])
    catalog_df.to_csv(cleaned_catalog_path, index=False)

    basic_only = new_rows_df[
        new_rows_df["Categories"].isin(["Ornament", "Stocking (W3LQNKF77II35AUEVYTGCLXZ)"])
    ]
    if not basic_only.empty:
        print(
            f"{len(basic_only)} item(s) are still tagged with only broad categories. "
            "Consider refining these manually."
        )
        sample = basic_only[["Item Name", "Categories"]].head(10)
        print("Items needing manual category refinement (first 10):")
        print(sample.to_string(index=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        required=True,
        type=pathlib.Path,
        help="Path to the Square catalog export CSV.",
    )
    parser.add_argument(
        "--source",
        required=True,
        type=pathlib.Path,
        help="STYLE/DESCRIPTION CSV (e.g. new_ornaments_2025_with_exists.csv).",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=pathlib.Path,
        help="Destination CSV containing only the new rows with catalog columns.",
    )
    parser.add_argument(
        "--formatted",
        type=pathlib.Path,
        help="Optional override for the formatted invoice path; defaults to <source>_OUTPUT.csv.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog_path = args.catalog.resolve()
    source_path = args.source.resolve()
    formatted_path = (args.formatted or default_formatted_path(source_path)).resolve()
    output_path = args.output.resolve()

    formatted_invoice_path, cleaned_catalog_path = run_pipeline(
        catalog_path, source_path, formatted_path
    )

    extract_new_rows(cleaned_catalog_path, formatted_invoice_path, output_path)
    print("Formatted invoice CSV:", formatted_invoice_path)
    print("Cleaned catalog CSV:", cleaned_catalog_path)
    print("New items CSV:", output_path)


if __name__ == "__main__":
    main()
