#!/usr/bin/env python3
import argparse
import datetime as dt
import mailbox
import os
from email.utils import parsedate_to_datetime
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.parsers.deliverycom.parse_deliverycom_orders import parse_order

RAW_COLUMNS = [
    "order_id",
    "provider",
    "restaurant_name",
    "order_datetime",
    "order_type",
    "payment_type",
    "customer_name",
    "phone",
    "address",
    "items",
    "item_count",
    "subtotal",
    "tax",
    "tip",
    "delivery_fee",
    "total",
    "discount",
    "notes",
    "source_file",
    "email_date",
    "added_at",
]


def upsert_raw(existing_path: str, new_rows: List[Dict[str, str]]) -> int:
    now = dt.datetime.now().isoformat()
    if os.path.exists(existing_path):
        existing_df = pd.read_csv(existing_path, dtype=str).fillna("")
        existing_rows = existing_df.to_dict("records")
    else:
        existing_rows = []

    existing_map = {str(row.get("order_id", "")).strip(): row for row in existing_rows}
    updated = 0
    for row in new_rows:
        order_id = str(row.get("order_id", "")).strip()
        if not order_id:
            continue
        current = existing_map.get(order_id)
        if current is None:
            row["added_at"] = now
            existing_map[order_id] = row
            updated += 1
            continue
        changed = False
        for col in RAW_COLUMNS:
            if col == "added_at":
                continue
            old_val = str(current.get(col, "") or "")
            new_val = str(row.get(col, "") or "")
            if old_val != new_val:
                current[col] = new_val
                changed = True
        if changed:
            current["added_at"] = now
            updated += 1

    final_rows = list(existing_map.values())
    for row in final_rows:
        row.setdefault("added_at", now)
    os.makedirs(os.path.dirname(existing_path), exist_ok=True)
    pd.DataFrame(final_rows).reindex(columns=RAW_COLUMNS).to_csv(existing_path, index=False)
    return updated


def run(mbox_path: str, out_path: str) -> int:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        parsed = parse_order(msg)
        if not parsed:
            continue
        email_date = ""
        if msg.get("Date"):
            try:
                email_date = parsedate_to_datetime(msg.get("Date")).isoformat()
            except Exception:
                email_date = ""
        rows.append(
            {
                "order_id": parsed.get("order_id", ""),
                "provider": parsed.get("provider", ""),
                "restaurant_name": parsed.get("restaurant_name", ""),
                "order_datetime": parsed.get("order_datetime", ""),
                "order_type": parsed.get("order_type", ""),
                "payment_type": parsed.get("payment_type", ""),
                "customer_name": parsed.get("customer_name", ""),
                "phone": parsed.get("phone", ""),
                "address": parsed.get("address", ""),
                "items": parsed.get("items", ""),
                "item_count": parsed.get("item_count", ""),
                "subtotal": parsed.get("subtotal", ""),
                "tax": parsed.get("tax", ""),
                "tip": parsed.get("tip", ""),
                "delivery_fee": parsed.get("delivery_fee", ""),
                "total": parsed.get("total", ""),
                "discount": parsed.get("discount", ""),
                "notes": parsed.get("notes", ""),
                "source_file": os.path.basename(mbox_path),
                "email_date": email_date,
            }
        )
    updated = upsert_raw(out_path, rows)
    print(f"Upserted {updated} order row(s) into {out_path}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract delivery.com orders from mbox.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Orders-DeliveryCom.mbox"),
        help="Path to Orders-DeliveryCom.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("deliverycom", "orders_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
