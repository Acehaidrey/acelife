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
from orders_analytics.utils.google_sheets import download_sheet_entry
from orders_analytics.utils.google_sheets_registry import SHEETS
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
    "promotions",
    "customer_paid",
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


def parse_decimal(value: str) -> float:
    text = str(value or "").strip().replace("$", "").replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


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


def parse_manual_datetime(placed_text: str, order_date: str) -> str:
    value = str(placed_text or "").strip()
    if value:
        for fmt in ("%I:%M %p, %m/%d/%Y", "%I:%M %p, %m/%d/%y"):
            try:
                return dt.datetime.strptime(value, fmt).isoformat()
            except ValueError:
                continue
    date_only = str(order_date or "").strip()
    if date_only:
        for fmt in ("%m/%d/%Y", "%m/%d/%y"):
            try:
                return dt.datetime.strptime(date_only, fmt).date().isoformat()
            except ValueError:
                continue
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
                cleaned = re.sub(r"^-{2,}\s*", "", line.strip())
                if cleaned:
                    items.append(cleaned)
                if re.match(r"^\d+\s+", cleaned):
                    item_count += 1

    subtotal = ""
    tax = ""
    tip = ""
    delivery_fee = ""
    promotions = ""
    customer_paid = ""
    total = ""
    grand_total = ""
    support_local_fee = ""
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
        elif lower.startswith("promotions:"):
            promotions = parse_amount_line(line)
        elif lower.startswith("customer paid:"):
            customer_paid = parse_amount_line(line)
        elif lower.startswith("support local fee:"):
            support_local_fee = parse_amount_line(line)
            if support_local_fee:
                note = f"support_local_fee={support_local_fee}"
                if note not in notes:
                    notes.append(note)
        elif lower.startswith("grand total:") or lower.startswith("*grand total"):
            grand_total = parse_amount_line(line)
        elif lower.startswith("total:"):
            total = parse_amount_line(line)
        elif "credit has been applied" in lower and "(" in line and ")" in line:
            credit_match = re.search(r"\(([-$\d.,]+)\)", line)
            if credit_match:
                amount = normalize_money(credit_match.group(1))
                if amount and not str(amount).startswith("-"):
                    amount = f"-{amount}"
                promotions = amount
    if grand_total:
        total = grand_total
    elif promotions and not customer_paid:
        customer_paid = total
        total = normalize_money(
            f"{(parse_decimal(subtotal) + parse_decimal(tax) + parse_decimal(tip) + parse_decimal(delivery_fee) + parse_decimal(support_local_fee)):.2f}"
        )

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
        "promotions": promotions,
        "customer_paid": customer_paid,
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


def parse_manual_missing_orders(path: str) -> List[Dict[str, str]]:
    if not path or not os.path.exists(path):
        return []
    df = pd.read_csv(path, dtype=str).fillna("")
    rows: List[Dict[str, str]] = []
    for _, row in df.iterrows():
        order_id = str(row.get("Order ID", "")).strip()
        if not order_id:
            continue
        service = str(row.get("Service", "")).strip()
        order_type = normalize_order_type(service)
        notes: List[str] = ["source=manual_missing_orders", "manual_missing_order"]
        if service and order_type and order_type != service.lower():
            notes.append(f"order_type_raw={service}")
        status = str(row.get("Status", "")).strip()
        if status:
            notes.append(f"status={status}")
        support_local_fee = normalize_money(row.get("Support Local Fee", ""))
        if support_local_fee:
            notes.append(f"support_local_fee={support_local_fee}")

        courier_tip = parse_decimal(row.get("Courier Tip", ""))
        restaurant_tip = parse_decimal(row.get("Restaurant Tip", ""))
        tip_val = courier_tip + restaurant_tip
        tip = normalize_money(f"{tip_val:.2f}") if tip_val else ""

        payment_raw = str(row.get("Payment Type", "")).strip().lower()
        payment_type = "cash" if "cash" in payment_raw else ("credit" if payment_raw else "")

        rows.append(
            {
                "order_id": order_id,
                "provider": normalize_provider(row.get("Store", "")) if row.get("Store", "") else "",
                "restaurant_name": row.get("Store", ""),
                "order_datetime": parse_manual_datetime(row.get("Placed", ""), row.get("Order Date", "")),
                "order_type": order_type,
                "payment_type": payment_type,
                "customer_name": row.get("Customer Name", ""),
                "phone": row.get("Phone Number", ""),
                "email": row.get("Email", ""),
                "address": row.get("Address", ""),
                "items": "",
                "item_count": "",
                "subtotal": normalize_money(row.get("Subtotal", "")),
                "tax": normalize_money(row.get("Taxes", "")),
                "tip": tip,
                "delivery_fee": normalize_money(row.get("Delivery Fee", "")),
                "promotions": "",
                "customer_paid": "",
                "total": normalize_money(row.get("Total", "")),
                "notes": " | ".join(notes),
                "source_file": os.path.basename(path),
                "email_date": "",
            }
        )
    return rows


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
    manual_sheet = SHEETS.get("chownow_manual_missing_orders")
    manual_path = (
        manual_sheet["out"]
        if manual_sheet
        else raw_path("chownow", "chownow_manual_missing_orders.csv")
    )
    if manual_sheet:
        try:
            download_sheet_entry(manual_sheet)
        except Exception:
            if not os.path.exists(manual_path):
                raise
    rows.extend(parse_manual_missing_orders(manual_path))
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
