#!/usr/bin/env python3
import argparse
import os
import re
from datetime import datetime
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
    "order_total_raw",
    "status",
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


def clean_restaurant_name(value: str) -> str:
    text = str(value or "").strip()
    lower = text.lower()
    if "aroma" in lower:
        return "Aroma Pizza & Pasta"
    if "ameci" in lower:
        return "Ameci Pizza & Pasta"
    match = re.search(r"((?:Aroma|Ameci)\s+Pizza\s*&?\s*Pasta.*)$", text, re.IGNORECASE)
    return match.group(1).strip() if match else text


def store_from_filename(path: str) -> str:
    base = os.path.basename(path)
    match = re.search(r"-\s*(.+)\.(xlsx|xls)$", base, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"All Orders\s+(.+)\.(xlsx|xls)$", base, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    stem = os.path.splitext(base)[0].strip()
    return stem


def parse_all_orders_excel(path: str) -> List[Dict[str, str]]:
    if not path or not os.path.exists(path):
        return []
    df = pd.read_excel(path, dtype=str).fillna("")
    df.columns = [str(col).strip() for col in df.columns]
    store_name = clean_restaurant_name(store_from_filename(path))
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
        processing_fee = parse_money(row.get("CC Fee", ""))
        if processing_fee and not str(processing_fee).startswith("-"):
            processing_fee = f"-{processing_fee}"
        misc_fee = parse_money(row.get("Shop Funded Discounts Amount", ""))

        notes = ["source_excel"]
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
                "order_total_raw": "",
                "status": "active",
                "partnership_fee": partnership_fee,
                "processing_fee": processing_fee,
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
    df.columns = [str(col).strip() for col in df.columns]
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
        store_name = clean_restaurant_name(str(row.get("restaurant_name", "")).strip())
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
                "order_total_raw": parse_money(row.get("total", "")),
                "status": "active",
                "partnership_fee": "",
                "processing_fee": "",
                "misc_fee": "",
                "notes": "source_history",
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
    for row in rows:
        row["restaurant_name"] = clean_restaurant_name(str(row.get("restaurant_name", "")).strip())
        notes = str(row.get("notes", "") or "").strip()
        if "source_pdf" not in notes:
            row["notes"] = " | ".join(filter(None, [notes, "source_pdf"]))
    return rows


def load_existing_raw(path: str) -> List[Dict[str, str]]:
    if not path or not os.path.exists(path):
        return []
    return pd.read_csv(path, dtype=str).fillna("").to_dict("records")


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


def normalize_row_values(row: Dict[str, str]) -> Dict[str, str]:
    normalized = {col: str(row.get(col, "") or "").strip() for col in RAW_COLUMNS}
    normalized["provider"] = str(row.get("provider", "") or "").strip()
    normalized["restaurant_name"] = clean_restaurant_name(row.get("restaurant_name", ""))
    normalized["status"] = str(row.get("status", "") or "").strip().lower() or "active"
    return normalized


def build_source_map(rows: List[Dict[str, str]]) -> Dict[Tuple[str, str], Dict[str, str]]:
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    for row in rows:
        normalized = normalize_row_values(row)
        order_id = normalized.get("order_id", "")
        provider = normalized.get("provider", "")
        if not order_id or not provider:
            continue
        out[(order_id, provider)] = normalized
    return out


def pick_first(rows: List[Dict[str, str]], field: str) -> str:
    for row in rows:
        value = str(row.get(field, "") or "").strip()
        if value:
            return value
    return ""


def merge_orders(
    excel_rows: List[Dict[str, str]],
    history_rows: List[Dict[str, str]],
    statement_rows: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    excel_map = build_source_map(excel_rows)
    history_map = build_source_map(history_rows)
    statement_map = build_source_map(statement_rows)
    all_keys = sorted(set(excel_map) | set(history_map) | set(statement_map))
    final_rows: List[Dict[str, str]] = []
    now = datetime.now().isoformat()
    precedence_fields = [
        "restaurant_name",
        "order_datetime",
        "order_type",
        "payment_type",
        "payment_status",
        "subtotal",
        "customer_delivery_fee",
        "order_adjustments",
        "tax",
        "tip",
        "total",
        "order_total_raw",
        "status",
        "partnership_fee",
        "processing_fee",
        "misc_fee",
        "statement_period_start",
        "statement_period_end",
        "account_id",
        "source_file",
    ]
    history_enrichment_fields = ["customer_name", "phone", "email", "address"]

    for key in all_keys:
        statement_row = statement_map.get(key, {})
        excel_row = excel_map.get(key, {})
        history_row = history_map.get(key, {})
        if statement_row:
            precedence_rows = [statement_row]
            winner_source = "statement"
        elif excel_row:
            precedence_rows = [excel_row]
            winner_source = "excel"
        elif history_row:
            precedence_rows = [history_row]
            winner_source = "history"
        else:
            precedence_rows = []
            winner_source = "history"

        merged = {col: "" for col in RAW_COLUMNS}
        merged["order_id"], merged["provider"] = key
        for field in precedence_fields:
            merged[field] = pick_first(precedence_rows, field)

        # History is only used for customer/contact enrichment.
        for field in history_enrichment_fields:
            merged[field] = str(history_row.get(field, "") or "").strip()

        note_parts: List[str] = []
        statement_notes = str(statement_row.get("notes", "") or "").strip()
        if statement_notes:
            note_parts.append(statement_notes)
        if winner_source != "statement":
            note_parts.append(f"source={winner_source}")
            chosen_notes = str(
                (excel_row if winner_source == "excel" else history_row).get("notes", "") or ""
            ).strip()
            if winner_source == "history" and chosen_notes == "source_history":
                chosen_notes = ""
            if winner_source == "excel" and chosen_notes == "source_excel":
                chosen_notes = ""
            if chosen_notes and chosen_notes not in note_parts:
                note_parts.append(chosen_notes)
        merged["notes"] = " | ".join(part for part in note_parts if part)

        if not str(merged.get("total", "") or "").strip():
            merged["total"] = compute_total(merged)
        if not str(merged.get("status", "") or "").strip():
            merged["status"] = "active"
        merged["added_at"] = now
        final_rows.append(merged)

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
            "Takeout/Slice/All Orders Aroma.xlsx",
            "Takeout/Slice/All Orders Ameci.xlsx",
        ],
        help="Slice All Orders Excel files.",
    )
    parser.add_argument(
        "--order-history",
        default="Takeout/GoogleSheets/slice_order_history.csv",
        help="Order history CSV with customer info.",
    )
    parser.add_argument(
        "--download-history",
        action="store_true",
        default=True,
        help="Download order history from Google Sheets before parsing.",
    )
    parser.add_argument(
        "--no-download-history",
        action="store_true",
        help="Skip downloading order history from Google Sheets.",
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
    try:
        for path in args.offline_online:
            excel_rows.extend(parse_all_orders_excel(path))
    except ImportError as exc:
        if "openpyxl" not in str(exc).lower():
            raise
        excel_rows = load_existing_raw(args.excel_out)
        if not excel_rows:
            raise
        print(f"Using existing Slice Excel raw because openpyxl is unavailable: {args.excel_out}")
    history_path = args.order_history
    if args.download_history and not args.no_download_history:
        from orders_analytics.utils.google_sheets import GoogleSheetsDownloader
        from orders_analytics.utils.google_sheets_registry import SHEETS

        entry = SHEETS.get("slice_order_history")
        if not entry:
            raise ValueError("slice_order_history not found in google sheets registry.")
        downloader = GoogleSheetsDownloader(entry["sheet_id"])
        downloader.download_csv(entry["gid"], history_path)
    history_rows = parse_order_history(history_path)
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
