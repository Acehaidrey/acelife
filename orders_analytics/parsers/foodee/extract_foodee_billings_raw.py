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
from orders_analytics.utils.normalize import normalize_money

RAW_COLUMNS = [
    "order_id",
    "invoice_date",
    "payment_date",
    "invoice_total",
    "amount_paid",
    "still_owing",
    "provider",
    "restaurant_name",
    "restaurant_address",
    "raw_text",
    "added_at",
]

DATE_RE = re.compile(r"[A-Za-z]{3}\d{1,2},\d{4}")
ORDER_ID_RE = re.compile(r"\b[A-Z]{2,4}-\d+\b")


def parse_pdf(payload: bytes) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    restaurant_name = "Aroma Pizza & Pasta"
    restaurant_address = "20491 Alton Parkway, Lake Forest, CA 92610, United States"
    name_match = re.search(r"Aroma\\s*Pizza\\s*&\\s*Pasta", text, re.IGNORECASE)
    if name_match:
        restaurant_name = "Aroma Pizza & Pasta"
    addr_match = re.search(
        r"20491\\s*Alton\\s*Parkway[^A-Za-z0-9]*([A-Z\\s]{4,15})\\s*CA\\s*92610",
        text,
        re.IGNORECASE,
    )
    if addr_match:
        city = addr_match.group(1).strip().title()
        restaurant_address = f"20491 Alton Parkway, {city}, CA 92610, United States"
    payment_date = ""
    match = re.search(r"PaymentDate\s*([A-Za-z]{3}\d{1,2},\d{4})", text)
    if match:
        payment_date = match.group(1)
    else:
        dates = DATE_RE.findall(text)
        if dates:
            payment_date = dates[0]

    for match in re.finditer(
        r"([A-Za-z]{3}\d{1,2},\d{4})\s+([A-Z]{2,4}-\d+)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)",
        text,
    ):
        invoice_date, order_id, invoice_total, amount_paid, still_owing = match.groups()
        rows.append(
            {
                "order_id": order_id,
                "invoice_date": invoice_date,
                "payment_date": payment_date,
                "invoice_total": normalize_money(invoice_total),
                "amount_paid": normalize_money(amount_paid),
                "still_owing": normalize_money(still_owing),
                "provider": "AROMA",
                "restaurant_name": restaurant_name,
                "restaurant_address": restaurant_address,
                "raw_text": " ".join(match.groups()),
            }
        )
    return rows


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
            rows.extend(parse_pdf(payload))
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
    print(f"Upserted {updated} billing row(s) into {out}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Foodee billings from mbox PDFs.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Billings-Foodee.mbox"),
        help="Path to Billings-Foodee.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("foodee", "billings_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
