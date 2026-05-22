#!/usr/bin/env python3
import argparse
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from orders_analytics.utils.constants import raw_path


METRICS = [
    "orders_count",
    "orders_total_amount",
    "phone_orders_count",
    "processing_fee",
    "slice_partnership_fee",
    "slice_partnership_fee_phone_orders",
    "slice_adjustments",
    "sales_tax_withholding",
    "net_sales",
    "taxes",
    "cust_delivery_fee",
    "tips",
]


def parse_decimal(value: str) -> Decimal:
    text = str(value or "").strip().replace("$", "").replace(",", "")
    if not text:
        return Decimal("0.00")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0.00")


def load_cancelled_keys(path: str) -> set[tuple[str, str]]:
    if not Path(path).exists():
        return set()
    df = pd.read_csv(path, dtype=str).fillna("")
    return {
        (str(r["order_id"]).strip(), str(r["provider"]).strip())
        for _, r in df.iterrows()
        if str(r.get("order_id", "")).strip() and str(r.get("provider", "")).strip()
    }


def to_key(order_id: str, provider: str) -> str:
    return f"{str(order_id).strip()}||{str(provider).strip()}"


def load_statement_summary(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    df = df[df["provider"].isin(["AMECI", "AROMA"])].copy()
    df["label"] = df["label"].replace({"slice_adjustments_phone_orders": "slice_adjustments"})
    df["period_end_dt"] = pd.to_datetime(df["statement_period_end"], errors="coerce")
    df = df[df["period_end_dt"].notna()]
    df = df[(df["period_end_dt"] >= pd.Timestamp("2020-01-01")) & (df["period_end_dt"] < pd.Timestamp("2026-01-01"))]
    pivot = (
        df.pivot_table(
            index=["provider", "statement_period_start", "statement_period_end"],
            columns="label",
            values="value",
            aggfunc="first",
        )
        .reset_index()
    )
    pivot.columns.name = None
    return pivot.fillna("")


def build_order_aggregates(orders_path: str, cancelled_path: str) -> pd.DataFrame:
    df = pd.read_csv(orders_path, dtype=str).fillna("")
    cancelled = load_cancelled_keys(cancelled_path)
    if cancelled:
        cancelled_keys = {to_key(order_id, provider) for order_id, provider in cancelled}
        df["_key"] = df["order_id"].map(str).str.strip() + "||" + df["provider"].map(str).str.strip()
        df = df[~df["_key"].isin(cancelled_keys)].copy()
    df = df[df["provider"].isin(["AMECI", "AROMA"])].copy()
    df["period_end_dt"] = pd.to_datetime(df["statement_period_end"], errors="coerce")
    df = df[df["period_end_dt"].notna()]
    df = df[(df["period_end_dt"] >= pd.Timestamp("2020-01-01")) & (df["period_end_dt"] < pd.Timestamp("2026-01-01"))]
    df = df[df["status"].fillna("active").str.lower().eq("active")].copy()

    numeric_cols = [
        "total",
        "subtotal",
        "order_adjustments",
        "tax",
        "tip",
        "customer_delivery_fee",
        "partnership_fee",
        "processing_fee",
    ]
    for col in numeric_cols:
        df[col] = df[col].map(parse_decimal)

    df["is_phone"] = df["order_type"].eq("phone_call")
    df["order_dt"] = pd.to_datetime(df["order_datetime"], errors="coerce")
    df["sales_tax_withholding_calc"] = Decimal("0.00")
    tax_mask = df["order_dt"].ge(pd.Timestamp("2020-06-01")) & ~df["is_phone"]
    df.loc[tax_mask, "sales_tax_withholding_calc"] = df.loc[tax_mask, "tax"].map(lambda v: -v)
    df["net_sales_calc"] = df["subtotal"] + df["order_adjustments"]
    df.loc[df["is_phone"], "net_sales_calc"] = Decimal("0.00")
    df["phone_adjustments_calc"] = Decimal("0.00")
    df.loc[df["is_phone"], "phone_adjustments_calc"] = df.loc[df["is_phone"], "order_adjustments"]

    rows = []
    group_cols = ["provider", "statement_period_start", "statement_period_end"]
    for keys, grp in df.groupby(group_cols, dropna=False):
        provider, period_start, period_end = keys
        main = grp[~grp["is_phone"]]
        phone = grp[grp["is_phone"]]
        rows.append(
            {
                "provider": provider,
                "statement_period_start": period_start,
                "statement_period_end": period_end,
                "orders_count": len(main),
                "orders_total_amount": main["total"].sum(),
                "phone_orders_count": len(phone),
                "phone_orders_total_amount": phone["total"].sum(),
                "processing_fee": main["processing_fee"].sum(),
                "slice_partnership_fee": main["partnership_fee"].sum(),
                "slice_partnership_fee_phone_orders": phone["partnership_fee"].sum(),
                "slice_adjustments": phone["phone_adjustments_calc"].sum(),
                "sales_tax_withholding": main["sales_tax_withholding_calc"].sum(),
                "net_sales": main["net_sales_calc"].sum(),
                "taxes": main["tax"].sum(),
                "cust_delivery_fee": main["customer_delivery_fee"].sum(),
                "tips": main["tip"].sum(),
            }
        )
    return pd.DataFrame(rows)


def fmt_decimal(value) -> str:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if value == "":
        return ""
    if pd.isna(value):
        return ""
    try:
        dec = Decimal(str(value))
    except InvalidOperation:
        return str(value)
    return f"{dec:.2f}"


def build_reconciliation(statements: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    merged = statements.merge(
        orders,
        on=["provider", "statement_period_start", "statement_period_end"],
        how="outer",
        suffixes=("_statement", "_orders"),
    )
    merged = merged.fillna("")
    for metric in METRICS:
        stmt_col = f"{metric}_statement"
        ord_col = f"{metric}_orders"
        if stmt_col not in merged.columns:
            merged[stmt_col] = ""
        if ord_col not in merged.columns:
            merged[ord_col] = ""
        merged[f"{metric}_statement"] = merged[stmt_col].map(parse_decimal)
        merged[f"{metric}_orders"] = merged[ord_col].map(parse_decimal)
        merged[f"{metric}_diff"] = merged[f"{metric}_orders"] - merged[f"{metric}_statement"]

    mismatch_notes = []
    for _, row in merged.iterrows():
        parts = []
        for metric in METRICS:
            if row[f"{metric}_diff"] != Decimal("0.00"):
                parts.append(f"{metric}={row[f'{metric}_diff']:.2f}")
        mismatch_notes.append(" | ".join(parts))
    merged["mismatch_notes"] = mismatch_notes

    period_end = pd.to_datetime(merged["statement_period_end"], errors="coerce")
    merged = merged[(period_end >= pd.Timestamp("2020-01-01")) & (period_end < pd.Timestamp("2026-01-01"))].copy()

    out_cols = ["provider", "statement_period_start", "statement_period_end"]
    for metric in METRICS:
        out_cols.extend(
            [
                f"{metric}_statement",
                f"{metric}_orders",
                f"{metric}_diff",
            ]
        )
    out_cols.append("mismatch_notes")
    out = merged[out_cols].copy()
    for col in out.columns:
        if col.endswith(("_statement", "_orders", "_diff")):
            out[col] = out[col].map(fmt_decimal)
    return out.sort_values(["provider", "statement_period_start"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Slice statement vs orders reconciliation.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("slice", "orders_raw.csv"),
        help="Merged Slice orders raw CSV.",
    )
    parser.add_argument(
        "--statements-raw",
        default=raw_path("slice", "statements_raw_from_statements.csv"),
        help="Slice statement summary raw CSV.",
    )
    parser.add_argument(
        "--cancelled-raw",
        default=raw_path("slice", "cancelled_orders_manual.csv"),
        help="Manual cancelled Slice orders CSV.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("slice", "statement_reconciliation_2020_2025.csv"),
        help="Output reconciliation CSV.",
    )
    args = parser.parse_args()

    statements = load_statement_summary(args.statements_raw)
    orders = build_order_aggregates(args.orders_raw, args.cancelled_raw)
    out = build_reconciliation(statements, orders)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(args.out)


if __name__ == "__main__":
    main()
