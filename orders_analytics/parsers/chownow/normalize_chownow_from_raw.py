#!/usr/bin/env python3
import argparse
import os
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Tuple

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_money
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.validation import normalize_order_type
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.schema import build_normalized_row


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def load_cancellations(path: str) -> set[str]:
    if not path or not os.path.exists(path):
        return set()
    df = pd.read_csv(path, dtype=str).fillna("")
    return {
        str(row.get("order_id", "")).strip()
        for row in df.to_dict("records")
        if row.get("order_id")
    }


def parse_decimal(value: str) -> Decimal:
    text = str(value or "").strip().replace("$", "").replace(",", "")
    if not text:
        return Decimal("0.00")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0.00")


def sum_money(*values: str) -> str:
    total = Decimal("0.00")
    for value in values:
        total += parse_decimal(value)
    if total == Decimal("0.00"):
        return ""
    return normalize_money(f"{total:.2f}")


def build_orders_map(orders: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    return {str(row.get("order_id", "")).strip(): row for row in orders if row.get("order_id")}


def normalize_rows(
    orders: List[Dict[str, str]],
    billings: List[Dict[str, str]],
    cancelled: set[str],
) -> List[Dict[str, str]]:
    orders_map = build_orders_map(orders)
    refund_totals: Dict[str, Decimal] = {}
    refund_notes: Dict[str, str] = {}
    refund_disbursements: Dict[str, Decimal] = {}
    for row in billings:
        order_id = str(row.get("Order Id", "")).strip()
        if not order_id:
            continue
        if order_id in cancelled:
            continue
        if str(row.get("Order Type", "")).strip().lower() == "full refund":
            amount = parse_decimal(normalize_money(row.get("Refund Amount", "")))
            if amount == Decimal("0.00"):
                continue
            refund_totals[order_id] = refund_totals.get(order_id, Decimal("0.00")) + amount
            refund_notes[order_id] = f"refund_total={normalize_money(f'{refund_totals[order_id]:.2f}')}"
            disbursement = parse_decimal(normalize_money(row.get("Disbursement Amount", "")))
            if disbursement != Decimal("0.00"):
                refund_disbursements[order_id] = (
                    refund_disbursements.get(order_id, Decimal("0.00")) + disbursement
                )
    normalized: List[Dict[str, str]] = []
    for row in billings:
        order_id = str(row.get("Order Id", "")).strip()
        if not order_id:
            continue
        if order_id in cancelled:
            continue
        if str(row.get("Order Type", "")).strip().lower() == "full refund":
            continue
        order = orders_map.get(order_id, {})
        notes: List[str] = []
        errors: List[str] = []
        order_notes = str(order.get("notes", "") or "").strip()
        if order_notes:
            notes.append(order_notes)

        subtotal = normalize_money(row.get("Subtotal", ""))
        tax = normalize_money(row.get("Tax", ""))
        inhouse_tip = normalize_money(row.get("In-house Tip", ""))
        serv_grat = normalize_money(row.get("Serv/Grat Fee", ""))
        tip = sum_money(inhouse_tip, serv_grat)

        delivery_fee_component = normalize_money(row.get("Delivery Fee", ""))
        flex_delivery_fee = normalize_money(row.get("Flex Delivery Fee", ""))
        delivery_fee = sum_money(delivery_fee_component, flex_delivery_fee)
        if delivery_fee_component and delivery_fee_component != "0.00":
            notes.append(f"delivery_fee_component={delivery_fee_component}")
        if flex_delivery_fee and flex_delivery_fee != "0.00":
            notes.append(f"flex_delivery_fee={flex_delivery_fee}")
        flex_tip = normalize_money(row.get("Flex Delivery Tip", ""))
        flex_tip_fee = normalize_money(row.get("Flex Delivery Tip.1", ""))
        if flex_tip and flex_tip != "0.00":
            notes.append(f"flex_delivery_tip={flex_tip}")
        if flex_tip_fee and flex_tip_fee != "0.00":
            notes.append(f"flex_delivery_tip_fee={flex_tip_fee}")

        transaction_fee = normalize_money(row.get("Transaction Fee", ""))
        commission_fee = sum_money(row.get("Finder's Fee", ""), row.get("External Partner Fee", ""))
        misc_fee = normalize_money(row.get("Faxes Sent", ""))
        bucks = normalize_money(row.get("Bucks", ""))
        refund_amount = normalize_money(row.get("Refund Amount", ""))
        withheld_date = str(row.get("Withheld Date", "")).strip()
        if withheld_date:
            notes.append(f"withheld_date={withheld_date}")
        disbursement_amount = normalize_money(row.get("Disbursement Amount", ""))
        if refund_disbursements.get(order_id):
            disbursement_total = parse_decimal(disbursement_amount) + refund_disbursements[order_id]
            disbursement_amount = normalize_money(f"{disbursement_total:.2f}")

        refund_total = refund_totals.get(order_id, Decimal("0.00"))
        if refund_total != Decimal("0.00"):
            notes.append(refund_notes.get(order_id, f"refund_total={refund_total:.2f}"))

        support_fee = Decimal("0.00")
        if order_notes:
            for part in order_notes.split("|"):
                part = part.strip()
                if part.startswith("support_local_fee="):
                    support_fee = parse_decimal(part.split("=", 1)[1])
                    break

        adjustments_total = refund_total if refund_total != Decimal("0.00") else parse_decimal(refund_amount)
        if support_fee != Decimal("0.00"):
            adjustments_total += -support_fee
        adjustments_value = normalize_money(f"{adjustments_total:.2f}") if adjustments_total != Decimal("0.00") else ""

        promo_value = Decimal("0.00")
        promotions = normalize_money(order.get("promotions", ""))
        if bucks:
            promo_value = -parse_decimal(bucks)
        elif promotions:
            promo_value = parse_decimal(promotions)
        marketing_fee = normalize_money(f"{promo_value:.2f}") if promo_value != Decimal("0.00") else ""

        total = normalize_money(row.get("Gross", ""))
        if support_fee != Decimal("0.00") and total:
            total = normalize_money(f"{(parse_decimal(total) + support_fee):.2f}")

        order_type_raw = str(order.get("order_type", "")).strip()
        order_type = normalize_order_type(order_type_raw)
        if not order_type:
            billing_type = str(row.get("Order Type", "")).strip().lower()
            if "pickup" in billing_type:
                order_type = OrderTypes.PICKUP
            elif "delivery" in billing_type:
                order_type = OrderTypes.DELIVERY
        if flex_delivery_fee and flex_delivery_fee != "0.00" and order_type == OrderTypes.DELIVERY:
            order_type = OrderTypes.PICKUP
        if not order:
            notes.append("order_record_missing")

        payment_type = order.get("payment_type", "").strip()
        if not payment_type:
            card_type = str(row.get("Card Type", "")).strip().lower()
            if "cash" in card_type or "collect" in card_type:
                payment_type = PaymentTypes.CASH
            else:
                payment_type = PaymentTypes.CREDIT

        # discrepancy checks against orders_raw (if present)
        def mismatch(field: str, billing_value: str, order_value: str) -> None:
            if not order_value or not billing_value:
                return
            if normalize_money(order_value) != normalize_money(billing_value):
                errors.append(f"{field}_mismatch")

        mismatch("subtotal", subtotal, order.get("subtotal", ""))
        mismatch("tax", tax, order.get("tax", ""))
        mismatch("delivery_fee", delivery_fee, order.get("delivery_fee", ""))
        mismatch("tip", tip, order.get("tip", ""))
        order_total = order.get("total", "")
        order_customer_paid = order.get("customer_paid", "")
        order_promotions = normalize_money(order.get("promotions", ""))
        if order_customer_paid and order_promotions:
            try:
                order_total = normalize_money(
                    f"{(parse_decimal(order_customer_paid) - parse_decimal(order_promotions)):.2f}"
                )
            except Exception:
                pass
        mismatch("total", total, order_total)

        order_datetime = order.get("order_datetime", "").strip()
        if not order_datetime:
            order_date = str(row.get("Order Date", "")).strip()
            order_time = str(row.get("Order Time (PST)", "")).strip()
            if order_date and order_time:
                try:
                    order_datetime = pd.to_datetime(
                        f"{order_date} {order_time}", errors="raise"
                    ).isoformat()
                except Exception:
                    order_datetime = ""
            elif order_date:
                try:
                    order_datetime = pd.to_datetime(order_date, errors="raise").isoformat()
                except Exception:
                    order_datetime = ""

        provider = order.get("provider", "").strip()
        restaurant_name = (order.get("restaurant_name", "") or "").strip()
        billing_restaurant = str(row.get("Restaurant Name", "")).strip()
        if not restaurant_name and billing_restaurant:
            restaurant_name = billing_restaurant
        if not provider and restaurant_name:
            from orders_analytics.utils.providers import normalize_provider

            provider = normalize_provider(restaurant_name)

        customer_name = order.get("customer_name", "")
        if "test order" in str(customer_name or "").strip().lower():
            continue

        normalized.append(
            build_normalized_row(
                Platforms.CHOWNOW.upper(),
                order_id=order_id,
                provider=provider,
                restaurant_name=restaurant_name,
                order_datetime=order_datetime,
                order_type=order_type,
                customer_name=customer_name,
                phone=order.get("phone", ""),
                email=order.get("email", ""),
                address=order.get("address", ""),
                payment_type=payment_type,
                subtotal=subtotal,
                tax=tax,
                tax_withheld="",
                tip=tip,
                delivery_fee=delivery_fee,
                total=total,
                item_count=order.get("item_count", ""),
                processing_fee=transaction_fee,
                commission_fee=commission_fee,
                items=order.get("items", ""),
                adjustments=adjustments_value,
                marketing_fee=marketing_fee,
                misc_fee=misc_fee,
                payout=disbursement_amount,
                errors=" | ".join(errors),
                notes=" | ".join([n for n in notes if n]),
            )
        )
    return normalized


class ChowNowNormalizer(BaseParser):
    platform = "CHOWNOW"
    provider = ""

    def compute_expected_payout(self, row: Dict[str, str]) -> str:
        expected = super().compute_expected_payout(row)
        if not expected:
            return expected
        notes = str(row.get("notes") or "")
        support_fee = ""
        if "support_local_fee=" in notes:
            for part in notes.split("|"):
                part = part.strip()
                if part.startswith("support_local_fee="):
                    support_fee = part.split("=", 1)[1]
                    break
        if not support_fee:
            return expected
        try:
            return f"{(Decimal(expected) + parse_decimal(support_fee)):.2f}"
        except InvalidOperation:
            return expected

    def default_input_path(self) -> str:
        return raw_path("chownow", "billings_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("chownow_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        orders_path = self.extra.get("orders_raw") or raw_path("chownow", "orders_raw.csv")
        cancellations_path = self.extra.get("cancellations_raw") or raw_path(
            "chownow", "cancellations_raw.csv"
        )
        return (
            load_raw(orders_path),
            load_raw(input_path),
            load_cancellations(cancellations_path),
        )

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        orders_df, billings_df, cancelled = inputs
        return normalize_rows(
            orders_df.to_dict("records"),
            billings_df.to_dict("records"),
            cancelled,
        )


def run(
    orders_raw_path: str,
    billings_raw_path: str,
    cancellations_raw_path: str,
    out_path: str,
    reset_errors: bool = False,
) -> int:
    parser = ChowNowNormalizer(
        input_path=billings_raw_path,
        out_path=out_path,
        orders_raw=orders_raw_path,
        cancellations_raw=cancellations_raw_path,
        reset_errors=reset_errors,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize ChowNow raw CSVs.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("chownow", "orders_raw.csv"),
        help="Path to ChowNow orders raw CSV.",
    )
    parser.add_argument(
        "--billings-raw",
        default=raw_path("chownow", "billings_raw.csv"),
        help="Path to ChowNow billings raw CSV.",
    )
    parser.add_argument(
        "--cancellations-raw",
        default=raw_path("chownow", "cancellations_raw.csv"),
        help="Path to ChowNow cancellations raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("chownow_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_raw, args.billings_raw, args.cancellations_raw, args.out)


if __name__ == "__main__":
    main()
