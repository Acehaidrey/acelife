#!/usr/bin/env python3
import argparse
import os
from datetime import datetime
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_money
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.schema import build_normalized_row


def parse_float(value: str) -> float:
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except Exception:
        return 0.0


def normalize_order_type(row: pd.Series) -> str:
    if parse_float(row.get("Consumer delivery fee", "")) > 0:
        return OrderTypes.DELIVERY
    return OrderTypes.PICKUP


def choose_order_id(row: pd.Series, idx: int) -> str:
    order_id = str(row.get("DoorDash order ID", "")).strip()
    if order_id:
        return order_id
    delivery_uuid = str(row.get("Delivery UUID", "")).strip()
    if delivery_uuid:
        return f"DD_DELIVERY_{delivery_uuid}"
    tx_id = str(row.get("DoorDash transaction ID", "")).strip()
    if tx_id:
        return f"DD_TX_{tx_id}"
    return f"DD_ROW_{idx}"


def load_errors(errors_path: str) -> pd.DataFrame:
    if not os.path.exists(errors_path):
        return pd.DataFrame()
    df = pd.read_csv(errors_path, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    df["errors_total"] = df.apply(
        lambda r: parse_float(r.get("Error charges", "")) + parse_float(r.get("Adjustments", "")),
        axis=1,
    )
    df["errors_order_id"] = df.apply(
        lambda r: choose_order_id(r, r.name), axis=1
    )
    return df


def load_payouts(payouts_path: str) -> pd.DataFrame:
    if not os.path.exists(payouts_path):
        return pd.DataFrame()
    df = pd.read_csv(payouts_path, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    return df


def map_total(row: pd.Series) -> str:
    total = (
        parse_float(row.get("Subtotal", ""))
        + parse_float(row.get("Subtotal tax passed to merchant", ""))
        + parse_float(row.get("Staff tip", ""))
        + parse_float(row.get("Consumer tip", ""))
        + parse_float(row.get("Consumer delivery fee", ""))
        + parse_float(row.get("Consumer service fee", ""))
        + parse_float(row.get("Consumer small order fee", ""))
        + parse_float(row.get("Consumer legislative fee", ""))
    )
    return f"{total:.2f}" if total else ""


class DoorDashOrdersParser(BaseParser):
    platform = Platforms.DOORDASH.upper()
    total_components_fields = (
        "subtotal",
        "tax",
        "tip",
        "delivery_fee",
        "adjustments",
    )

    def default_input_path(self) -> str:
        return raw_path("doordash", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("doordash_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        orders = pd.read_csv(input_path, dtype=str).fillna("")
        orders.columns = [c.strip() for c in orders.columns]
        errors = load_errors(raw_path("doordash", "errors_raw.csv"))
        payouts = load_payouts(raw_path("doordash", "payouts_raw.csv"))
        return {"orders": orders, "errors": errors, "payouts": payouts}

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        orders = inputs["orders"].copy()
        errors = inputs["errors"].copy()
        payouts = inputs["payouts"].copy()

        error_map = {}
        for _, row in errors.iterrows():
            oid = row.get("errors_order_id", "")
            if not oid:
                continue
            error_map[oid] = error_map.get(oid, 0.0) + parse_float(row.get("errors_total", ""))

        rows: List[Dict[str, str]] = []
        seen_error_ids = set()
        for idx, row in orders.iterrows():
            order_id = choose_order_id(row, idx)
            order_datetime = row.get("Timestamp local time", "")
            payout_id = row.get("Payout ID", "")
            status = row.get("Final order status", "")

            subtotal = normalize_money(row.get("Subtotal", ""))
            tax = normalize_money(row.get("Subtotal tax passed to merchant", ""))
            tax_withheld = normalize_money(row.get("Subtotal tax remitted by DoorDash to tax authorities", ""))
            tip = normalize_money(row.get("Staff tip", ""))
            ad_fee_tax = parse_float(row.get("Ad fee tax (for historical reference only)", ""))
            if ad_fee_tax:
                tax = f"{parse_float(tax) + ad_fee_tax:.2f}"
            delivery_fee = normalize_money(row.get("Consumer delivery fee", ""))
            commission_fee = normalize_money(row.get("Commission", ""))
            processing_fee = normalize_money(row.get("Payment processing fee", ""))
            marketing_total = (
                parse_float(row.get("Marketing fees | (including any applicable taxes)", ""))
                + parse_float(row.get("Customer discounts from marketing | (funded by you)", ""))
                + parse_float(row.get("Customer discounts from marketing | (funded by DoorDash)", ""))
                + parse_float(row.get("Customer discounts from marketing | (funded by a third-party)", ""))
                + parse_float(row.get("DoorDash marketing credit", ""))
                + parse_float(row.get("Marketing fees (for historical reference only) | (all discounts and fees)", ""))
                + parse_float(row.get("Ad fee (for historical reference only)", ""))
            )
            marketing_fee = f"{marketing_total:.2f}" if marketing_total else ""
            misc_fee = ""
            adjustments = parse_float(row.get("Error charges", "")) + parse_float(row.get("Adjustments", ""))

            extra_error = error_map.get(order_id)
            if extra_error is not None:
                seen_error_ids.add(order_id)
                if round(extra_error - adjustments, 2) != 0:
                    # keep detailed adjustment but note mismatch
                    note_mismatch = True
                else:
                    note_mismatch = False
            else:
                note_mismatch = False

            adjustments_str = f"{adjustments:.2f}" if adjustments else ""
            total = normalize_money(row.get("Net total", ""))

            notes = []
            if status:
                notes.append(f"status={status}")
            if row.get("Transaction type"):
                notes.append(f"transaction_type={row.get('Transaction type')}")
            if note_mismatch:
                notes.append(f"error_adjustment_mismatch detailed={adjustments:.2f} errors={extra_error:.2f}")
            if payout_id:
                notes.append(f"payout_id={payout_id}")

            rows.append(
                build_normalized_row(
                    Platforms.DOORDASH.upper(),
                    order_id=order_id,
                    provider=normalize_provider(row.get("Store name", "")),
                    restaurant_name=row.get("Store name", ""),
                    order_datetime=order_datetime,
                    order_type=normalize_order_type(row),
                    payment_type=PaymentTypes.CREDIT,
                    subtotal=subtotal,
                    tax=tax,
                    tax_withheld=tax_withheld,
                    tip=tip,
                    delivery_fee=delivery_fee,
                    total=total,
                    processing_fee=processing_fee,
                    commission_fee=commission_fee,
                    marketing_fee=marketing_fee,
                    misc_fee=misc_fee,
                    adjustments=adjustments_str,
                    payout=normalize_money(row.get("Net total", "")),
                    notes=" | ".join(notes),
                    errors="",
                )
            )

        # Add any error-only rows (no matching order id)
        for oid, total_err in error_map.items():
            if oid in seen_error_ids:
                continue
            rows.append(
                build_normalized_row(
                    Platforms.DOORDASH.upper(),
                    order_id=oid,
                    provider="",
                    restaurant_name="",
                    order_datetime="",
                    order_type=OrderTypes.PICKUP,
                    payment_type=PaymentTypes.CREDIT,
                    subtotal="",
                    tax="",
                    tax_withheld="",
                    tip="",
                    delivery_fee="",
                    total="",
                    processing_fee="",
                    commission_fee="",
                    marketing_fee="",
                    misc_fee="",
                    adjustments=f"{total_err:.2f}",
                    payout="",
                    notes="errors_only_record",
                    errors="",
                )
            )

        return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize DoorDash detailed transactions.")
    parser.add_argument("--csv", default=None, help="Path to DoorDash detailed raw CSV.")
    parser.add_argument("--out", default=None, help="Output normalized CSV path.")
    args = parser.parse_args()

    runner = DoorDashOrdersParser(input_path=args.csv, out_path=args.out)
    stats = runner.run()
    if not stats.rows_written:
        print("No rows parsed.")
        return
    out_path = runner.resolve_paths()[1]
    print(f"Wrote {stats.rows_written} rows to {out_path}")


if __name__ == "__main__":
    main()
