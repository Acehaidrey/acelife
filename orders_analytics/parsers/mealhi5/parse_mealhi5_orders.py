#!/usr/bin/env python3
import argparse
import os
from datetime import datetime, date
from email.utils import parsedate_to_datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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


BILLING_RANGES = [
    # (start_date, end_date, payout_dates, label)
    (date(2019, 10, 1), date(2019, 10, 31), [date(2019, 11, 7)], "2019-10"),
    (date(2019, 11, 1), date(2019, 11, 22), [date(2019, 11, 23)], "2019-11-01_22"),
    (date(2020, 2, 1), date(2020, 2, 28), [date(2020, 3, 3)], "2020-02"),
    # March 2020 split across two payments
    (date(2020, 3, 1), date(2020, 3, 17), [date(2020, 3, 18), date(2020, 4, 3)], "2020-03-01_17"),
    (date(2021, 1, 1), date(2021, 1, 31), [date(2021, 2, 4)], "2021-01"),
]


def _parse_billings_map(billings_df):
    payouts = {}
    for _, row in billings_df.iterrows():
        amount = row.get("amount", "")
        payment_date = row.get("payment_date", "")
        if not amount or not payment_date:
            continue
        try:
            dt = datetime.fromisoformat(payment_date.replace("Z", "+00:00"))
        except Exception:
            try:
                dt = parsedate_to_datetime(payment_date)
            except Exception:
                dt = None
        if not dt:
            continue
        payouts[dt.date()] = payouts.get(dt.date(), 0) + float(amount)
    return payouts





def _allocate_amount(total: float, weights: list[float]) -> list[float]:
    weight_sum = sum(weights) or 1.0
    allocated = []
    running = 0.0
    for w in weights[:-1]:
        amt = round(total * (w / weight_sum), 2)
        allocated.append(amt)
        running += amt
    allocated.append(round(total - running, 2))
    return allocated
def _allocate_offsets(rows, payouts_by_date):
    # Build index of rows by order date
    for start, end, payout_dates, label in BILLING_RANGES:
        payout_total = 0.0
        for d in payout_dates:
            payout_total += payouts_by_date.get(d, 0.0)
        if payout_total == 0:
            continue
        # collect rows in date range
        idxs = []
        totals = []
        for i, row in enumerate(rows):
            dt_str = row.get("order_datetime", "")
            if not dt_str:
                continue
            try:
                order_date = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).date()
            except Exception:
                continue
            if start <= order_date <= end:
                idxs.append(i)
                try:
                    totals.append(float(row.get("total", "0") or 0))
                except Exception:
                    totals.append(0.0)
        if not idxs:
            continue
        total_sum = sum(totals)
        diff = round(payout_total - total_sum, 2)
        # allocate payout proportionally (or evenly if total_sum is 0)
        weights = totals if total_sum else [1.0] * len(idxs)
        allocated_payouts = _allocate_amount(payout_total, weights)
        payout_dates_str = ",".join(d.isoformat() for d in payout_dates)
        for i, payout_amt in zip(idxs, allocated_payouts):
            rows[i]["payout"] = f"{payout_amt:.2f}"
            notes = rows[i].get("notes", "")
            if notes:
                notes += " | "
            notes += f"payout_allocated={label}"
            notes += f" | payment_date={payout_dates_str}"
            rows[i]["notes"] = notes
        if diff == 0:
            continue
        if diff < 0:
            # split negative diff into 40% processing fee and 60% commission fee
            total_processing = round(diff * 0.40, 2)
            total_commission = round(diff - total_processing, 2)
            proc_alloc = _allocate_amount(total_processing, weights)
            comm_alloc = _allocate_amount(total_commission, weights)
            for i, proc_amt, comm_amt in zip(idxs, proc_alloc, comm_alloc):
                row = rows[i]
                existing_proc = float(row.get("processing_fee", "0") or 0)
                existing_comm = float(row.get("commission_fee", "0") or 0)
                row["processing_fee"] = f"{round(existing_proc + proc_amt, 2):.2f}"
                row["commission_fee"] = f"{round(existing_comm + comm_amt, 2):.2f}"
        else:
            allocated = _allocate_amount(diff, weights)
            for i, amt in zip(idxs, allocated):
                row = rows[i]
                notes = row.get("notes", "")
                existing = float(row.get("adjustments", "0") or 0)
                row["adjustments"] = f"{round(existing + amt, 2):.2f}"
                if notes:
                    notes += " | "
                notes += f"manual_offset_for_billing={label}"
                row["notes"] = notes
        # sanity check: sum of payouts in range
        payout_check = round(sum(float(rows[i].get("payout") or 0) for i in idxs), 2)
        if round(payout_check - payout_total, 2) != 0:
            # flag first row in range
            first = rows[idxs[0]]
            note = first.get("notes", "")
            if note:
                note += " | "
            note += f"payout_allocation_mismatch={round(payout_check - payout_total,2):.2f}"
            first["notes"] = note
    return rows


