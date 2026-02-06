#!/usr/bin/env python3
import argparse
import os
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.normalize import (
    clean_text,
    join_address_parts,
    normalize_datetime,
    normalize_money,
    normalize_order_type,
)
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.schema import build_normalized_row


def normalize_date(value: str) -> str:
    return normalize_datetime(
        value,
        formats=("%m/%d/%Y %I:%M %p", "%m/%d/%Y"),
        allow_iso=False,
    )


def format_address(row: pd.Series) -> str:
    street = str(row.get("Street Address", "") or "").strip()
    city = str(row.get("City", "") or "").strip()
    state = str(row.get("State", "") or "").strip()
    zip_code = str(row.get("Zip Code", "") or "").strip()
    city_state = ", ".join(p for p in [city, state] if p)
    return join_address_parts([street, city_state, zip_code], sep=", ")


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
            source_lower = source.lower()
            if "delivery" in source_lower:
                order_type = OrderTypes.DELIVERY
            else:
                order_type = OrderTypes.PICKUP
            if "relish" in source_lower:
                order_type = OrderTypes.PICKUP
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
            ppp = normalize_money(row.get("Preferred Partner Program", ""))
            rewards = normalize_money(row.get("ezRewards", ""))
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
            adj = normalize_money(row.get("Adjustments", ""))
            discounts = normalize_money(row.get("Discounts", ""))
            promo_amt = normalize_money(row.get("Promotion", ""))
            misc_fees = normalize_money(row.get("Misc Fees", ""))
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
                build_normalized_row(
                    Platforms.EZCATER.upper(),
                    order_id=order_id,
                    provider=normalize_provider(location),
                    restaurant_name=location,
                    order_datetime=normalize_date(row.get("Event Date", "")),
                    order_type=order_type
                    if order_type in (OrderTypes.PICKUP, OrderTypes.DELIVERY)
                    else OrderTypes.DELIVERY,
                    customer_name=details.get("customer_name", ""),
                    company_name=details.get("company_name", ""),
                    phone=details.get("phone", ""),
                    email=details.get("email", ""),
                    address=address,
                    payment_type=PaymentTypes.CREDIT,
                    subtotal=normalize_money(row.get("Food Total", "")),
                    tax=normalize_money(row.get("Sales Tax", "")),
                    tax_withheld=normalize_money(row.get("Sales Tax Remitted by ezCater", "")),
                    tip=normalize_money(row.get("Tip", "")),
                    delivery_fee=normalize_money(row.get("Delivery Fee", "")),
                    total=normalize_money(row.get("Food Total", "")),
                    payout=normalize_money(row.get("Caterer Total Due", "")),
                    processing_fee=normalize_money(row.get("Payment Transaction Fee", "")),
                    commission_fee=normalize_money(row.get("Commission", "")),
                    adjustments=adjustments,
                    marketing_fee=marketing_fee,
                    errors="",
                    notes=" | ".join(notes),
                )
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
