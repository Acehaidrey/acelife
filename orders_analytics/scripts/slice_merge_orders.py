#!/usr/bin/env python3
import argparse
import os
import re
from datetime import datetime
from typing import Dict, List

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
    "payment_status",
    "customer_name",
    "phone",
    "email",
    "address",
    "subtotal",
    "customer_delivery_fee",
    "order_adjustments",
    "tax",
    "tip",
    "total",
    "partnership_fee",
    "processing_fee",
    "misc_fee",
    "notes",
    "statement_period_start",
    "statement_period_end",
    "account_id",
    "source_file",
    "email_date",
    "added_at",
]


def parse_money(value: str) -> str:
    return normalize_money(str(value or "").strip())


def parse_datetime(value: str) -> str:
    if not value:
        return ""
    try:
        return pd.to_datetime(value, errors="coerce").isoformat()
    except Exception:
        return ""


def store_from_filename(path: str) -> str:
    base = os.path.basename(path)
    match = re.search(r"-\s*(.+)\.(xlsx|xls)$", base, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def parse_offline_online_excel(path: str) -> List[Dict[str, str]]:
    if not path or not os.path.exists(path):
        return []
    df = pd.read_excel(path, dtype=str).fillna("")
    store_name = store_from_filename(path)
    provider = normalize_provider(store_name) if store_name else ""
    rows: List[Dict[str, str]] = []
    for _, row in df.iterrows():
        order_id = str(row.get("Order ID", "")).strip()
        if not order_id:
            continue
        payment_method = str(row.get("Payment Method", "")).strip().lower()
        payment_type = ""
        if "cash" in payment_method:
            payment_type = "cash"
        elif payment_method:
            payment_type = "credit"
        payment_status = str(row.get("Payment Status", "")).strip().lower()

        subtotal = parse_money(row.get("Subtotal", ""))
        delivery_fee = parse_money(row.get("Delivery Fee", ""))
        order_type = "delivery" if delivery_fee and delivery_fee != "0.00" else "pickup"
        tax = parse_money(row.get("Tax Amount", ""))
        tip = parse_money(row.get("Tip Amount", ""))
        partnership_fee = parse_money(row.get("Flat Shop Fee", ""))
        if partnership_fee and not str(partnership_fee).startswith("-"):
            partnership_fee = f"-{partnership_fee}"
        misc_fee = parse_money(row.get("Shop Funded Discounts Amount", ""))

        notes = []
        if misc_fee and misc_fee != "0.00":
            notes.append(f"discount_for_order={misc_fee}")

        rows.append(
            {
                "order_id": order_id,
                "provider": provider,
                "restaurant_name": store_name,
                "order_datetime": parse_datetime(row.get("Purchase Ts Pt Date", "")),
                "order_type": order_type,
                "payment_type": payment_type,
                "payment_status": payment_status,
                "customer_name": "",
                "phone": "",
                "email": "",
                "address": "",
                "subtotal": subtotal,
                "customer_delivery_fee": delivery_fee,
                "order_adjustments": "",
                "tax": tax,
                "tip": tip,
                "total": "",
                "partnership_fee": partnership_fee,
                "processing_fee": "",
                "misc_fee": misc_fee,
                "notes": " | ".join(notes),
                "statement_period_start": "",
                "statement_period_end": "",
                "account_id": "",
                "source_file": os.path.basename(path),
                "email_date": "",
                "added_at": datetime.now().isoformat(),
            }
        )
    return rows


def parse_order_history(path: str) -> List[Dict[str, str]]:
    if not path or not os.path.exists(path):
        return []
    df = pd.read_csv(path, dtype=str).fillna("")
    rows: List[Dict[str, str]] = []
    for _, row in df.iterrows():
        order_id = str(row.get("order_number", "")).strip()
        if not order_id:
            continue
        payment_method = str(row.get("payment_method", "")).strip().lower()
        payment_type = ""
        if "cash" in payment_method:
            payment_type = "cash"
        elif payment_method:
            payment_type = "credit"
        order_datetime = ""
        order_date = str(row.get("order_date", "")).strip()
        order_time = str(row.get("order_time", "")).strip()
        if order_date and order_time:
            try:
                order_datetime = pd.to_datetime(f"{order_date} {order_time}", errors="coerce").isoformat()
            except Exception:
                order_datetime = ""
        store_name = str(row.get("restaurant_name", "")).strip()
        delivery_fee = parse_money(row.get("delivery_fee", ""))
        order_type = "delivery" if delivery_fee and delivery_fee != "0.00" else "pickup"
        provider = normalize_provider(store_name) if store_name else ""
        customer_name = " ".join(
            [part for part in [row.get("first_name", ""), row.get("last_name", "")] if part]
        ).strip()

        rows.append(
            {
                "order_id": order_id,
                "provider": provider,
                "restaurant_name": store_name,
                "order_datetime": order_datetime,
                "order_type": order_type,
                "payment_type": payment_type,
                "payment_status": "",
                "customer_name": customer_name,
                "phone": str(row.get("phone_number", "")).strip(),
                "email": "",
                "address": str(row.get("address", "")).strip(),
                "subtotal": parse_money(row.get("subtotal", "")),
                "customer_delivery_fee": parse_money(row.get("delivery_fee", "")),
                "order_adjustments": "",
                "tax": parse_money(row.get("tax", "")),
                "tip": parse_money(row.get("tip", "")),
                "total": parse_money(row.get("total", "")),
                "partnership_fee": "",
                "processing_fee": "",
                "misc_fee": "",
                "notes": "",
                "statement_period_start": "",
                "statement_period_end": "",
                "account_id": "",
                "source_file": os.path.basename(path),
                "email_date": "",
                "added_at": datetime.now().isoformat(),
            }
        )
    return rows


def load_pdf_raw(path: str) -> List[Dict[str, str]]:
    if not path or not os.path.exists(path):
        return []
    df = pd.read_csv(path, dtype=str).fillna("")
    rows = df.to_dict("records")
    return rows


def is_midnight(value: str) -> bool:
    text = str(value or "").strip()
    return text.endswith("T00:00:00") or text.endswith(" 00:00:00")


def coalesce_row(base: Dict[str, str], other: Dict[str, str]) -> Dict[str, str]:
    for col in RAW_COLUMNS:
        if col in ("notes", "added_at"):
            continue
        base_val = str(base.get(col, "") or "").strip()
        other_val = str(other.get(col, "") or "").strip()
        if col == "order_datetime" and other_val:
            if not base_val or is_midnight(base_val):
                base[col] = other_val
            continue
        if not base_val and other_val:
            base[col] = other_val
    base_notes = str(base.get("notes", "") or "").strip()
    other_notes = str(other.get("notes", "") or "").strip()
    if other_notes and other_notes not in base_notes:
        if base_notes:
            base["notes"] = f"{base_notes} | {other_notes}"
        else:
            base["notes"] = other_notes
    return base


def compute_total(row: Dict[str, str]) -> str:
    subtotal = parse_money(row.get("subtotal", ""))
    tip = parse_money(row.get("tip", ""))
    delivery_fee = parse_money(row.get("customer_delivery_fee", ""))
    tax = parse_money(row.get("tax", ""))
    if not subtotal and not tip and not delivery_fee and not tax:
        return ""
    total_val = 0.0
    for val in (subtotal, tip, delivery_fee, tax):
        if val:
            try:
                total_val += float(val)
            except ValueError:
                continue
    return f"{total_val:.2f}"


def merge_orders(
    base_rows: List[Dict[str, str]],
    history_rows: List[Dict[str, str]],
    pdf_rows: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    merged: Dict[str, Dict[str, str]] = {}
    for row in base_rows:
        merged[str(row.get("order_id", "")).strip()] = row
    for row in history_rows:
        key = str(row.get("order_id", "")).strip()
        if not key:
            continue
        if key in merged:
            merged[key] = coalesce_row(merged[key], row)
        else:
            merged[key] = row
    for row in pdf_rows:
        key = str(row.get("order_id", "")).strip()
        if not key:
            continue
        if key in merged:
            merged[key] = coalesce_row(merged[key], row)
        else:
            merged[key] = row

    final_rows: List[Dict[str, str]] = []
    now = datetime.now().isoformat()
    for row in merged.values():
        if not str(row.get("total", "") or "").strip():
            row["total"] = compute_total(row)
        row.setdefault("added_at", now)
        final_rows.append(row)

    return final_rows


def write_csv(path: str, rows: List[Dict[str, str]]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(rows).reindex(columns=RAW_COLUMNS).to_csv(path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge Slice order sources into orders_raw.csv.")
    parser.add_argument(
        "--offline-online",
        nargs="*",
        default=[
            "Takeout/Slice/Offline & Online Orders - Aroma Pizza & Pasta.xlsx",
            "Takeout/Slice/Offline & Online Orders 2020-2026 - Ameci Pizza & Pasta.xlsx",
        ],
        help="Offline/Online orders Excel files.",
    )
    parser.add_argument(
        "--order-history",
        default="Takeout/Slice/VA Task Sheet - Slice Order History.csv",
        help="Order history CSV with customer info.",
    )
    parser.add_argument(
        "--pdf-raw",
        default=raw_path("slice", "orders_raw_from_statements.csv"),
        help="Existing Slice raw orders from PDF extraction.",
    )
    parser.add_argument(
        "--excel-out",
        default=raw_path("slice", "orders_raw_from_excel.csv"),
        help="Output CSV for merged offline/online Excel orders.",
    )
    parser.add_argument(
        "--history-out",
        default=raw_path("slice", "orders_raw_from_history.csv"),
        help="Output CSV for order history rows.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("slice", "orders_raw.csv"),
        help="Output merged orders raw CSV path.",
    )
    args = parser.parse_args()

    excel_rows: List[Dict[str, str]] = []
    for path in args.offline_online:
        excel_rows.extend(parse_offline_online_excel(path))
    history_rows = parse_order_history(args.order_history)
    pdf_rows = load_pdf_raw(args.pdf_raw)

    write_csv(args.excel_out, excel_rows)
    write_csv(args.history_out, history_rows)

    merged_rows = merge_orders(excel_rows, history_rows, pdf_rows)
    write_csv(args.out, merged_rows)
    print(f"Wrote {len(excel_rows)} Excel rows -> {args.excel_out}")
    print(f"Wrote {len(history_rows)} history rows -> {args.history_out}")
    print(f"Wrote {len(merged_rows)} merged rows -> {args.out}")


if __name__ == "__main__":
    main()
