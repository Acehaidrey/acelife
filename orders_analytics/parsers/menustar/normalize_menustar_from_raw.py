#!/usr/bin/env python3
import argparse
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List, Tuple, Optional

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import (
    normalize_address,
    normalize_order_type,
    normalize_payment_type,
)
from orders_analytics.utils.providers import Providers, normalize_provider, normalize_datetime




def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def date_key(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10]


def normalize_provider_key(value: str) -> str:
    return str(value or "").strip().lower()


def parse_decimal(value: str) -> Optional[Decimal]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def amount_equal(left: Optional[Decimal], right: Optional[Decimal]) -> bool:
    if left is None or right is None:
        return False
    return left.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == right.quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def format_fee(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if quantized == Decimal("0.00"):
        return "0.00"
    return str(quantized)


def allocate_commission(
    billing_rows: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    # Allocate MenuStar Fees proportionally across all orders by subtotal.
    # If billing rows already have an allocated value, use it.
    has_allocated = any(row.get("statement_menustar_fees_allocated") for row in billing_rows)
    if has_allocated:
        for row in billing_rows:
            alloc = row.get("statement_menustar_fees_allocated", "")
            if alloc:
                try:
                    alloc_dec = Decimal(alloc)
                    payment_type = normalize_payment_type(str(row.get("payment_type", "")))
                    if payment_type == "cash":
                        commission = alloc_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        processing = Decimal("0.00")
                    else:
                        commission = (alloc_dec * Decimal("0.70")).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                        processing = (alloc_dec - commission).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                    row["commission_fee"] = str(
                        format_fee(commission * Decimal("-1"))
                    )
                    row["processing_fee"] = str(
                        format_fee(processing * Decimal("-1"))
                    )
                except InvalidOperation:
                    row["commission_fee"] = ""
                    row["processing_fee"] = ""
        return billing_rows
    grouped: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
    for row in billing_rows:
        key = (row.get("provider", ""), row.get("statement_source_file", ""))
        grouped.setdefault(key, []).append(row)

    for key, rows in grouped.items():
        fee_raw = rows[0].get("statement_menustar_fees", "")
        if not fee_raw:
            continue
        try:
            fee_total = Decimal(fee_raw)
        except InvalidOperation:
            continue
        try:
            subtotal_sum = sum(
                Decimal(r.get("subtotal") or "0") for r in rows
            )
        except InvalidOperation:
            continue
        if subtotal_sum == 0:
            continue
        allocs: List[Decimal] = []
        for row in rows:
            try:
                subtotal = Decimal(row.get("subtotal") or "0")
            except InvalidOperation:
                subtotal = Decimal("0")
            share = (subtotal / subtotal_sum) * fee_total
            allocs.append(share.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        remainder = (fee_total - sum(allocs)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cent = Decimal("0.01")
        cents = int((abs(remainder) / cent).to_integral_value(rounding=ROUND_HALF_UP))
        step = cent if remainder > 0 else -cent
        for i in range(cents):
            allocs[i % len(allocs)] = (allocs[i % len(allocs)] + step).quantize(
                cent, rounding=ROUND_HALF_UP
            )
        for row, alloc in zip(rows, allocs):
            payment_type = normalize_payment_type(str(row.get("payment_type", "")))
            if payment_type == "cash":
                commission = alloc.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                processing = Decimal("0.00")
            else:
                commission = (alloc * Decimal("0.70")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                processing = (alloc - commission).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            row["commission_fee"] = str(
                format_fee(commission * Decimal("-1"))
            )
            row["processing_fee"] = str(
                format_fee(processing * Decimal("-1"))
            )
    return billing_rows


def merge_rows(orders_raw: pd.DataFrame, billings_raw: pd.DataFrame) -> List[Dict[str, str]]:
    if billings_raw.empty:
        return []
    billing_rows = billings_raw.to_dict("records")
    billing_rows = allocate_commission(billing_rows)

    orders_by_day: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
    for _, row in orders_raw.iterrows():
        row_dict = row.to_dict()
        key = (
            normalize_provider_key(row_dict.get("provider", "")),
            date_key(str(row_dict.get("order_datetime", "")).strip()),
        )
        if key[0] and key[1]:
            orders_by_day.setdefault(key, []).append(row_dict)

    merged: List[Dict[str, str]] = []
    for row in billing_rows:
        key = (
            normalize_provider_key(row.get("provider", "")),
            date_key(str(row.get("order_datetime", "")).strip()),
        )
        candidates = orders_by_day.get(key, [])
        best_idx = None
        best_score = -1
        best_total_diff = None
        best_subtotal_diff = None

        billing_amounts = {
            "subtotal": parse_decimal(row.get("subtotal", "")),
            "tax": parse_decimal(row.get("tax", "")),
            "delivery_fee": parse_decimal(row.get("delivery_fee", "")),
            "tip": parse_decimal(row.get("tip", "")),
            "total": parse_decimal(row.get("total", "")),
        }
        billing_order_type = normalize_order_type(str(row.get("order_type", ""))).strip()
        billing_payment_type = normalize_payment_type(str(row.get("payment_type", ""))).strip()

        for idx, candidate in enumerate(candidates):
            score = 0
            candidate_amounts = {
                "subtotal": parse_decimal(candidate.get("subtotal", "")),
                "tax": parse_decimal(candidate.get("tax", "")),
                "delivery_fee": parse_decimal(candidate.get("delivery_fee", "")),
                "tip": parse_decimal(candidate.get("tip", "")),
                "total": parse_decimal(candidate.get("total", "")),
            }
            for field in ("subtotal", "tax", "delivery_fee", "tip", "total"):
                if amount_equal(billing_amounts[field], candidate_amounts[field]):
                    score += 2

            candidate_order_type = normalize_order_type(str(candidate.get("order_type", ""))).strip()
            if billing_order_type and candidate_order_type and billing_order_type == candidate_order_type:
                score += 1
            candidate_payment_type = normalize_payment_type(
                str(candidate.get("payment_type", ""))
            ).strip()
            if billing_payment_type and candidate_payment_type and billing_payment_type == candidate_payment_type:
                score += 1

            total_diff = None
            if billing_amounts["total"] is not None and candidate_amounts["total"] is not None:
                total_diff = abs(billing_amounts["total"] - candidate_amounts["total"])
            subtotal_diff = None
            if (
                billing_amounts["subtotal"] is not None
                and candidate_amounts["subtotal"] is not None
            ):
                subtotal_diff = abs(billing_amounts["subtotal"] - candidate_amounts["subtotal"])

            is_better = False
            if score > best_score:
                is_better = True
            elif score == best_score:
                if best_total_diff is None and total_diff is not None:
                    is_better = True
                elif best_total_diff is not None and total_diff is not None and total_diff < best_total_diff:
                    is_better = True
                elif best_total_diff == total_diff:
                    if best_subtotal_diff is None and subtotal_diff is not None:
                        is_better = True
                    elif (
                        best_subtotal_diff is not None
                        and subtotal_diff is not None
                        and subtotal_diff < best_subtotal_diff
                    ):
                        is_better = True

            if is_better:
                best_idx = idx
                best_score = score
                best_total_diff = total_diff
                best_subtotal_diff = subtotal_diff

        order = {}
        if best_idx is not None:
            order = candidates.pop(best_idx)
        merged.append({**row, **{f"{k}_order": v for k, v in order.items()}})
    return merged


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for row in rows:
        customer_name = str(row.get("customer_name_order") or "")
        if customer_name and "test" in customer_name.lower():
            continue
        order_datetime = normalize_datetime(row.get("order_datetime_order") or row.get("order_datetime", ""))
        provider = row.get("provider") or normalize_provider(row.get("restaurant_name", ""))
        address_raw = row.get("address_order", "") or row.get("address", "")
        normalized.append(
            {
                "order_id": row.get("order_id_order", ""),
                "platform": "MENUSTAR",
                "provider": provider,
                "restaurant_name": row.get("restaurant_name", ""),
                "order_datetime": order_datetime,
                "order_type": normalize_order_type(row.get("order_type", "")),
                "customer_name": row.get("customer_name_order", ""),
                "company_name": "",
                "phone": row.get("phone_order", ""),
                "email": row.get("email_order", ""),
                "address": normalize_address(address_raw) or address_raw,
                "payment_type": normalize_payment_type(row.get("payment_type", "")),
                "subtotal": row.get("subtotal", ""),
                "tax": row.get("tax", ""),
                "tax_withheld": "",
                "tip": row.get("tip", ""),
                "delivery_fee": row.get("delivery_fee", ""),
                "total": row.get("total", ""),
                "item_count": row.get("item_count_order", ""),
                "processing_fee": row.get("processing_fee", ""),
                "commission_fee": row.get("commission_fee", ""),
                "items": row.get("items_order", ""),
                "adjustments": row.get("statement_adjustments", ""),
                "marketing_fee": "",
                "misc_fee": "",
                "errors": "",
                "notes": "",
            }
        )
    return normalized


class MenuStarNormalizer(BaseParser):
    platform = "MENUSTAR"
    provider = ""

    def __init__(self, orders_raw_path: str = "", billings_raw_path: str = "", out_path: str = ""):
        super().__init__(input_path=orders_raw_path, out_path=out_path, billings_raw=billings_raw_path)

    def default_input_path(self) -> str:
        return raw_path("menustar", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("menustar_orders_normalized.csv")

    def resolve_paths(self) -> Tuple[str, str]:
        input_path = self.input_path or self.default_input_path()
        out_path = self.out_path or self.default_out_path()
        return input_path, out_path

    def load_inputs(self, input_path: str) -> Dict[str, pd.DataFrame]:
        billings_path = self.extra.get("billings_raw") or raw_path("menustar", "billings_raw.csv")
        return {
            "orders_raw": load_raw(input_path),
            "billings_raw": load_raw(billings_path),
        }

    def parse_rows(self, inputs: Dict[str, pd.DataFrame]) -> List[Dict[str, str]]:
        rows = merge_rows(inputs["orders_raw"], inputs["billings_raw"])
        return normalize_rows(rows)


def run(orders_raw_path: str, billings_raw_path: str, out_path: str) -> int:
    parser = MenuStarNormalizer(
        orders_raw_path=orders_raw_path,
        billings_raw_path=billings_raw_path,
        out_path=out_path,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize MenuStar raw CSVs.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("menustar", "orders_raw.csv"),
        help="Path to MenuStar orders raw CSV.",
    )
    parser.add_argument(
        "--billings-raw",
        default=raw_path("menustar", "billings_raw.csv"),
        help="Path to MenuStar billings raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("menustar_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_raw, args.billings_raw, args.out)


if __name__ == "__main__":
    main()
