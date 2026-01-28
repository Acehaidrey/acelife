#!/usr/bin/env python3
import argparse
import os
import re
from datetime import datetime

import pandas as pd

import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from orders_analytics.utils.schema import canonicalize_dataframe


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize BeyondMenu order history CSV into standard schema."
    )
    parser.add_argument(
        "--csv",
        default="orders_analytics/data/raw/beyondmenu/BeyondMenu_Order_History.csv",
        help="Path to BeyondMenu_Order_History.csv",
    )
    parser.add_argument(
        "--out",
        default="orders_analytics/data/normalized/beyondmenu_orders_normalized.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    df = pd.read_csv(args.csv)
    df["Status"] = df["Status"].astype(str).str.strip().str.lower()
    df = df[df["Status"] == "active"]
    df["order_datetime"] = df.apply(
        lambda row: normalize_order_datetime(str(row.get("Req Time", "")), str(row.get("year", ""))),
        axis=1,
    )
    df["provider"] = df["Store"].apply(normalize_provider)
    df["restaurant"] = df["Store"].apply(normalize_restaurant)
    df["order_type"] = df["Type"].astype(str).str.strip().str.lower()
    df["Name"] = df["Name"].astype(str).str.title()
    df["Address"] = df["Address"].astype(str).apply(title_with_state)

    normalized = pd.DataFrame(
        {
            "order_id": df["Order #"],
            "platform": "BEYONDMENU",
            "provider": df["provider"],
            "restaurant_name": df["restaurant"],
            "order_datetime": df["order_datetime"],
            "order_type": df["order_type"],
            "customer_name": df.get("Name", ""),
            "phone": df.get("Phone", ""),
            "email": "",
            "address": df.get("Address", ""),
            "payment_type": "",
            "subtotal": df.get("Subtotal", ""),
            "tax": df.get("Tax", ""),
            "tip": df.get("Tip", ""),
            "delivery_fee": df.get("Delivery Fee", ""),
            "total": df.get("Total", ""),
            "items": "",
            "item_count": "",
            "processing_fee": df.get("Merchant Fee", ""),
            "commission_fee": df.get("Commission Fee", ""),
            "tax_withheld": "",
            "adjustments": "",
            "marketing_fee": "",
            "misc_fee": df.get("Misc Fee", ""),
            "notes": df.get("Notes", ""),
        }
    )

    normalized = normalized.drop_duplicates(subset=["order_id"])
    normalized = canonicalize_dataframe(normalized)
    normalized.to_csv(args.out, index=False)
    print(f"Wrote {len(normalized)} rows to {args.out}")


if __name__ == "__main__":
    main()
