#!/usr/bin/env python3
import argparse
import os
from typing import Dict, List, Tuple

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_money
from orders_analytics.utils.validation import normalize_order_type, normalize_payment_type
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.schema import build_normalized_row


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def merge_billings(
    orders: List[Dict[str, str]],
    billings: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    if not billings:
        return orders
    billings_map = {
        str(row.get("order_id", "")).strip(): row for row in billings if row.get("order_id")
    }
    for row in orders:
        order_id = str(row.get("order_id", "")).strip()
        billing = billings_map.get(order_id)
        if not billing:
            continue
        mismatches = []
        for field, bill_field in (
            ("subtotal", "subtotal"),
            ("tax", "tax"),
            ("tip", "tip"),
            ("delivery_fee", "delivery_fee"),
            ("total", "total_invoice_amount"),
        ):
            order_val = row.get(field, "")
            billing_val = billing.get(bill_field, "")
            if billing_val:
                row[field] = billing_val
            if order_val and billing_val:
                if normalize_money(order_val) != normalize_money(billing_val):
                    mismatches.append(
                        f"{field} mismatch (orders={order_val}, billings={billing_val})"
                    )
        if mismatches:
            row["errors"] = " | ".join([row.get("errors", ""), *mismatches]).strip(" |")
    return orders


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized = []
    for row in rows:
        status = row.get("status", "")
        if status and "cancel" in status.lower():
            continue
        discount = row.get("discount", "")
        notes = row.get("notes", "")
        if status and status.lower() not in ("confirmed", "complete", "completed"):
            notes = " | ".join([notes, f"status={status}"]).strip(" |")
        normalized.append(
            build_normalized_row(
                Platforms.DELIVERYCOM.upper(),
                order_id=row.get("order_id", ""),
                provider=row.get("provider", ""),
                restaurant_name=row.get("restaurant_name", ""),
                order_datetime=row.get("order_datetime", ""),
                order_type=normalize_order_type(row.get("order_type", "")),
                customer_name=row.get("customer_name", ""),
                phone=row.get("phone", ""),
                address=row.get("address", ""),
                payment_type=normalize_payment_type(row.get("payment_type", "")),
                subtotal=row.get("subtotal", ""),
                tax=row.get("tax", ""),
                tax_withheld="",
                tip=row.get("tip", ""),
                delivery_fee=row.get("delivery_fee", ""),
                total=row.get("total", ""),
                item_count=row.get("item_count", ""),
                items=row.get("items", ""),
                adjustments=discount,
                errors=row.get("errors", ""),
                notes=notes,
            )
        )
    return normalized


class DeliveryComNormalizer(BaseParser):
    platform = "DELIVERYCOM"
    provider = ""

    def default_input_path(self) -> str:
        return raw_path("deliverycom", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("deliverycom_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        billings_path = self.extra.get("billings_raw") or raw_path(
            "deliverycom", "billings_raw.csv"
        )
        return {
            "orders_raw": load_raw(input_path),
            "billings_raw": load_raw(billings_path),
        }

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        orders = inputs["orders_raw"].to_dict("records")
        billings = inputs["billings_raw"].to_dict("records")
        merged = merge_billings(orders, billings)
        return normalize_rows(merged)


def run(
    orders_raw_path: str,
    billings_raw_path: str,
    out_path: str,
    reset_errors: bool = False,
) -> int:
    parser = DeliveryComNormalizer(
        input_path=orders_raw_path,
        out_path=out_path,
        billings_raw=billings_raw_path,
        reset_errors=reset_errors,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize delivery.com raw CSV.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("deliverycom", "orders_raw.csv"),
        help="Path to delivery.com orders raw CSV.",
    )
    parser.add_argument(
        "--billings-raw",
        default=raw_path("deliverycom", "billings_raw.csv"),
        help="Path to delivery.com billings raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("deliverycom_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_raw, args.billings_raw, args.out)


if __name__ == "__main__":
    main()
