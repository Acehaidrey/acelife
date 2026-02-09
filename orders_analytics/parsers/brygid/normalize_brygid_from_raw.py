#!/usr/bin/env python3
import argparse
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_datetime, normalize_order_type, normalize_payment_type
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.schema import build_normalized_row


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


def load_cancellations(path: str) -> set:
    if not os.path.exists(path):
        return set()
    df = pd.read_csv(path, dtype=str).fillna("")
    if "order_id" not in df.columns:
        return set()
    return set(df["order_id"].astype(str))


def compute_commission(values: pd.Series, rate: float = 0.025) -> pd.Series:
    commission = values * rate
    return commission.clip(lower=0.50, upper=2.00)


def allocate_proportional(total: float, weights: List[float]) -> List[float]:
    if not weights:
        return []
    total_weight = sum(w for w in weights if w > 0)
    n = len(weights)
    if total_weight <= 0:
        raw = [total / n for _ in weights]
    else:
        raw = [total * (w / total_weight) for w in weights]
    rounded = [round(value, 2) for value in raw]
    diff = round(total - sum(rounded), 2)
    cents = int(round(diff * 100))
    if cents:
        order = sorted(range(n), key=lambda i: (raw[i] - rounded[i]), reverse=cents > 0)
        step = 0.01 if cents > 0 else -0.01
        for idx in range(abs(cents)):
            rounded[order[idx % n]] += step
    return rounded


def format_money(value: float) -> str:
    return f"{value:.2f}"


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


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def normalize_order_datetime(value: str) -> str:
    return normalize_datetime(
        value,
        formats=(
            "%a, %b %d %Y @ %I:%M %p",
            "%b %d %Y @ %I:%M %p",
            "%a, %b %d %Y %I:%M %p",
            "%b %d %Y %I:%M %p",
            "%m/%d/%Y %H:%M",
        ),
        allow_iso=False,
    )


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    cancellations = load_cancellations(raw_path("brygid", "cancellations_raw.csv"))
    for row in rows:
        order_id = str(row.get("order_id", "") or "").strip()
        if order_id and order_id in cancellations:
            continue
        order_type = normalize_order_type(row.get("order_type", "")) or OrderTypes.PICKUP
        payment_type = normalize_payment_type(row.get("payment_type", "")) or PaymentTypes.CREDIT
        notes = row.get("notes", "")
        normalized.append(
            build_normalized_row(
                Platforms.BRYGID.upper(),
                order_id=order_id,
                provider=row.get("provider", ""),
                restaurant_name=row.get("restaurant_name", ""),
                order_datetime=normalize_order_datetime(row.get("order_datetime", "")),
                order_type=order_type,
                customer_name=row.get("customer_name", ""),
                phone=row.get("phone", ""),
                email=row.get("email", ""),
                address=row.get("address", ""),
                payment_type=payment_type,
                subtotal=row.get("subtotal", ""),
                tax=row.get("tax", ""),
                tip=row.get("tip", ""),
                delivery_fee=row.get("delivery_fee", ""),
                total=row.get("total", ""),
                commission_fee=row.get("commission_fee", ""),
                items=row.get("items", ""),
                item_count=row.get("item_count", ""),
                notes=notes,
                errors="",
            )
        )
    return normalized


