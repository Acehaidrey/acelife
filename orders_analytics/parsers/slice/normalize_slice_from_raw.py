#!/usr/bin/env python3
import argparse
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Tuple

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_money
from orders_analytics.utils.validation import normalize_order_type, normalize_payment_type
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.schema import build_normalized_row


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


def normalize_dash_zero(value: str) -> str:
    text = str(value or "").strip()
    if text == "-":
        return "0.00"
    return normalize_money(text)

def parse_adjustment_month(adjustment_datetime: str) -> str:
    if not adjustment_datetime:
        return "0000"
    try:
        dt_value = datetime.fromisoformat(adjustment_datetime)
    except ValueError:
        return "0000"
    return dt_value.strftime("%m%y")


def synth_adjustment_id(adjustment_datetime: str, description: str) -> str:
    prefix = parse_adjustment_month(adjustment_datetime)
    desc = str(description or "").strip().lower()
    if "hardware" in desc:
        suffix = "HARDWARE"
    elif "promo" in desc or "credit" in desc:
        suffix = "PROMO"
    else:
        suffix = "ADJUSTMENT"
    return f"{prefix}_{suffix}"


def normalize_order_type_for_slice(value: str) -> str:
    text = str(value or "").strip().lower()
    return normalize_order_type(text)


def build_adjustments_map(
    adjustments: List[Dict[str, str]],
) -> Tuple[Dict[str, List[Tuple[Decimal, str, str]]], List[Dict[str, str]]]:
    adjustments_map: Dict[str, List[Tuple[Decimal, str, str]]] = {}
    synthetic_rows: List[Dict[str, str]] = []
    for row in adjustments:
        order_id = str(row.get("order_id", "")).strip()
        amount = parse_decimal(normalize_money(row.get("adjustment_amount", "")))
        description = str(row.get("adjustment_description", "")).strip()
        adjustment_datetime = str(row.get("adjustment_datetime", "")).strip()
        if not order_id:
            if amount == Decimal("0.00"):
                continue
            synth_id = synth_adjustment_id(adjustment_datetime, description)
            synthetic_rows.append(
                {
                    "order_id": synth_id,
                    "order_datetime": adjustment_datetime,
                    "adjustment_amount": amount,
                    "adjustment_description": description,
                }
            )
            continue
        adjustments_map.setdefault(order_id, []).append((amount, description, adjustment_datetime))
    return adjustments_map, synthetic_rows


