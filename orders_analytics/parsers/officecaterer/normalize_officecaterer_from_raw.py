#!/usr/bin/env python3
import argparse
import os
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.validation import normalize_order_type


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized = []
    for row in rows:
        subtotal = row.get("subtotal", "")
        commission_fee = ""
        processing_fee = ""
        if subtotal:
            try:
                subtotal_val = float(subtotal)
                commission_fee = f"{-(subtotal_val * 0.27):.2f}"
                processing_fee = f"{-(subtotal_val * 0.03):.2f}"
            except ValueError:
                commission_fee = ""
                processing_fee = ""
        normalized.append(
            {
                "order_id": row.get("order_id", ""),
                "platform": "OFFICECATERER",
                "provider": row.get("provider", ""),
                "restaurant_name": row.get("restaurant_name", ""),
                "order_datetime": row.get("order_datetime", ""),
                "order_type": normalize_order_type(row.get("order_type", "")),
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
                "errors": "",
                "notes": row.get("notes", ""),
            }
        )
    return normalized


class OfficeCatererNormalizer(BaseParser):
    platform = "OFFICECATERER"
    provider = ""

    def default_input_path(self) -> str:
        return raw_path("officecaterer", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("officecaterer_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return load_raw(input_path)

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        return normalize_rows(inputs.to_dict("records"))


def run(orders_raw_path: str, out_path: str) -> int:
    parser = OfficeCatererNormalizer(
        input_path=orders_raw_path,
        out_path=out_path,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Office Caterer raw CSV.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("officecaterer", "orders_raw.csv"),
        help="Path to Office Caterer orders raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("officecaterer_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_raw, args.out)


if __name__ == "__main__":
    main()
