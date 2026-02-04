#!/usr/bin/env python3
import argparse
import os
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.validation import normalize_order_type


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized = []
    for row in rows:
        subtotal = row.get("subtotal", "")
        commission_fee = ""
        processing_fee = ""
        if subtotal:
            try:
                subtotal_val = float(subtotal)
                commission_fee = f"{-(subtotal_val * 0.27):.2f}"
                processing_fee = f"{-(subtotal_val * 0.03):.2f}"
            except ValueError:
                commission_fee = ""
                processing_fee = ""
        normalized.append(
            {
                "order_id": row.get("order_id", ""),
                "platform": "OFFICECATERER",
                "provider": row.get("provider", ""),
                "restaurant_name": row.get("restaurant_name", ""),
                "order_datetime": row.get("order_datetime", ""),
                "order_type": normalize_order_type(row.get("order_type", "")),
                "customer_name": row.get("customer_name", ""),
                "company_name": row.get("company_name", ""),
                "phone": row.get("phone", ""),
                "email": row.get("email", ""),
                "address": row.get("address", ""),
                "address_formatted": "",
                "lat": "",
                "lng": "",
                "payment_type": "credit",
                "subtotal": row.get("subtotal", ""),
                "tax": row.get("tax", ""),
                "tax_withheld": "",
                "tip": row.get("tip", ""),
                "delivery_fee": row.get("delivery_fee", ""),
                "total": row.get("total", ""),
                "item_count": row.get("item_count", ""),
                "processing_fee": processing_fee,
                "commission_fee": commission_fee,
                "items": row.get("items", ""),
                "adjustments": "",
                "marketing_fee": "",
                "misc_fee": "",
                "errors": row.get("errors", ""),
                "notes": row.get("notes", ""),
            }
        )
    return normalized


class OfficeCatererNormalizer(BaseParser):
    platform = "OFFICECATERER"
    provider = ""

    def default_input_path(self) -> str:
        return raw_path("officecaterer", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("officecaterer_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        billings_path = self.extra.get("billings_raw") or raw_path(
            "officecaterer", "billings_raw.csv"
        )
        return {
            "orders_raw": load_raw(input_path),
            "billings_raw": load_raw(billings_path),
        }

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        orders = inputs["orders_raw"].to_dict("records")
        billings = inputs["billings_raw"].to_dict("records")
        if billings:
            billings_map = {str(row.get("order_id", "")).strip(): row for row in billings}
            for row in orders:
                order_id = str(row.get("order_id", "")).strip()
                billing = billings_map.get(order_id)
                if not billing:
                    continue
                mismatches = []
                for field in ("subtotal", "tax"):
                    order_val = row.get(field, "")
                    billing_val = billing.get(field, "")
                    if billing_val:
                        row[field] = billing_val
                    if order_val and billing_val and order_val != billing_val:
                        mismatches.append(
                            f"{field} mismatch (orders={order_val}, billings={billing_val})"
                        )
                if billing.get("restaurant_name") and not row.get("restaurant_name"):
                    row["restaurant_name"] = billing.get("restaurant_name")
                if billing.get("provider") and not row.get("provider"):
                    row["provider"] = billing.get("provider")
                notes = []
                for key in ("statement_date", "period_start", "period_end", "payout", "statement_id"):
                    value = billing.get(key, "")
                    if value:
                        notes.append(f"{key}={value}")
                if notes:
                    row["notes"] = " | ".join([row.get("notes", ""), *notes]).strip(" |")
                if mismatches:
                    row["errors"] = " | ".join([row.get("errors", ""), *mismatches]).strip(" |")
        return normalize_rows(orders)


def run(
    orders_raw_path: str,
    out_path: str,
    reset_errors: bool = False,
    billings_raw_path: str = "",
) -> int:
    parser = OfficeCatererNormalizer(
        input_path=orders_raw_path,
        out_path=out_path,
        billings_raw=billings_raw_path or raw_path("officecaterer", "billings_raw.csv"),
        reset_errors=reset_errors,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Office Caterer raw CSV.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("officecaterer", "orders_raw.csv"),
        help="Path to Office Caterer orders raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("officecaterer_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    parser.add_argument(
        "--billings-raw",
        default=raw_path("officecaterer", "billings_raw.csv"),
        help="Path to Office Caterer billings raw CSV.",
    )
    args = parser.parse_args()
    run(args.orders_raw, args.out, billings_raw_path=args.billings_raw)


if __name__ == "__main__":
    main()
