#!/usr/bin/env python3
import argparse
import os

import pandas as pd

from orders_analytics.utils.constants import raw_path, takeout_path


def is_zero_or_blank(series: pd.Series) -> bool:
    values = series.astype(str).str.strip()
    return values.isin({"", "0", "0.0", "0.00", "$0.00", "$0", "($0.00)", "$0.0"}).all()


def run(input_path: str, out_path: str) -> int:
    df = pd.read_csv(input_path, encoding="utf-16", sep="\t", dtype=str).fillna("")

    if not df.empty:
        first_col = df.columns[0]
        df = df[df[first_col].astype(str).str.strip().str.lower() != "grand total"].copy()

    duplicate_columns_to_drop = [
        "Tax (Restaurant to remit)",
    ]
    df = df.drop(columns=[column for column in duplicate_columns_to_drop if column in df.columns])

    keep_columns = [column for column in df.columns if not is_zero_or_blank(df[column])]
    df = df[keep_columns].copy()

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path, sep="\t", encoding="utf-16", index=False)
    print(f"Wrote {len(df)} row(s) -> {out_path}")
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract cleaned Fooda raw orders CSV.")
    parser.add_argument(
        "--input",
        default=takeout_path("Mail", "fooda_sales.csv"),
        help="Path to Fooda source CSV.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("fooda", "fooda_sales.csv"),
        help="Output cleaned raw CSV path.",
    )
    args = parser.parse_args()
    run(args.input, args.out)


if __name__ == "__main__":
    main()