def apply_commissions(
    orders: pd.DataFrame,
    billings: pd.DataFrame,
) -> Tuple[pd.DataFrame, List[Dict[str, str]]]:
    orders = dedupe_orders(orders)
    orders["order_dt"] = orders["order_datetime"].apply(parse_order_dt)
    orders = orders.dropna(subset=["order_dt"]).copy()
    cancellations = load_cancellations(raw_path("brygid", "cancellations_raw.csv"))
    if cancellations:
        orders = orders[~orders["order_id"].astype(str).isin(cancellations)].copy()
    orders["subtotal_num"] = pd.to_numeric(orders.get("subtotal", ""), errors="coerce").fillna(0.0)
    orders["total_num"] = pd.to_numeric(orders.get("total", ""), errors="coerce").fillna(0.0)
    orders["commission_fee"] = -compute_commission(orders["subtotal_num"])

    billings = billings.copy()
    billings["billing_date_dt"] = pd.to_datetime(billings.get("billing_date", ""), errors="coerce")
    billings = billings.dropna(subset=["billing_date_dt"])

    manual_rows: List[Dict[str, str]] = []
    for _, bill in billings.iterrows():
        billing_dt = bill["billing_date_dt"]
        start = (billing_dt - pd.DateOffset(months=1)).replace(day=15)
        end = (billing_dt - pd.DateOffset(days=1)).replace(hour=23, minute=59, second=59)
        mask = (orders["order_dt"] >= start) & (orders["order_dt"] <= end)
        subset = orders.loc[mask]

        billed_total_sales = float(pd.to_numeric(bill.get("total_sales", ""), errors="coerce") or 0.0)
        billed_service_fees = float(
            pd.to_numeric(bill.get("invoice_total", ""), errors="coerce")
            or pd.to_numeric(bill.get("total_service_fees", ""), errors="coerce")
            or 0.0
        )
        billed_order_count = int(pd.to_numeric(bill.get("total_order_count", ""), errors="coerce") or 0)

        period_subtotal = float(subset["subtotal_num"].sum())
        period_total = float(subset["total_num"].sum())
        total_diff = period_total - billed_total_sales
        total_match = abs(total_diff) <= 0.01

        if total_match and not subset.empty:
            allocated = allocate_proportional(billed_service_fees, subset["subtotal_num"].tolist())
            orders.loc[subset.index, "commission_fee"] = [-value for value in allocated]
            continue

        # Order count diff should not include manual rows (subset excludes them already).
        order_count_diff = int(subset["order_id"].count()) - billed_order_count
        manual_weight = max(1, abs(order_count_diff))
        manual_row = None

        if abs(total_diff) > 0.0:
            manual_total = -total_diff
            manual_subtotal = manual_total / 1.0775
            manual_tax = manual_total - manual_subtotal
            period_key = billing_dt.strftime("%Y-%m-%d")
            end_dt = (billing_dt - pd.DateOffset(days=1)).replace(hour=23, minute=59, second=59)
            billing_dt_str = end_dt.strftime("%a, %b %d %Y @ %I:%M %p")

            provider = "AMECI"
            restaurant = "AMECI PIZZA AND PASTA - LAKE FOREST"
            if not subset.empty:
                if "provider" in subset.columns:
                    mode_vals = subset["provider"].mode()
                    if not mode_vals.empty:
                        provider = str(mode_vals.iloc[0])
                if "restaurant_name" in subset.columns:
                    mode_vals = subset["restaurant_name"].mode()
                    if not mode_vals.empty:
                        restaurant = str(mode_vals.iloc[0])

            manual_row = build_normalized_row(
                Platforms.BRYGID.upper(),
                order_id=f"PERIOD_{billing_dt.strftime('%Y%m%d')}_MANUAL",
                provider=provider,
                restaurant_name=restaurant,
                order_datetime=billing_dt_str,
                order_type=OrderTypes.PICKUP,
                payment_type=PaymentTypes.CREDIT,
                subtotal=format_money(manual_subtotal),
                tax=format_money(manual_tax),
                total=format_money(manual_total),
                notes=(
                    f"manual_period_adjustment period={period_key} "
                    f"orders_diff={order_count_diff} "
                    f"total_diff={format_money(manual_total)}"
                ),
            )

        weights = [1.0] * len(subset)
        if manual_row:
            weights.append(float(manual_weight))
        if weights:
            allocated = allocate_proportional(billed_service_fees, weights)
            orders.loc[subset.index, "commission_fee"] = [-value for value in allocated[: len(subset)]]
            if manual_row:
                manual_row["commission_fee"] = format_money(-allocated[-1])
                manual_rows.append(manual_row)

    return orders, manual_rows


class BrygidNormalizer(BaseParser):
    platform = "BRYGID"
    provider = ""

    def default_input_path(self) -> str:
        return raw_path("brygid", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("brygid_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return load_raw(input_path)

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        billings = load_raw(raw_path("brygid", "billings_raw.csv"))
        orders, manual_rows = apply_commissions(inputs, billings)
        rows = orders.to_dict("records")
        rows.extend(manual_rows)
        return normalize_rows(rows)


def run(orders_raw_path: str, out_path: str, reset_errors: bool = False) -> int:
    parser = BrygidNormalizer(input_path=orders_raw_path, out_path=out_path, reset_errors=reset_errors)
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Brygid raw CSV.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("brygid", "orders_raw.csv"),
        help="Path to Brygid orders raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("brygid_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_raw, args.out)


if __name__ == "__main__":
    main()
