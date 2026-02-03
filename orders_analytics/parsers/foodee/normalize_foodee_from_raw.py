#!/usr/bin/env python3
import argparse
import os
from typing import Dict, List

import pandas as pd
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_money
from orders_analytics.utils.validation import normalize_order_type


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def load_adjustments(path: str) -> Dict[str, str]:
    if not path or not os.path.exists(path):
        return {}
    df = pd.read_csv(path, dtype=str).fillna("")
    return {
        str(row.get("order_id", "")).strip(): str(row.get("adjustments", "")).strip()
        for row in df.to_dict("records")
        if row.get("order_id")
    }


def merge_billings(orders: List[Dict[str, str]], billings: List[Dict[str, str]]) -> List[Dict[str, str]]:
    if not billings:
        return orders
    billings_map = {str(row.get("order_id", "")).strip(): row for row in billings}
    for row in orders:
        order_id = str(row.get("order_id", "")).strip()
        billing = billings_map.get(order_id)
        if not billing:
            continue
        mismatches = []
        order_total = row.get("total", "")
        bill_total = billing.get("amount_paid") or billing.get("invoice_total")
        adjustment = row.get("adjustments", "")
        adjusted_total = bill_total
        if bill_total and adjustment:
            try:
                adjusted_total = str(
                    (Decimal(str(bill_total)) + Decimal(str(adjustment))).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                )
            except (InvalidOperation, ZeroDivisionError):
                adjusted_total = bill_total
        if adjusted_total:
            row["total"] = adjusted_total
            try:
                total_val = Decimal(str(adjusted_total))
                subtotal_val = (total_val / Decimal("0.85")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                commission_val = (subtotal_val - total_val).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                tax_withheld_val = (subtotal_val * Decimal("0.0775")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                row["subtotal"] = str(subtotal_val)
                row["tax_withheld"] = str(tax_withheld_val)
                row["commission_fee"] = str(-commission_val)
            except (InvalidOperation, ZeroDivisionError):
                pass
        if order_total and adjusted_total and not adjustment:
            if normalize_money(order_total) != normalize_money(adjusted_total):
                mismatches.append(
                    f"total mismatch (orders={order_total}, billings={adjusted_total})"
                )
        if mismatches:
            row["errors"] = " | ".join([row.get("errors", ""), *mismatches]).strip(" |")
        if billing.get("payment_date"):
            note = f"payment_date={billing.get('payment_date')}"
            row["notes"] = " | ".join([row.get("notes", ""), note]).strip(" |")
    return orders


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized = []
    for row in rows:
        notes = (row.get("notes") or "").lower()
        if "status=canceled" in notes or "status=inactive" in notes:
            continue
        normalized.append(
            {
                "order_id": row.get("order_id", ""),
                "platform": "FOODEE",
                "provider": row.get("provider", ""),
                "restaurant_name": row.get("restaurant_name", ""),
                "order_datetime": row.get("order_datetime", ""),
                "order_type": "pickup",
                "customer_name": row.get("customer_name", ""),
                "company_name": row.get("company_name", ""),
                "phone": row.get("phone", ""),
                "email": row.get("email", ""),
                "address": row.get("address", ""),
                "address_formatted": "",
                "lat": "",
                "lng": "",
                "payment_type": "credit",
                "subtotal": row.get("subtotal", ""),
                "tax": row.get("tax", ""),
                "tax_withheld": row.get("tax_withheld", ""),
                "tip": row.get("tip", ""),
                "delivery_fee": row.get("delivery_fee", ""),
                "total": row.get("total", ""),
                "item_count": row.get("item_count", ""),
                "processing_fee": "",
                "commission_fee": row.get("commission_fee", ""),
                "items": row.get("items", ""),
                "adjustments": row.get("adjustments", ""),
                "marketing_fee": "",
                "misc_fee": "",
                "errors": row.get("errors", ""),
                "notes": row.get("notes", ""),
            }
        )
    return normalized


class FoodeeNormalizer(BaseParser):
    platform = "FOODEE"
    provider = ""

    def default_input_path(self) -> str:
        return raw_path("foodee", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("foodee_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        billings_path = self.extra.get("billings_raw") or raw_path("foodee", "billings_raw.csv")
        adjustments_path = self.extra.get("adjustments_raw") or raw_path(
            "foodee", "adjustments_raw.csv"
        )
        return {
            "orders_raw": load_raw(input_path),
            "billings_raw": load_raw(billings_path),
            "adjustments_raw": load_adjustments(adjustments_path),
        }

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        orders = inputs["orders_raw"].to_dict("records")
        adjustments = inputs.get("adjustments_raw") or {}
        for row in orders:
            adj = adjustments.get(str(row.get("order_id", "")).strip())
            if adj:
                row["adjustments"] = adj
        billings = inputs["billings_raw"].to_dict("records")
        merged = merge_billings(orders, billings)
        return normalize_rows(merged)


def run(orders_raw_path: str, billings_raw_path: str, adjustments_raw_path: str, out_path: str) -> int:
    parser = FoodeeNormalizer(
        input_path=orders_raw_path,
        out_path=out_path,
        billings_raw=billings_raw_path,
        adjustments_raw=adjustments_raw_path,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Foodee raw CSV.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("foodee", "orders_raw.csv"),
        help="Path to Foodee orders raw CSV.",
    )
    parser.add_argument(
        "--billings-raw",
        default=raw_path("foodee", "billings_raw.csv"),
        help="Path to Foodee billings raw CSV.",
    )
    parser.add_argument(
        "--adjustments-raw",
        default=raw_path("foodee", "adjustments_raw.csv"),
        help="Path to Foodee adjustments raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("foodee_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_raw, args.billings_raw, args.adjustments_raw, args.out)


if __name__ == "__main__":
    main()
