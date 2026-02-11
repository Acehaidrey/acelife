#!/usr/bin/env python3
import argparse
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path

from orders_analytics.utils.validation import normalize_order_type, validate_tax_fields
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.schema import build_normalized_row


def load_raw(path: str) -> pd.DataFrame:
    if not path or not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def load_cancellations(path: str) -> set[tuple[str, str]]:
    if not path or not os.path.exists(path):
        return set()
    df = pd.read_csv(path, dtype=str).fillna("")
    return {
        (
            str(row.get("provider", "")).strip().upper(),
            str(row.get("order_id", "")).strip(),
        )
        for row in df.to_dict("records")
        if row.get("order_id")
    }


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


def build_billings_only_rows(
    orders_raw: pd.DataFrame,
    billings_raw: pd.DataFrame,
) -> List[Dict[str, str]]:
    if billings_raw.empty:
        return []
    order_ids = set(str(order_id) for order_id in orders_raw.get("order_id", []).astype(str))
    rows: List[Dict[str, str]] = []
    for row in billings_raw.to_dict("records"):
        order_id = str(row.get("order_id", "")).strip()
        if not order_id or order_id in order_ids:
            continue
        rows.append(
            {
                "order_id": order_id,
                "provider": row.get("provider", ""),
                "order_date": row.get("order_date", ""),
                "order_time": row.get("order_time", ""),
                "order_type": row.get("order_type", ""),
                "payment_method": row.get("payment_method", ""),
                "tip": row.get("tip", ""),
                "total": row.get("total", ""),
                "processing_fee": row.get("processing_fee", ""),
                "commission_fee": row.get("commission_fee", ""),
                "notes": "missing_order_record",
            }
        )
    return rows


def parse_order_datetime(order_date: str, order_time: str) -> str:
    order_date = str(order_date or "").strip()
    order_time = str(order_time or "").strip()
    if not order_date:
        return ""
    if order_time:
        try:
            dt = datetime.strptime(f"{order_date} {order_time}", "%m/%d/%Y %I:%M %p")
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            return ""
    try:
        dt = datetime.strptime(order_date, "%m/%d/%Y")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return ""


def normalize_rows(
    rows: List[Dict[str, str]],
    cancelled: set[tuple[str, str]],
) -> List[Dict[str, str]]:
    normalized = []
    for row in rows:
        provider = str(row.get("provider", "")).strip().upper()
        order_id = str(row.get("order_id", "")).strip()
        if (provider, order_id) in cancelled:
            continue
        customer_name = str(row.get("customer_name") or "")
        if customer_name and "test" in customer_name.lower():
            continue
        payment_type = row.get("payment_type", "")
        if str(row.get("payment_method", "") or "").lower() == "cash":
            payment_type = "cash"
        elif not payment_type:
            payment_type = "credit"
            if not str(row.get("payment_method", "") or "").strip():
                row["notes"] = "payment_type_missing" if not row.get("notes") else f"{row.get('notes')} | payment_type_missing"
        processing_fee = row.get("processing_fee", "")
        commission_fee = row.get("commission_fee", "")
        if str(processing_fee).strip().lower() == "nan":
            processing_fee = ""
        if str(commission_fee).strip().lower() == "nan":
            commission_fee = ""
        notes = []
        base_notes = str(row.get("notes") or "").strip()
        if base_notes:
            notes.append(base_notes)
        subtotal_raw = str(row.get("subtotal", "") or "").replace("$", "").replace(",", "").strip()
        subtotal = None
        if subtotal_raw:
            try:
                subtotal = Decimal(subtotal_raw)
            except InvalidOperation:
                subtotal = None
        order_dt = row.get("order_datetime_iso", "") or row.get("order_datetime_raw", "")
        if not order_dt:
            order_dt = parse_order_datetime(row.get("order_date", ""), row.get("order_time", ""))
        year = order_dt[:4]

        row_tax = row.get("tax", "")
        tax_withheld = ""
        delivery_fee = row.get("delivery_fee", "")
        if not str(delivery_fee or "").strip():
            order_type = str(row.get("order_type") or "").lower()
            if "delivery" in order_type:
                delivery_fee = "3.00"
            else:
                delivery_fee = "0.00"
        if subtotal is None and str(row.get("total") or "").strip():
            try:
                subtotal = Decimal(str(row.get("total")).replace("$", "").replace(",", ""))
                subtotal -= Decimal(str(row.get("tip") or "0").replace("$", "").replace(",", ""))
                subtotal -= Decimal(str(delivery_fee or "0").replace("$", "").replace(",", ""))
                subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except InvalidOperation:
                subtotal = None
        if not str(row_tax or "").strip() and subtotal is not None:
            total_base = subtotal
            try:
                total_base += Decimal(str(row.get("tip") or "0").replace("$", "").replace(",", ""))
                total_base += Decimal(str(delivery_fee or "0").replace("$", "").replace(",", ""))
            except InvalidOperation:
                total_base = subtotal
            inferred_tax = (total_base * Decimal("0.0775")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if year and year.isdigit() and int(year) >= 2020:
                if payment_type == "cash":
                    row_tax = str(inferred_tax)
                    notes.append("tax_inferred_7_75pct_total")
                else:
                    tax_withheld = str(inferred_tax)
                    notes.append("tax_withheld_inferred_7_75pct_total")
            else:
                row_tax = str(inferred_tax)
                notes.append("tax_inferred_7_75pct_total")

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
            build_normalized_row(
                (row.get("platform") or Platforms.EATSTREET).upper(),
                order_id=row.get("order_id", ""),
                provider=row.get("provider", ""),
                order_datetime=order_dt,
                order_type=normalize_order_type(row.get("order_type", "")),
                customer_name=row.get("customer_name", ""),
                phone=row.get("phone", ""),
                email=row.get("email", ""),
                address=row.get("address", ""),
                payment_type=payment_type,
                subtotal=str(subtotal) if subtotal is not None else row.get("subtotal", ""),
                tax=row_tax,
                tax_withheld=tax_withheld,
                tip=row.get("tip", ""),
                delivery_fee=delivery_fee,
                total=row.get("total", ""),
                item_count=row.get("item_count", ""),
                processing_fee=processing_fee,
                commission_fee=commission_fee,
                restaurant_name=row.get("restaurant_name", ""),
                items=row.get("items", ""),
                errors="",
                notes=" | ".join(notes),
            )
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
        cancellations_path = self.extra.get("cancellations_raw") or raw_path(
            "eatstreet", "eatstreet_cancellations.csv"
        )
        return {
            "orders_raw": load_raw(input_path),
            "billings_raw": load_raw(billings_path),
            "cancellations_raw": load_cancellations(cancellations_path),
        }

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        rows = merge_raw(inputs["orders_raw"], inputs["billings_raw"])
        rows.extend(build_billings_only_rows(inputs["orders_raw"], inputs["billings_raw"]))
        return normalize_rows(rows, inputs["cancellations_raw"])

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
