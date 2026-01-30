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
from orders_analytics.utils.validation import normalize_order_type


def normalize_provider(name: str) -> str:
    text = (name or "").lower()
    if "aroma" in text:
        return "AROMA"
    if "ameci" in text:
        return "AMECI"
    return ""


def parse_money(value: str) -> str:
    text = str(value or "").strip()
    if text == "":
        return ""
    neg = False
    if text.startswith("(") and text.endswith(")"):
        neg = True
        text = text[1:-1]
    text = text.replace("$", "").replace(",", "").strip()
    if text == "":
        return ""
    try:
        amount = Decimal(text)
        if neg:
            amount = -amount
        return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        return text


def normalize_date(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return text


def format_address(row: pd.Series) -> str:
    street = str(row.get("Street Address", "") or "").strip()
    city = str(row.get("City", "") or "").strip()
    state = str(row.get("State", "") or "").strip()
    zip_code = str(row.get("Zip Code", "") or "").strip()
    parts = [street, ", ".join(p for p in [city, state] if p), zip_code]
    return ", ".join([p for p in parts if p])


def clean_text(value: str) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()


class EzCaterOrdersParser(BaseParser):
    platform = "EZCATER"
    dedupe_key = "order_id"

    def default_input_path(self) -> str:
        return raw_path(
            "ezcater",
            "ezcater_all_orders_from_2020_2020-01-01_2026-01-01_2026-01-29 - Order Data.csv",
        )

    def default_out_path(self) -> str:
        return normalized_path("ezcater_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return pd.read_csv(input_path, dtype=str).fillna("")

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        df = inputs.copy()
        supplemental_path = self.extra.get(
            "supplement_csv",
            raw_path("ezcater", "VA Task Sheet - EZcater Order History.csv"),
        )
        supplement = {}
        if supplemental_path and os.path.exists(supplemental_path):
            sup_df = pd.read_csv(supplemental_path, dtype=str).fillna("")
            for _, sup_row in sup_df.iterrows():
                order_id = clean_text(sup_row.get("Order Number", ""))
                if not order_id:
                    continue
                supplement[order_id] = {
                    "customer_name": clean_text(sup_row.get("Customer Name", "")),
                    "company_name": clean_text(sup_row.get("Company", "")),
                    "phone": clean_text(sup_row.get("Phone", "")),
                    "email": clean_text(sup_row.get("Email", "")),
                    "address": clean_text(sup_row.get("Address", "")),
                }
        rows: List[Dict[str, str]] = []
        for _, row in df.iterrows():
            order_id = clean_text(row.get("Order Number", ""))
            if order_id.lower() == "total":
                continue
            location = row.get("Store Name", "") or row.get("Location", "")
            source = str(row.get("Source", "") or "")
            order_type = normalize_order_type(source) or "delivery"
            if "relish" in source.lower():
                order_type = "pickup"
            notes = []
            status = row.get("Status", "")
            promo = row.get("Promotion Code", "")
            if status:
                notes.append(f"status={status}")
            if source:
                notes.append(f"source={source}")
            if promo:
                notes.append(f"promo_code={promo}")

            marketing_fee = ""
            ppp = parse_money(row.get("Preferred Partner Program", ""))
            rewards = parse_money(row.get("ezRewards", ""))
            if ppp or rewards:
                try:
                    marketing_fee = str(
                        (Decimal(ppp or "0") + Decimal(rewards or "0")).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                    )
                except InvalidOperation:
                    marketing_fee = ""

            adjustments = ""
            adj = parse_money(row.get("Adjustments", ""))
            discounts = parse_money(row.get("Discounts", ""))
            promo_amt = parse_money(row.get("Promotion", ""))
            misc_fees = parse_money(row.get("Misc Fees", ""))
            if adj or discounts or promo_amt or misc_fees:
                try:
                    adjustments = str(
                        (Decimal(adj or "0") + Decimal(discounts or "0") + Decimal(promo_amt or "0") + Decimal(misc_fees or "0")).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                    )
                except InvalidOperation:
                    adjustments = ""

            details = supplement.get(order_id, {})
            address = details.get("address", "") or format_address(row)

            rows.append(
                {
                    "order_id": order_id,
                    "platform": "EZCATER",
                    "provider": normalize_provider(location),
                    "restaurant_name": location,
                    "order_datetime": normalize_date(row.get("Event Date", "")),
                    "order_type": order_type if order_type in ("pickup", "delivery") else "delivery",
                    "customer_name": details.get("customer_name", ""),
                    "company_name": details.get("company_name", ""),
                    "phone": details.get("phone", ""),
                    "email": details.get("email", ""),
                    "address": address,
                    "payment_type": "credit",
                    "subtotal": parse_money(row.get("Food Total", "")),
                    "tax": parse_money(row.get("Sales Tax", "")),
                    "tax_withheld": parse_money(row.get("Sales Tax Remitted by ezCater", "")),
                    "tip": parse_money(row.get("Tip", "")),
                    "delivery_fee": parse_money(row.get("Delivery Fee", "")),
                    "total": parse_money(row.get("Caterer Total Due", "")) or parse_money(row.get("Food Total", "")),
                    "item_count": "",
                    "processing_fee": parse_money(row.get("Payment Transaction Fee", "")),
                    "commission_fee": parse_money(row.get("Commission", "")),
                    "items": "",
                    "adjustments": adjustments,
                    "marketing_fee": marketing_fee,
                    "misc_fee": "",
                    "errors": "",
                    "notes": " | ".join(notes),
                }
            )
        return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize ezCater orders CSV.")
    parser.add_argument("--csv", default=None, help="Path to ezCater orders CSV.")
    parser.add_argument("--out", default=None, help="Output normalized CSV path.")
    args = parser.parse_args()

    runner = EzCaterOrdersParser(input_path=args.csv, out_path=args.out)
    stats = runner.run()
    if not stats.rows_written:
        print("No rows parsed.")
        return
    out_path = runner.resolve_paths()[1]
    print(f"Wrote {stats.rows_written} rows to {out_path}")


if __name__ == "__main__":
    main()
