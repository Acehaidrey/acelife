#!/usr/bin/env python3
import argparse
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.constants import normalized_path, raw_path

from orders_analytics.utils.schema import write_normalized_rows
from orders_analytics.utils.validation import normalize_order_type, validate_tax_fields
from orders_analytics.utils.errors import reconcile_errors
from orders_analytics.utils.constants import ERRORS_PATH


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def merge_raw(orders_raw: pd.DataFrame, billings_raw: pd.DataFrame) -> List[Dict[str, str]]:
    if orders_raw.empty:
        return []
    merged = orders_raw.copy()
    if not billings_raw.empty:
        billings = billings_raw[
            ["order_id", "processing_fee", "commission_fee", "payment_method"]
        ].copy()
        merged = merged.merge(billings, on="order_id", how="left", suffixes=("", "_bill"))
        if "processing_fee_bill" in merged.columns:
            merged["processing_fee"] = merged["processing_fee_bill"].combine_first(
                merged.get("processing_fee", "")
            )
        if "commission_fee_bill" in merged.columns:
            merged["commission_fee"] = merged["commission_fee_bill"].combine_first(
                merged.get("commission_fee", "")
            )
        if "payment_method_bill" in merged.columns:
            merged["payment_method_bill"] = merged["payment_method_bill"]
        merged.drop(columns=[col for col in merged.columns if col.endswith("_bill")], inplace=True)
    return merged.to_dict("records")


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized = []
    for row in rows:
        customer_name = str(row.get("customer_name") or "")
        if customer_name and "test" in customer_name.lower():
            continue
        payment_type = row.get("payment_type", "")
        if str(row.get("payment_method", "") or "").lower() == "cash":
            payment_type = "cash"
        processing_fee = row.get("processing_fee", "")
        commission_fee = row.get("commission_fee", "")
        notes = []
        subtotal_raw = str(row.get("subtotal", "") or "").replace("$", "").replace(",", "").strip()
        subtotal = None
        if subtotal_raw:
            try:
                subtotal = Decimal(subtotal_raw)
            except InvalidOperation:
                subtotal = None
        order_dt = row.get("order_datetime_iso", "") or row.get("order_datetime_raw", "")
        year = order_dt[:4]

        row_tax = row.get("tax", "")
        tax_withheld = ""
        if not str(row_tax or "").strip():
            if year and year.isdigit() and int(year) >= 2020 and subtotal is not None:
                tax_withheld = str(
                    (subtotal * Decimal("0.0775")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                )

        if not commission_fee and subtotal is not None:
            commission_fee = str((subtotal * Decimal("0.15")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            notes.append("commission_fee_estimated_15pct_subtotal")

        if payment_type == "credit":
            if not processing_fee and subtotal is not None:
                processing_fee = str((subtotal * Decimal("0.043")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                notes.append("processing_fee_estimated_4_3pct_subtotal")
        else:
            if not processing_fee:
                processing_fee = "0.00"

        if notes:
            notes.append("verify_with_platform")
        if payment_type == "cash" and (processing_fee == "" or processing_fee is None):
            processing_fee = "0.00"
        normalized.append(
            {
                "order_id": row.get("order_id", ""),
                "platform": row.get("platform", "EATSTREET"),
                "provider": row.get("provider", ""),
                "order_datetime": order_dt,
                "order_type": normalize_order_type(row.get("order_type", "")),
                "customer_name": row.get("customer_name", ""),
                "company_name": "",
                "phone": row.get("phone", ""),
                "email": row.get("email", ""),
                "address": row.get("address", ""),
                "payment_type": payment_type,
                "subtotal": row.get("subtotal", ""),
                "tax": row_tax,
                "tip": row.get("tip", ""),
                "delivery_fee": row.get("delivery_fee", ""),
                "total": row.get("total", ""),
                "item_count": row.get("item_count", ""),
                "processing_fee": processing_fee,
                "commission_fee": commission_fee,
                "restaurant_name": row.get("restaurant_name", ""),
                "items": row.get("items", ""),
                "tax_withheld": tax_withheld,
                "adjustments": "",
                "marketing_fee": "",
                "misc_fee": "",
                "notes": " | ".join(notes),
            }
        )
    return normalized


def run(orders_raw_path: str, billings_raw_path: str, out_path: str) -> int:
    orders_raw = load_raw(orders_raw_path)
    billings_raw = load_raw(billings_raw_path)
    rows = merge_raw(orders_raw, billings_raw)
    normalized = normalize_rows(rows)
    if not normalized:
        print("No rows to normalize.")
        return 0
    normalized, errors = validate_tax_fields(normalized, source=out_path)
    write_normalized_rows(normalized, out_path)
    reconcile_errors(errors, ERRORS_PATH)
    print(f"Wrote {len(normalized)} rows to {out_path}")
    return len(normalized)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize EatStreet raw CSVs into canonical schema."
    )
    parser.add_argument(
        "--orders-raw",
        default=raw_path("eatstreet", "orders_raw.csv"),
        help="Path to EatStreet orders raw CSV.",
    )
    parser.add_argument(
        "--billings-raw",
        default=raw_path("eatstreet", "billings_raw.csv"),
        help="Path to EatStreet billings raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("eatstreet_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()

    run(args.orders_raw, args.billings_raw, args.out)


if __name__ == "__main__":
    main()
