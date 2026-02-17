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
from orders_analytics.utils.normalize import normalize_datetime, normalize_money
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.schema import build_normalized_row


def normalize_date(value: str) -> str:
    return normalize_datetime(
        value,
        formats=("%m/%d/%Y", "%m/%d/%y"),
        allow_iso=False,
    )


class FoodjaOrdersParser(BaseParser):
    platform = "FOODJA"
    dedupe_key = "order_id"

    def default_input_path(self) -> str:
        return raw_path("foodja", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("foodja_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return pd.read_csv(input_path, dtype=str).fillna("")

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        df = inputs.copy()
        billings = {}
        billings_path = raw_path("foodja", "billings_raw.csv")
        if os.path.exists(billings_path):
            billings_df = pd.read_csv(billings_path, dtype=str).fillna("")
            for _, b in billings_df.iterrows():
                oid = str(b.get("order_id", "")).strip()
                if not oid:
                    continue
                billings[oid] = b

        rows: List[Dict[str, str]] = []
        seen_order_ids = set()
        for _, row in df.iterrows():
            location = row.get("Location", "")
            order_id = str(row.get("order_id", "") or row.get("Order #", "")).strip()
            if order_id:
                seen_order_ids.add(order_id)
            subtotal = normalize_money(row.get("Food Total", ""))
            try:
                subtotal_dec = Decimal(subtotal) if subtotal != "" else None
            except InvalidOperation:
                subtotal_dec = None
            commission_fee = ""
            tax_withheld = ""
            if subtotal_dec is not None:
                commission_fee = str((subtotal_dec * Decimal("-0.30")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                tax_withheld = str((subtotal_dec * Decimal("0.0775")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

            notes = []
            errors = []
            period = row.get("Period", "")
            check_date = row.get("Check Date", "")
            if period:
                notes.append(f"period={period}")
            if check_date:
                notes.append(f"check_date={check_date}")

            payout = ""
            processing_fee = "0.00"
            bill = billings.get(order_id)
            if bill is not None:
                bill_subtotal = normalize_money(bill.get("subtotal", ""))
                bill_payout = normalize_money(bill.get("payout", ""))
                # Use billings values first; note mismatches with orders values.
                if bill_subtotal:
                    if subtotal and bill_subtotal != subtotal:
                        notes.append(f"subtotal_mismatch orders={subtotal} billings={bill_subtotal}")
                        errors.append("subtotal_mismatch_orders_vs_billings")
                    subtotal = bill_subtotal
                    try:
                        subtotal_dec = Decimal(subtotal)
                    except InvalidOperation:
                        subtotal_dec = None
                if bill_payout:
                    payout = bill_payout
                    try:
                        if subtotal_dec is not None:
                            commission_fee = str((Decimal(payout) - subtotal_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                    except InvalidOperation:
                        pass
                notes.append("billings_override")
            else:
                notes.append("billings_missing_receivable")
                notes.append("billings_missing_order_record")

            if not payout and subtotal_dec is not None and commission_fee:
                try:
                    payout = str(
                        (
                            subtotal_dec
                            + Decimal(commission_fee)
                            + Decimal(processing_fee or "0")
                        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    )
                    notes.append("billings_missing_commission_payout_estimated")
                except InvalidOperation:
                    payout = ""
            rows.append(
                build_normalized_row(
                    Platforms.FOODJA.upper(),
                    order_id=order_id,
                    provider=normalize_provider(location),
                    restaurant_name=location,
                    order_datetime=normalize_date(row.get("Delivery Date", "")),
                    order_type=OrderTypes.PICKUP,
                    payment_type=PaymentTypes.CREDIT,
                    subtotal=subtotal,
                    tax="",
                    tax_withheld=tax_withheld,
                    tip="",
                    delivery_fee="",
                    total=subtotal,
                    processing_fee=processing_fee,
                    commission_fee=commission_fee,
                    payout=payout,
                    errors=" | ".join(errors),
                    notes=" | ".join(notes),
                )
            )
        for order_id, bill in billings.items():
            if order_id in seen_order_ids:
                continue
            subtotal = normalize_money(bill.get("subtotal", ""))
            payout = normalize_money(bill.get("payout", ""))
            provider = normalize_provider(bill.get("provider", ""))
            try:
                subtotal_dec = Decimal(subtotal) if subtotal else None
            except InvalidOperation:
                subtotal_dec = None
            commission_fee = ""
            tax_withheld = ""
            if subtotal_dec is not None:
                commission_fee = str((Decimal(payout) - subtotal_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if payout else ""
                tax_withheld = str((subtotal_dec * Decimal("0.0775")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

            notes = ["billings_only_record", "billings_override"]
            period = str(bill.get("period", "")).strip()
            payment_date = str(bill.get("payment_date", "")).strip()
            if period:
                notes.append(f"period={period}")
            if payment_date:
                notes.append(f"payment_date={payment_date}")
            rows.append(
                build_normalized_row(
                    Platforms.FOODJA.upper(),
                    order_id=order_id,
                    provider=provider,
                    restaurant_name=provider,
                    order_datetime=normalize_date(payment_date),
                    order_type=OrderTypes.PICKUP,
                    payment_type=PaymentTypes.CREDIT,
                    subtotal=subtotal,
                    tax="",
                    tax_withheld=tax_withheld,
                    tip="",
                    delivery_fee="",
                    total=subtotal,
                    processing_fee="0.00",
                    commission_fee=commission_fee,
                    payout=payout,
                    errors="",
                    notes=" | ".join(notes),
                )
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
