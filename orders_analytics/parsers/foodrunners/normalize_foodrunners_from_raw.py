#!/usr/bin/env python3
import argparse
import os
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_money
from orders_analytics.utils.validation import normalize_order_type
from orders_analytics.utils.order_types import OrderTypes


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def load_cancellations(path: str) -> set[str]:
    if not path or not os.path.exists(path):
        return set()
    df = pd.read_csv(path, dtype=str).fillna("")
    return {
        str(row.get("order_id", "")).strip()
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
        for field in ("subtotal", "tax"):
            order_val = row.get(field, "")
            billing_val = billing.get(field, "")
            if billing_val:
                row[field] = billing_val
            if order_val and billing_val:
                if normalize_money(order_val) != normalize_money(billing_val):
                    mismatches.append(
                        f"{field} mismatch (orders={order_val}, billings={billing_val})"
                    )
        if billing.get("commission_fee"):
            row["commission_fee"] = billing.get("commission_fee")
        if billing.get("processing_fee"):
            row["processing_fee"] = billing.get("processing_fee")
        if billing.get("payout"):
            note = f"payout={billing.get('payout')}"
            row["notes"] = " | ".join([row.get("notes", ""), note]).strip(" |")
        if mismatches:
            row["errors"] = " | ".join([row.get("errors", ""), *mismatches]).strip(" |")
    return orders


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized = []
    for row in rows:
        tax = row.get("tax", "")
        commission_fee = row.get("commission_fee", "")
        processing_fee = row.get("processing_fee", "")
        if row.get("subtotal") and not any([tax, commission_fee, processing_fee]):
            try:
                subtotal = float(row.get("subtotal") or 0)
            except ValueError:
                subtotal = 0.0
            if subtotal:
                tax = normalize_money(f"{subtotal * 0.0775:.2f}")
                commission_fee = normalize_money(f"{-(subtotal * 0.25):.2f}")
                processing_fee = normalize_money(f"{-(subtotal * 0.02):.2f}")
                note = "billings missing; fees/tax estimated from subtotal"
                row["errors"] = " | ".join([row.get("errors", ""), note]).strip(" |")
        normalized.append(
            {
                "order_id": row.get("order_id", ""),
                "platform": "FOODRUNNERS",
                "provider": row.get("provider", ""),
                "restaurant_name": row.get("restaurant_name", ""),
                "order_datetime": row.get("order_datetime", ""),
                "order_type": OrderTypes.PICKUP,
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
                "tax": tax,
                "tax_withheld": "",
                "tip": row.get("tip", ""),
                "delivery_fee": row.get("delivery_fee", ""),
                "total": row.get("total", ""),
                "item_count": row.get("item_count", ""),
                "processing_fee": processing_fee,
                "commission_fee": commission_fee,
                "items": row.get("items", ""),
                "adjustments": "",
                "marketing_fee": "",
                "misc_fee": "",
                "errors": row.get("errors", ""),
                "notes": "",
            }
        )
    return normalized


class FoodRunnersNormalizer(BaseParser):
    platform = "FOODRUNNERS"
    provider = ""

    def default_input_path(self) -> str:
        return raw_path("foodrunners", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("foodrunners_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        billings_path = self.extra.get("billings_raw") or raw_path(
            "foodrunners", "billings_raw.csv"
        )
        cancellations_path = self.extra.get("cancellations_raw") or raw_path(
            "foodrunners", "cancellations_raw.csv"
        )
        return {
            "orders_raw": load_raw(input_path),
            "billings_raw": load_raw(billings_path),
            "cancellations_raw": load_cancellations(cancellations_path),
        }

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        orders = inputs["orders_raw"].to_dict("records")
        cancellations = inputs.get("cancellations_raw") or set()
        if cancellations:
            orders = [
                row
                for row in orders
                if str(row.get("order_id", "")).strip() not in cancellations
            ]
        billings = inputs["billings_raw"].to_dict("records")
        merged = merge_billings(orders, billings)
        return normalize_rows(merged)


def run(
    orders_raw_path: str,
    billings_raw_path: str,
    out_path: str,
    reset_errors: bool = False,
) -> int:
    parser = FoodRunnersNormalizer(
        input_path=orders_raw_path,
        out_path=out_path,
        billings_raw=billings_raw_path,
        reset_errors=reset_errors,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Food Runners raw CSV.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("foodrunners", "orders_raw.csv"),
        help="Path to Food Runners orders raw CSV.",
    )
    parser.add_argument(
        "--billings-raw",
        default=raw_path("foodrunners", "billings_raw.csv"),
        help="Path to Food Runners billings raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("foodrunners_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_raw, args.billings_raw, args.out)


if __name__ == "__main__":
    main()
