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
from orders_analytics.utils.providers import normalize_provider

RAW_COLUMNS = [
    "order_id",
    "order_date",
    "order_datetime",
    "statement_date",
    "period_start",
    "period_end",
    "restaurant_name",
    "provider",
    "subtotal",
    "tax",
    "commission_fee",
    "payout",
    "statement_id",
    "raw_text",
    "added_at",
]


def parse_pdf(payload: bytes) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    statement_date = ""
    period_start = ""
    period_end = ""
    restaurant_name = ""
    statement_id = ""

    def commit_statement_id() -> str:
        parts = [statement_date, period_start, period_end]
        return " | ".join([p for p in parts if p])

    for line in lines:
        if line.lower().startswith("statement"):
            statement_date = ""
            period_start = ""
            period_end = ""
            restaurant_name = ""
            statement_id = ""
            continue

        match = re.search(r"\bDate\s+(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if match:
            statement_date = match.group(1)
            statement_id = commit_statement_id()
            continue

        match = re.search(r"\bPeriod Start\s+(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if match:
            period_start = match.group(1)
            statement_id = commit_statement_id()
            continue

        match = re.search(r"\bPeriod End\s+(\d{1,2}/\d{1,2}/\d{4})", line, re.IGNORECASE)
        if match:
            period_end = match.group(1)
            statement_id = commit_statement_id()
            continue

        if not restaurant_name and period_start:
            if any(token in line.lower() for token in ("payable", "order no.", "total", "phone", "www.")):
                pass
            elif re.search(r"\d", line):
                pass
            else:
                restaurant_name = line.strip()
                statement_id = commit_statement_id()

        if line.upper().startswith("TOTAL"):
            continue

        order_match = re.match(
            r"^(\d+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})",
            line,
        )
        if order_match:
            order_id, date_str, amount, tax, commission, payable = order_match.groups()
            order_date = date_str
            order_datetime = f"{order_date}T00:00:00" if order_date else ""
            commission_val = normalize_money(commission)
            if commission_val:
                try:
                    dec = Decimal(commission_val)
                    if dec > 0:
                        commission_val = str((-dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                except InvalidOperation:
                    pass
            rows.append(
                {
                    "order_id": order_id,
                    "order_date": order_date,
                    "order_datetime": order_datetime,
                    "statement_date": statement_date,
                    "period_start": period_start,
                    "period_end": period_end,
                    "restaurant_name": restaurant_name,
                    "provider": normalize_provider(restaurant_name),
                    "subtotal": normalize_money(amount),
                    "tax": normalize_money(tax),
                    "commission_fee": commission_val,
                    "payout": normalize_money(payable),
                    "statement_id": statement_id,
                    "raw_text": text[:4000],
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
    parser = argparse.ArgumentParser(description="Extract Office Caterer billings from mbox PDFs.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Billings-OfficeCaterer.mbox"),
        help="Path to Billings-OfficeCaterer.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("officecaterer", "billings_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