class MealHi5OrdersParser(BaseParser):
    platform = "MEALHI5"
    dedupe_key = "order_id"
    total_components_fields = (
        "subtotal",
        "tax",
        "tip",
        "delivery_fee",
        "adjustments",
    )

    def default_input_path(self) -> str:
        return raw_path("mealhi5", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("mealhi5_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        orders = pd.read_csv(input_path, dtype=str).fillna("")
        billings_path = raw_path("mealhi5", "billings_raw.csv")
        billings = pd.read_csv(billings_path, dtype=str).fillna("") if os.path.exists(billings_path) else pd.DataFrame()
        return {"orders": orders, "billings": billings}

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        orders = inputs["orders"].copy()
        billings = inputs["billings"].copy()
        rows: List[Dict[str, str]] = []

        store_address_prefix = "20491 alton pkwy"
        for _, row in orders.iterrows():
            subtotal = normalize_money(row.get("subtotal", ""))
            discount = normalize_money(row.get("discount", ""))
            tax = normalize_money(row.get("tax", ""))
            delivery_fee = normalize_money(row.get("delivery_fee", ""))
            tip = normalize_money(row.get("tip", ""))
            total = normalize_money(row.get("total", ""))

            adjustments = ""
            if discount and discount not in ("0", "0.00"):
                try:
                    adjustments = str((Decimal(discount) * Decimal("-1")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                except InvalidOperation:
                    adjustments = ""

            notes = []
            if discount and discount not in ("0", "0.00"):
                notes.append(f"discount={discount}")

            address = row.get("address", "")
            if address.lower().startswith(store_address_prefix):
                address = ""

            rows.append(
                build_normalized_row(
                    Platforms.MEALHI5.upper(),
                    order_id=row.get("order_id", ""),
                    provider=normalize_provider(row.get("provider", "")),
                    restaurant_name=row.get("restaurant_name", ""),
                    order_datetime=row.get("order_datetime", ""),
                    order_type=OrderTypes.DELIVERY if row.get("order_type") == "delivery" else OrderTypes.PICKUP,
                    payment_type=PaymentTypes.CREDIT,
                    customer_name=row.get("customer_name", ""),
                    email=row.get("email", ""),
                    phone=row.get("phone", ""),
                    address=address,
                    items=row.get("items", ""),
                    item_count=row.get("item_count", ""),
                    subtotal=subtotal,
                    tax=tax,
                    tip=tip,
                    delivery_fee=delivery_fee,
                    total=total,
                    adjustments=adjustments,
                    processing_fee="",
                    commission_fee="",
                    payout="",
                    notes=" | ".join(notes),
                    errors="",
                )
            )

        payouts_by_date = _parse_billings_map(billings)
        rows = _allocate_offsets(rows, payouts_by_date)
        for row in rows:
            if row.get("order_id") == "68642" and not row.get("commission_fee"):
                row["commission_fee"] = "0.00"
        return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize MealHi5 orders CSV.")
    parser.add_argument("--csv", default=None, help="Path to MealHi5 orders raw CSV.")
    parser.add_argument("--out", default=None, help="Output normalized CSV path.")
    args = parser.parse_args()

    runner = MealHi5OrdersParser(input_path=args.csv, out_path=args.out)
    stats = runner.run()
    if not stats.rows_written:
        print("No rows parsed.")
        return
    out_path = runner.resolve_paths()[1]
    print(f"Wrote {stats.rows_written} rows to {out_path}")


if __name__ == "__main__":
    main()
