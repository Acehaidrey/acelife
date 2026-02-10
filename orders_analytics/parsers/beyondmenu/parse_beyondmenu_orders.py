#!/usr/bin/env python3
import argparse
import os
import sys
from typing import Dict, List

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.normalize import (
    normalize_datetime,
    normalize_order_type,
    normalize_payment_type,
    title_with_state,
)
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.schema import build_normalized_row
from orders_analytics.utils.google_sheets import download_sheet_entry
from orders_analytics.utils.google_sheets_registry import SHEETS


def normalize_restaurant(store: str) -> str:
    name = (store or "").lower()
    if "aroma" in name:
        return "Aroma Pizza and Pasta"
    if "ameci" in name:
        return "Ameci Pizza and Pasta"
    return store


def normalize_order_datetime(req_time: str, year: str) -> str:
    if not req_time or not year:
        return ""
    text = f"{req_time.strip()} {year}".replace("  ", " ")
    return normalize_datetime(
        text,
        formats=("%m/%d %I:%M %p %Y", "%m/%d %I:%M%p %Y"),
        allow_iso=False,
    )


def negate_money_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series.replace({"\$": "", ",": ""}, regex=True), errors="coerce")
    negated = numeric * -1
    return negated


def parse_money_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series.replace({"\$": "", ",": ""}, regex=True), errors="coerce")
    return numeric


def format_money(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)




class BeyondMenuOrdersParser(BaseParser):
    platform = "BEYONDMENU"
    dedupe_key = "order_id"
    total_components_fields = (
        "subtotal",
        "tax",
        "tip",
        "delivery_fee",
        "adjustments",
    )

    def default_input_path(self) -> str:
        sheet = SHEETS.get("beyond_menu_order_history")
        if sheet:
            return sheet["out"]
        return raw_path("beyondmenu", "beyond_menu_order_history.csv")

    def default_out_path(self) -> str:
        return normalized_path("beyondmenu_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        sheet = SHEETS.get("beyond_menu_order_history")
        if sheet:
            input_path = sheet["out"]
            try:
                download_sheet_entry(sheet)
            except Exception:
                if not os.path.exists(input_path):
                    raise
        annual_sheet = SHEETS.get("beyond_menu_annual_billing_summary")
        if annual_sheet:
            try:
                download_sheet_entry(annual_sheet)
            except Exception:
                if not os.path.exists(annual_sheet["out"]):
                    raise
        return pd.read_csv(input_path)

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        df = inputs
        df = df.copy()
        # Only keep active orders; inactive are filtered out by design.
        df["Status"] = df["Status"].astype(str).str.strip().str.lower()
        df = df[df["Status"] == "active"].copy()
        df["order_datetime"] = df.apply(
            lambda row: normalize_order_datetime(
                str(row.get("Req Time", "")), str(row.get("year", ""))
            ),
            axis=1,
        )
        df["provider"] = df["Store"].apply(normalize_provider)
        df["restaurant"] = df["Store"].apply(normalize_restaurant)
        df["order_type"] = df["Type"].astype(str).apply(normalize_order_type)
        df["Name"] = df["Name"].fillna("").astype(str).str.title()
        df["Address"] = df["Address"].fillna("").astype(str).apply(title_with_state)

        payment_source = ""
        if "Payment Type" in df.columns:
            payment_source = df.get("Payment Type", "")
        elif "Payment" in df.columns:
            payment_source = df.get("Payment", "")

        if hasattr(payment_source, "apply"):
            payment_series = payment_source.apply(normalize_payment_type)
        else:
            payment_series = pd.Series([PaymentTypes.CREDIT] * len(df))

        df = df.reset_index(drop=True)
        rows: List[Dict[str, str]] = []
        for idx, row in df.iterrows():
            merchant_fee = parse_money_series(pd.Series([row.get("Merchant Fee", "")])).iloc[0]
            commission_fee = parse_money_series(pd.Series([row.get("Commission Fee", "")])).iloc[0]
            misc_fee = parse_money_series(pd.Series([row.get("Misc Fee", "")])).iloc[0]
            convenience_fee = parse_money_series(
                pd.Series(
                    [
                        row.get("Convenience Fee", row.get("convenience_fee", "")),
                    ]
                )
            ).iloc[0]
            payment_type = str(payment_series.iloc[idx] or PaymentTypes.CREDIT)
            if payment_type == PaymentTypes.CASH:
                commission_out = -(commission_fee + merchant_fee)
                processing_out = 0
            else:
                commission_out = -commission_fee
                processing_out = -merchant_fee
            adjustments_value = 0.0
            if "Adjustments" in df.columns:
                adjustments_value = parse_money_series(pd.Series([row.get("Adjustments", "")])).iloc[0]
            if convenience_fee:
                adjustments_value += abs(convenience_fee)
            adjustments_out = format_money(adjustments_value) if adjustments_value else ""
            misc_fee_out = misc_fee + convenience_fee
            rows.append(
                build_normalized_row(
                    Platforms.BEYONDMENU.upper(),
                    order_id=str(row.get("Order #", "")),
                    provider=str(row.get("provider", "")),
                    restaurant_name=str(row.get("restaurant", "")),
                    order_datetime=str(row.get("order_datetime", "")),
                    order_type=str(row.get("order_type", "")),
                    customer_name=str(row.get("Name", "")),
                    phone=str(row.get("Phone", "")),
                    address=str(row.get("Address", "")),
                    payment_type=payment_type,
                    subtotal=str(row.get("Subtotal", "")),
                    tax=str(row.get("Tax", "")),
                    tip=str(row.get("Tip", "")),
                    delivery_fee=str(row.get("Delivery Fee", "")),
                    total=str(row.get("Total", "")),
                    processing_fee=str(processing_out),
                    commission_fee=format_money(commission_out),
                    adjustments=adjustments_out,
                    misc_fee=format_money(misc_fee_out),
                    notes=str(row.get("Notes", "")),
                )
            )
        return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize BeyondMenu order history CSV into standard schema."
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="Path to BeyondMenu_Order_History.csv",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output CSV path",
    )
    args = parser.parse_args()

    runner = BeyondMenuOrdersParser(input_path=args.csv, out_path=args.out)
    stats = runner.run()
    if not stats.rows_written:
        print("No rows parsed.")
        return
    out_path = runner.resolve_paths()[1]
    print(f"Wrote {stats.rows_written} rows to {out_path}")


if __name__ == "__main__":
    main()
