#!/usr/bin/env python3
import argparse
import datetime as dt
import os
from pathlib import Path

import pandas as pd

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.normalize import normalize_money


def infer_provider_from_filename(path: Path) -> str:
    name = path.stem.lower()
    if "aroma" in name:
        return "AROMA"
    if "ameci" in name:
        return "AMECI"
    return normalize_provider(path.stem)


def run(input_dir: str, out_path: str) -> int:
    now = dt.datetime.now().isoformat()
    input_dir = Path(input_dir)
    files = sorted([p for p in input_dir.glob("*.xlsx") if p.is_file()])
    if not files:
        raise SystemExit(f"No xlsx files found in {input_dir}")

    rows = []
    for file_path in files:
        provider = infer_provider_from_filename(file_path)
        xls = pd.ExcelFile(file_path)
        df = pd.read_excel(file_path, sheet_name=xls.sheet_names[0], dtype=str).fillna("")
        df.columns = [str(c).strip() for c in df.columns]
        for _, row in df.iterrows():
            order_id = str(row.get("Order: Order Number", "")).strip()
            if not order_id:
                continue
            subtotal = normalize_money(row.get("Food Total", ""))
            payout = normalize_money(row.get("Total Paid", ""))
            period = str(row.get("Period", "")).strip()
            payment_date = str(row.get("Payment Date", "")).strip()
            rows.append(
                {
                    "order_id": order_id,
                    "Order #": order_id,
                    "Order": order_id,
                    "provider": provider,
                    "subtotal": subtotal,
                    "payout": payout,
                    "period": period,
                    "payment_date": payment_date,
                    "source_file": str(file_path),
                    "added_at": now,
                }
            )

    out_df = pd.DataFrame(rows)
    out_df.to_csv(out_path, index=False)
    return len(out_df)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Foodja billings raw from XLSX exports.")
    parser.add_argument(
        "--input-dir",
        default=takeout_path("foodja"),
        help="Directory containing Foodja XLSX exports.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("foodja", "billings_raw.csv"),
        help="Output billings_raw.csv path.",
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    rows = run(args.input_dir, args.out)
    print(f"Wrote {rows} rows -> {args.out}")


if __name__ == "__main__":
    main()
