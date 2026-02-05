#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import os
import re
from typing import Dict, List, Tuple

import pandas as pd

from orders_analytics.utils.constants import raw_path
from orders_analytics.utils.normalize import normalize_money
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
    "subtotal",
    "upcharges",
    "tax",
    "delivery_fee",
    "tip",
    "total",
    "customer_fees",
    "restaurant_fees",
    "delivery_service",
    "tax_withholdings",
    "tax_payout",
    "total_payout",
    "adjustments",
    "notes",
    "source_file",
    "added_at",
]


def normalize_name(value: str) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text).lower()


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits


def parse_date(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%m/%d/%y %I:%M%p", "%m/%d/%Y %I:%M%p", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return text


def make_order_id(parts: List[str]) -> str:
    key = "|".join([str(p or "").strip().lower() for p in parts])
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def load_customer_email_map(path: str) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    if not path or not os.path.exists(path):
        return {}, {}, {}
    df = pd.read_csv(path, dtype=str).fillna("")
    by_phone = {}
    by_name = {}
    phone_by_name = {}
    for _, row in df.iterrows():
        name = normalize_name(f"{row.get('First Name','')} {row.get('Last Name','')}")
        phone = normalize_phone(row.get("Phone", ""))
        email = str(row.get("Email", "")).strip()
        if phone and email:
            by_phone[phone] = email
        if name and email:
            by_name[name] = email
        if name and phone:
            phone_by_name[name] = phone
    return by_phone, by_name, phone_by_name


def load_customer_address_map(path: str) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    if not path or not os.path.exists(path):
        return {}, {}, {}
    df = pd.read_csv(path, dtype=str).fillna("")
    by_phone = {}
    by_name = {}
    phone_by_name = {}
    for _, row in df.iterrows():
        name = normalize_name(f"{row.get('First Name','')} {row.get('Last Name','')}")
        phone = normalize_phone(row.get("Phone", ""))
        parts = [
            row.get("Address1", ""),
            row.get("Address2", ""),
            row.get("City", ""),
            row.get("State", ""),
            row.get("ZipCode", ""),
        ]
        address = ", ".join([str(p).strip() for p in parts if str(p).strip()])
        if phone and address:
            by_phone[phone] = address
        if name and address:
            by_name[name] = address
        if name and phone:
            phone_by_name[name] = phone
    return by_phone, by_name, phone_by_name


def load_refunds(refund_paths: List[str]) -> Dict[Tuple[str, str, str], float]:
    refunds: Dict[Tuple[str, str, str], float] = {}
    for path in refund_paths:
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path, dtype=str).fillna("")
        for _, row in df.iterrows():
            date_str = str(row.get("Date", "")).strip()
            location = str(row.get("Location", "")).strip()
            customer_name = str(row.get("Customer Name", "")).strip()
            refund_raw = row.get("Refund", "")
            if not date_str or not location or not customer_name:
                continue
            date_key = parse_date(date_str)[:10]
            if not date_key:
                continue
            try:
                refund_val = float(str(refund_raw).replace("$", "").replace(",", ""))
            except ValueError:
                continue
            key = (date_key, location, customer_name)
            refunds[key] = refunds.get(key, 0.0) + refund_val
    return refunds


