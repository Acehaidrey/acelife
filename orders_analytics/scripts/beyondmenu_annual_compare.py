#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from typing import List

import pandas as pd

from orders_analytics.utils.constants import raw_path
from orders_analytics.utils.google_sheets import download_sheet_entry
from orders_analytics.utils.google_sheets_registry import SHEETS
from orders_analytics.utils.providers import normalize_provider


MONEY_COLUMNS = ["Subtotal", "Tax", "Tip", "Delivery Fee", "Total", "Convenience Fee"]


def parse_money(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False)
    return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)


def load_sheet(sheet_key: str, fallback_path: str) -> pd.DataFrame:
    sheet = SHEETS.get(sheet_key)
    path = sheet["out"] if sheet else fallback_path
    if sheet:
        try:
            download_sheet_entry(sheet)
        except Exception:
            if not os.path.exists(path):
                raise
    return pd.read_csv(path, dtype=str).fillna("")


def find_fee_column(df: pd.DataFrame, needle: str) -> str | None:
    needle_lower = needle.lower()
    for col in df.columns:
        if needle_lower in col.lower():
            return col
    return None


def prepare_orders(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    if "Store" not in data.columns:
        raise ValueError("Order history is missing 'Store' column.")
    data["provider"] = data["Store"].apply(normalize_provider)
    data["year"] = pd.to_numeric(data.get("year", ""), errors="coerce")
    data["status"] = data.get("Status", "").astype(str).str.strip().str.lower()
    data["is_active"] = data["status"] == "active"
    for col in MONEY_COLUMNS:
        if col not in data.columns:
            data[col] = 0.0
        data[col] = parse_money(data[col])

    for col in ["Commission Fee", "Merchant Fee"]:
        if col not in data.columns:
            data[col] = 0.0
        data[col] = parse_money(data[col])

    phone_fee_col = find_fee_column(data, "phone fee")
    fax_fee_col = find_fee_column(data, "fax fee")
    if phone_fee_col:
        data["Phone Fee"] = parse_money(data[phone_fee_col])
    else:
        data["Phone Fee"] = 0.0
    if fax_fee_col:
        data["Fax Fee"] = parse_money(data[fax_fee_col])
    else:
        data["Fax Fee"] = 0.0

    return data


def prepare_billing(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    if "Provider" not in data.columns:
        raise ValueError("Annual billing summary is missing 'Provider' column.")
    data["provider"] = data["Provider"].apply(normalize_provider)
    data["year"] = pd.to_numeric(data.get("Year", ""), errors="coerce")

    data["billing_total_count"] = pd.to_numeric(data.get("Order Count", ""), errors="coerce").fillna(0.0)
    data["billing_void_count"] = pd.to_numeric(data.get("Void Count", ""), errors="coerce").fillna(0.0)
    data["billing_active_count"] = (data["billing_total_count"] - data["billing_void_count"]).clip(lower=0)
    data["billing_total_count"] = data["billing_active_count"] + data["billing_void_count"]

    data["billing_subtotal_sum"] = parse_money(data.get("Order Subtotals", 0.0))
    data["billing_tax_sum"] = parse_money(data.get("Taxes", 0.0))
    data["billing_tip_sum"] = parse_money(data.get("Tips", 0.0))
    data["billing_delivery_fee_sum"] = parse_money(data.get("Delivery Fees", 0.0))
    data["billing_total_sum"] = parse_money(data.get("Order Amount Total", 0.0))
    data["billing_commission_fee_sum"] = parse_money(data.get("Order Commissions", 0.0))
    data["billing_fax_fee_sum"] = parse_money(data.get("Fax Fees", 0.0))
    data["billing_phone_fee_sum"] = parse_money(data.get("Phone Fees", 0.0))
    data["billing_processing_total_sum"] = parse_money(data.get("CC Processing Fee", 0.0))
    data["billing_commission_total_sum"] = (
        data["billing_commission_fee_sum"]
        + data["billing_fax_fee_sum"]
        + data["billing_phone_fee_sum"]
    )
    return data


def aggregate(df: pd.DataFrame, label: str) -> pd.DataFrame:
    active = df[df["is_active"]].copy()
    grouped = active.groupby(["provider", "year"], dropna=False).agg(
        active_count=("is_active", "size"),
        subtotal_sum=("Subtotal", "sum"),
        tax_sum=("Tax", "sum"),
        tip_sum=("Tip", "sum"),
        delivery_fee_sum=("Delivery Fee", "sum"),
        total_sum=("Total", "sum"),
        convenience_fee_sum=("Convenience Fee", "sum"),
        commission_fee_sum=("Commission Fee", "sum"),
        merchant_fee_sum=("Merchant Fee", "sum"),
        phone_fee_sum=("Phone Fee", "sum"),
        fax_fee_sum=("Fax Fee", "sum"),
    )
    counts = df.groupby(["provider", "year"], dropna=False).agg(
        total_count=("is_active", "size"),
        void_count=("is_active", lambda s: (~s).sum()),
    )
    merged = grouped.join(counts, how="outer").reset_index()
    for col in [
        "active_count",
        "subtotal_sum",
        "tax_sum",
        "tip_sum",
        "delivery_fee_sum",
        "total_sum",
        "convenience_fee_sum",
        "commission_fee_sum",
        "merchant_fee_sum",
        "phone_fee_sum",
        "fax_fee_sum",
        "total_count",
        "void_count",
    ]:
        if col not in merged.columns:
            merged[col] = 0
    merged = merged.fillna(0)
    numeric_cols = [
        "active_count",
        "subtotal_sum",
        "tax_sum",
        "tip_sum",
        "delivery_fee_sum",
        "total_sum",
        "convenience_fee_sum",
        "commission_fee_sum",
        "merchant_fee_sum",
        "phone_fee_sum",
        "fax_fee_sum",
        "total_count",
        "void_count",
    ]
    for col in numeric_cols:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0.0)
    merged["total_count"] = merged["active_count"] + merged["void_count"]

    merged["commission_total_sum"] = (
        merged["commission_fee_sum"] + merged["phone_fee_sum"] + merged["fax_fee_sum"]
    )
    merged["processing_total_sum"] = merged["merchant_fee_sum"]
    merged["total_net_sum"] = merged["total_sum"] + merged["convenience_fee_sum"]

    merged = merged.rename(
        columns={
            "total_count": f"{label}_total_count",
            "active_count": f"{label}_active_count",
            "void_count": f"{label}_void_count",
            "subtotal_sum": f"{label}_subtotal_sum",
            "tax_sum": f"{label}_tax_sum",
            "tip_sum": f"{label}_tip_sum",
            "delivery_fee_sum": f"{label}_delivery_fee_sum",
            "total_sum": f"{label}_total_sum",
            "convenience_fee_sum": f"{label}_convenience_fee_sum",
            "commission_fee_sum": f"{label}_commission_fee_sum",
            "merchant_fee_sum": f"{label}_merchant_fee_sum",
            "phone_fee_sum": f"{label}_phone_fee_sum",
            "fax_fee_sum": f"{label}_fax_fee_sum",
            "commission_total_sum": f"{label}_commission_total_sum",
            "processing_total_sum": f"{label}_processing_total_sum",
            "total_net_sum": f"{label}_total_net_sum",
        }
    )
    return merged


def compare(orders: pd.DataFrame, billing: pd.DataFrame, tol: float = 0.01) -> pd.DataFrame:
    merged = orders.merge(billing, on=["provider", "year"], how="outer")
    merged = merged.fillna(0)

    def diff(col: str) -> pd.Series:
        return (merged[f"orders_{col}"] - merged[f"billing_{col}"]).round(2)

    merged["diff_total_count"] = (merged["orders_active_count"] - merged["billing_total_count"]).round(2)
    merged["diff_void_count"] = diff("void_count")
    merged["diff_subtotal"] = diff("subtotal_sum")
    merged["diff_tax"] = diff("tax_sum")
    merged["diff_tip"] = diff("tip_sum")
    merged["diff_delivery_fee"] = diff("delivery_fee_sum")
    merged["diff_total"] = (merged["orders_total_net_sum"] - merged["billing_total_sum"]).round(2)
    merged["diff_commission_total"] = diff("commission_total_sum")
    merged["diff_processing_total"] = diff("processing_total_sum")

    merged["match_total_count"] = merged["diff_total_count"] == 0
    merged["match_void_count"] = merged["diff_void_count"] == 0
    for field in ["subtotal", "tax", "tip", "delivery_fee", "total", "commission_total", "processing_total"]:
        merged[f"match_{field}"] = merged[f"diff_{field}"].abs() <= tol

    merged["all_match"] = (
        merged["match_total_count"]
        & merged["match_void_count"]
        & merged["match_subtotal"]
        & merged["match_tax"]
        & merged["match_tip"]
        & merged["match_delivery_fee"]
        & merged["match_total"]
        & merged["match_commission_total"]
        & merged["match_processing_total"]
    )
    merged = merged.sort_values(["provider", "year"]).reset_index(drop=True)
    numeric_cols = merged.select_dtypes(include=["number"]).columns
    merged[numeric_cols] = merged[numeric_cols].round(2)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare BeyondMenu order history vs annual billing summary by year/provider."
    )
    parser.add_argument(
        "--orders",
        default=raw_path("beyondmenu", "beyond_menu_order_history.csv"),
        help="Orders history CSV path.",
    )
    parser.add_argument(
        "--billing",
        default=raw_path("beyondmenu", "beyond_menu_annual_billing_summary.csv"),
        help="Annual billing summary CSV path.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("beyondmenu", "beyondmenu_annual_billing_check.csv"),
        help="Output comparison CSV path.",
    )
    args = parser.parse_args()

    orders_df = load_sheet("beyond_menu_order_history", args.orders)
    billing_df = load_sheet("beyond_menu_annual_billing_summary", args.billing)

    orders_ready = prepare_orders(orders_df)
    billing_ready = prepare_billing(billing_df)

    orders_agg = aggregate(orders_ready, "orders")
    billing_agg = billing_ready[
        [
            "provider",
            "year",
            "billing_active_count",
            "billing_total_count",
            "billing_void_count",
            "billing_subtotal_sum",
            "billing_tax_sum",
            "billing_tip_sum",
            "billing_delivery_fee_sum",
            "billing_total_sum",
            "billing_commission_fee_sum",
            "billing_fax_fee_sum",
            "billing_phone_fee_sum",
            "billing_commission_total_sum",
            "billing_processing_total_sum",
        ]
    ].copy()

    comparison = compare(orders_agg, billing_agg)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    comparison.to_csv(args.out, index=False)
    print(f"Wrote BeyondMenu annual comparison -> {args.out}")


if __name__ == "__main__":
    main()
