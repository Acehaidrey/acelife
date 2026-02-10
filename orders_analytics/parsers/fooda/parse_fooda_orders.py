#!/usr/bin/env python3
import argparse
import os
import sys
from decimal import Decimal, InvalidOperation
from typing import Dict, List

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_datetime, normalize_money
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.order_types import OrderTypes


def parse_date(value: str) -> str:
    return normalize_datetime(
        value,
        formats=("%m/%d/%Y", "%m/%d/%y"),
        allow_iso=False,
    )


def sum_money(*values: str) -> str:
    total = Decimal("0.00")
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            total += Decimal(text)
        except InvalidOperation:
            continue
    return str(total.quantize(Decimal("0.01")))


class FoodaOrdersParser(BaseParser):
    platform = "FOODA"
    dedupe_key = "order_id"

    def default_input_path(self) -> str:
        return raw_path("fooda", "fooda_sales.csv")

    def default_out_path(self) -> str:
        return normalized_path("fooda_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return pd.read_csv(input_path, encoding="utf-16", sep="\t", dtype=str).fillna("")

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        df = inputs.copy()
        df["Restaurant Name"] = df["Restaurant Name"].astype(str)
        df["Product"] = df["Product"].astype(str)
        df = df[df["Restaurant Name"].str.strip().str.lower() != "grand total"].copy()
        df = df[df["Product"].str.strip().str.lower() != "popup"].copy()

        rows: List[Dict[str, str]] = []
        for _, row in df.iterrows():
            section_ref = str(row.get("Section Reference", "")).strip()
            if not section_ref:
                continue
            restaurant = str(row.get("Restaurant Name", "")).strip()
            product = str(row.get("Product", "")).strip().lower()

            subtotal = normalize_money(row.get("Food sales (excludes Tax)", ""))
            tax = normalize_money(row.get("Tax (Restaurant to remit)", ""))
            tax_withheld = normalize_money(row.get("Tax (Fooda to remit)", ""))
            commission_fee = normalize_money(
                row.get("Fooda Commission plus Additional Event Fees", "")
            )
            processing_fee = normalize_money(row.get("Payment Processing Fees", ""))
            adjustments = normalize_money(row.get("Other Fees", ""))
            misc_fee = normalize_money(row.get("Unpaid Orders", ""))
            total = normalize_money(row.get("Subsidy", ""))
            if total and total != "0.00":
                delivery_fee = sum_money(
                    total,
                    f"-{subtotal}" if subtotal else "0.00",
                    f"-{tax}" if tax else "0.00",
                )
            else:
                delivery_fee = "0.00"

            notes = []
            if product:
                notes.append(f"product={product}")
            payment_date = str(row.get("Payment Date", "")).strip()
            if payment_date:
                notes.append(f"payment_date={payment_date}")
            payout = normalize_money(row.get("Paid to Restaurant", ""))
            if payout and payout != "0.00":
                notes.append(f"paid_to_restaurant={payout}")

            rows.append(
                {
                    "order_id": section_ref,
                    "platform": "FOODA",
                    "provider": normalize_provider(restaurant),
                    "restaurant_name": restaurant,
                    "order_datetime": parse_date(row.get("Event date", "")),
                    "order_type": OrderTypes.DELIVERY,
                    "customer_name": "",
                    "company_name": "",
                    "phone": "",
                    "email": "",
                    "address": "",
                    "address_formatted": "",
                    "lat": "",
                    "lng": "",
                    "payment_type": "credit",
                    "subtotal": subtotal,
                    "tax": tax,
                    "tax_withheld": tax_withheld,
                    "tip": "",
                    "delivery_fee": delivery_fee,
                    "total": total,
                    "item_count": "",
                    "processing_fee": processing_fee,
                    "commission_fee": commission_fee,
                    "items": "",
                    "adjustments": adjustments,
                    "marketing_fee": "",
                    "misc_fee": misc_fee,
                    "errors": "",
                    "notes": " | ".join(notes),
                }
            )
        return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Fooda sales CSV.")
    parser.add_argument("--csv", default=None, help="Path to Fooda sales CSV.")
    parser.add_argument("--out", default=None, help="Output normalized CSV path.")
    args = parser.parse_args()

    runner = FoodaOrdersParser(input_path=args.csv, out_path=args.out)
    stats = runner.run()
    if not stats.rows_written:
        print("No rows parsed.")
        return
    out_path = runner.resolve_paths()[1]
    print(f"Wrote {stats.rows_written} rows to {out_path}")


if __name__ == "__main__":
    main()
