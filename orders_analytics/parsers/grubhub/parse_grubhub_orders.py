#!/usr/bin/env python3
import argparse
import re
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path, takeout_path
from orders_analytics.utils.grubhub_adjustments import compute_adjustment_total
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.schema import build_normalized_row


NULL_LIKE = {"", "N/A", "n/a", "nan", "NaN"}


def _clean_str(value: str) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text in NULL_LIKE:
        return ""
    return text


def _to_num(value: str) -> float:
    text = _clean_str(value)
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _first_non_empty(values: List[str]) -> str:
    for val in values:
        if val:
            return val
    return ""


def _join_distinct(values: List[str]) -> str:
    return " | ".join(sorted({v for v in values if v}))


def _build_datetime(date_str: str, time_str: str) -> str:
    if " | " in date_str:
        date_str = date_str.split(" | ", 1)[0]
    if " | " in time_str:
        time_str = time_str.split(" | ", 1)[0]
    date_clean = _clean_str(date_str)
    time_clean = _clean_str(time_str)
    if not date_clean:
        return ""
    if "," in time_clean:
        time_clean = time_clean.split(",", 1)[0].strip()
    # Drop trailing timezone abbreviations like PDT/PST to avoid parse warnings.
    time_clean = re.sub(r"\s+(PDT|PST)$", "", time_clean)
    combined = f"{date_clean} {time_clean}".strip()
    parsed = pd.to_datetime(combined, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%dT%H:%M:%S")


class GrubhubOrdersParser(BaseParser):
    platform = Platforms.GRUBHUB.upper()
    total_components_fields = (
        "subtotal",
        "tax",
        "tip",
        "delivery_fee",
        "misc_fee",
        "adjustments",
    )

    def default_input_path(self) -> str:
        return raw_path("grubhub", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("grubhub_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        df = pd.read_csv(input_path, dtype=str).fillna("")
        return {"orders": df}

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        df = inputs["orders"].copy()
        # normalize column names
        df.columns = [c.strip() for c in df.columns]

        # aggregate duplicates by Order ID
        grouped = []
        for order_id, group in df.groupby("ID", dropna=False):
            rows = group.to_dict("records")
            merged_count = len(rows)

            restaurants = [_clean_str(r.get("Restaurant", "")) for r in rows]
            fulfillment_types = [_clean_str(r.get("Fulfillment Type", "")) for r in rows]
            order_types_raw = [_clean_str(r.get("Type", "")) for r in rows]
            descriptions = [_clean_str(r.get("Description", "")) for r in rows]

            date_str = _join_distinct([_clean_str(r.get("Date", "")) for r in rows])
            time_str = _join_distinct([_clean_str(r.get("Time", "")) for r in rows])

            subtotal = sum(_to_num(r.get("Subtotal", "")) for r in rows)
            delivery_fee = sum(_to_num(r.get("Delivery Fee", "")) for r in rows)
            service_fee = sum(_to_num(r.get("Service Fee", "")) for r in rows)
            service_fee_exemption = sum(_to_num(r.get("Service Fee Exemption", "")) for r in rows)
            flexible_fees = sum(_to_num(r.get("(flexible fees)", "")) for r in rows)
            tax_fee = sum(_to_num(r.get("Tax Fee", "")) for r in rows)
            tax_fee_exemption = sum(_to_num(r.get("Tax Fee Exemption", "")) for r in rows)
            tip = sum(_to_num(r.get("Tip", "")) for r in rows)
            total = sum(_to_num(r.get("Restaurant Total", "")) for r in rows)
            commission = sum(_to_num(r.get("Commission", "")) for r in rows)
            gh_plus_commission = sum(_to_num(r.get("GH+ Commission", "")) for r in rows)
            delivery_commission = sum(_to_num(r.get("Delivery Commission", "")) for r in rows)
            processing_fee = sum(_to_num(r.get("Processing Fee", "")) for r in rows)
            withheld_tax = sum(_to_num(r.get("Withheld Tax", "")) for r in rows)
            withheld_tax_exemption = sum(_to_num(r.get("Withheld Tax Exemption", "")) for r in rows)
            targeted_promo = sum(_to_num(r.get("Targeted Promotion", "")) for r in rows)
            rewards = sum(_to_num(r.get("Rewards", "")) for r in rows)

            # computed fields
            tax = tax_fee - tax_fee_exemption
            tax_withheld = withheld_tax + withheld_tax_exemption
            misc_fee = service_fee + service_fee_exemption + flexible_fees
            commission_fee = commission + gh_plus_commission + delivery_commission
            marketing_fee = targeted_promo + rewards

            order_id_clean = _clean_str(order_id)
            has_adjustment_rows, adjustment_total = compute_adjustment_total(order_id_clean, rows)

            restaurant = _join_distinct(restaurants)
            provider = normalize_provider(restaurant)

            fulfillment = _join_distinct(fulfillment_types).lower()
            order_type = ""
            notes: List[str] = []
            if merged_count > 1:
                notes.append(f"merged_rows={merged_count}")
            if has_adjustment_rows:
                notes.append(f"adjustment_total={adjustment_total:.2f}")
            if fulfillment == "self delivery":
                order_type = OrderTypes.DELIVERY
            elif fulfillment == "pick-up":
                order_type = OrderTypes.PICKUP
            elif fulfillment == "grubhub delivery":
                order_type = OrderTypes.PICKUP
                notes.append("grubhub_delivery")
            elif fulfillment:
                notes.append(f"fulfillment_type_raw={fulfillment}")

            order_type_raw = _join_distinct(order_types_raw)
            payment_type = ""
            if order_type_raw.lower() == "prepaid order":
                payment_type = PaymentTypes.CREDIT
            elif order_type_raw:
                notes.append(f"payment_type_raw={order_type_raw}")

            description = _join_distinct(descriptions)
            if description:
                notes.append(description)

            order_datetime = _build_datetime(date_str, time_str)

            grouped.append(build_normalized_row(
                Platforms.GRUBHUB.upper(),
                order_id=order_id_clean,
                provider=provider,
                restaurant_name=restaurant,
                order_datetime=order_datetime,
                order_type=order_type,
                payment_type=payment_type,
                subtotal=f"{subtotal:.2f}" if subtotal else "",
                tax=f"{tax:.2f}" if tax else "",
                tax_withheld=f"{tax_withheld:.2f}" if tax_withheld else "",
                tip=f"{tip:.2f}" if tip else "",
                delivery_fee=f"{delivery_fee:.2f}" if delivery_fee else "",
                total=f"{total:.2f}" if total else "",
                commission_fee=f"{commission_fee:.2f}" if commission_fee else "",
                processing_fee=f"{processing_fee:.2f}" if processing_fee else "",
                marketing_fee=f"{marketing_fee:.2f}" if marketing_fee else "",
                misc_fee=f"{misc_fee:.2f}" if misc_fee else "",
                adjustments=f"{adjustment_total:.2f}" if adjustment_total else "",
                payout="",
                notes=" | ".join([n for n in notes if n]),
            ))

        return grouped


def run(input_path: str, out_path: str) -> int:
    parser = GrubhubOrdersParser(input_path=input_path, out_path=out_path)
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse Grubhub CSV to normalized output.")
    parser.add_argument(
        "--input",
        default=raw_path("grubhub", "orders_raw.csv"),
        help="Input Grubhub CSV path.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("grubhub_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.input, args.out)


if __name__ == "__main__":
    main()
