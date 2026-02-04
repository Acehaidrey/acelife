#!/usr/bin/env python3
import argparse
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path

from orders_analytics.utils.validation import normalize_order_type, validate_tax_fields


def load_raw(path: str) -> pd.DataFrame:
    if not path or not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def merge_raw(orders_raw: pd.DataFrame, billings_raw: pd.DataFrame) -> List[Dict[str, str]]:
    if orders_raw.empty:
        return []
    merged = orders_raw.copy()
    if not billings_raw.empty:
        billings = billings_raw[
            ["order_id", "processing_fee", "commission_fee", "payment_method"]
        ].copy()
        merged = merged.merge(billings, on="order_id", how="left", suffixes=("", "_bill"))
        if "processing_fee_bill" in merged.columns:
            merged["processing_fee"] = merged["processing_fee_bill"].combine_first(
                merged.get("processing_fee", "")
            )
        if "commission_fee_bill" in merged.columns:
            merged["commission_fee"] = merged["commission_fee_bill"].combine_first(
                merged.get("commission_fee", "")
            )
        if "payment_method_bill" in merged.columns:
            merged["payment_method_bill"] = merged["payment_method_bill"]
        merged.drop(columns=[col for col in merged.columns if col.endswith("_bill")], inplace=True)
    return merged.to_dict("records")


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized = []
    for row in rows:
        customer_name = str(row.get("customer_name") or "")
        if customer_name and "test" in customer_name.lower():
            continue
        payment_type = row.get("payment_type", "")
        if str(row.get("payment_method", "") or "").lower() == "cash":
            payment_type = "cash"
        processing_fee = row.get("processing_fee", "")
        commission_fee = row.get("commission_fee", "")
        notes = []
        subtotal_raw = str(row.get("subtotal", "") or "").replace("$", "").replace(",", "").strip()
        subtotal = None
        if subtotal_raw:
            try:
                subtotal = Decimal(subtotal_raw)
            except InvalidOperation:
                subtotal = None
        order_dt = row.get("order_datetime_iso", "") or row.get("order_datetime_raw", "")
        year = order_dt[:4]

        row_tax = row.get("tax", "")
        tax_withheld = ""
        if not str(row_tax or "").strip():
            if year and year.isdigit() and int(year) >= 2020 and subtotal is not None:
                tax_withheld = str(
                    (subtotal * Decimal("0.0775")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                )

        if not commission_fee and subtotal is not None:
            commission_fee = str((subtotal * Decimal("0.15")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            notes.append("commission_fee_estimated_15pct_subtotal")
        if commission_fee:
            try:
                fee_val = Decimal(str(commission_fee))
                if fee_val > 0:
                    commission_fee = str((-fee_val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            except InvalidOperation:
                pass

        if payment_type == "credit":
            if not processing_fee and subtotal is not None:
                processing_fee = str((subtotal * Decimal("0.043")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                notes.append("processing_fee_estimated_4_3pct_subtotal")
        else:
            if not processing_fee:
                processing_fee = "0.00"

        if processing_fee:
            try:
                fee_val = Decimal(str(processing_fee))
                if fee_val > 0:
                    processing_fee = str((-fee_val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            except InvalidOperation:
                pass

        if notes:
            notes.append("verify_with_platform")
        if payment_type == "cash" and (processing_fee == "" or processing_fee is None):
            processing_fee = "0.00"
        normalized.append(
            {
                "order_id": row.get("order_id", ""),
                "platform": row.get("platform", "EATSTREET"),
                "provider": row.get("provider", ""),
                "order_datetime": order_dt,
                "order_type": normalize_order_type(row.get("order_type", "")),
                "customer_name": row.get("customer_name", ""),
                "company_name": "",
                "phone": row.get("phone", ""),
                "email": row.get("email", ""),
                "address": row.get("address", ""),
                "payment_type": payment_type,
                "subtotal": row.get("subtotal", ""),
                "tax": row_tax,
                "tip": row.get("tip", ""),
                "delivery_fee": row.get("delivery_fee", ""),
                "total": row.get("total", ""),
                "item_count": row.get("item_count", ""),
                "processing_fee": processing_fee,
                "commission_fee": commission_fee,
                "restaurant_name": row.get("restaurant_name", ""),
                "items": row.get("items", ""),
                "tax_withheld": tax_withheld,
                "adjustments": "",
                "marketing_fee": "",
                "misc_fee": "",
                "errors": "",
                "notes": " | ".join(notes),
            }
        )
    return normalized


class EatstreetNormalizer(BaseParser):
    platform = "EATSTREET"
    provider = ""

    def default_input_path(self) -> str:
        return raw_path("eatstreet", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("eatstreet_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        billings_path = self.extra.get("billings_raw") or raw_path(
            "eatstreet", "billings_raw.csv"
        )
        return {
            "orders_raw": load_raw(input_path),
            "billings_raw": load_raw(billings_path),
        }

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        rows = merge_raw(inputs["orders_raw"], inputs["billings_raw"])
        return normalize_rows(rows)

    def post_process(self, rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
        rows = super().post_process(rows)
        rows, errors = validate_tax_fields(rows, source=self.resolve_paths()[1])
        if errors:
            self.stats.errors.extend(errors)
        return rows


def run(
    orders_raw_path: str,
    billings_raw_path: str,
    out_path: str,
    reset_errors: bool = False,
) -> int:
    parser = EatstreetNormalizer(
        input_path=orders_raw_path,
        out_path=out_path,
        billings_raw=billings_raw_path,
        reset_errors=reset_errors,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize EatStreet raw CSVs into canonical schema."
    )
    parser.add_argument(
        "--orders-raw",
        default=raw_path("eatstreet", "orders_raw.csv"),
        help="Path to EatStreet orders raw CSV.",
    )
    parser.add_argument(
        "--billings-raw",
        default=raw_path("eatstreet", "billings_raw.csv"),
        help="Path to EatStreet billings raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("eatstreet_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()

    run(args.orders_raw, args.billings_raw, args.out)


if __name__ == "__main__":
    main()
