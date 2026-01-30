#!/usr/bin/env python3
import argparse
import os
from datetime import datetime
from typing import Dict, List, Tuple

import pandas as pd

from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.validation import normalize_order_type


def normalize_provider(name: str) -> str:
    text = (name or "").lower()
    if "aroma" in text:
        return "AROMA"
    if "ameci" in text:
        return "AMECI"
    return ""


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def max_int(a: str, b: str) -> str:
    try:
        av = int(float(a))
    except ValueError:
        av = 0
    try:
        bv = int(float(b))
    except ValueError:
        bv = 0
    return str(max(av, bv)) if max(av, bv) else ""


def calc_tax_withheld(subtotal: str, rate: float = 0.0775) -> str:
    try:
        value = float(str(subtotal).replace(",", "").strip())
    except ValueError:
        return ""
    return f"{value * rate:.2f}"


def normalize_datetime(order_date: str, order_time: str) -> str:
    if not order_date:
        return ""
    if not isinstance(order_date, str):
        order_date = str(order_date)
    text = order_date.strip()
    if text.lower() in ("nan", "none"):
        return ""
    if order_time:
        if not isinstance(order_time, str):
            order_time = str(order_time)
        text = f"{text} {order_time.strip()}"
    for fmt in (
        "%a %m/%d %Y %H:%M",
        "%a %m/%d %Y",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%m/%d/%y %H:%M",
        "%m/%d/%y",
        "%a %m/%d %y %H:%M",
        "%a %m/%d %y",
    ):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return text


def merge_raw(orders_raw: pd.DataFrame, billings_raw: pd.DataFrame) -> List[Dict[str, str]]:
    if billings_raw.empty:
        return []
    merged = billings_raw.copy()
    if not orders_raw.empty:
        merged = merged.merge(orders_raw, on="order_id", how="left", suffixes=("", "_order"))
    return merged.to_dict("records")


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized = []
    for row in rows:
        item_count = max_int(row.get("item_count", ""), row.get("headcount", ""))
        normalized.append(
            {
                "order_id": row.get("order_id", ""),
                "platform": "CATER2ME",
                "provider": normalize_provider(row.get("restaurant_name", "")),
                "restaurant_name": row.get("restaurant_name", ""),
                "order_datetime": normalize_datetime(
                    row.get("order_date_order", ""),
                    row.get("order_time", ""),
                )
                or normalize_datetime(row.get("order_date", ""), row.get("order_time", "")),
                "order_type": normalize_order_type("delivery"),
                "customer_name": row.get("customer_name", ""),
                "company_name": row.get("company_name", ""),
                "phone": row.get("phone", ""),
                "email": row.get("email", ""),
                "address": row.get("address", ""),
                "payment_type": "credit",
                "subtotal": row.get("pre_tax", ""),
                "tax": "",
                "tax_withheld": calc_tax_withheld(row.get("pre_tax", "")),
                "tip": row.get("tip", ""),
                "delivery_fee": row.get("adjustments_delivery_fee", ""),
                "total": row.get("order_total", ""),
                "item_count": item_count,
                "processing_fee": row.get("processing_fee", ""),
                "commission_fee": row.get("service_fee", ""),
                "items": row.get("items", ""),
                "adjustments": row.get("adjustments_total", ""),
                "marketing_fee": "",
                "misc_fee": "",
                "errors": "",
                "notes": row.get("adjustments_notes", ""),
            }
        )
    return normalized


class Cater2MeNormalizer(BaseParser):
    platform = "CATER2ME"
    provider = ""

    def __init__(self, orders_raw_path: str = "", billings_raw_path: str = "", out_path: str = ""):
        super().__init__(input_path=orders_raw_path, out_path=out_path, billings_raw=billings_raw_path)

    def default_input_path(self) -> str:
        return raw_path("cater2me", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("cater2me_orders_normalized.csv")

    def resolve_paths(self) -> Tuple[str, str]:
        input_path = self.input_path or self.default_input_path()
        out_path = self.out_path or self.default_out_path()
        return input_path, out_path

    def load_inputs(self, input_path: str) -> Dict[str, pd.DataFrame]:
        billings_path = self.extra.get("billings_raw") or raw_path("cater2me", "billings_raw.csv")
        return {
            "orders_raw": load_raw(input_path),
            "billings_raw": load_raw(billings_path),
        }

    def parse_rows(self, inputs: Dict[str, pd.DataFrame]) -> List[Dict[str, str]]:
        rows = merge_raw(inputs["orders_raw"], inputs["billings_raw"])
        return normalize_rows(rows)


def run(orders_raw_path: str, billings_raw_path: str, out_path: str) -> int:
    parser = Cater2MeNormalizer(
        orders_raw_path=orders_raw_path,
        billings_raw_path=billings_raw_path,
        out_path=out_path,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Cater2Me raw CSVs.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("cater2me", "orders_raw.csv"),
        help="Path to Cater2Me orders raw CSV.",
    )
    parser.add_argument(
        "--billings-raw",
        default=raw_path("cater2me", "billings_raw.csv"),
        help="Path to Cater2Me billings raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("cater2me_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_raw, args.billings_raw, args.out)


if __name__ == "__main__":
    main()