def parse_orders_csv(path: str, payment_type: str, refunds: Dict[Tuple[str, str, str], float]) -> List[Dict[str, str]]:
    df = pd.read_csv(path, dtype=str).fillna("")
    rows: List[Dict[str, str]] = []
    for _, row in df.iterrows():
        date_raw = str(row.get("Date", "")).strip()
        location = str(row.get("Location", "")).strip()
        customer_name = str(row.get("Customer Name", "")).strip()
        if not date_raw or not location or not customer_name:
            continue
        order_datetime = parse_date(date_raw)
        order_date_key = order_datetime[:10] if order_datetime else ""
        provider = normalize_provider(location)
        restaurant_name = location
        delivery_fee = normalize_money(row.get("Customer Carryout or Delivery Charge", ""))
        order_type = "delivery" if delivery_fee and delivery_fee not in ("0", "0.00") else "pickup"
        subtotal = normalize_money(row.get("Subtotal", ""))
        upcharges = normalize_money(row.get("Upcharges", ""))
        tax = normalize_money(row.get("Tax", ""))
        tip = normalize_money(row.get("Tip", ""))
        total = normalize_money(row.get("Total", ""))
        customer_fees = normalize_money(row.get("Customer Fees", ""))
        restaurant_fees = normalize_money(row.get("Restaurant Fees", ""))
        delivery_service = normalize_money(row.get("Delivery Service", ""))
        tax_withholdings = normalize_money(row.get("Tax Withholdings", ""))
        tax_payout = normalize_money(row.get("Tax Payout", ""))
        total_payout = normalize_money(row.get("Total Payout", ""))
        adjustment_val = refunds.get((order_date_key, location, customer_name), 0.0)
        adjustments = ""
        notes = ""
        if adjustment_val:
            adjustments = normalize_money(adjustment_val)
            notes = f"refund={adjustments}"
        order_id = make_order_id(
            [date_raw, location, customer_name, subtotal, tax, delivery_fee, tip, total, payment_type]
        )
        rows.append(
            {
                "order_id": order_id,
                "provider": provider,
                "restaurant_name": restaurant_name,
                "order_datetime": order_datetime,
                "order_type": order_type,
                "payment_type": payment_type,
                "customer_name": customer_name,
                "phone": "",
                "email": "",
                "address": "",
                "subtotal": subtotal,
                "upcharges": upcharges,
                "tax": tax,
                "delivery_fee": delivery_fee,
                "tip": tip,
                "total": total,
                "customer_fees": customer_fees,
                "restaurant_fees": restaurant_fees,
                "delivery_service": delivery_service,
                "tax_withholdings": tax_withholdings,
                "tax_payout": tax_payout,
                "total_payout": total_payout,
                "adjustments": adjustments,
                "notes": notes,
                "source_file": os.path.basename(path),
            }
        )
    return rows


def collect_csv_files(root: str) -> Tuple[List[str], List[str], List[str]]:
    paid_online = []
    paid_in_store = []
    refunds = []
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if not filename.lower().endswith(".csv"):
                continue
            path = os.path.join(dirpath, filename)
            lower = filename.lower()
            if "refunds" in lower:
                refunds.append(path)
            elif "paid online" in lower:
                paid_online.append(path)
            elif "paid in-store" in lower or "paid instore" in lower:
                paid_in_store.append(path)
    return paid_online, paid_in_store, refunds


def attach_customer_info(
    rows: List[Dict[str, str]],
    email_by_phone: Dict[str, str],
    email_by_name: Dict[str, str],
    phone_by_name: Dict[str, str],
    addr_by_phone: Dict[str, str],
    addr_by_name: Dict[str, str],
    addr_phone_by_name: Dict[str, str],
) -> None:
    for row in rows:
        name_key = normalize_name(row.get("customer_name", ""))
        phone_key = normalize_phone(row.get("phone", ""))
        email = ""
        address = ""
        if phone_key:
            email = email_by_phone.get(phone_key, "")
            address = addr_by_phone.get(phone_key, "")
        if not email:
            email = email_by_name.get(name_key, "")
        if not address:
            address = addr_by_name.get(name_key, "")
        if not phone_key:
            phone_key = phone_by_name.get(name_key, "") or addr_phone_by_name.get(name_key, "")
        row["phone"] = phone_key
        row["email"] = email
        row["address"] = address


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


def run(orders_root: str, out: str, emails_csv: str, addresses_csv: str) -> int:
    paid_online, paid_in_store, refund_paths = collect_csv_files(orders_root)
    refunds = load_refunds(refund_paths)
    rows: List[Dict[str, str]] = []
    for path in paid_online:
        rows.extend(parse_orders_csv(path, "credit", refunds))
    for path in paid_in_store:
        rows.extend(parse_orders_csv(path, "cash", refunds))
    email_by_phone, email_by_name, phone_by_name = load_customer_email_map(emails_csv)
    addr_by_phone, addr_by_name, addr_phone_by_name = load_customer_address_map(addresses_csv)
    attach_customer_info(
        rows,
        email_by_phone,
        email_by_name,
        phone_by_name,
        addr_by_phone,
        addr_by_name,
        addr_phone_by_name,
    )
    updated = upsert_raw(out, rows)
    print(f"Upserted {updated} Menufy order row(s) into {out}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Menufy orders raw CSV from export files.")
    parser.add_argument(
        "--orders-root",
        default="Takeout/Menufy/orders",
        help="Root directory containing Menufy order CSV exports.",
    )
    parser.add_argument(
        "--emails-csv",
        default="Takeout/Menufy/Customer_Emails_02-05-2026.csv",
        help="Customer emails CSV path.",
    )
    parser.add_argument(
        "--addresses-csv",
        default="Takeout/Menufy/Customer_Delivery_Addresses_02-05-2026.csv",
        help="Customer delivery addresses CSV path.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("menufy", "orders_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_root, args.out, args.emails_csv, args.addresses_csv)


if __name__ == "__main__":
    main()
