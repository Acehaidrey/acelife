#!/usr/bin/env python3
import argparse
import datetime as dt
import mailbox
import os
import re
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional, Set

import pandas as pd

from orders_analytics.parsers.deliverycom.parse_deliverycom_orders import html_to_lines
from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.normalize import normalize_datetime, normalize_money
from orders_analytics.utils.order_types import OrderTypes

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

ORDER_ID_RE = re.compile(r"\b[A-Z]{2,4}-\d+\b")


def extract_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(errors="ignore")
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(errors="ignore")
    payload = msg.get_payload(decode=True)
    if payload:
        return payload.decode(errors="ignore")
    return ""


def parse_order_id(lines: List[str]) -> str:
    for line in lines:
        match = ORDER_ID_RE.search(line)
        if match:
            return match.group(0)
    return ""


def parse_order_datetime(lines: List[str], msg_date: str) -> str:
    year = None
    try:
        year = parsedate_to_datetime(msg_date).year
    except Exception:
        year = dt.datetime.now().year

    for idx, line in enumerate(lines):
        if line.lower().startswith("pickup date & time"):
            date_line = lines[idx + 1] if idx + 1 < len(lines) else ""
            time_line = lines[idx + 2] if idx + 2 < len(lines) else ""
            match = re.search(
                r"(\w+),\s*([A-Za-z]{3,9})\s+(\d{1,2})",
                date_line,
                re.IGNORECASE,
            )
            if match and time_line:
                _, month, day = match.groups()
                time_clean = time_line.replace(" ", "")
                date_text = f"{month} {day} {year} {time_clean}"
                return normalize_datetime(
                    date_text,
                    formats=("%b %d %Y %I:%M%p", "%B %d %Y %I:%M%p"),
                    allow_iso=False,
                )
        if "@" in line and any(month in line for month in ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")):
            match = re.search(
                r"([A-Za-z]{3,9})\s+([A-Za-z]{3})\s+(\d{1,2})\s+@\s*(\d{1,2}:\d{2}\s*(?:AM|PM))",
                line,
                re.IGNORECASE,
            )
            if match:
                _, month, day, time = match.groups()
                date_text = f"{month} {day} {year} {time.replace(' ', '')}"
                return normalize_datetime(
                    date_text,
                    formats=("%b %d %Y %I:%M%p", "%B %d %Y %I:%M%p"),
                    allow_iso=False,
                )
    return ""


def parse_counts(lines: List[str]) -> str:
    for idx, line in enumerate(lines):
        if "Number of items" in line:
            match = re.search(r"Number of items\s*[:\*]?\s*(\d+)", line)
            if match:
                return match.group(1)
            if idx + 1 < len(lines):
                next_line = lines[idx + 1].strip()
                if next_line.isdigit():
                    return next_line
    return ""


def parse_money_line(lines: List[str], label: str) -> str:
    for idx, line in enumerate(lines):
        if label.lower() not in line.lower():
            continue
        money = re.findall(r"\(?-?\$?\d[\d,]*\.\d{2}\)?", line)
        if money:
            return normalize_money(money[-1])
        if idx + 1 < len(lines):
            next_line = lines[idx + 1]
            money = re.findall(r"\(?-?\$?\d[\d,]*\.\d{2}\)?", next_line)
            if money:
                return normalize_money(money[-1])
    return ""


def parse_items(lines: List[str]) -> str:
    has_qty = any(line.strip().lower().startswith("qty") for line in lines)
    has_item = any(line.strip().lower().startswith("item") for line in lines)
    if not has_qty or not has_item:
        return ""
    start = None
    for idx, line in enumerate(lines):
        if line.strip().lower().startswith("qty"):
            start = idx + 1
            break
    if start is None:
        return ""
    items: List[str] = []
    seen_any = False
    idx = start
    while idx < len(lines):
        line = lines[idx].strip()
        lower = line.lower()
        if lower.startswith("subtotal"):
            if seen_any:
                break
            idx += 1
            continue
        if lower.startswith("notes") or line.startswith("•"):
            idx += 1
            continue
        if line.isdigit():
            qty = line
            name = ""
            price = ""
            lookahead = idx + 1
            while lookahead < len(lines):
                candidate = lines[lookahead].strip()
                if not candidate:
                    lookahead += 1
                    continue
                if candidate.lower().startswith("subtotal"):
                    break
                if not name:
                    name = candidate
                    lookahead += 1
                    continue
                money = re.findall(r"\(?-?\$?\d[\d,]*\.\d{2}\)?", candidate)
                if money:
                    price = money[-1]
                    break
                lookahead += 1
            if name:
                items.append(name)
                seen_any = True
            idx = lookahead + 1
            continue
        idx += 1
    return "; ".join(items)


def parse_order(lines: List[str], msg_date: str, subject: str) -> Optional[Dict[str, str]]:
    if not any("Order Summary" in line for line in lines):
        return None
    order_id = parse_order_id(lines)
    if not order_id:
        match = ORDER_ID_RE.search(subject or "")
        if match:
            order_id = match.group(0)
    if not order_id:
        return None
    order_type = OrderTypes.PICKUP if any("Order Pickup time" in line for line in lines) else ""
    if any("Order Delivery time" in line for line in lines):
        order_type = OrderTypes.DELIVERY

    order_datetime = parse_order_datetime(lines, msg_date)
    subtotal = parse_money_line(lines, "Subtotal")
    tax = parse_money_line(lines, "Tax")
    total = parse_money_line(lines, "Total")
    item_count = parse_counts(lines)
    items = parse_items(lines)

    notes = []
    if is_canceled(lines, subject):
        notes.append("status=canceled")

    return {
        "order_id": order_id,
        "provider": "AROMA",
        "restaurant_name": "Aroma Pizza and Pasta",
        "order_datetime": order_datetime,
        "order_type": order_type,
        "customer_name": "",
        "company_name": "",
        "phone": "",
        "email": "",
        "address": "",
        "items": items,
        "item_count": item_count,
        "subtotal": subtotal,
        "tax": tax,
        "tip": "",
        "delivery_fee": "",
        "total": total,
        "notes": " | ".join(notes),
    }


def decode_subject(subject: str) -> str:
    if not subject:
        return ""
    decoded = []
    for value, encoding in decode_header(subject):
        if isinstance(value, bytes):
            decoded.append(value.decode(encoding or "utf-8", errors="ignore"))
        else:
            decoded.append(value)
    return "".join(decoded)


def is_canceled(lines: List[str], subject: str) -> bool:
    subj = (subject or "").lower()
    if "cancelled order" in subj or "canceled order" in subj:
        return True
    for line in lines:
        lower = line.strip().lower()
        if lower in ("order canceled", "order cancelled"):
            return True
        if "has been canceled" in lower or "has been cancelled" in lower:
            return True
        if "confirming this cancellation" in lower:
            return True
    return False

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
            if not new_val:
                continue
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
    canceled_ids: Set[str] = set()
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        text = extract_text(msg)
        if not text:
            continue
        lines = html_to_lines(text)
        subject = decode_subject(msg.get("Subject", ""))
        order_id = parse_order_id(lines)
        if order_id and is_canceled(lines, subject):
            canceled_ids.add(order_id)
        parsed = parse_order(lines, msg.get("Date", ""), subject)
        if parsed:
            rows.append(parsed)
    if canceled_ids:
        for row in rows:
            if row.get("order_id") in canceled_ids:
                notes = row.get("notes", "")
                if "status=canceled" not in notes:
                    row["notes"] = " | ".join([notes, "status=canceled"]).strip(" |")
    updated = upsert_raw(out_path, rows)
    print(f"Upserted {updated} order row(s) into {out_path}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Foodee orders from mbox.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Orders-Foodee.mbox"),
        help="Path to Orders-Foodee.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("foodee", "orders_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
