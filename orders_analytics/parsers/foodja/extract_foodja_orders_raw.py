#!/usr/bin/env python3
import argparse
import datetime as dt
import os
from pathlib import Path

import pandas as pd

from orders_analytics.utils.constants import raw_path, takeout_path


def run(input_path: str, out_path: str) -> int:
    now = dt.datetime.now().isoformat()
    df = pd.read_csv(input_path, dtype=str).fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    if "Order #" in df.columns:
        df = df.rename(columns={"Order #": "order_id"})
    df["source_file"] = input_path
    df["added_at"] = now
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path, index=False)
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Foodja orders to raw CSV.")
    parser.add_argument(
        "--input",
        default=takeout_path("foodja", "oex-orders-02-17-26.csv"),
        help="Input Foodja orders CSV path.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("foodja", "orders_raw.csv"),
        help="Output raw orders path.",
    )
    args = parser.parse_args()
    rows = run(args.input, args.out)
    print(f"Wrote {rows} rows -> {args.out}")


if __name__ == "__main__":
    main()
