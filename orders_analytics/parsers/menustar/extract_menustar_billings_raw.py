#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import io
import mailbox
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.constants import raw_path
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.normalize import normalize_money

RAW_COLUMNS = [
    "order_id",
    "provider",
    "restaurant_name",
    "order_datetime",
    "order_type",
    "payment_type",
    "subtotal",
    "tax",
    "delivery_fee",
    "tip",
    "total",
    "statement_all_orders",
    "statement_prepaid_orders",
    "statement_menustar_fees",
    "statement_menustar_fees_allocated",
    "statement_adjustments",
    "statement_net_payout",
    "statement_source_file",
    "added_at",
]


def parse_csv_rows(text: str, provider: str, filename: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    summary = {
        "statement_all_orders": "",
        "statement_prepaid_orders": "",
        "statement_menustar_fees": "",
        "statement_adjustments": "",
        "statement_net_payout": "",
    }
    reader = list(csv.reader(io.StringIO(text)))
    header_idx = None
    for idx, row in enumerate(reader):
        if row and row[0].strip() == "Date":
            header_idx = idx
            break
    if header_idx is None:
        return rows

    # First pass: capture summary rows anywhere in the file.
    for row in reader:
        if not row or not row[0]:
            continue
        label = row[0].strip().lower()
        if label == "all orders":
            summary["statement_all_orders"] = normalize_money(row[1] if len(row) > 1 else "")
        elif label == "pre-paid orders":
            summary["statement_prepaid_orders"] = normalize_money(row[1] if len(row) > 1 else "")
        elif label == "menustar fees":
            summary["statement_menustar_fees"] = normalize_money(row[1] if len(row) > 1 else "")
        elif label == "adjustments":
            summary["statement_adjustments"] = normalize_money(row[1] if len(row) > 1 else "")
        elif label == "net payout":
            summary["statement_net_payout"] = normalize_money(row[1] if len(row) > 1 else "")

    headers = reader[header_idx]
    data_rows = reader[header_idx + 1 :]
    for row in data_rows:
        if not row or not row[0]:
            continue
        label = row[0].strip()
        if label.lower() in ("total", "all orders", "pre-paid orders", "menustar fees", "adjustments", "net payout"):
            continue
        if label.lower() == "total":
            continue
        try:
            date_str = row[0]
        except IndexError:
            continue
        record = dict(zip(headers, row))
        order_datetime = ""
        try:
            order_datetime = dt.datetime.strptime(date_str, "%m/%d/%Y %H:%M:%S").isoformat()
        except ValueError:
            try:
                order_datetime = dt.datetime.strptime(date_str, "%m/%d/%Y %H:%M").isoformat()
            except ValueError:
                order_datetime = date_str
        rows.append(
            {
                "order_id": "",
                "provider": provider,
                "restaurant_name": filename.replace(".csv", "").replace(".xlsx", "").strip(),
                "order_datetime": order_datetime,
                "order_type": record.get("Order Type", "").strip(),
                "payment_type": record.get("Payment Type", "").strip(),
                "subtotal": normalize_money(record.get("Subtotal", "")),
                "tax": normalize_money(record.get("Tax", "")),
                "delivery_fee": normalize_money(record.get("Delivery Fee", "")),
                "tip": normalize_money(record.get("Tip", "")),
                "total": normalize_money(record.get("Total", "")),
                **summary,
                "statement_menustar_fees_allocated": "",
                "statement_source_file": filename,
            }
        )
    # Allocate MenuStar Fees across all orders by subtotal.
    fee_raw = summary.get("statement_menustar_fees", "")
    if fee_raw and rows:
        try:
            fee_total = Decimal(fee_raw)
            subtotal_sum = sum(Decimal(r.get("subtotal") or "0") for r in rows)
        except InvalidOperation:
            subtotal_sum = Decimal("0")
        if subtotal_sum:
            allocs = []
            for row in rows:
                try:
                    subtotal = Decimal(row.get("subtotal") or "0")
                except InvalidOperation:
                    subtotal = Decimal("0")
                share = (subtotal / subtotal_sum) * fee_total
                allocs.append(share.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            remainder = (fee_total - sum(allocs)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cent = Decimal("0.01")
            cents = int((abs(remainder) / cent).to_integral_value(rounding=ROUND_HALF_UP))
            step = cent if remainder > 0 else -cent
            for i in range(cents):
                allocs[i % len(allocs)] = (allocs[i % len(allocs)] + step).quantize(
                    cent, rounding=ROUND_HALF_UP
                )
            for row, alloc in zip(rows, allocs):
                row["statement_menustar_fees_allocated"] = str(alloc)
    return rows


def read_attachment_rows(payload: bytes, filename: str) -> List[Dict[str, str]]:
    lower = filename.lower()
    provider = normalize_provider(filename)
    if lower.endswith(".csv"):
        text = payload.decode(errors="ignore")
        return parse_csv_rows(text, provider, filename)
    if lower.endswith(".xlsx"):
        try:
            df = pd.read_excel(io.BytesIO(payload))
        except ImportError:
            print("Missing openpyxl; skipping xlsx attachment:", filename)
            return []
        text = df.to_csv(index=False)
        return parse_csv_rows(text, provider, filename)
    return []


def parse_mbox(mbox_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        for part in msg.walk():
            filename = part.get_filename()
            if not filename:
                continue
            if not filename.lower().endswith((".csv", ".xlsx")):
                continue
            payload = part.get_payload(decode=True) or b""
            rows.extend(read_attachment_rows(payload, filename))
    return rows


def upsert_raw(existing_path: str, new_rows: List[Dict[str, str]]) -> int:
    now = dt.datetime.now().isoformat()
    if os.path.exists(existing_path):
        existing_df = pd.read_csv(existing_path, dtype=str).fillna("")
        existing_rows = existing_df.to_dict("records")
    else:
        existing_rows = []

    existing_map = {
        f"{row.get('provider','')}|{row.get('order_datetime','')}|{row.get('subtotal','')}|{row.get('total','')}": row
        for row in existing_rows
    }
    updated = 0
    for row in new_rows:
        key = f"{row.get('provider','')}|{row.get('order_datetime','')}|{row.get('subtotal','')}|{row.get('total','')}"
        current = existing_map.get(key)
        if current is None:
            row["added_at"] = now
            existing_map[key] = row
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
    rows = parse_mbox(mbox_path)
    updated = upsert_raw(out_path, rows)
    print(f"Upserted {updated} billing row(s) into {out_path}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Menustar billings from mbox attachments.")
    parser.add_argument(
        "--mbox",
        default="TakeoutESBM/Mail/Billings-Menustar.mbox",
        help="Path to Billings-Menustar.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("menustar", "billings_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
