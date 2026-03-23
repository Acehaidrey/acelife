#!/usr/bin/env python3
import argparse
import os
import sys
from decimal import Decimal, InvalidOperation
from typing import Dict, List

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_datetime, normalize_money
from orders_analytics.utils.order_types import OrderTypes


def load_adjustments() -> Dict[str, Dict[str, str]]:
    path = raw_path("fooda", "adjustments.csv")
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path, dtype=str).fillna("")
    overrides: Dict[str, Dict[str, str]] = {}
    for _, row in df.iterrows():
        order_id = str(row.get("order_id", "")).strip()
        if order_id:
            overrides[order_id] = {str(k): str(v).strip() for k, v in row.items()}
    return overrides


def load_company_info() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for filename in ("orders_company_raw.csv", "orders_company_overrides.csv"):
        path = raw_path("fooda", filename)
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path, dtype=str).fillna("")
        for _, row in df.iterrows():
            event_id = (
                str(row.get("event_number_normalized", "")).strip()
                or normalized_section_event_id(str(row.get("order_id", "")).strip())
            )
            company_name = str(row.get("company_name", "")).strip()
            if event_id and company_name:
                mapping[event_id] = company_name
    return mapping


def parse_date(value: str) -> str:
    return normalize_datetime(
        value,
        formats=("%m/%d/%Y", "%m/%d/%y"),
        allow_iso=False,
    )


def parse_year(value: str) -> str:
    normalized = parse_date(value)
    return normalized[:4] if normalized else ""


def to_decimal(value: str) -> Decimal:
    text = str(value or "").strip()
    if not text:
        return Decimal("0.00")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0.00")


def normalized_section_event_id(section_ref: str) -> str:
    text = str(section_ref or "").strip()
    if text.startswith("MS_"):
        parts = text.split("_")
        if len(parts) >= 2:
            return parts[1].lstrip("0") or "0"
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.lstrip("0") or "0"


def sum_money(*values: str) -> str:
    total = Decimal("0.00")
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            total += Decimal(text)
        except InvalidOperation:
            continue
    return str(total.quantize(Decimal("0.01")))


def is_nonzero_money(value: str) -> bool:
    normalized = normalize_money(value)
    return bool(normalized and normalized != "0.00")


