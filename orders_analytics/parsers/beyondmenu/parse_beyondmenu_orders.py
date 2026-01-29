#!/usr/bin/env python3
import argparse
import os
import re
import sys
from datetime import datetime
from typing import Dict, List

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.validation import normalize_order_type, normalize_payment_type


def normalize_provider(store: str) -> str:
    name = (store or "").lower()
    if "aroma" in name:
        return "AROMA"
    if "ameci" in name:
        return "AMECI"
    return ""


def normalize_restaurant(store: str) -> str:
    name = (store or "").lower()
    if "aroma" in name:
        return "Aroma Pizza and Pasta"
    if "ameci" in name:
        return "Ameci Pizza and Pasta"
    return store


def normalize_order_datetime(req_time: str, year: str) -> str:
    if not req_time or not year:
        return ""
    text = f"{req_time.strip()} {year}".replace("  ", " ")
    for fmt in ("%m/%d %I:%M %p %Y", "%m/%d %I:%M%p %Y"):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return ""


def title_with_state(address: str) -> str:
    value = (address or "").strip()
    if not value:
        return value
    titled = value.title()

    def repl(match):
        return f", {match.group(1).upper()} {match.group(2)}"

    return re.sub(r",\\s*([A-Za-z]{2})\\s+(\\d{5}(?:-\\d{4})?)$", repl, titled)




class BeyondMenuOrdersParser(BaseParser):
    platform = "BEYONDMENU"
    dedupe_key = "order_id"

    def default_input_path(self) -> str:
        return raw_path("beyondmenu", "BeyondMenu_Order_History.csv")

    def default_out_path(self) -> str:
        return normalized_path("beyondmenu_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return pd.read_csv(input_path)

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        df = inputs
        df = df.copy()
        # Only keep active orders; inactive are filtered out by design.
        df["Status"] = df["Status"].astype(str).str.strip().str.lower()
        df = df[df["Status"] == "active"].copy()
        df["order_datetime"] = df.apply(
            lambda row: normalize_order_datetime(
                str(row.get("Req Time", "")), str(row.get("year", ""))
            ),
            axis=1,
        )
        df["provider"] = df["Store"].apply(normalize_provider)
        df["restaurant"] = df["Store"].apply(normalize_restaurant)
        df["order_type"] = df["Type"].astype(str).apply(normalize_order_type)
        df["Name"] = df["Name"].fillna("").astype(str).str.title()
        df["Address"] = df["Address"].fillna("").astype(str).apply(title_with_state)

        payment_source = ""
        if "Payment Type" in df.columns:
            payment_source = df.get("Payment Type", "")
        elif "Payment" in df.columns:
            payment_source = df.get("Payment", "")

        normalized = pd.DataFrame(
            {
                "order_id": df["Order #"],
                "platform": "BEYONDMENU",
                "provider": df["provider"],
                "restaurant_name": df["restaurant"],
                "order_datetime": df["order_datetime"],
                "order_type": df["order_type"],
                "customer_name": df.get("Name", "").fillna(""),
                "company_name": "",
                "phone": df.get("Phone", "").fillna(""),
                "email": "",
                "address": df.get("Address", "").fillna(""),
                "payment_type": payment_source.apply(normalize_payment_type) if hasattr(payment_source, "apply") else "credit",
                "subtotal": df.get("Subtotal", "").fillna(""),
                "tax": df.get("Tax", "").fillna(""),
                "tip": df.get("Tip", "").fillna(""),
                "delivery_fee": df.get("Delivery Fee", "").fillna(""),
                "total": df.get("Total", "").fillna(""),
                "items": "",
                "item_count": "",
                "processing_fee": df.get("Merchant Fee", "").fillna(""),
                "commission_fee": df.get("Commission Fee", "").fillna(""),
                "tax_withheld": "",
                "adjustments": "",
                "marketing_fee": "",
                "misc_fee": df.get("Misc Fee", "").fillna(""),
                "errors": "",
                "notes": df.get("Notes", "").fillna(""),
            }
        )
        return normalized.to_dict("records")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize BeyondMenu order history CSV into standard schema."
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="Path to BeyondMenu_Order_History.csv",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output CSV path",
    )
    args = parser.parse_args()

    runner = BeyondMenuOrdersParser(input_path=args.csv, out_path=args.out)
    stats = runner.run()
    if not stats.rows_written:
        print("No rows parsed.")
        return
    out_path = runner.resolve_paths()[1]
    print(f"Wrote {stats.rows_written} rows to {out_path}")


if __name__ == "__main__":
    main()
