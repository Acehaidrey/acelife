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
    match = re.search(r"P\.O\. NO\.\s*(\d+)", text)
    if match:
        order_id = match.group(1)

    date_text = ""
    match = re.search(r"DATE\s+(\d{2}/\d{2}/\d{4})", text)
    if match:
        date_text = match.group(1)

    time_text = ""
    match = re.search(r"PICK UP TIME:?\s*\n?\s*([0-9]{1,2}:[0-9]{2}\s*[AP]M)", text, re.IGNORECASE)
    if match:
        time_text = match.group(1).replace(" ", "")

    order_datetime = ""
    if date_text and time_text:
        order_datetime = normalize_datetime(
            f"{date_text} {time_text}",
            formats=("%m/%d/%Y %I:%M%p",),
            allow_iso=False,
        )

    tax = ""
    match = re.search(r"Tax(?:es)?[^\d]*([\d.]+)", text, re.IGNORECASE)
    if match:
        tax = normalize_money(match.group(1))

    total = ""
    match = re.search(r"TOTAL\s*\$?([\d.]+)", text, re.IGNORECASE)
    if match:
        total = normalize_money(match.group(1))

    items = []
    item_count = 0
    subtotal_amounts = []
    for line in text.splitlines():
        line = line.strip()
        match = re.match(r"^(.+?)\s+(\d+)\s+([\d.]+)\s+([\d.]+)$", line)
        if match:
            name, qty, _, amount = match.groups()
            if name.lower().startswith("activity"):
                continue
            items.append(name)
            try:
                item_count += int(qty)
            except ValueError:
                pass
            subtotal_amounts.append(normalize_money(amount))

    subtotal = ""
    if subtotal_amounts:
        try:
            subtotal = f"{sum(float(val) for val in subtotal_amounts if val):.2f}"
        except ValueError:
            subtotal = ""
    if not subtotal and total and tax:
        try:
            subtotal = normalize_money(f"{(float(total) - float(tax)):.2f}")
        except ValueError:
            subtotal = ""

    restaurant_name = ""
    vendor_match = re.search(
        r"^(.+?)\s+The Office Caterer\s+DATE",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if vendor_match:
        restaurant_name = vendor_match.group(1).strip()
    elif "VENDOR" in text:
        fallback = re.search(r"VENDOR\s*\n([^\n]+)", text, re.IGNORECASE)
        if fallback:
            restaurant_name = fallback.group(1).strip()
    provider = normalize_provider(restaurant_name) if restaurant_name else ""

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
        "items": "; ".join(items),
        "item_count": str(item_count) if item_count else "",
        "subtotal": subtotal,
        "tax": tax,
        "tip": "",
        "delivery_fee": "",
        "total": total,
        "notes": "",
    }


def parse_mbox(mbox_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        if not msg.is_multipart():
            continue
        for part in msg.walk():
            if part.get_content_type() != "application/pdf":
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
    parser = argparse.ArgumentParser(description="Extract Office Caterer orders from mbox PDFs.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Orders-Office Caterer.mbox"),
        help="Path to Orders-Office Caterer.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("officecaterer", "orders_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
