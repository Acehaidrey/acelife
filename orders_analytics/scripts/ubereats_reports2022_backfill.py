#!/usr/bin/env python3
"""One-time helper to find UberEats rows from reports2022 not in base Uber CSV."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]

BASE_UBER_PATH = REPO_ROOT / ".." / "Takeout" / "uber-bc08b66d-0603-49ef-8186-07a637505732-united_states.csv"
REPORTS_ROOT = REPO_ROOT / ".." / "Takeout" / "reports2022"
OUTPUT_PATH = REPO_ROOT / ".." / "Takeout" / "uber_reports2022_missing_from_base.csv"
POSTMATES_PATH = REPO_ROOT / ".." / "Takeout" / "postmates_missing_as_uber.csv"


def read_uber_csv(path: Path) -> pd.DataFrame:
    # Try header=0 first, then header=1 if needed.
    try:
        df = pd.read_csv(path)
    except Exception:
        df = pd.read_csv(path, header=1)
    if "Order ID" not in df.columns:
        try:
            df = pd.read_csv(path, header=1)
        except Exception:
            pass
    # Normalize older column headers to the base Uber export names.
    column_map = {
        "Order Date / Refund date": "Order Date",
        "Order Date/Refund Date": "Order Date",
        "Food Sales (excluding tax)": "Sales (excl. tax)",
        "Tax on Food Sales": "Tax on Sales",
        "Food sales (including tax)": "Sales (incl. tax)",
        "Total Sales after Adjustments (including tax)": "Total Sales after Adjustments (incl tax)",
        "Total Sales after Adjustments (incl. tax)": "Total Sales after Adjustments (incl tax)",
        "Total Sales After Adjustments (incl tax)": "Total Sales after Adjustments (incl tax)",
        "Total Sales After Adjustments (incl. tax)": "Total Sales after Adjustments (incl tax)",
        "Adjustments (excluding tax)": "Price adjustments (excl. tax)",
        "Tax on Adjustments": "Tax on Price Adjustments",
        "Promo Spend on food": "Offers on items (incl. tax)",
        "Tax on Promotion on Food": "Tax On Offers on items",
        "Promo Spend on Delivery": "Delivery Offer Redemptions (incl. tax)",
        "Tax on Promo Spend on Delivery": "Tax On Delivery Offer Redemptions",
        "Marketing Service Fee Adjustment": "Marketing Adjustment",
        "Uber Service Fee": "Marketplace Fee",
        "Gratuity": "Tips",
        "Miscellaneous Payments": "Other payments",
        "Misc Payment Description": "Other payments description",
        "Payout": "Total payout ",
        "Dispatch Fee": "Delivery Network Fee",
        "Tax on Dispatch Fee": "Tax on Delivery Network Fee",
        "Marketplace Facilitator Tax Adjustment": "Marketplace Facilitator Tax Adjustment\n",
    }
    df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})
    df = df.loc[:, ~df.columns.duplicated()]
    return df


def key_columns(df: pd.DataFrame) -> Tuple[str | None, str | None, str | None, str | None, str | None]:
    order_id = "Order ID" if "Order ID" in df.columns else None
    workflow_id = "Workflow ID" if "Workflow ID" in df.columns else None
    store = "Store Name" if "Store Name" in df.columns else None
    order_date = "Order Date" if "Order Date" in df.columns else None
    order_time = "Order Accept Time" if "Order Accept Time" in df.columns else None
    return order_id, workflow_id, store, order_date, order_time


def build_keys(df: pd.DataFrame) -> List[str]:
    order_id, workflow_id, store, order_date, order_time = key_columns(df)
    parts = []
    for col in [order_id, workflow_id, store, order_date, order_time]:
        if col is None:
            parts.append("")
        else:
            parts.append(df[col].astype(str).fillna(""))
    return (parts[0] + "|" + parts[1] + "|" + parts[2] + "|" + parts[3] + "|" + parts[4]).tolist()


def iter_report_files() -> Iterable[Path]:
    roots = [REPORTS_ROOT / "Ameci", REPORTS_ROOT / "Aroma"]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.csv"):
            lower = path.name.lower()
            if "uber" in lower or "ubereats" in lower:
                yield path


def main() -> None:
    if not BASE_UBER_PATH.exists():
        raise SystemExit(f"Base Uber file not found: {BASE_UBER_PATH}")

    base_df = read_uber_csv(BASE_UBER_PATH)
    base_cols = list(base_df.columns)
    base_keys = set(build_keys(base_df))

    frames = []
    for path in sorted(iter_report_files()):
        parts = path.parts
        year = None
        month = None
        for part in parts:
            if part.isdigit() and len(part) == 4:
                year = int(part)
            if part.isdigit() and len(part) == 2:
                try:
                    m = int(part)
                except ValueError:
                    continue
                if 1 <= m <= 12:
                    month = m
        if year is None or year < 2020 or year > 2021:
            continue
        if year == 2021 and (month is None or month > 2):
            continue

        df = read_uber_csv(path)
        if df.empty:
            continue
        df = df.copy()
        df["source_file"] = str(path)
        # Reindex to base columns (plus source_file)
        for col in base_cols:
            if col not in df.columns:
                df[col] = pd.NA
        df = df[base_cols + ["source_file"]]
        keys = build_keys(df)
        df["__key__"] = keys
        df = df[~df["__key__"].isin(base_keys)]
        if not df.empty:
            frames.append(df)

    if not frames and not POSTMATES_PATH.exists():
        print("No missing rows found.")
        return

    missing = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not missing.empty and "__key__" in missing.columns:
        missing = missing.drop(columns=["__key__"])

    if POSTMATES_PATH.exists():
        postmates = pd.read_csv(POSTMATES_PATH, dtype=str)
        if not postmates.empty:
            for col in base_cols:
                if col not in postmates.columns:
                    postmates[col] = pd.NA
            if "Order ID" in postmates.columns:
                postmates["Order ID"] = postmates["Order ID"].astype(str).str.replace(r"\.0$", "", regex=True)
            postmates = postmates[base_cols + [c for c in postmates.columns if c not in base_cols]]
            missing = pd.concat([missing, postmates], ignore_index=True)

    if missing.empty:
        print("No missing rows found.")
        return

    missing.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(missing)} rows -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
