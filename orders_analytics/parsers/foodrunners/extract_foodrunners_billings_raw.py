#!/usr/bin/env python3
import argparse
import datetime as dt
import io
import mailbox
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List

import pandas as pd
import pdfplumber

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.normalize import normalize_money

RAW_COLUMNS = [
    "order_id",
    "delivery_date",
    "order_datetime",
    "subtotal",
    "tax",
    "commission_fee",
    "processing_fee",
    "payout",
    "statement_id",
    "raw_text",
    "added_at",
]


def allocate_fee(total_raw: str, rows: List[Dict[str, str]], column: str) -> None:
    if not total_raw or not rows:
        return
    try:
        total = Decimal(total_raw)
    except InvalidOperation:
        return
    if len(rows) == 1:
        rows[0][column] = str(total)
        return
    try:
        subtotal_sum = sum(Decimal(row.get("subtotal") or "0") for row in rows)
    except InvalidOperation:
        subtotal_sum = Decimal("0")
    if subtotal_sum == 0:
        return
    allocs: List[Decimal] = []
    for row in rows:
        try:
            subtotal = Decimal(row.get("subtotal") or "0")
        except InvalidOperation:
            subtotal = Decimal("0")
        share = (subtotal / subtotal_sum) * total
        allocs.append(share.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    remainder = (total - sum(allocs)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    cent = Decimal("0.01")
    cents = int((abs(remainder) / cent).to_integral_value(rounding=ROUND_HALF_UP))
    step = cent if remainder > 0 else -cent
    for i in range(cents):
        allocs[i % len(allocs)] = (allocs[i % len(allocs)] + step).quantize(
            cent, rounding=ROUND_HALF_UP
        )
    for row, alloc in zip(rows, allocs):
        row[column] = str(alloc)


def parse_pdf(payload: bytes) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    statement_id = ""
    match = re.search(r"Settlement\s*#\s*(\d+)", text, re.IGNORECASE)
    if match:
        statement_id = match.group(1)

    order_rows = []
    seen_orders = set()
    for line in text.splitlines():
        line = line.strip()
        match = re.match(
            r"^(\d{5,})\s+(\d{2}/\d{2}/\d{4})\s+\$?([\d,]+(?:\.\d{2})?)\s+\$?([\d,]+(?:\.\d{2})?)",
            line,
        )
        if match:
            order_id, delivery_date, tax, subtotal = match.groups()
            key = (order_id, delivery_date, tax, subtotal)
            if key in seen_orders:
                continue
            seen_orders.add(key)
            order_datetime = ""
            if delivery_date:
                order_datetime = f"{delivery_date}T00:00:00"
            order_rows.append(
                {
                    "order_id": order_id,
                    "delivery_date": delivery_date,
                    "order_datetime": order_datetime,
                    "subtotal": normalize_money(subtotal),
                    "tax": normalize_money(tax),
                }
            )

    commission_fee = ""
    match = re.search(
        r"Commission\)\s*\$?\(?(-?[\d,]+(?:\.\d{2})?)\)?",
        text,
        re.IGNORECASE,
    )
    if match:
        commission_fee = normalize_money(f"({match.group(1)})") if "-" not in match.group(1) else normalize_money(match.group(1))

    processing_fee = ""
    match = re.search(
        r"Merchant Fee\s*\d+%:?\s*\$?\(?(-?[\d,]+(?:\.\d{2})?)\)?",
        text,
        re.IGNORECASE,
    )
    if match:
        processing_fee = normalize_money(f"({match.group(1)})") if "-" not in match.group(1) else normalize_money(match.group(1))

    payout = ""
    match = re.search(
        r"Balance pay:?\s*\$?\(?([\d,]+(?:\.\d{2})?)\)?", text, re.IGNORECASE
    )
    if match:
        payout = normalize_money(match.group(1))

    for row in order_rows:
        row.update(
            {
                "commission_fee": "",
                "processing_fee": "",
                "payout": payout,
                "statement_id": statement_id,
                "raw_text": text[:4000],
            }
        )
    allocate_fee(commission_fee, order_rows, "commission_fee")
    allocate_fee(processing_fee, order_rows, "processing_fee")
    rows.extend(order_rows)
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
            if old_val:
                continue
            if new_val and old_val != new_val:
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
    parser = argparse.ArgumentParser(description="Extract Food Runners billings from mbox PDFs.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Billings-FoodRunners.mbox"),
        help="Path to Billings-FoodRunners.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("foodrunners", "billings_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
