#!/usr/bin/env python3
import argparse
import os
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path


def normalize_provider(location: str) -> str:
    name = (location or "").lower()
    if "aroma" in name:
        return "AROMA"
    if "ameci" in name:
        return "AMECI"
    return ""


def normalize_date(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return text


def normalize_money(value: str) -> str:
    text = (value or "").replace("$", "").replace(",", "").strip()
    if text == "":
        return ""
    try:
        amount = Decimal(text)
        return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        return text


class FoodjaOrdersParser(BaseParser):
    platform = "FOODJA"
    dedupe_key = "order_id"

    def default_input_path(self) -> str:
        return raw_path("foodja", "oex-orders-01-28-26.csv")

    def default_out_path(self) -> str:
        return normalized_path("foodja_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return pd.read_csv(input_path, dtype=str).fillna("")

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        df = inputs.copy()
        rows: List[Dict[str, str]] = []
        for _, row in df.iterrows():
            location = row.get("Location", "")
            subtotal = normalize_money(row.get("Food Total", ""))
            try:
                subtotal_dec = Decimal(subtotal) if subtotal != "" else None
            except InvalidOperation:
                subtotal_dec = None
            commission_fee = ""
            tax_withheld = ""
            if subtotal_dec is not None:
                commission_fee = str((subtotal_dec * Decimal("0.30")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                tax_withheld = str((subtotal_dec * Decimal("0.0775")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

            notes = []
            period = row.get("Period", "")
            check_date = row.get("Check Date", "")
            if period:
                notes.append(f"period={period}")
            if check_date:
                notes.append(f"check_date={check_date}")

            rows.append(
                {
                    "order_id": row.get("Order #", ""),
                    "platform": "FOODJA",
                    "provider": normalize_provider(location),
                    "restaurant_name": location,
                    "order_datetime": normalize_date(row.get("Delivery Date", "")),
                    "order_type": "pickup",
                    "customer_name": "",
                    "company_name": "",
                    "phone": "",
                    "email": "",
                    "address": "",
                    "payment_type": "credit",
                    "subtotal": subtotal,
                    "tax": "",
                    "tax_withheld": tax_withheld,
                    "tip": "",
                    "delivery_fee": "",
                    "total": subtotal,
                    "item_count": "",
                    "processing_fee": "0.00",
                    "commission_fee": commission_fee,
                    "items": "",
                    "adjustments": "",
                    "marketing_fee": "",
                    "misc_fee": "",
                    "errors": "",
                    "notes": " | ".join(notes),
                }
            )
        return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Foodja orders CSV.")
    parser.add_argument(
        "--csv",
        default=None,
        help="Path to Foodja orders CSV.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()

    runner = FoodjaOrdersParser(input_path=args.csv, out_path=args.out)
    stats = runner.run()
    if not stats.rows_written:
        print("No rows parsed.")
        return
    out_path = runner.resolve_paths()[1]
    print(f"Wrote {stats.rows_written} rows to {out_path}")


if __name__ == "__main__":
    main()
