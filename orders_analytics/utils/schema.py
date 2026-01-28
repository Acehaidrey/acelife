from __future__ import annotations

import csv
import os
from typing import Dict, Iterable, List

CANONICAL_COLUMNS: List[str] = [
    "order_id",
    "platform",
    "provider",
    "order_datetime",
    "order_type",
    "customer_name",
    "phone",
    "email",
    "address",
    "payment_type",
    "restaurant_name",
    "items",
    "item_count",
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
