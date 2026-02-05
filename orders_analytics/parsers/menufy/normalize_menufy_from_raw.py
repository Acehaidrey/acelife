#!/usr/bin/env python3
import argparse
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_money
from orders_analytics.utils.validation import normalize_order_type, normalize_payment_type


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def parse_decimal(value: str) -> Decimal:
    text = str(value or "").strip().replace("$", "").replace(",", "")
    if not text:
        return Decimal("0.00")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0.00")


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized = []
    for row in rows:
        refund_note = str(row.get("notes", "") or "").strip()
        refund_value = Decimal("0.00")
        if refund_note.startswith("refund="):
            try:
                refund_value = parse_decimal(refund_note.split("=", 1)[1])
            except InvalidOperation:
                refund_value = Decimal("0.00")

        upcharges = parse_decimal(row.get("upcharges", ""))
        customer_fees = parse_decimal(row.get("customer_fees", ""))
        adjustments_total = refund_value + upcharges + customer_fees

        tax = normalize_money(row.get("tax", ""))
        tax_payout = normalize_money(row.get("tax_payout", ""))
        errors = ""
        if tax and tax_payout and tax != tax_payout:
            errors = "tax_payout_mismatch"

        notes = []
        if refund_note:
            notes.append(refund_note)
        total_payout = normalize_money(row.get("total_payout", ""))
        if total_payout:
            notes.append(f"total_payout={total_payout}")

        normalized.append(
            {
                "order_id": row.get("order_id", ""),
                "platform": "MENUFY",
                "provider": row.get("provider", ""),
                "restaurant_name": row.get("restaurant_name", ""),
                "order_datetime": row.get("order_datetime", ""),
                "order_type": normalize_order_type(row.get("order_type", "")),
                "customer_name": row.get("customer_name", ""),
                "company_name": "",
                "phone": row.get("phone", ""),
                "email": row.get("email", ""),
                "address": row.get("address", ""),
                "address_formatted": "",
                "lat": "",
                "lng": "",
                "payment_type": normalize_payment_type(row.get("payment_type", "")),
                "subtotal": row.get("subtotal", ""),
                "tax": tax,
                "tax_withheld": normalize_money(row.get("tax_withholdings", "")),
                "tip": row.get("tip", ""),
                "delivery_fee": row.get("delivery_fee", ""),
                "total": row.get("total", ""),
                "item_count": "",
                "processing_fee": normalize_money(
                    f"{-parse_decimal(row.get('restaurant_fees', '')):.2f}"
                )
                if row.get("restaurant_fees", "")
                else "",
                "commission_fee": normalize_money(f"{-customer_fees:.2f}") if customer_fees else "",
                "items": "",
                "adjustments": normalize_money(adjustments_total),
                "marketing_fee": "",
                "misc_fee": normalize_money(row.get("delivery_service", "")),
                "errors": errors,
                "notes": " | ".join([n for n in notes if n]),
            }
        )
    return normalized


class MenufyNormalizer(BaseParser):
    platform = "MENUFY"
    provider = ""

    def default_input_path(self) -> str:
        return raw_path("menufy", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("menufy_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return load_raw(input_path)

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        return normalize_rows(inputs.to_dict("records"))


def run(orders_raw_path: str, out_path: str, reset_errors: bool = False) -> int:
    parser = MenufyNormalizer(
        input_path=orders_raw_path,
        out_path=out_path,
        reset_errors=reset_errors,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Menufy raw CSV.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("menufy", "orders_raw.csv"),
        help="Path to Menufy orders raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("menufy_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_raw, args.out)


if __name__ == "__main__":
    main()
