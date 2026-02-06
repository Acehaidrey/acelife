from __future__ import annotations

import csv
import os
from typing import Dict, Iterable, List
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CANONICAL_COLUMNS: List[str] = [
    "order_id",
    "platform",
    "provider",
    "order_datetime",
    "order_type",
    "payment_type",
    "subtotal",
    "tax",
    "tax_withheld",
    "tip",
    "delivery_fee",
    "total",
    "processing_fee",
    "commission_fee",
    "adjustments",
    "marketing_fee",
    "misc_fee",
    "payout",
    "expected_payout",
    "customer_name",
    "company_name",
    "phone",
    "email",
    "address",
    "address_formatted",
    "lat",
    "lng",
    "restaurant_name",
    "items",
    "item_count",
    "errors",
    "notes",
]


def canonicalize_row(row: Dict[str, str]) -> Dict[str, str]:
    return {col: row.get(col, "") for col in CANONICAL_COLUMNS}


def canonicalize_rows(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    return [canonicalize_row(row) for row in rows]


def canonicalize_dataframe(df):
    return df.reindex(columns=CANONICAL_COLUMNS, fill_value="")


def write_normalized_rows(rows: Iterable[Dict[str, str]], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_COLUMNS)
        writer.writeheader()
        for row in canonicalize_rows(rows):
            writer.writerow(row)


def build_normalized_row(platform: str, **kwargs: str) -> Dict[str, str]:
    unknown = [key for key in kwargs.keys() if key not in CANONICAL_COLUMNS]
    if unknown:
        raise KeyError(f"Unknown normalized fields: {', '.join(sorted(unknown))}")
    row = {col: "" for col in CANONICAL_COLUMNS}
    row["platform"] = platform
    for key, value in kwargs.items():
        row[key] = "" if value is None else value
    return row


def compute_expected_payout(row: Dict[str, str]) -> str:
    def to_decimal(value: str):
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return Decimal(text.replace("$", "").replace(",", ""))
        except InvalidOperation:
            return None

    subtotal = to_decimal(row.get("subtotal", ""))
    tax = to_decimal(row.get("tax", ""))
    tip = to_decimal(row.get("tip", ""))
    delivery_fee = to_decimal(row.get("delivery_fee", ""))
    adjustments = to_decimal(row.get("adjustments", ""))
    commission_fee = to_decimal(row.get("commission_fee", ""))
    processing_fee = to_decimal(row.get("processing_fee", ""))
    marketing_fee = to_decimal(row.get("marketing_fee", ""))
    misc_fee = to_decimal(row.get("misc_fee", ""))

    values = [
        subtotal,
        tax,
        tip,
        delivery_fee,
        adjustments,
        commission_fee,
        processing_fee,
        marketing_fee,
        misc_fee,
    ]
    if all(v is None for v in values):
        return ""

    expected = Decimal("0.00")
    if subtotal is not None:
        expected += subtotal
    if tax is not None:
        expected += tax
    if tip is not None:
        expected += tip
    if delivery_fee is not None:
        expected += delivery_fee
    if adjustments is not None:
        expected += adjustments
    for fee in (commission_fee, processing_fee, marketing_fee, misc_fee):
        if fee is not None:
            expected += fee
    return f"{expected.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
