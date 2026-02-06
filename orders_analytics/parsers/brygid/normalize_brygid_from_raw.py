#!/usr/bin/env python3
import argparse
import os
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_datetime, normalize_order_type, normalize_payment_type
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.schema import build_normalized_row


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def normalize_order_datetime(value: str) -> str:
    return normalize_datetime(
        value,
        formats=(
            "%a, %b %d %Y @ %I:%M %p",
            "%b %d %Y @ %I:%M %p",
            "%a, %b %d %Y %I:%M %p",
            "%b %d %Y %I:%M %p",
        ),
        allow_iso=False,
    )


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for row in rows:
        order_type = normalize_order_type(row.get("order_type", "")) or OrderTypes.PICKUP
        payment_type = normalize_payment_type(row.get("payment_type", "")) or PaymentTypes.CREDIT
        normalized.append(
            build_normalized_row(
                Platforms.BRYGID.upper(),
                order_id=row.get("order_id", ""),
                provider=row.get("provider", ""),
                restaurant_name=row.get("restaurant_name", ""),
                order_datetime=normalize_order_datetime(row.get("order_datetime", "")),
                order_type=order_type,
                customer_name=row.get("customer_name", ""),
                phone=row.get("phone", ""),
                email=row.get("email", ""),
                address=row.get("address", ""),
                payment_type=payment_type,
                subtotal=row.get("subtotal", ""),
                tax=row.get("tax", ""),
                tip=row.get("tip", ""),
                delivery_fee=row.get("delivery_fee", ""),
                total=row.get("total", ""),
                items=row.get("items", ""),
                item_count=row.get("item_count", ""),
                notes=row.get("notes", ""),
                errors="",
            )
        )
    return normalized


class BrygidNormalizer(BaseParser):
    platform = "BRYGID"
    provider = ""

    def default_input_path(self) -> str:
        return raw_path("brygid", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("brygid_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return load_raw(input_path)

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        return normalize_rows(inputs.to_dict("records"))


def run(orders_raw_path: str, out_path: str, reset_errors: bool = False) -> int:
    parser = BrygidNormalizer(input_path=orders_raw_path, out_path=out_path, reset_errors=reset_errors)
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Brygid raw CSV.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("brygid", "orders_raw.csv"),
        help="Path to Brygid orders raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("brygid_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_raw, args.out)


if __name__ == "__main__":
    main()
