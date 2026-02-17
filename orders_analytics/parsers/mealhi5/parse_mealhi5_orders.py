#!/usr/bin/env python3
import argparse
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_money
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.schema import build_normalized_row


class MealHi5OrdersParser(BaseParser):
    platform = "MEALHI5"
    dedupe_key = "order_id"
    total_components_fields = (
        "subtotal",
        "tax",
        "tip",
        "delivery_fee",
        "adjustments",
    )

    def default_input_path(self) -> str:
        return raw_path("mealhi5", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("mealhi5_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        orders = pd.read_csv(input_path, dtype=str).fillna("")
        billings_path = raw_path("mealhi5", "billings_raw.csv")
        billings = pd.read_csv(billings_path, dtype=str).fillna("") if os.path.exists(billings_path) else pd.DataFrame()
        return {"orders": orders, "billings": billings}

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        orders = inputs["orders"].copy()
        billings = inputs["billings"].copy()
        rows: List[Dict[str, str]] = []

        for _, row in orders.iterrows():
            subtotal = normalize_money(row.get("subtotal", ""))
            discount = normalize_money(row.get("discount", ""))
            tax = normalize_money(row.get("tax", ""))
            delivery_fee = normalize_money(row.get("delivery_fee", ""))
            tip = normalize_money(row.get("tip", ""))
            total = normalize_money(row.get("total", ""))

            adjustments = ""
            if discount and discount not in ("0", "0.00"):
                try:
                    adjustments = str((Decimal(discount) * Decimal("-1")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                except InvalidOperation:
                    adjustments = ""

            notes = []
            if discount and discount not in ("0", "0.00"):
                notes.append(f"discount={discount}")

            rows.append(
                build_normalized_row(
                    Platforms.MEALHI5.upper(),
                    order_id=row.get("order_id", ""),
                    provider=normalize_provider(row.get("provider", "")),
                    restaurant_name=row.get("restaurant_name", ""),
                    order_datetime=row.get("order_datetime", ""),
                    order_type=OrderTypes.DELIVERY if row.get("order_type") == "delivery" else OrderTypes.PICKUP,
                    payment_type=PaymentTypes.CREDIT,
                    customer_name=row.get("customer_name", ""),
                    email=row.get("email", ""),
                    phone=row.get("phone", ""),
                    address=row.get("address", ""),
                    items=row.get("items", ""),
                    item_count=row.get("item_count", ""),
                    subtotal=subtotal,
                    tax=tax,
                    tip=tip,
                    delivery_fee=delivery_fee,
                    total=total,
                    adjustments=adjustments,
                    processing_fee="",
                    commission_fee="",
                    payout="",
                    notes=" | ".join(notes),
                    errors="",
                )
            )

        # Billings are check amounts only (no order IDs). We leave payout reconciliation to manual entry.
        return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize MealHi5 orders CSV.")
    parser.add_argument("--csv", default=None, help="Path to MealHi5 orders raw CSV.")
    parser.add_argument("--out", default=None, help="Output normalized CSV path.")
    args = parser.parse_args()

    runner = MealHi5OrdersParser(input_path=args.csv, out_path=args.out)
    stats = runner.run()
    if not stats.rows_written:
        print("No rows parsed.")
        return
    out_path = runner.resolve_paths()[1]
    print(f"Wrote {stats.rows_written} rows to {out_path}")


if __name__ == "__main__":
    main()
