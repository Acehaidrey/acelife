#!/usr/bin/env python3
import argparse
import datetime as dt
import io
import mailbox
import os
import re
from email.utils import parsedate_to_datetime
from typing import Dict, List

import pandas as pd
import pdfplumber

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.normalize import normalize_money

RAW_COLUMNS = [
    "order_id",
    "order_date",
    "order_time",
    "headcount",
    "pre_tax",
    "tip",
    "service_fee",
    "processing_fee",
    "order_total",
    "adjustments_total",
    "adjustments_delivery_fee",
    "adjustments_notes",
    "statement_period_start",
    "statement_period_end",
    "statement_date",
    "restaurant_name",
    "source_file",
    "email_date",
    "added_at",
]


def extract_pdf_text(payload: bytes) -> str:
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def statement_period_range(text: str) -> tuple[str, str]:
    patterns = [
        r"(?:Statement\s+)?Period:\s*(\d{1,2}/\d{1,2}/\d{2,4})\s*-\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        r"(?:Statement\s+)?Period\s+(\d{1,2}/\d{1,2}/\d{2,4})\s*-\s*(\d{1,2}/\d{1,2}/\d{2,4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1), match.group(2)
    match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})\s*-\s*(\d{1,2}/\d{1,2}/\d{2,4})", text)
    if match:
        return match.group(1), match.group(2)
    return "", ""


def statement_date(text: str) -> str:
    match = re.search(r"Statement Date:\s*(\d{1,2}/\d{1,2}/\d{2,4})", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def restaurant_name(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:5]:
        if "period:" in line.lower() or "statement" in line.lower():
            continue
        return line
    return ""


def parse_order_lines(text: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    period_start, period_end = statement_period_range(text)
    stmt_date = statement_date(text)
    # Billing tables omit the year in order dates; infer from statement period when available.
    year = period_end.split("/")[-1] if period_end else ""
    rest = restaurant_name(text)
    in_orders = False
    for line in lines:
        if "Order Date" in line and "Order ID" in line:
            in_orders = True
            continue
        if "Adjustments" in line:
            in_orders = False
        if not in_orders:
            continue
        if not re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),", line):
            continue
        tokens = line.replace("*", "").split()
        money = [t for t in tokens if re.match(r"^-?\$?\d[\d,]*\.\d{2}$", t)]
        if len(money) < 5:
            continue
        pre_tax, tip, service_fee, processing_fee, order_total = [normalize_money(m) for m in money[-5:]]
        first_money = money[-5]
        first_money_idx = tokens.index(first_money)
        headcount = tokens[first_money_idx - 1] if first_money_idx - 1 >= 0 else ""
        time_token = ""
        order_id = ""
        date_token = ""
        if len(tokens) >= 3:
            date_token = f"{tokens[0]} {tokens[1]}".replace(",", "")
            order_id = re.sub(r"\\D", "", tokens[2])
        for token in tokens:
            if ":" in token:
                time_token = token
                break
        rows.append(
            {
                "order_id": order_id,
                "order_date": f"{date_token} {year}".strip(),
                "order_time": time_token,
                "headcount": headcount,
                "pre_tax": pre_tax,
                "tip": tip,
                "service_fee": service_fee,
                "processing_fee": processing_fee,
                "order_total": order_total,
                "adjustments_total": "",
                "restaurant_name": rest,
                "statement_period_start": period_start,
                "statement_period_end": period_end,
                "statement_date": stmt_date,
            }
        )
    return rows


def parse_adjustments(text: str) -> Dict[str, Dict[str, float]]:
    totals: Dict[str, float] = {}
    delivery_fees: Dict[str, float] = {}
    notes: Dict[str, List[str]] = {}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    in_adj = False
    for line in lines:
        if line.startswith("Adjustments"):
            in_adj = True
            continue
        if in_adj and line.startswith("Statement Total"):
            in_adj = False
        if not in_adj:
            continue
        if not re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),", line):
            continue
        tokens = line.split()
        money = [t for t in tokens if re.match(r"^-?\$?\d[\d,]*\.\d{2}$", t)]
        if len(money) < 3:
            continue
        total = normalize_money(money[-1])
        try:
            total_val = float(total)
        except ValueError:
            total_val = 0.0
        first_money_idx = None
        for idx, token in enumerate(tokens):
            if token in money:
                first_money_idx = idx
                break
        order_id = ""
        if len(tokens) >= 3:
            order_id = re.sub(r"\\D", "", tokens[2])
        description = ""
        if first_money_idx is not None and first_money_idx > 3:
            description = " ".join(tokens[3:first_money_idx])
        if order_id and "delivery" in description.lower() and total_val > 0:
            delivery_fees[order_id] = delivery_fees.get(order_id, 0.0) + total_val
        elif order_id:
            totals[order_id] = totals.get(order_id, 0.0) + total_val
            if description:
                notes.setdefault(order_id, []).append(f"{description}: {total_val:.2f}")
    return {
        "adjustments_total": totals,
        "adjustments_delivery_fee": delivery_fees,
        "adjustments_notes": notes,
    }


def parse_pdf(payload: bytes) -> List[Dict[str, str]]:
    text = extract_pdf_text(payload)
    rows = parse_order_lines(text)
    adjustments = parse_adjustments(text)
    for row in rows:
        order_id = row.get("order_id", "")
        if order_id in adjustments["adjustments_total"]:
            row["adjustments_total"] = str(adjustments["adjustments_total"][order_id])
        if order_id in adjustments["adjustments_delivery_fee"]:
            row["adjustments_delivery_fee"] = str(adjustments["adjustments_delivery_fee"][order_id])
        if order_id in adjustments["adjustments_notes"]:
            row["adjustments_notes"] = "; ".join(adjustments["adjustments_notes"][order_id])
    return rows


def parse_mbox(mbox_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        email_date = ""
        if msg.get("Date"):
            try:
                email_date = parsedate_to_datetime(msg.get("Date")).isoformat()
            except (TypeError, ValueError):
                email_date = ""
        for part in msg.walk():
            if part.get_content_type() == "application/pdf":
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                filename = part.get_filename() or ""
                parsed_rows = parse_pdf(payload)
                for row in parsed_rows:
                    row["source_file"] = filename
                    row["email_date"] = email_date
                rows.extend(parsed_rows)
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


def run(mbox_path: str, out_path: str) -> int:
    rows = parse_mbox(mbox_path)
    updated = upsert_raw(out_path, rows)
    print(f"Upserted {updated} billing row(s) into {out_path}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Cater2Me billing PDFs to raw CSV.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Billings-Cater2Me.mbox"),
        help="Path to Billings-Cater2Me.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("cater2me", "billings_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
