#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from decimal import Decimal, InvalidOperation
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_datetime, normalize_money
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.providers import Providers
from orders_analytics.utils.schema import build_normalized_row, compute_expected_payout


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def _to_decimal(value: str) -> Decimal:
    text = normalize_money(str(value or ""))
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def _fmt_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for row in rows:
        order_id = str(row.get("order_id", "")).strip()
        if not order_id:
            continue
        subtotal = normalize_money(row.get("subtotal", ""))
        tax = normalize_money(row.get("tax", ""))
        tip = normalize_money(row.get("tip", ""))
        delivery_fee = normalize_money(row.get("delivery_fee", ""))
        adjustments = normalize_money(row.get("discounts", ""))
        total = normalize_money(row.get("invoice_total", ""))
        overage_tip = _to_decimal(row.get("payment_overage_to_tip", ""))
        if overage_tip > Decimal("0"):
            total = _fmt_decimal(_to_decimal(total) + overage_tip)
        payout = normalize_money(row.get("paid_in_amount", ""))
        if payout in {"", "0", "0.0", "0.00"}:
            payout = ""
        fee = _to_decimal(row.get("merchant_account_fee", ""))
        processing_fee = str((-fee).quantize(Decimal("0.01"))) if fee else "0.00"

        notes_value = ""
        if overage_tip > Decimal("0"):
            notes_value = f"payment_overage_to_tip={_fmt_decimal(overage_tip)}"

        payment_type = PaymentTypes.CREDIT
        payment_hint = str(row.get("payment_type_hint", "")).strip().lower()
        if payment_hint == "cash":
            payment_type = PaymentTypes.CASH
        if fee != Decimal("0"):
            payment_type = PaymentTypes.CREDIT

        normalized = build_normalized_row(
            Platforms.WAVE.upper(),
            order_id=order_id,
            provider=Providers.AROMA,
            order_datetime=normalize_datetime(
                str(row.get("transaction_date", "")).strip(),
                formats=["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"],
            ),
            order_type=str(row.get("order_type", "")).strip().lower() or OrderTypes.PICKUP,
            payment_type=payment_type,
            subtotal=subtotal,
            tax=tax,
            tax_withheld="0.00",
            tip=tip,
            delivery_fee=delivery_fee,
            total=total,
            processing_fee=processing_fee,
            commission_fee="0.00",
            adjustments=adjustments,
            payout=payout,
            customer_name=str(row.get("customer_name", "")).strip(),
            company_name=str(row.get("company_name", "")).strip(),
            phone=str(row.get("phone", "")).strip(),
            email=str(row.get("email", "")).strip(),
            address=str(row.get("address", "")).strip(),
            restaurant_name="Aroma Pizza and Pasta",
            items=str(row.get("items", "")).strip(),
            item_count=str(row.get("item_count", "")).strip(),
            notes=notes_value,
        )
        if payment_type == PaymentTypes.CASH and payout:
            normalized["expected_payout"] = payout
        else:
            normalized["expected_payout"] = compute_expected_payout(normalized)
        out.append(normalized)
    return out


class WaveNormalizer(BaseParser):
    platform = "WAVE"
    provider = "AROMA"
    total_components_fields = (
        "subtotal",
        "tax",
        "tip",
        "delivery_fee",
        "adjustments",
    )

    def default_input_path(self) -> str:
        return raw_path("wave", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("wave_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return {"orders_raw": load_raw(input_path)}

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        return normalize_rows(inputs["orders_raw"].to_dict("records"))


def run(orders_raw_path: str, out_path: str, reset_errors: bool = False) -> int:
    parser = WaveNormalizer(
        input_path=orders_raw_path,
        out_path=out_path,
        reset_errors=reset_errors,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Wave invoice-payment rows.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("wave", "orders_raw.csv"),
        help="Input raw CSV path.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("wave_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_raw, args.out)


if __name__ == "__main__":
    main()
