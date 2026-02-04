#!/usr/bin/env python3
import argparse
import datetime as dt
import io
import mailbox
import os
import re
from typing import Dict, List

import pandas as pd
import pdfplumber

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.normalize import normalize_datetime, normalize_money
from orders_analytics.utils.providers import normalize_provider

RAW_COLUMNS = [
    "order_id",
    "provider",
    "restaurant_name",
    "order_datetime",
    "order_type",
    "customer_name",
    "company_name",
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
    "added_at",
]


def parse_pdf(payload: bytes) -> Dict[str, str]:
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    order_id = ""
    match = re.search(r"INVOICE\s*#\s*(\d+)", text, re.IGNORECASE)
    if match:
        order_id = match.group(1)

    restaurant_name = ""
    rest_match = re.search(
        r"Restaurant Information:.*?\n(?:Food Total.*?\n)?([A-Z][A-Za-z0-9 &]+)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if rest_match:
        restaurant_name = rest_match.group(1).strip().title()
    provider = normalize_provider(restaurant_name) if restaurant_name else ""

    date_text = ""
    match = re.search(r"Date:\s*([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})", text)
    if match:
        date_text = match.group(1)

    time_text = ""
    match = re.search(r"Pick-?up Time:?\s*([0-9]{1,2}:[0-9]{2}\s*[AP]M)", text, re.IGNORECASE)
    if match:
        time_text = match.group(1).replace(" ", "")

    order_datetime = ""
    if date_text and time_text:
        order_datetime = normalize_datetime(
            f"{date_text} {time_text}",
            formats=("%d-%b-%Y %I:%M%p",),
            allow_iso=False,
        )

    subtotal = ""
    match = re.search(r"Food Total\s*:?\s*\$?([\d,.]+)", text, re.IGNORECASE)
    if match:
        subtotal = normalize_money(match.group(1))

    item_count = ""
    match = re.search(r"Item Count:\s*(\d+)", text, re.IGNORECASE)
    if match:
        item_count = match.group(1)

    notes = ""
    match = re.search(r"Restaurant Instructions\s*\n(.+?)(?:\nPhone:|\n\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE | re.DOTALL)
    if match:
        notes = " ".join(line.strip() for line in match.group(1).splitlines() if line.strip())

    total = subtotal

    return {
        "order_id": order_id,
        "provider": provider,
        "restaurant_name": restaurant_name,
        "order_datetime": order_datetime,
        "order_type": "pickup",
        "customer_name": "",
        "company_name": "",
        "phone": "",
        "email": "",
        "address": "",
        "items": "",
        "item_count": item_count,
        "subtotal": subtotal,
        "tax": "",
        "tip": "",
        "delivery_fee": "",
        "total": total,
        "notes": notes,
    }


def parse_mbox(mbox_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        if not msg.is_multipart():
            continue
        for part in msg.walk():
            if part.get_content_type() != "application/octet-stream":
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            row = parse_pdf(payload)
            if row.get("order_id"):
                rows.append(row)
    return rows


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


def run(mbox: str, out: str) -> int:
    rows = parse_mbox(mbox)
    updated = upsert_raw(out, rows)
    print(f"Upserted {updated} order row(s) into {out}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Food Runners orders from mbox PDFs.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Orders-FoodRunners.mbox"),
        help="Path to Orders-FoodRunners.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("foodrunners", "orders_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
