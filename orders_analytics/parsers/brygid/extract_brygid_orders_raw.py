#!/usr/bin/env python3
import argparse
import mailbox
import os
import re
import html as html_lib
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

import pandas as pd

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.normalize import normalize_money
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.providers import normalize_provider

RAW_COLUMNS = [
    "order_id",
    "provider",
    "restaurant_name",
    "order_datetime",
    "order_type",
    "payment_type",
    "customer_name",
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
    "source_file",
    "email_date",
    "added_at",
]


def _get_part_payload(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    payload = msg.get_payload(decode=True)
    if payload:
        return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return ""


def _strip_tags(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_field(html: str, label: str) -> str:
    match = re.search(
        rf"{re.escape(label)}\s*:?\s*(?:</?[^>]+>)*\s*([^<]+)",
        html,
        flags=re.IGNORECASE,
    )
    return _strip_tags(match.group(1)) if match else ""


def _extract_amount(label: str, html: str) -> str:
    match = re.search(rf"{re.escape(label)}\s*:?\s*(\$?[-\d,.]+)", html, flags=re.IGNORECASE)
    return normalize_money(match.group(1)) if match else ""


def parse_order(html: str) -> Dict[str, str]:
    order_id = ""
    match = re.search(r"Order#(\d+)", html, flags=re.IGNORECASE)
    if match:
        order_id = match.group(1)
    placed_on = _extract_field(html, "Placed On")
    customer_name = _extract_field(html, "Customer Name")
    phone = _extract_field(html, "Phone")
    email = _extract_field(html, "Email")

    restaurant_name = ""
    restaurant_match = re.search(r"<font[^>]*>\s*([^<]+)\s*</font>", html, flags=re.IGNORECASE)
    if restaurant_match:
        restaurant_name = _strip_tags(restaurant_match.group(1))

    order_type = OrderTypes.PICKUP
    header_match = re.search(r"Online Order\s*\(([^)]+)\)", html, flags=re.IGNORECASE)
    if header_match and "delivery" in header_match.group(1).lower():
        order_type = OrderTypes.DELIVERY

    payment_type = "credit"
    if re.search(r"Pay with Cash", html, flags=re.IGNORECASE):
        payment_type = "cash"

    street = _extract_field(html, "Street")
    city_state = _extract_field(html, "City/State")
    address = ", ".join([part for part in [street, city_state] if part])

    subtotal = _extract_amount("Subtotal", html)
    tax = _extract_amount("Taxes", html)
    tip = _extract_amount("Gratuity", html)
    delivery_fee = _extract_amount("Delivery Charge", html) or _extract_amount("Delivery Fee", html)
    total = _extract_amount("Order Total", html) or _extract_amount("Total", html)

    items = []
    item_count = 0
    item_rows = re.findall(
        r"<tr>\s*<td>\s*(\d+)\s*</td>.*?<td[^>]*>(.*?)</td>\s*<td[^>]*>\s*\$",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for qty, item_html in item_rows:
        cleaned = _strip_tags(item_html)
        if not cleaned:
            continue
        item_name = cleaned.split("\n", 1)[0].strip()
        if item_name:
            items.append(item_name)
            try:
                item_count += int(qty)
            except ValueError:
                item_count += 1

    return {
        "order_id": order_id,
        "provider": normalize_provider(restaurant_name),
        "restaurant_name": restaurant_name,
        "order_datetime": placed_on,
        "order_type": order_type,
        "payment_type": payment_type,
        "customer_name": customer_name,
        "phone": phone,
        "email": email,
        "address": address,
        "items": " | ".join(items),
        "item_count": str(item_count) if item_count else "",
        "subtotal": subtotal,
        "tax": tax,
        "tip": tip,
        "delivery_fee": delivery_fee,
        "total": total,
        "notes": "",
    }


def parse_mbox(mbox_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if not os.path.exists(mbox_path):
        return rows
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        payload = _get_part_payload(msg)
        if not payload:
            continue
        row = parse_order(payload)
        if not row.get("order_id"):
            continue
        email_date = ""
        if msg.get("Date"):
            try:
                email_date = parsedate_to_datetime(msg.get("Date")).isoformat()
            except Exception:
                email_date = ""
        row["source_file"] = os.path.basename(mbox_path)
        row["email_date"] = email_date
        rows.append(row)
    return rows


def run(mbox_path: str, out_path: str) -> int:
    rows = parse_mbox(mbox_path)
    if not rows:
        return 0
    now = pd.Timestamp.utcnow().isoformat()
    for row in rows:
        row["added_at"] = now
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pd.DataFrame(rows).reindex(columns=RAW_COLUMNS).to_csv(out_path, index=False)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Brygid orders from mbox.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Orders-Brygid.mbox"),
        help="Path to Orders-Brygid.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("brygid", "orders_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    count = run(args.mbox, args.out)
    print(f"Wrote {count} rows to {args.out}")


if __name__ == "__main__":
    main()
