#!/usr/bin/env python3
import argparse
import datetime as dt
import mailbox
import os
import re
from email.utils import parsedate_to_datetime
from typing import Dict, List

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

LABELS = {
    "restaurant name",
    "restaurant phone number",
    "restaurant address1",
    "restaurant address2",
    "city",
    "state",
    "zip",
    "time of order",
    "date of order",
    "estimated time of delivery",
    "requested pickup time",
    "customer name",
    "customer phone number",
    "customer address",
    "order type",
    "delivery instructions",
    "single-use disposables",
    "sub-total",
    "item total",
    "taxes",
    "delivery fee",
    "delivery fee",
    "support local fee",
    "tip",
    "total",
    "*grand total",
}


def parse_amount_line(line: str) -> str:
    match = re.search(r"(-?\$?\d[\d,]*\.\d{2})", line)
    return normalize_money(match.group(1)) if match else ""


def normalize_order_type(raw: str) -> str:
    text = str(raw or "").strip().lower()
    if "pickup" in text:
        return OrderTypes.PICKUP
    if "deliver" in text or "uber" in text:
        return OrderTypes.DELIVERY
    return ""


def parse_order_datetime(date_text: str, time_text: str) -> str:
    if not date_text or not time_text:
        return ""
    try:
        return dt.datetime.strptime(
            f"{date_text} {time_text}", "%b %d, %Y %I:%M %p"
        ).isoformat()
    except ValueError:
        return ""


def extract_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                return payload.decode(errors="ignore")
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(errors="ignore")


def parse_order(text: str, subject: str, email_date: str) -> Dict[str, str]:
    lines = [line.rstrip() for line in text.splitlines()]
    order_id = ""
    for line in lines:
        match = re.search(r"Order\s*#(\d+)", line)
        if match:
            order_id = match.group(1)
            break
    if not order_id:
        match = re.search(r"#(\d+)", subject or "")
        if match:
            order_id = match.group(1)

    restaurant_name = ""
    customer_name = ""
    customer_phone = ""
    order_type_raw = ""
    date_of_order = ""
    time_of_order = ""
    address = ""
    notes: List[str] = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.lower().startswith("restaurant name:"):
            restaurant_name = line.split(":", 1)[1].strip()
        elif line.lower().startswith("customer name:"):
            customer_name = line.split(":", 1)[1].strip()
        elif line.lower().startswith("customer phone number:"):
            customer_phone = line.split(":", 1)[1].strip()
        elif line.lower().startswith("order type:"):
            order_type_raw = line.split(":", 1)[1].strip()
        elif line.lower().startswith("date of order:"):
            date_of_order = line.split(":", 1)[1].strip()
        elif line.lower().startswith("time of order:"):
            time_of_order = line.split(":", 1)[1].strip()
        elif line.lower().startswith("customer address:"):
            address_lines = []
            j = i + 1
            while j < len(lines):
                candidate = lines[j].strip()
                if not candidate:
                    break
                if ":" in candidate:
                    label = candidate.split(":", 1)[0].strip().lower()
                    if label in LABELS:
                        break
                address_lines.append(candidate)
                j += 1
            address = ", ".join(address_lines)
        elif line.lower().startswith("support local fee:"):
            value = parse_amount_line(line)
            if value:
                notes.append(f"support_local_fee={value}")
        i += 1

    order_type = normalize_order_type(order_type_raw)
    if order_type_raw and order_type != order_type_raw.lower():
        notes.append(f"order_type_raw={order_type_raw}")

    order_datetime = parse_order_datetime(date_of_order, time_of_order)

    items = []
    item_count = 0
    in_items = False
    for line in lines:
        if line.strip().lower().startswith("order details"):
            in_items = True
            continue
        if in_items:
            if line.strip().lower().startswith(("sub-total:", "item total:", "taxes:", "total:", "*grand total")):
                in_items = False
                continue
            if line.strip():
                items.append(line.strip())
                if re.match(r"^\d+\s+", line.strip()):
                    item_count += 1

    subtotal = ""
    tax = ""
    tip = ""
    delivery_fee = ""
    total = ""
    for line in lines:
        lower = line.strip().lower()
        if lower.startswith("sub-total:") or lower.startswith("item total:"):
            subtotal = parse_amount_line(line)
        elif lower.startswith("taxes:"):
            tax = parse_amount_line(line)
        elif lower.startswith("tip:"):
            tip = parse_amount_line(line)
        elif lower.startswith("delivery fee:") or lower.startswith("delivery fee"):
            delivery_fee = parse_amount_line(line)
        elif lower.startswith("total:") or lower.startswith("*grand total"):
            total = parse_amount_line(line)

    provider = normalize_provider(restaurant_name) if restaurant_name else ""

    return {
        "order_id": order_id,
        "provider": provider,
        "restaurant_name": restaurant_name,
        "order_datetime": order_datetime,
        "order_type": order_type,
        "payment_type": "",
        "customer_name": customer_name,
        "phone": customer_phone,
        "email": "",
        "address": address,
        "items": " | ".join(items),
        "item_count": str(item_count) if item_count else "",
        "subtotal": subtotal,
        "tax": tax,
        "tip": tip,
        "delivery_fee": delivery_fee,
        "total": total,
        "notes": " | ".join(notes),
        "source_file": "",
        "email_date": email_date,
    }


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def load_customer_emails(paths: List[str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for path in paths:
        if not path or not os.path.exists(path):
            continue
        df = pd.read_excel(path, dtype=str).fillna("")
        for _, row in df.iterrows():
            name = normalize_name(row.get("Customer Name", ""))
            email = str(row.get("Email", "")).strip()
            if name and email and name not in mapping:
                mapping[name] = email
    return mapping


def parse_mbox(mbox_path: str, customer_email_map: Dict[str, str]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        subject = msg.get("Subject", "") or ""
        email_date = ""
        if msg.get("Date"):
            try:
                email_date = parsedate_to_datetime(msg.get("Date")).isoformat()
            except (TypeError, ValueError):
                email_date = ""
        text = extract_text(msg)
        if "Order #" not in text and "#" not in subject:
            continue
        row = parse_order(text, subject, email_date)
        if row.get("customer_name") and not row.get("email"):
            key = normalize_name(row.get("customer_name", ""))
            row["email"] = customer_email_map.get(key, "")
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


def run(mbox_path: str, out_path: str, customer_files: List[str]) -> int:
    customer_email_map = load_customer_emails(customer_files)
    rows = parse_mbox(mbox_path, customer_email_map)
    updated = upsert_raw(out_path, rows)
    print(f"Upserted {updated} ChowNow order row(s) into {out_path}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract ChowNow orders raw CSV from mbox.")
    parser.add_argument(
        "--orders-mbox",
        default=takeout_path("Mail", "Orders-ChowNow.mbox"),
        help="ChowNow orders mbox path.",
    )
    parser.add_argument(
        "--customer-files",
        nargs="*",
        default=[
            "Takeout/Chownow/CustomerOrders_lastran_06Feb26.xls",
            "Takeout/Chownow/CustomerOrders_lastran_06Feb26 (1).xls",
        ],
        help="Customer email XLS files (ChowNow exports).",
    )
    parser.add_argument(
        "--out",
        default=raw_path("chownow", "orders_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_mbox, args.out, args.customer_files)


if __name__ == "__main__":
    main()
