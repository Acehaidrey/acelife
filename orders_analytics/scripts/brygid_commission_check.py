#!/usr/bin/env python3
import argparse
import os
import sys
from datetime import datetime
from typing import Optional

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from orders_analytics.utils.constants import raw_path, normalized_path  # noqa: E402


def parse_order_dt(text: str) -> Optional[datetime]:
    t = str(text or "").strip()
    if not t:
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%a, %b %d %Y @ %I:%M %p", "%a, %b %d %Y @ %I:%M%p"):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            continue
    return None


def dedupe_orders(df: pd.DataFrame) -> pd.DataFrame:
    if "order_id" not in df.columns:
        return df

    def score(row) -> int:
        return sum(1 for value in row if str(value).strip())

    df = df.copy()
    df["__score"] = df.apply(score, axis=1)
    df = df.sort_values(
        by=["order_id", "__score", "order_datetime"],
        ascending=[True, False, False],
    )
    df = df.drop_duplicates(subset=["order_id"], keep="first")
    return df.drop(columns=["__score"])


def compute_commission(
    values: pd.Series,
    rate: float,
    clip_min: bool = True,
    clip_max: bool = True,
) -> pd.Series:
    commission = values * rate
    lower = 0.50 if clip_min else None
    upper = 2.00 if clip_max else None
    if lower is None and upper is None:
        return commission
    return commission.clip(lower=lower, upper=upper)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Brygid orders vs billings (15th-14th rule).")
    parser.add_argument(
        "--orders-path",
        default=normalized_path("brygid_orders_normalized.csv"),
        help="Path to Brygid orders CSV (normalized preferred).",
    )
    parser.add_argument(
        "--include-manual",
        action="store_true",
        help="Include PERIOD_YYYYMMDD_MANUAL rows when computing commissions.",
    )
    parser.add_argument(
        "--exclude-cancelled",
        action="store_true",
        help="Exclude rows with notes containing cancelled:christmas or cancelled:thanksgiving.",
    )
    parser.add_argument(
        "--commission-base",
        choices=("subtotal", "total"),
        default="subtotal",
        help="Column to base the 2.5%% commission on.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("brygid", "commission_check.csv"),
        help="Output CSV path.",
    )
    args = parser.parse_args()

    orders_path = args.orders_path
    if not os.path.exists(orders_path):
        orders_path = raw_path("brygid", "orders_raw.csv")
    billings_path = raw_path("brygid", "billings_raw.csv")

    orders = pd.read_csv(orders_path, dtype=str).fillna("")
    billings = pd.read_csv(billings_path, dtype=str).fillna("")

    orders_no_manual = orders.copy()
    if "order_id" in orders_no_manual.columns:
        orders_no_manual = orders_no_manual[
            ~orders_no_manual["order_id"].astype(str).str.startswith("PERIOD_")
        ].copy()
    orders_with_manual = orders.copy()

    if args.exclude_cancelled and "notes" in orders.columns:
        notes = orders["notes"].astype(str).str.lower()
        mask = ~(
            notes.str.contains("cancelled:christmas", na=False)
            | notes.str.contains("cancelled:thanksgiving", na=False)
        )
        orders_no_manual = orders_no_manual[mask].copy()
        orders_with_manual = orders_with_manual[mask].copy()

    orders_no_manual = dedupe_orders(orders_no_manual)
    orders_no_manual["order_dt"] = orders_no_manual["order_datetime"].apply(parse_order_dt)
    orders_no_manual = orders_no_manual.dropna(subset=["order_dt"])

    orders_with_manual = dedupe_orders(orders_with_manual)
    orders_with_manual["order_dt"] = orders_with_manual["order_datetime"].apply(parse_order_dt)
    orders_with_manual = orders_with_manual.dropna(subset=["order_dt"])

    for col in ("subtotal", "total"):
        if col in orders_no_manual.columns:
            orders_no_manual[col] = pd.to_numeric(orders_no_manual[col], errors="coerce").fillna(0.0)
        if col in orders_with_manual.columns:
            orders_with_manual[col] = pd.to_numeric(orders_with_manual[col], errors="coerce").fillna(0.0)
    if "commission_fee" in orders_no_manual.columns:
        orders_no_manual["commission_fee_num"] = pd.to_numeric(
            orders_no_manual.get("commission_fee", ""), errors="coerce"
        ).fillna(0.0)
    if "commission_fee" in orders_with_manual.columns:
        orders_with_manual["commission_fee_num"] = pd.to_numeric(
            orders_with_manual.get("commission_fee", ""), errors="coerce"
        ).fillna(0.0)

    base_col = "total" if args.commission_base == "total" else "subtotal"
    if base_col not in orders.columns:
        orders[base_col] = 0.0

    billings["billing_date_dt"] = pd.to_datetime(billings.get("billing_date", ""), errors="coerce")
    billings = billings.dropna(subset=["billing_date_dt"])

    period_rows = []
    for _, row in billings.iterrows():
        billing_dt = row["billing_date_dt"]
        start = (billing_dt - pd.DateOffset(months=1)).replace(day=15)
        end = (billing_dt - pd.DateOffset(days=1)).replace(hour=23, minute=59, second=59)
        period_rows.append(
            {
                "period_key": billing_dt.strftime("%Y-%m-%d"),
                "billing_date": row.get("billing_date", ""),
                "start_dt": start,
                "end_dt": end,
                "billed_order_count": int(pd.to_numeric(row.get("total_order_count", ""), errors="coerce") or 0),
                "billed_total_sales": float(pd.to_numeric(row.get("total_sales", ""), errors="coerce") or 0.0),
                "billed_service_fees": float(
                    pd.to_numeric(row.get("invoice_total", ""), errors="coerce")
                    or pd.to_numeric(row.get("total_service_fees", ""), errors="coerce")
                    or 0.0
                ),
            }
        )

    periods = pd.DataFrame(period_rows)

    def agg_for(df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for _, period in periods.iterrows():
            mask = (df["order_dt"] >= period["start_dt"]) & (df["order_dt"] <= period["end_dt"])
            subset = df.loc[mask]
            commission_sum_norm = 0.0
            if "commission_fee_num" in subset.columns:
                commission_sum_norm = float((-subset["commission_fee_num"]).sum())
            rows.append(
                {
                    "period_key": period["period_key"],
                    "orders_count": int(subset["order_id"].count()),
                    "subtotal_sum": float(subset["subtotal"].sum()),
                    "total_sum": float(subset["total"].sum()),
                    "commission_sum_norm": commission_sum_norm,
                }
            )
        return pd.DataFrame(rows)

    agg_no = agg_for(orders_no_manual)
    agg_with = agg_for(orders_with_manual)

    merged = agg_no.merge(
        periods[["period_key", "billed_order_count", "billed_total_sales", "billed_service_fees"]],
        on="period_key",
        how="left",
    )
    merged = merged.rename(
        columns={
            "orders_count": "orders_count_no_manual",
            "subtotal_sum": "subtotal_sum_no_manual",
            "total_sum": "total_sum_no_manual",
            "commission_sum_norm": "commission_sum_norm_no_manual",
        }
    )
    merged_with = agg_with.rename(
        columns={
            "orders_count": "orders_count_with_manual",
            "subtotal_sum": "subtotal_sum_with_manual",
            "total_sum": "total_sum_with_manual",
            "commission_sum_norm": "commission_sum_norm_with_manual",
        }
    )
    merged = merged.merge(merged_with, on="period_key", how="left")

    merged["order_count_diff_no_manual"] = (
        merged["orders_count_no_manual"] - merged["billed_order_count"]
    )
    merged["total_sales_diff_no_manual"] = (
        merged["total_sum_no_manual"] - merged["billed_total_sales"]
    )
    merged["service_fees_diff_norm_no_manual"] = (
        merged["commission_sum_norm_no_manual"] - merged["billed_service_fees"]
    )
    merged["total_match_no_manual"] = merged["total_sales_diff_no_manual"].abs() <= 0.01

    merged["order_count_diff_with_manual"] = (
        merged["orders_count_with_manual"] - merged["billed_order_count"]
    )
    merged["total_sales_diff_with_manual"] = (
        merged["total_sum_with_manual"] - merged["billed_total_sales"]
    )
    merged["service_fees_diff_norm_with_manual"] = (
        merged["commission_sum_norm_with_manual"] - merged["billed_service_fees"]
    )
    merged["total_match_with_manual"] = merged["total_sales_diff_with_manual"].abs() <= 0.01

    for col in [
        "subtotal_sum_no_manual",
        "total_sum_no_manual",
        "commission_sum_norm_no_manual",
        "subtotal_sum_with_manual",
        "total_sum_with_manual",
        "commission_sum_norm_with_manual",
        "billed_total_sales",
        "billed_service_fees",
        "total_sales_diff_no_manual",
        "service_fees_diff_norm_no_manual",
        "total_sales_diff_with_manual",
        "service_fees_diff_norm_with_manual",
    ]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").round(2)

    merged.to_csv(args.out, index=False)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