def normalize_rows(
    orders: List[Dict[str, str]],
    adjustments: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    adjustments_map, synthetic_rows = build_adjustments_map(adjustments)
    normalized: List[Dict[str, str]] = []
    order_ids = {str(row.get("order_id", "")).strip() for row in orders}
    provider_default = ""
    restaurant_default = ""
    for row in orders:
        if row.get("provider"):
            provider_default = row.get("provider", "")
        if row.get("restaurant_name"):
            restaurant_default = row.get("restaurant_name", "")
        notes: List[str] = []
        order_id = str(row.get("order_id", "")).strip()
        payment_type = normalize_payment_type(row.get("payment_type", ""))
        payment_status = str(row.get("payment_status", "") or "").strip().lower()
        if payment_status:
            if payment_type == PaymentTypes.CREDIT and payment_status != "paid":
                if payment_status != "refunded":
                    continue
            if payment_type == PaymentTypes.CASH and payment_status != "authorized":
                if payment_status != "refunded":
                    continue
            if not payment_type and payment_status not in {"paid", "authorized"}:
                if payment_status != "refunded":
                    continue

        total_value = normalize_dash_zero(row.get("total", ""))
        if not total_value:
            total_value = normalize_money(
                f"{(parse_decimal(row.get('subtotal', '')) + parse_decimal(row.get('tip', '')) + parse_decimal(row.get('customer_delivery_fee', '')) + parse_decimal(row.get('tax', ''))):.2f}"
            )

        order_adjustments = parse_decimal(normalize_money(row.get("order_adjustments", "")))
        if order_adjustments != Decimal("0.00"):
            notes.append(f"order_adjustments={order_adjustments:.2f}")
        raw_notes = str(row.get("notes", "") or "").strip()
        if raw_notes:
            notes.append(raw_notes)
        extra_adjustments = Decimal("0.00")
        for amount, description, _ in adjustments_map.get(order_id, []):
            extra_adjustments += amount
            if description:
                notes.append(description)
        adjustments_total = order_adjustments + extra_adjustments
        if payment_status == "refunded":
            refund_adjustment = -parse_decimal(total_value)
            if refund_adjustment != Decimal("0.00"):
                adjustments_total += refund_adjustment
                notes.append(f"refund_total={normalize_money(f'{refund_adjustment:.2f}')}")
            notes.append("payment_status_refunded")
        normalized.append(
            build_normalized_row(
                Platforms.SLICE.upper(),
                order_id=order_id,
                provider=row.get("provider", ""),
                restaurant_name=row.get("restaurant_name", ""),
                order_datetime=row.get("order_datetime", ""),
                order_type=normalize_order_type_for_slice(row.get("order_type", "")),
                payment_type=payment_type,
                customer_name=row.get("customer_name", ""),
                phone=row.get("phone", ""),
                email=row.get("email", ""),
                address=row.get("address", ""),
                subtotal=normalize_dash_zero(row.get("subtotal", "")),
                tax="",
                tax_withheld=normalize_dash_zero(row.get("tax", "")),
                tip=normalize_dash_zero(row.get("tip", "")),
                delivery_fee=normalize_dash_zero(row.get("customer_delivery_fee", "")),
                total=total_value,
                processing_fee=normalize_dash_zero(row.get("processing_fee", "")),
                commission_fee=normalize_money(row.get("partnership_fee", "")),
                misc_fee=normalize_money(row.get("misc_fee", "")),
                adjustments=normalize_money(f"{adjustments_total:.2f}"),
                payout="",
                errors="",
                notes=" | ".join([note for note in notes if note]),
            )
        )

    for synth in synthetic_rows:
        notes = []
        if synth.get("adjustment_description"):
            notes.append(synth["adjustment_description"])
        if synth.get("adjustment_amount"):
            amount_note = normalize_money(f"{synth['adjustment_amount']:.2f}")
            notes.append(f"adjustment_amount={amount_note}")
        adjustments_value = normalize_money(f"{synth['adjustment_amount']:.2f}")
        normalized.append(
            build_normalized_row(
                Platforms.SLICE.upper(),
                order_id=synth["order_id"],
                provider=provider_default,
                restaurant_name=restaurant_default,
                order_datetime=synth.get("order_datetime", ""),
                order_type=OrderTypes.PHONE_CALL,
                payment_type=PaymentTypes.CASH,
                subtotal="0.00",
                tax="0.00",
                tax_withheld="0.00",
                tip="0.00",
                delivery_fee="0.00",
                total="0.00",
                commission_fee="0.00",
                processing_fee="0.00",
                marketing_fee="0.00",
                misc_fee="0.00",
                adjustments=adjustments_value,
                payout="",
                errors="adjustment_only",
                notes=" | ".join([note for note in notes if note]),
            )
        )

    for order_id, items in adjustments_map.items():
        if order_id in order_ids:
            continue
        total = sum((amount for amount, _, _ in items), Decimal("0.00"))
        notes = [desc for _, desc, _ in items if desc]
        adjustment_datetime = items[0][2] if items else ""
        adjustments_value = normalize_money(f"{total:.2f}")
        normalized.append(
            build_normalized_row(
                Platforms.SLICE.upper(),
                order_id=order_id,
                provider=provider_default,
                restaurant_name=restaurant_default,
                order_datetime=adjustment_datetime,
                payment_type=PaymentTypes.CASH,
                subtotal="0.00",
                tax="0.00",
                tax_withheld="0.00",
                tip="0.00",
                delivery_fee="0.00",
                total="0.00",
                commission_fee="0.00",
                processing_fee="0.00",
                marketing_fee="0.00",
                misc_fee="0.00",
                adjustments=adjustments_value,
                payout="",
                errors="adjustment_only",
                notes=" | ".join([note for note in notes if note]),
            )
        )

    return normalized


class SliceNormalizer(BaseParser):
    platform = "SLICE"
    provider = ""

    def default_input_path(self) -> str:
        return raw_path("slice", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("slice_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        adjustments_path = self.extra.get("adjustments_raw") or raw_path(
            "slice", "adjustments_raw.csv"
        )
        return load_raw(input_path), load_raw(adjustments_path)

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        orders_df, adjustments_df = inputs
        return normalize_rows(
            orders_df.to_dict("records"), adjustments_df.to_dict("records")
        )


def run(
    orders_raw_path: str,
    adjustments_raw_path: str,
    out_path: str,
    reset_errors: bool = False,
) -> int:
    parser = SliceNormalizer(
        input_path=orders_raw_path,
        out_path=out_path,
        adjustments_raw=adjustments_raw_path,
        reset_errors=reset_errors,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Slice raw CSV.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("slice", "orders_raw.csv"),
        help="Path to Slice orders raw CSV.",
    )
    parser.add_argument(
        "--adjustments-raw",
        default=raw_path("slice", "adjustments_raw_from_statements.csv"),
        help="Path to Slice adjustments raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("slice_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_raw, args.adjustments_raw, args.out)


if __name__ == "__main__":
    main()
