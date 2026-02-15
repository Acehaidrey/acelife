#!/usr/bin/env python3
"""One-time helper to find UberEats rows from reports2022 not in base Uber CSV."""
from __future__ import annotations

import os
import re
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




def _extract_year_month(path: Path) -> tuple[int | None, int | None]:
    year = None
    month = None
    # Handle folder names like 2021_02 or 2021-02
    for part in path.parts:
        m = re.match(r"^(\d{4})[_-](\d{2})$", part)
        if m:
            year = int(m.group(1))
            month = int(m.group(2))
        if part.isdigit() and len(part) == 4:
            year = int(part)
        if part.isdigit() and len(part) == 2:
            try:
                mo = int(part)
            except ValueError:
                continue
            if 1 <= mo <= 12:
                month = mo
    return year, month




def _infer_order_date_from_source(source: str) -> str:
    if not source:
        return ""
    parts = str(source).split('/')
    year = None
    month = None
    for part in parts:
        m = re.match(r"^(\d{4})[_-](\d{2})$", part)
        if m:
            year = int(m.group(1))
            month = int(m.group(2))
        if part.isdigit() and len(part) == 4:
            year = int(part)
        if part.isdigit() and len(part) == 2:
            mo = int(part)
            if 1 <= mo <= 12:
                month = mo
    if year and month:
        last_day = __import__("calendar").monthrange(year, month)[1]
        return f"{year:04d}-{month:02d}-{last_day:02d}"
    return ""


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
    empty_order_frames = []
    for path in sorted(iter_report_files()):
        year, month = _extract_year_month(path)
        if year is None or year < 2020 or year > 2021:
            continue
        if year == 2021 and (month is None or month > 2):
            continue

        df = read_uber_csv(path)
        if "Order Date" in df.columns:
            order_dates = pd.to_datetime(df["Order Date"], errors="coerce")
            cutoff = pd.Timestamp("2021-02-11")
            if "Order ID" in df.columns:
                empty_rows = df[(df["Order ID"].fillna("").astype(str).str.strip() == "") & (order_dates.isna())]
                if not empty_rows.empty:
                    empty_rows = empty_rows.copy()
                    empty_rows["source_file"] = str(path)
                    empty_order_frames.append(empty_rows)
            df = df[(order_dates < cutoff) | (order_dates.isna())]
        if df.empty:
            continue
        df = df.copy()
        df["source_file"] = str(path)
        if "Order ID" in df.columns:
            empty_rows = df[df["Order ID"].fillna("").astype(str).str.strip() == ""]
            if not empty_rows.empty:
                empty_order_frames.append(empty_rows)
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

    if empty_order_frames:
        empty_rows = pd.concat(empty_order_frames, ignore_index=True)
        for col in base_cols:
            if col not in empty_rows.columns:
                empty_rows[col] = pd.NA
        empty_rows = empty_rows[base_cols + ["source_file"]]
        missing = pd.concat([missing, empty_rows], ignore_index=True)

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

    # Fill Order Date for empty Order ID rows when missing.
    if "Order Date" in missing.columns:
        order_raw = missing["Order Date"].fillna("").astype(str).str.strip()
        payout_raw = missing["Payout Date"].fillna("").astype(str).str.strip() if "Payout Date" in missing.columns else ""
        # prefer payout date when order date missing
        if isinstance(payout_raw, str):
            payout_raw = order_raw
        filled = order_raw.where(order_raw != "", payout_raw)
        if "source_file" in missing.columns:
            still_missing = filled.fillna("").astype(str).str.strip() == ""
            if still_missing.any():
                inferred = [ _infer_order_date_from_source(v) for v in missing.loc[still_missing, "source_file"] ]
                filled.loc[still_missing] = inferred
        missing["Order Date"] = filled

    if missing.empty:
        print("No missing rows found.")
        return

    missing.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(missing)} rows -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
