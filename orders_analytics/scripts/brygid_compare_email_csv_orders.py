#!/usr/bin/env python3
import argparse
from pathlib import Path

import pandas as pd


NUM_FIELDS = ["subtotal", "tax", "tip", "delivery_fee", "total"]


def to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace("", pd.NA), errors="coerce").fillna(0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare email vs CSV Brygid orders for numeric diffs.")
    parser.add_argument(
        "--email",
        default="orders_analytics/data/raw/brygid/orders_raw_from_email.csv",
        help="Email-sourced orders CSV.",
    )
    parser.add_argument(
        "--csv",
        default="orders_analytics/data/raw/brygid/orders_raw_from_csvs_normalized.csv",
        help="CSV-sourced normalized orders.",
    )
    parser.add_argument(
        "--out",
        default="orders_analytics/data/raw/brygid/orders_email_csv_diffs.csv",
        help="Output diff report path.",
    )
    args = parser.parse_args()

    email = pd.read_csv(args.email, dtype=str).fillna("")
    csvs = pd.read_csv(args.csv, dtype=str).fillna("")

    merged = email.merge(csvs, on="order_id", suffixes=("_email", "_csv"))
    if merged.empty:
        print("No matching order_ids.")
        return

    diffs = []
    for field in NUM_FIELDS:
        a = to_num(merged[f"{field}_email"])
        b = to_num(merged[f"{field}_csv"])
        mask = (a - b).abs() > 0.005
        if mask.any():
            rows = merged.loc[mask, ["order_id", f"{field}_email", f"{field}_csv"]].copy()
            rows["field"] = field
            rows["diff"] = (a - b)[mask].round(2).values
            diffs.append(rows)

    if not diffs:
        print("No numeric discrepancies found.")
        return

    report = pd.concat(diffs, ignore_index=True)
    report = report.rename(
        columns={
            "subtotal_email": "value_email",
            "subtotal_csv": "value_csv",
            "tax_email": "value_email",
            "tax_csv": "value_csv",
            "tip_email": "value_email",
            "tip_csv": "value_csv",
            "delivery_fee_email": "value_email",
            "delivery_fee_csv": "value_csv",
            "total_email": "value_email",
            "total_csv": "value_csv",
        }
    )
    # Fix columns after concat (some columns may be duplicated)
    cols = ["order_id", "field", "value_email", "value_csv", "diff"]
    report = report[cols]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(out_path, index=False)
    print(f"Wrote {len(report)} diffs -> {out_path}")


if __name__ == "__main__":
    main()
