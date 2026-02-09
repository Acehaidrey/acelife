#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path
from typing import List

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from orders_analytics.utils.normalize import normalize_money  # noqa: E402
from orders_analytics.utils.normalize import normalize_datetime  # noqa: E402


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


def normalize_zip(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "." in text:
        text = text.split(".", 1)[0]
    return text


def build_address(row: pd.Series) -> str:
    parts = []
    street = str(row.get("STREET", "") or "").strip()
    suite = str(row.get("SUITE_APT", "") or "").strip()
    city = str(row.get("CITY", "") or "").strip()
    state = str(row.get("STATE", "") or "").strip()
    zipcode = normalize_zip(row.get("ZIP", ""))
    if street:
        parts.append(street)
    if suite:
        parts.append(suite)
    tail = " ".join([p for p in [city, state, zipcode] if p])
    if tail:
        parts.append(tail)
    return ", ".join(parts)


def map_rows(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["order_id"] = df.get("ORDER_ID", "").astype(str)
    out["provider"] = "AMECI"
    out["restaurant_name"] = df.get("STORE", "").astype(str)
    out["order_datetime"] = df.get("DATE", "").astype(str)
    out["order_datetime_parsed"] = out["order_datetime"].apply(
        lambda v: normalize_datetime(v, formats=("%m/%d/%Y %H:%M",), allow_iso=False)
    )
    order_type_raw = df.get("TYPE", "").astype(str).str.strip().str.lower()
    out["order_type"] = order_type_raw.apply(
        lambda v: "delivery" if v == "delivery" else "pickup"
    )

    pay_type = df.get("PAY_TYPE", "").astype(str).str.lower()
    out["payment_type"] = pay_type.apply(lambda v: "cash" if "cash" in v else "credit")

    first = df.get("FIRST_NAME", "").astype(str).str.strip()
    last = df.get("LAST_NAME", "").astype(str).str.strip()
    out["customer_name"] = (first + " " + last).str.strip()
    out["phone"] = df.get("PHONE", "").astype(str)
    out["email"] = df.get("EMAIL", "").astype(str)
    out["address"] = df.apply(build_address, axis=1)

    out["items"] = ""
    out["item_count"] = ""
    out["subtotal"] = df.get("TOTAL_BEFORE_TAX", "").astype(str).apply(normalize_money)
    out["tax"] = df.get("TAX", "").astype(str).apply(normalize_money)
    out["tip"] = df.get("TIP_AMOUNT", "").astype(str).apply(normalize_money)
    out["delivery_fee"] = df.get("delivery_fee", "").astype(str)
    out["total"] = df.get("TOTAL_AFTER_TAX", "").astype(str).apply(normalize_money)

    notes_parts: List[str] = []
    status = df.get("STATUS", "").astype(str)
    notes_parts.append(status.where(status.str.strip() != "", ""))
    import_notes = df.get("import_notes", "").astype(str)
    out["notes"] = (
        notes_parts[0].where(notes_parts[0].str.strip() != "", "")
        + import_notes.where(import_notes.str.strip() != "", "").apply(
            lambda v: f" | {v}" if v else ""
        )
    ).str.strip(" |")

    out["source_file"] = df.get("source_file", "").astype(str)
    out["email_date"] = ""
    out["added_at"] = ""

    # keep company_name for visibility in this intermediate output
    out["company_name"] = df.get("COMPANY", "").astype(str)

    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize aggregated Brygid report CSVs into raw schema for review."
    )
    parser.add_argument(
        "--in",
        dest="in_path",
        default="orders_analytics/data/raw/brygid/orders_raw_from_csvs.csv",
        help="Input aggregated CSV path.",
    )
    parser.add_argument(
        "--out",
        default="orders_analytics/data/raw/brygid/orders_raw_from_csvs_normalized.csv",
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()

    in_path = Path(args.in_path)
    if not in_path.exists():
        raise SystemExit(f"Missing input: {in_path}")

    df = pd.read_csv(in_path, dtype=str).fillna("")
    mapped = map_rows(df)

    # Ensure standard raw columns are first
    for col in RAW_COLUMNS:
        if col not in mapped.columns:
            mapped[col] = ""
    ordered = RAW_COLUMNS + [c for c in mapped.columns if c not in RAW_COLUMNS]
    mapped = mapped[ordered]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mapped.to_csv(out_path, index=False)
    print(f"Wrote {len(mapped)} rows -> {out_path}")


if __name__ == "__main__":
    main()
