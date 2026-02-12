#!/usr/bin/env python3
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_datetime, normalize_money
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.schema import build_normalized_row


def _normalize_amount(row: pd.Series) -> str:
    amount = normalize_money(row.get("Amount (One column)", ""))
    if amount:
        return amount
    debit = normalize_money(row.get("Debit Amount (Two Column Approach)", ""))
    credit = normalize_money(row.get("Credit Amount (Two Column Approach)", ""))
    if debit:
        try:
            return str(Decimal(debit) * Decimal("-1"))
        except InvalidOperation:
            return debit
    return credit


def _as_negative(value: str) -> str:
    if not value:
        return ""
    try:
        return str((Decimal(value) * Decimal("-1")).copy_abs() * Decimal("-1"))
    except InvalidOperation:
        return value


class OrderInnParser(BaseParser):
    platform = "ORDERINN"
    dedupe_key = "order_id"

    def default_input_path(self) -> str:
        return raw_path("orderinn", "commissions_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("orderinn_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return pd.read_csv(input_path, dtype=str).fillna("")

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        df = inputs.copy()
        rows: List[Dict[str, str]] = []
        for _, row in df.iterrows():
            order_id = row.get("Transaction ID", "")
            order_datetime = normalize_datetime(
                row.get("Transaction Date", ""),
                formats=("%Y-%m-%d", "%m/%d/%Y"),
                allow_iso=True,
            )
            commission_fee = _as_negative(_normalize_amount(row))
            notes = []
            description = row.get("Transaction Description", "")
            line_description = row.get("Transaction Line Description", "")
            if description:
                notes.append(f"transaction_description={description}")
            if line_description:
                notes.append(f"transaction_line_description={line_description}")
            rows.append(
                build_normalized_row(
                    Platforms.ORDERINN.upper(),
                    order_id=order_id,
                    provider=normalize_provider("ameci"),
                    order_datetime=order_datetime,
                    order_type=OrderTypes.PICKUP,
                    payment_type=PaymentTypes.CREDIT,
                    commission_fee=commission_fee,
                    notes=" | ".join(notes),
                )
            )
        return rows


def run(raw_path_in: str, out_path: str) -> None:
    runner = OrderInnParser(input_path=raw_path_in, out_path=out_path)
    runner.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Order Inn commissions from Wave export.")
    parser.add_argument(
        "--raw",
        default=raw_path("orderinn", "commissions_raw.csv"),
        help="Path to Order Inn raw commissions CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("orderinn_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    runner = OrderInnParser(input_path=args.raw, out_path=args.out)
    stats = runner.run()
    print(f"[{Platforms.ORDERINN}] normalized -> {args.out} ({stats.rows_written} rows)")


if __name__ == "__main__":
    main()