class FoodaOrdersParser(BaseParser):
    platform = "FOODA"
    dedupe_key = "order_id"
    total_components_fields = (
        "subtotal",
        "tax",
        "tip",
        "delivery_fee",
    )

    def default_input_path(self) -> str:
        return raw_path("fooda", "fooda_sales.csv")

    def default_out_path(self) -> str:
        return normalized_path("fooda_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return pd.read_csv(input_path, encoding="utf-16", sep="\t", dtype=str).fillna("")

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        df = inputs.copy()
        adjustments_overrides = load_adjustments()
        company_info = load_company_info()
        df["Restaurant Name"] = df["Restaurant Name"].astype(str)
        df["Product"] = df["Product"].astype(str)
        df = df[df["Restaurant Name"].str.strip().str.lower() != "grand total"].copy()

        rows: List[Dict[str, str]] = []
        for _, row in df.iterrows():
            section_ref = str(row.get("Section Reference", "")).strip()
            if not section_ref:
                continue
            restaurant = str(row.get("Restaurant Name", "")).strip()
            product = str(row.get("Product", "")).strip().lower()
            order_datetime = parse_date(row.get("Event date", ""))
            order_year = parse_year(row.get("Event date", ""))
            company_name = company_info.get(normalized_section_event_id(section_ref), "")

            food_sales = normalize_money(row.get("Food sales (excludes Tax)", "")) or "0.00"
            tax = (
                normalize_money(row.get("Tax", ""))
                or normalize_money(row.get("Tax (Restaurant to remit)", ""))
                or "0.00"
            )
            original_tax = tax
            tax_withheld = normalize_money(row.get("Tax (Fooda to remit)", "")) or "0.00"
            subsidy = normalize_money(row.get("Subsidy", "")) or "0.00"
            commission_fee = normalize_money(
                row.get("Fooda Commission plus Additional Event Fees", "")
            ) or "0.00"
            processing_fee = normalize_money(row.get("Payment Processing Fees", "")) or "0.00"
            adjustments = sum_money(
                normalize_money(row.get("Other Fees", "")) or "0.00",
                normalize_money(row.get("Restaurant Fee Tax", "")) or "0.00",
            )

            if is_nonzero_money(subsidy):
                subtotal = food_sales
                delivery_fee = sum_money(subsidy, f"-{food_sales}", f"-{tax}")
                total = subsidy
            else:
                subtotal = sum_money(food_sales, tax)
                tax = "0.00"
                delivery_fee = "0.00"
                total = subtotal

            if order_year == "2020" and tax == "0.00":
                tax_withheld = sum_money(Decimal(subtotal) * Decimal("0.0775"))
            if order_year == "2020" and Decimal(subtotal) >= Decimal("20.00"):
                subtotal = sum_money(subtotal, "-20.00")
                delivery_fee = sum_money(delivery_fee, "20.00")

            notes = []
            if product:
                notes.append(f"product={product}")
            if is_nonzero_money(subsidy):
                notes.append("delivery_fee_inferred_from_subsidy")
            if order_year == "2020":
                notes.append("delivery_fee_base_20")
            if order_year == "2020" and tax == "0.00" and tax_withheld != "0.00":
                notes.append("tax_withheld_inferred_from_subtotal")
            payment_date = str(row.get("Payment Date", "")).strip()
            if payment_date:
                notes.append(f"payment_date={payment_date}")
            payout = normalize_money(row.get("Paid to Restaurant", ""))

            if product == "catering":
                override = adjustments_overrides.get(section_ref, {})
                if override:
                    delivery_fee = normalize_money(override.get("delivery_fee", "")) or delivery_fee
                    override_adjustments = normalize_money(override.get("adjustments", ""))
                    if override_adjustments:
                        adjustments = override_adjustments
                    if str(override.get("move_delivery_fee_to_adjustments", "")).strip().lower() in {
                        "1",
                        "true",
                        "yes",
                    }:
                        adjustments = sum_money(adjustments, delivery_fee)
                        delivery_fee = "0.00"
                    notes_append = str(override.get("notes_append", "")).strip()
                    if notes_append:
                        notes.append(notes_append)

                rows.append(
                    {
                        "order_id": section_ref,
                        "platform": "FOODA",
                        "provider": "FOODA",
                        "restaurant_name": restaurant,
                        "order_datetime": order_datetime,
                        "order_type": OrderTypes.DELIVERY,
                        "customer_name": "",
                        "company_name": company_name,
                        "phone": "",
                        "email": "",
                        "address": "",
                        "address_formatted": "",
                        "lat": "",
                        "lng": "",
                        "payment_type": "credit",
                        "subtotal": subtotal,
                        "tax": tax,
                        "tax_withheld": tax_withheld,
                        "tip": "0.00",
                        "delivery_fee": delivery_fee,
                        "total": total,
                        "item_count": "",
                        "processing_fee": processing_fee,
                        "commission_fee": commission_fee,
                        "items": "",
                        "adjustments": adjustments,
                        "marketing_fee": "0.00",
                        "misc_fee": "0.00",
                        "payout": payout or "0.00",
                        "errors": "",
                        "notes": " | ".join(notes),
                    }
                )
                continue

            if product != "popup" or order_year != "2020":
                continue

            food_sales_dec = to_decimal(food_sales)
            tax_dec = to_decimal(original_tax)
            tax_fee_dec = to_decimal(normalize_money(row.get("Restaurant Fee Tax", "")) or "0.00")
            total_dec = food_sales_dec + tax_dec
            cash_total_dec = to_decimal(normalize_money(row.get("Cash Collected by Restaurant", "")) or "0.00")
            cash_total_dec = min(max(cash_total_dec, Decimal("0.00")), total_dec)
            if total_dec > Decimal("0.00"):
                cash_tax_dec = ((tax_dec * cash_total_dec) / total_dec).quantize(Decimal("0.01"))
            else:
                cash_tax_dec = Decimal("0.00")
            cash_subtotal_dec = (cash_total_dec - cash_tax_dec).quantize(Decimal("0.01"))
            credit_subtotal_dec = (food_sales_dec - cash_subtotal_dec).quantize(Decimal("0.01"))
            credit_tax_dec = (tax_dec - cash_tax_dec + tax_fee_dec).quantize(Decimal("0.01"))
            rewards_dec = to_decimal(normalize_money(row.get("Rewards Coupons", "")) or "0.00")
            coupons_dec = to_decimal(normalize_money(row.get("Coupons", "")) or "0.00")
            unpaid_dec = to_decimal(normalize_money(row.get("Unpaid Orders", "")) or "0.00")
            credit_subtotal_dec = (credit_subtotal_dec + coupons_dec).quantize(Decimal("0.01"))
            popup_marketing_fee = str((-(rewards_dec + coupons_dec)).quantize(Decimal("0.01")))
            popup_adjustments = (
                str((-abs(unpaid_dec)).quantize(Decimal("0.01")))
                if unpaid_dec != Decimal("0.00")
                else "0.00"
            )

            common_popup_notes = [f"product={product}", "popup_2020_split"]
            if rewards_dec != Decimal("0.00"):
                common_popup_notes.append(
                    f"rewards_coupons={rewards_dec.quantize(Decimal('0.01'))}"
                )
            if coupons_dec != Decimal("0.00"):
                common_popup_notes.append(f"coupons={coupons_dec.quantize(Decimal('0.01'))}")
            if unpaid_dec != Decimal("0.00"):
                common_popup_notes.append(
                    f"unpaid_orders={unpaid_dec.quantize(Decimal('0.01'))}"
                )
            if payment_date:
                common_popup_notes.append(f"payment_date={payment_date}")

            if cash_total_dec > Decimal("0.00"):
                rows.append(
                    {
                        "order_id": f"{section_ref}|CASH",
                        "platform": "FOODA",
                        "provider": "FOODA",
                        "restaurant_name": restaurant,
                        "order_datetime": order_datetime,
                        "order_type": OrderTypes.PICKUP,
                        "customer_name": "",
                        "company_name": company_name,
                        "phone": "",
                        "email": "",
                        "address": "",
                        "address_formatted": "",
                        "lat": "",
                        "lng": "",
                        "payment_type": "cash",
                        "subtotal": str(cash_subtotal_dec),
                        "tax": str(cash_tax_dec),
                        "tax_withheld": "0.00",
                        "tip": "0.00",
                        "delivery_fee": "0.00",
                        "total": str(cash_total_dec.quantize(Decimal("0.01"))),
                        "item_count": "",
                        "processing_fee": "0.00",
                        "commission_fee": "0.00",
                        "items": "",
                        "adjustments": "0.00",
                        "marketing_fee": "0.00",
                        "misc_fee": "0.00",
                        "payout": str(cash_total_dec.quantize(Decimal("0.01"))),
                        "errors": "",
                        "notes": " | ".join(common_popup_notes + ["popup_cash_component"]),
                    }
                )

            rows.append(
                {
                    "order_id": f"{section_ref}|CREDIT",
                    "platform": "FOODA",
                    "provider": "FOODA",
                    "restaurant_name": restaurant,
                    "order_datetime": order_datetime,
                    "order_type": OrderTypes.PICKUP,
                    "customer_name": "",
                    "company_name": company_name,
                    "phone": "",
                    "email": "",
                    "address": "",
                    "address_formatted": "",
                    "lat": "",
                    "lng": "",
                    "payment_type": "credit",
                    "subtotal": str(credit_subtotal_dec),
                    "tax": str(credit_tax_dec),
                    "tax_withheld": "0.00",
                    "tip": "0.00",
                    "delivery_fee": "0.00",
                    "total": str((credit_subtotal_dec + credit_tax_dec).quantize(Decimal("0.01"))),
                    "item_count": "",
                    "processing_fee": processing_fee,
                    "commission_fee": commission_fee,
                    "items": "",
                    "adjustments": popup_adjustments,
                    "marketing_fee": popup_marketing_fee,
                    "misc_fee": normalize_money(row.get("Other Fees", "")) or "0.00",
                    "payout": payout or "0.00",
                    "errors": "",
                    "notes": " | ".join(common_popup_notes + ["popup_credit_component"]),
                }
            )
        return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Fooda sales CSV.")
    parser.add_argument("--csv", default=None, help="Path to Fooda sales CSV.")
    parser.add_argument("--out", default=None, help="Output normalized CSV path.")
    args = parser.parse_args()

    runner = FoodaOrdersParser(input_path=args.csv, out_path=args.out)
    stats = runner.run()
    if not stats.rows_written:
        print("No rows parsed.")
        return
    out_path = runner.resolve_paths()[1]
    print(f"Wrote {stats.rows_written} rows to {out_path}")


if __name__ == "__main__":
    main()
