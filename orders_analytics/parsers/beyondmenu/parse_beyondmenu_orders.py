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
)
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.schema import build_normalized_row
from orders_analytics.utils.google_sheets import download_sheet_entry
from orders_analytics.utils.google_sheets_registry import SHEETS


def parse_float(value) -> float:
    try:
        if pd.isna(value):
            return 0.0
    except TypeError:
        pass
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def allocate_amount(amount: float, weights: List[float]) -> List[float]:
    if not weights:
        return []
    total_weight = sum(weights)
    if total_weight <= 0:
        base = round(amount / len(weights), 2)
        alloc = [base] * len(weights)
    else:
        alloc = [round(amount * (w / total_weight), 2) for w in weights]
    remainder = round(amount - sum(alloc), 2)
    cents = int(round(remainder * 100))
    step = 0.01 if cents > 0 else -0.01
    for idx in range(abs(cents)):
        alloc_idx = idx % len(alloc)
        alloc[alloc_idx] = round(alloc[alloc_idx] + step, 2)
    return alloc


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
def normalize_notes(value) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return ""
    return text




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
        annual_path = annual_sheet["out"] if annual_sheet else ""
        return {
            "orders": pd.read_csv(input_path),
            "annual": pd.read_csv(annual_path) if annual_path and os.path.exists(annual_path) else pd.DataFrame(),
        }

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        df = inputs["orders"]
        annual_df = inputs.get("annual", pd.DataFrame()).copy()
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
        df["Address"] = df["Address"].fillna("").astype(str)

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
        row_years: List[int] = []
        row_providers: List[str] = []
        row_order_ids: List[str] = []
        row_subtotals: List[float] = []
        row_convenience_fees: List[float] = []
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
                commission_out = -commission_fee
                processing_out = 0
            else:
                commission_out = -commission_fee
                processing_out = -merchant_fee
            adjustments_value = 0.0
            if "Adjustments" in df.columns:
                adjustments_value = parse_money_series(pd.Series([row.get("Adjustments", "")])).iloc[0]
            if convenience_fee:
                adjustments_value += -convenience_fee
            adjustments_out = format_money(adjustments_value) if adjustments_value else ""
            misc_fee_out = misc_fee + convenience_fee
            provider = str(row.get("provider", ""))
            order_id = str(row.get("Order #", ""))
            year_val = int(parse_float(row.get("year", 0)))
            row_years.append(year_val)
            row_providers.append(provider)
            row_order_ids.append(order_id)
            row_subtotals.append(parse_float(row.get("Subtotal", 0)))
            row_convenience_fees.append(convenience_fee)
            rows.append(
                build_normalized_row(
                    Platforms.BEYONDMENU.upper(),
                    order_id=order_id,
                    provider=provider,
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
                    notes=normalize_notes(row.get("Notes", "")),
                )
            )

        if not annual_df.empty:
            annual = annual_df.copy()
            annual["provider"] = annual.get("Provider", "").apply(normalize_provider)
            annual["year"] = pd.to_numeric(annual.get("Year", ""), errors="coerce").fillna(0).astype(int)
            annual["additional_charges"] = parse_money_series(
                annual.get("Additional Charges", pd.Series(["0"] * len(annual)))
            )
            annual["credits"] = parse_money_series(
                annual.get("Credits", pd.Series(["0"] * len(annual)))
            )
            annual_map = {
                (str(row.get("provider", "")), int(row.get("year", 0))): {
                    "additional": float(row.get("additional_charges", 0.0)),
                    "credits": float(row.get("credits", 0.0)),
                }
                for _, row in annual.iterrows()
            }

            def net_adjustment(provider: str, year: int) -> float:
                data = annual_map.get((provider, year), {"additional": 0.0, "credits": 0.0})
                return -float(data.get("additional", 0.0) + data.get("credits", 0.0))

            aroma_2024 = annual_map.get(("AROMA", 2024), {"additional": 0.0, "credits": 0.0})
            aroma_2023 = annual_map.get(("AROMA", 2023), {"additional": 0.0, "credits": 0.0})
            aroma_2023_override = -float(aroma_2023.get("additional", 0.0) + aroma_2024.get("credits", 0.0))
            aroma_2024_override = -float(aroma_2024.get("additional", 0.0))  # credits handled in 2023 override

            allocations: Dict[int, float] = {}
            notes_additions: Dict[int, str] = {}
            for (provider, year), _vals in annual_map.items():
                target_amount = net_adjustment(provider, year)
                special_note = "additional_charges_distribution"
                if provider == "AROMA" and year == 2023:
                    target_amount = aroma_2023_override
                if provider == "AROMA" and year == 2024:
                    target_amount = aroma_2024_override
                    special_note = "partial_additional_charges_distribution"

                if abs(target_amount) < 0.005:
                    continue

                idxs = [
                    idx
                    for idx, (p, y) in enumerate(zip(row_providers, row_years))
                    if p == provider and y == year
                ]
                if provider == "AROMA" and year == 2024:
                    filtered = [idx for idx in idxs if row_order_ids[idx] != "101559574"]
                    if filtered:
                        idxs = filtered

                if not idxs:
                    continue
                weights = [row_subtotals[idx] for idx in idxs]
                alloc = allocate_amount(target_amount, weights)
                for idx, amt in zip(idxs, alloc):
                    allocations[idx] = allocations.get(idx, 0.0) + amt
                    notes_additions[idx] = special_note

            for idx, amt in allocations.items():
                current = parse_float(rows[idx].get("misc_fee", ""))
                new_val = current + amt
                rows[idx]["misc_fee"] = format_money(new_val) if abs(new_val) >= 0.005 else ""
                note = notes_additions.get(idx, "")
                if note:
                    existing_notes = normalize_notes(rows[idx].get("notes", ""))
                    if note not in existing_notes:
                        rows[idx]["notes"] = (existing_notes + " | " + note).strip(" | ")
            for idx, fee in enumerate(row_convenience_fees):
                if abs(parse_float(fee)) >= 0.005:
                    existing_notes = normalize_notes(rows[idx].get("notes", ""))
                    note = f"convenience_fee={format_money(fee)}"
                    if note not in existing_notes:
                        rows[idx]["notes"] = (existing_notes + " | " + note).strip(" | ")
        return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize BeyondMenu order history CSV into standard schema."
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="Path to beyondmenu_order_history.csv",
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
