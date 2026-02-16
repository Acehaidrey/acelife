#!/usr/bin/env python3
import argparse
import datetime as dt
import os

import pandas as pd

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.grubhub_adjustments import compute_adjustment_total


NUMERIC_COLUMNS = [
    "Subtotal",
    "Delivery Fee",
    "Service Fee",
    "Service Fee Exemption",
    "(flexible fees)",
    "Tax Fee",
    "Tax Fee Exemption",
    "Tip",
    "Restaurant Total",
    "Commission",
    "GH+ Commission",
    "Delivery Commission",
    "Processing Fee",
    "Withheld Tax",
    "Withheld Tax Exemption",
    "Targeted Promotion",
    "Rewards",
]


def _clean_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace({"N/A": "", "n/a": "", "nan": "", "NaN": ""}), errors="coerce").fillna(0.0)


def _first_non_empty(series: pd.Series) -> str:
    for value in series:
        if str(value).strip():
            return value
    return ""


def _join_distinct(series: pd.Series) -> str:
    values = sorted({str(v).strip() for v in series if str(v).strip()})
    return ", ".join(values)


def build_deduped(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = _clean_numeric(df[col])

    agg = {}
    for col in df.columns:
        if col in NUMERIC_COLUMNS:
            agg[col] = "sum"
        else:
            agg[col] = _join_distinct

    deduped = df.groupby("ID", dropna=False).agg(agg).reset_index(drop=True)
    counts = df.groupby("ID", dropna=False).size().reset_index(name="merged_rows")
    deduped = deduped.merge(counts, on="ID", how="left")

    adjustment_totals = {}
    for order_id, group in df.groupby("ID", dropna=False):
        order_id_clean = str(order_id).strip()
        has_adjustment, adjustment_total = compute_adjustment_total(order_id_clean, group.to_dict("records"))
        if has_adjustment:
            adjustment_totals[order_id_clean] = adjustment_total

    if adjustment_totals:
        def _append_adjustment_note(row):
            order_id = str(row.get("ID", "")).strip()
            if order_id not in adjustment_totals:
                return row
            note = f"adjustment_total={adjustment_totals[order_id]:.2f}"
            existing = str(row.get("Description", "") or "").strip()
            if existing:
                row["Description"] = existing + " | " + note
            else:
                row["Description"] = note
            return row
        deduped = deduped.apply(_append_adjustment_note, axis=1)
    return deduped


def run(input_path: str, out_path: str, deduped_path: str) -> int:
    now = dt.datetime.now().isoformat()
    df = pd.read_csv(input_path, dtype=str).fillna("")
    df.columns = [str(col).strip() for col in df.columns]
    df["source_file"] = input_path
    df["added_at"] = now
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path, index=False)

    deduped = build_deduped(df)
    os.makedirs(os.path.dirname(deduped_path), exist_ok=True)
    deduped.to_csv(deduped_path, index=False)

    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Grubhub orders to raw CSV.")
    parser.add_argument(
        "--input",
        default=takeout_path("gh_jan25_jun25.csv"),
        help="Input Grubhub CSV path.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("grubhub", "orders_raw.csv"),
        help="Output raw orders path.",
    )
    parser.add_argument(
        "--deduped",
        default=raw_path("grubhub", "orders_raw_deduped.csv"),
        help="Output deduped raw orders path.",
    )
    args = parser.parse_args()
    rows = run(args.input, args.out, args.deduped)
    print(f"Wrote {rows} rows to {args.out}")
    print(f"Wrote deduped rows to {args.deduped}")


if __name__ == "__main__":
    main()
