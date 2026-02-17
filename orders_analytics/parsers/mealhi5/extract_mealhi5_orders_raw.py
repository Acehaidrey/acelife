#!/usr/bin/env python3
import argparse
import datetime as dt
import io
import mailbox
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

import pdfplumber

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.normalize import normalize_datetime, normalize_money
from orders_analytics.utils.providers import normalize_provider


ORDER_ID_RE = re.compile(r"Order (?:No|#)\s*:\s*([0-9]+)", re.IGNORECASE)
DATETIME_RE = re.compile(r"Date\s*&\s*Time:\s*([0-9:\- ]+)", re.IGNORECASE)
ORDER_TYPE_RE = re.compile(r"FOR\s*:\s*(.*?)\s*ORDER DATE-TIME", re.IGNORECASE)
CUSTOMER_RE = re.compile(r"Name\s*:\s*(.+)", re.IGNORECASE)
EMAIL_RE = re.compile(r"Email\s*:\s*([^\s]+)", re.IGNORECASE)
PHONE_RE = re.compile(r"Phone No\s*:\s*([0-9\-() ]+)", re.IGNORECASE)
RESTAURANT_PHONE_RE = re.compile(r"Restaurant Phone No\s*:\s*([0-9\-() ]+)", re.IGNORECASE)
ADDRESS_RE = re.compile(r"Address\s*:\s*(.+)", re.IGNORECASE)
RESTAURANT_RE = re.compile(r"CUSTOMER DETAILS TO\s*:\s*(.+)", re.IGNORECASE)
SUBTOTAL_RE = re.compile(r"Subtotal\s*:\s*\$?([0-9,.]+)", re.IGNORECASE)
DISCOUNT_RE = re.compile(r"Discount\s*:\s*\$?([0-9,.]+)", re.IGNORECASE)
TAX_RE = re.compile(r"Tax(?: and Fee)?\s*:\s*(?:\$?([0-9,.]+)|\n\s*\$?([0-9,.]+))", re.IGNORECASE)
DELIVERY_FEE_RE = re.compile(r"Delivery Fee\s*:\s*(?:N/A|\$?([0-9,.]+))", re.IGNORECASE)
TIP_RE = re.compile(r"Tip\s*:\s*\$?([0-9,.]+)", re.IGNORECASE)
TOTAL_RE = re.compile(r"Total\s*:\s*\$?([0-9,.]+)", re.IGNORECASE)


def extract_first_match(pattern: re.Pattern, text: str) -> str:
    match = pattern.search(text)
    if not match:
        return ""
    if match.lastindex and match.lastindex >= 2 and match.group(1) is None:
        group = match.group(2)
    else:
        group = match.group(1)
    return group.strip() if group else ""




BLOCK_STOP_PREFIXES = ("FOR :", "ITEMS", "Subtotal", "Total", "Discount", "Tax", "Delivery Fee", "Tip", "Order Time", "Confirmation code")


def extract_line_value(label: str, lines: list[str]) -> str:
    prefix = f"{label}:"
    for line in lines:
        if line.strip().startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def extract_address(lines: list[str]) -> str:
    address_idxs = [i for i, line in enumerate(lines) if line.strip().startswith("Address")]
    if not address_idxs:
        return ""
    idx = address_idxs[-1]
    line = lines[idx]
    value = line.split(":", 1)[1].strip()
    parts = []
    if value and value != ",":
        parts.append(value.strip(","))
    if idx + 1 < len(lines):
        nxt = lines[idx + 1].strip()
        if nxt and not nxt.startswith(BLOCK_STOP_PREFIXES):
            parts.append(nxt.strip(","))
    return ", ".join([p for p in parts if p])


