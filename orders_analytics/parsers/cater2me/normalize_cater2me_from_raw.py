#!/usr/bin/env python3
import argparse
import os
from typing import Dict, List, Tuple

import pandas as pd

from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.normalize import normalize_datetime, normalize_order_type
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.schema import build_normalized_row


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def load_cancellations(path: str) -> set[str]:
    if not path or not os.path.exists(path):
        return set()
    df = pd.read_csv(path, dtype=str).fillna("")
    return {str(row.get("order_id", "")).strip() for row in df.to_dict("records") if row.get("order_id")}


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


def normalize_datetime_cater2me(order_date: str, order_time: str) -> str:
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
    return normalize_datetime(
        text,
        formats=(
            "%a %m/%d %Y %H:%M",
            "%a %m/%d %Y",
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y",
            "%m/%d/%y %H:%M",
            "%m/%d/%y",
            "%a %m/%d %y %H:%M",
            "%a %m/%d %y",
        ),
        allow_iso=False,
    )


def merge_raw(orders_raw: pd.DataFrame, billings_raw: pd.DataFrame) -> List[Dict[str, str]]:
    if billings_raw.empty:
        return []
    merged = billings_raw.copy()
    if not orders_raw.empty:
        merged = merged.merge(orders_raw, on="order_id", how="left", suffixes=("", "_order"))
    return merged.to_dict("records")


def normalize_rows(rows: List[Dict[str, str]], cancelled: set[str]) -> List[Dict[str, str]]:
    normalized = []
    for row in rows:
        order_id = str(row.get("order_id", "")).strip()
        if order_id and order_id in cancelled:
            continue
        item_count = max_int(row.get("item_count", ""), row.get("headcount", ""))
        subtotal = row.get("pre_tax", "")
        tip = row.get("tip", "")
        delivery_fee = row.get("adjustments_delivery_fee", "")
        total = ""
        try:
            total_val = float(subtotal or 0) + float(tip or 0) + float(delivery_fee or 0)
            total = f"{total_val:.2f}" if total_val else ""
        except ValueError:
            total = ""
        payout = row.get("order_total_after_adjustments", "") or row.get("order_total", "")
        customer_name = str(row.get("customer_name", "") or "").strip()
        if customer_name.lower() == "nan":
            customer_name = ""
        company_name = str(row.get("company_name", "") or "").strip()
        if company_name.lower() == "nan":
            company_name = ""
        phone = str(row.get("phone", "") or "").strip()
        if phone.lower() == "nan":
            phone = ""
        email = str(row.get("email", "") or "").strip()
        if email.lower() == "nan":
            email = ""
        address = str(row.get("address", "") or "").strip()
        if address.lower() == "nan":
            address = ""
        items = str(row.get("items", "") or "").strip()
        if items.lower() == "nan":
            items = ""

        notes = row.get("adjustments_notes", "") or ""
        if not customer_name and not company_name and not address and not items:
            notes = f"{notes} | missing_order_record".strip(" |")
        normalized.append(
            build_normalized_row(
                Platforms.CATER2ME.upper(),
                order_id=order_id,
                provider=normalize_provider(row.get("restaurant_name", "")),
                restaurant_name=row.get("restaurant_name", ""),
                order_datetime=row.get("order_datetime", "")
                or normalize_datetime_cater2me(
                    row.get("order_date_order", ""),
                    row.get("order_time", ""),
                )
                or normalize_datetime_cater2me(row.get("order_date", ""), row.get("order_time", "")),
                order_type=normalize_order_type(OrderTypes.DELIVERY),
                customer_name=customer_name,
                company_name=company_name,
                phone=phone,
                email=email,
                address=address,
                payment_type=PaymentTypes.CREDIT,
                subtotal=subtotal,
                tax="",
                tax_withheld=calc_tax_withheld(row.get("pre_tax", "")),
                tip=tip,
                delivery_fee=delivery_fee,
                total=total,
                item_count=item_count,
                processing_fee=row.get("processing_fee", ""),
                commission_fee=row.get("service_fee", ""),
                items=items,
                adjustments=row.get("adjustments_total", ""),
                payout=payout,
                errors="",
                notes=notes,
            )
        )
    return normalized


class Cater2MeNormalizer(BaseParser):
    platform = "CATER2ME"
    provider = ""

    def __init__(
        self,
        orders_raw_path: str = "",
        billings_raw_path: str = "",
        out_path: str = "",
        **kwargs,
    ):
        super().__init__(
            input_path=orders_raw_path,
            out_path=out_path,
            billings_raw=billings_raw_path,
            **kwargs,
        )

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
        cancellations_path = self.extra.get("cancellations_raw") or raw_path(
            "cater2me", "cater2me_cancellations.csv"
        )
        return {
            "orders_raw": load_raw(input_path),
            "billings_raw": load_raw(billings_path),
            "cancellations_raw": load_cancellations(cancellations_path),
        }

    def parse_rows(self, inputs: Dict[str, pd.DataFrame]) -> List[Dict[str, str]]:
        rows = merge_raw(inputs["orders_raw"], inputs["billings_raw"])
        return normalize_rows(rows, inputs["cancellations_raw"])


def run(
    orders_raw_path: str,
    billings_raw_path: str,
    out_path: str,
    reset_errors: bool = False,
) -> int:
    parser = Cater2MeNormalizer(
        orders_raw_path=orders_raw_path,
        billings_raw_path=billings_raw_path,
        out_path=out_path,
        reset_errors=reset_errors,
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
