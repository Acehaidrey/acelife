#!/usr/bin/env python3
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from orders_analytics.utils.constants import raw_path


RAW_COLUMNS = [
    "order_id",
    "provider",
    "restaurant_name",
    "order_datetime",
    "order_type",
    "payment_type",
    "customer_name",
    "phone",
    "email",
    "address",
    "items",
    "item_count",
    "subtotal",
    "tax",
    "tip",
    "delivery_fee",
    "total",
    "notes",
    "source_file",
    "email_date",
    "added_at",
]


def read_report_csv(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, sep="\t", engine="python", on_bad_lines="skip")
    except Exception:
        df = pd.read_csv(path, engine="python", on_bad_lines="skip")
    if len(df.columns) == 1 and "\t" in df.columns[0]:
        df = pd.read_csv(path, sep="\t", engine="python", on_bad_lines="skip")
    return df


def build_address(row: pd.Series) -> str:
    parts = []
    street = str(row.get("STREET", "") or "").strip()
    suite = str(row.get("SUITE_APT", "") or "").strip()
    city = str(row.get("CITY", "") or "").strip()
    state = str(row.get("STATE", "") or "").strip()
    zipcode = str(row.get("ZIP", "") or "").strip()
    if street:
        parts.append(street)
    if suite:
        parts.append(suite)
    if city or state or zipcode:
        tail = " ".join([p for p in [city, state, zipcode] if p])
        parts.append(tail)
    return ", ".join(parts) if parts else ""


def map_rows(df: pd.DataFrame, source_file: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for _, row in df.iterrows():
        order_id = str(row.get("ORDER_ID", "") or "").strip()
        if not order_id:
            continue
        first = str(row.get("FIRST_NAME", "") or "").strip()
        last = str(row.get("LAST_NAME", "") or "").strip()
        customer_name = " ".join([p for p in [first, last] if p])
        notes_parts = []
        status = str(row.get("STATUS", "") or "").strip()
        if status:
            notes_parts.append(f"status={status}")
        dispatch = str(row.get("DISPATCH_METHOD", "") or "").strip()
        if dispatch:
            notes_parts.append(f"dispatch={dispatch}")
        coupon = str(row.get("COUPON_NAME", "") or "").strip()
        if coupon:
            notes_parts.append(f"coupon={coupon}")
        notes = " | ".join(notes_parts)
        rows.append(
            {
                "order_id": order_id,
                "provider": "AMECI",
                "restaurant_name": str(row.get("STORE", "") or "Ameci Pizza and Pasta"),
                "order_datetime": str(row.get("DATE", "") or "").strip(),
                "order_type": str(row.get("TYPE", "") or "").strip(),
                "payment_type": str(row.get("PAY_TYPE", "") or "").strip(),
                "customer_name": customer_name,
                "phone": str(row.get("PHONE", "") or "").strip(),
                "email": str(row.get("EMAIL", "") or "").strip(),
                "address": build_address(row),
                "items": "",
                "item_count": "",
                "subtotal": str(row.get("TOTAL_BEFORE_TAX", "") or "").strip(),
                "tax": str(row.get("TAX", "") or "").strip(),
                "tip": str(row.get("TIP_AMOUNT", "") or "").strip(),
                "delivery_fee": "",
                "total": str(row.get("TOTAL_AFTER_TAX", "") or "").strip(),
                "notes": notes,
                "source_file": source_file,
                "email_date": "",
                "added_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Brygid report CSVs into orders_raw.csv.")
    parser.add_argument(
        "--base-dir",
        default="Takeout/reports2022/Ameci",
        help="Base directory containing Brygid report CSVs.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("brygid", "orders_raw.csv"),
        help="Output orders_raw.csv path.",
    )
    parser.add_argument(
        "--email-out",
        default=raw_path("brygid", "orders_raw_from_email.csv"),
        help="Output path for email-only orders (copy of current orders_raw.csv).",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        raise SystemExit(f"Missing base dir: {base_dir}")

    files = []
    for path in base_dir.rglob("*.csv"):
        name = path.name.lower()
        if "brygid" not in name:
            continue
        if "billing" in name:
            continue
        files.append(path)

    if not files:
        raise SystemExit("No Brygid report CSVs found.")

    existing = pd.read_csv(args.out, dtype=str).fillna("") if os.path.exists(args.out) else pd.DataFrame()
    if not existing.empty:
        existing.to_csv(args.email_out, index=False)
    existing_ids = set(existing.get("order_id", pd.Series(dtype=str)).astype(str))

    new_rows: List[Dict[str, str]] = []
    for path in sorted(files):
        df = read_report_csv(path)
        mapped = map_rows(df, str(path))
        for row in mapped:
            if row["order_id"] in existing_ids:
                continue
            new_rows.append(row)
            existing_ids.add(row["order_id"])

    if not new_rows:
        print("No new rows to add.")
        return

    new_df = pd.DataFrame(new_rows)
    # Ensure consistent columns
    for col in RAW_COLUMNS:
        if col not in new_df.columns:
            new_df[col] = ""
    new_df = new_df[RAW_COLUMNS]

    if existing.empty:
        merged = new_df
    else:
        for col in RAW_COLUMNS:
            if col not in existing.columns:
                existing[col] = ""
        existing = existing[RAW_COLUMNS]
        merged = pd.concat([existing, new_df], ignore_index=True)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    merged.to_csv(args.out, index=False)
    print(f"Added {len(new_rows)} rows -> {args.out}")


if __name__ == "__main__":
    main()