def extract_total(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Total") and not stripped.startswith("Subtotal"):
            return stripped.split(":", 1)[1].strip()
    return ""
def extract_items_block(text: str) -> Tuple[str, str]:
    if "ITEMS" not in text:
        return "", ""
    lines = [line.strip() for line in text.splitlines()]
    start_idx = None
    for idx, line in enumerate(lines):
        if line.upper().startswith("ITEMS"):
            start_idx = idx + 1
            break
    if start_idx is None:
        return "", ""
    item_lines: List[str] = []
    for line in lines[start_idx:]:
        if line.lower().startswith("subtotal"):
            break
        if line:
            item_lines.append(line)
    items = []
    item_count = 0
    for line in item_lines:
        match = re.search(r"(.+?)\s+(\d+)\s+\$[0-9,.]+$", line)
        if match:
            name = match.group(1).strip()
            qty = int(match.group(2))
            items.append(name)
            item_count += qty
        else:
            items.append(line)
    return " | ".join(items), str(item_count) if item_count else ""


def parse_pdf(payload: bytes) -> Dict[str, str]:
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    order_id = extract_first_match(ORDER_ID_RE, text)
    order_datetime = extract_first_match(DATETIME_RE, text)
    order_type_raw = extract_first_match(ORDER_TYPE_RE, text)
    order_type = "pickup"
    if "delivery" in order_type_raw.lower():
        order_type = "delivery"

    restaurant = extract_first_match(RESTAURANT_RE, text)
    customer_name = extract_first_match(CUSTOMER_RE, text)
    email = extract_first_match(EMAIL_RE, text)
    phone = extract_first_match(PHONE_RE, text)
    rest_phone = extract_first_match(RESTAURANT_PHONE_RE, text)
    if phone and rest_phone and phone == rest_phone:
        phone = ""
        for line in lines:
            if line.lower().startswith("phone no") and "restaurant" not in line.lower():
                phone = line.split(":", 1)[1].strip()
                break
    rest_phone = extract_first_match(RESTAURANT_PHONE_RE, text)
    if phone and rest_phone and phone == rest_phone:
        phone = ""
        for line in lines:
            if line.lower().startswith("phone no") and "restaurant" not in line.lower():
                phone = line.split(":", 1)[1].strip()
                break
    address = extract_address(lines)

    subtotal = normalize_money(extract_first_match(SUBTOTAL_RE, text))
    discount = normalize_money(extract_first_match(DISCOUNT_RE, text))
    tax_raw = extract_first_match(TAX_RE, text)
    tax = normalize_money(tax_raw)
    delivery_fee = normalize_money(extract_first_match(DELIVERY_FEE_RE, text))
    tip = normalize_money(extract_first_match(TIP_RE, text))
    total = normalize_money(extract_total(lines))

    items, item_count = extract_items_block(text)

    return {
        "order_id": order_id,
        "order_datetime": normalize_datetime(order_datetime, allow_iso=False) if order_datetime else "",
        "order_type": order_type,
        "order_type_raw": order_type_raw,
        "provider": normalize_provider(restaurant),
        "restaurant_name": restaurant,
        "customer_name": customer_name,
        "email": email,
        "phone": phone,
        "address": address,
        "subtotal": subtotal,
        "discount": discount,
        "tax": tax,
        "delivery_fee": delivery_fee,
        "tip": tip,
        "total": total,
        "items": items,
        "item_count": item_count,
    }


def parse_mbox(mbox_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        for part in msg.walk():
            if part.get_content_type() == "application/pdf":
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                row = parse_pdf(payload)
                if not row.get("order_id"):
                    continue
                row["source_file"] = os.path.basename(mbox_path)
                rows.append(row)
    return rows


def run(mbox_path: str, out_path: str) -> int:
    rows = parse_mbox(mbox_path)
    if not rows:
        return 0
    now = dt.datetime.now().isoformat()
    for row in rows:
        row["added_at"] = now
    import pandas as pd

    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract MealHi5 orders from mbox PDFs.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Orders-mealhi5.mbox"),
        help="Path to Orders-mealhi5.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("mealhi5", "orders_raw.csv"),
        help="Output orders raw CSV path.",
    )
    args = parser.parse_args()

    Path(os.path.dirname(args.out)).mkdir(parents=True, exist_ok=True)
    count = run(args.mbox, args.out)
    print(f"Wrote {count} rows -> {args.out}")


if __name__ == "__main__":
    main()
