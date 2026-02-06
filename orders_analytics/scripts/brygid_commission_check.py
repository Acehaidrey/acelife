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

from orders_analytics.utils.constants import raw_path  # noqa: E402


def parse_order_dt(text: str) -> Optional[datetime]:
    t = str(text or "").strip()
    if not t:
        return None
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

    orders_path = raw_path("brygid", "orders_raw.csv")
    billings_path = raw_path("brygid", "billings_raw.csv")

    orders = pd.read_csv(orders_path, dtype=str).fillna("")
    billings = pd.read_csv(billings_path, dtype=str).fillna("")

    orders = dedupe_orders(orders)
    orders["order_dt"] = orders["order_datetime"].apply(parse_order_dt)
    orders = orders.dropna(subset=["order_dt"])

    for col in ("subtotal", "total"):
        if col in orders.columns:
            orders[col] = pd.to_numeric(orders[col], errors="coerce").fillna(0.0)

    base_col = "total" if args.commission_base == "total" else "subtotal"
    if base_col not in orders.columns:
        orders[base_col] = 0.0
    orders["commission_calc"] = compute_commission(orders[base_col], 0.025, clip_min=True, clip_max=True)
    orders["commission_calc_no_clip"] = compute_commission(
        orders[base_col], 0.025, clip_min=False, clip_max=False
    )
    orders["commission_calc_225_clip"] = compute_commission(
        orders[base_col], 0.0225, clip_min=True, clip_max=True
    )
    orders["commission_calc_no_min"] = compute_commission(
        orders[base_col], 0.025, clip_min=False, clip_max=True
    )

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
                    pd.to_numeric(row.get("total_service_fees", ""), errors="coerce") or 0.0
                ),
            }
        )

    periods = pd.DataFrame(period_rows)

    agg_rows = []
    for _, period in periods.iterrows():
        mask = (orders["order_dt"] >= period["start_dt"]) & (orders["order_dt"] <= period["end_dt"])
        subset = orders.loc[mask]
        agg_rows.append(
            {
                "period_key": period["period_key"],
                "period_start": period["start_dt"].strftime("%Y-%m-%d"),
                "period_end": period["end_dt"].strftime("%Y-%m-%d"),
                "orders_count": int(subset["order_id"].count()),
                "subtotal_sum": float(subset["subtotal"].sum()),
                "total_sum": float(subset["total"].sum()),
                "commission_sum": float(subset["commission_calc"].sum()),
                "commission_sum_no_clip": float(subset["commission_calc_no_clip"].sum()),
                "commission_sum_225_clip": float(subset["commission_calc_225_clip"].sum()),
                "commission_sum_no_min": float(subset["commission_calc_no_min"].sum()),
            }
        )

    agg = pd.DataFrame(agg_rows)
    merged = agg.merge(
        periods[
            [
                "period_key",
                "billing_date",
                "billed_order_count",
                "billed_total_sales",
                "billed_service_fees",
            ]
        ],
        on="period_key",
        how="left",
    )

    merged["order_count_diff"] = merged["orders_count"] - merged["billed_order_count"]
    merged["total_sales_diff"] = merged["total_sum"] - merged["billed_total_sales"]
    merged["service_fees_diff"] = merged["commission_sum"] - merged["billed_service_fees"]
    merged["service_fees_diff_no_clip"] = (
        merged["commission_sum_no_clip"] - merged["billed_service_fees"]
    )
    merged["service_fees_diff_225_clip"] = (
        merged["commission_sum_225_clip"] - merged["billed_service_fees"]
    )
    merged["service_fees_diff_no_min"] = (
        merged["commission_sum_no_min"] - merged["billed_service_fees"]
    )
    merged["order_counts_match"] = merged["order_count_diff"] == 0
    merged["total_match"] = merged["total_sales_diff"].abs() <= 0.01

    for col in [
        "subtotal_sum",
        "total_sum",
        "commission_sum",
        "commission_sum_no_clip",
        "commission_sum_225_clip",
        "commission_sum_no_min",
        "billed_total_sales",
        "billed_service_fees",
        "total_sales_diff",
        "service_fees_diff",
        "service_fees_diff_no_clip",
        "service_fees_diff_225_clip",
        "service_fees_diff_no_min",
    ]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").round(2)

    merged.to_csv(args.out, index=False)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
