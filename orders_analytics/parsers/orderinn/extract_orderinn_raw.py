#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from typing import List

import pandas as pd

from orders_analytics.utils.constants import raw_path
from orders_analytics.utils.wave import filter_transactions, load_wave_transactions


def _build_mask(df: pd.DataFrame, columns: List[str], pattern: str) -> pd.Series:
    mask = pd.Series(False, index=df.index)
    for col in columns:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.contains(pattern, case=False, na=False, regex=True)
    return mask


def run(out_path: str | None = None) -> int:
    out_path = out_path or raw_path("orderinn", "commissions_raw.csv")
    transactions = load_wave_transactions("ameci")
    filtered = filter_transactions(transactions, account_group="expense")

    desc_cols = []
    for candidate in ("Transaction Description", "Transaction Line Description"):
        if candidate in filtered.columns:
            desc_cols.append(candidate)

    pattern = r"order.*inn"
    if desc_cols:
        filtered = filtered[_build_mask(filtered, desc_cols, pattern)]

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    filtered.to_csv(out_path, index=False)
    return len(filtered)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Order Inn commission rows from Wave transactions.")
    parser.add_argument(
        "--out",
        default=None,
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    count = run(args.out)
    print(f"Wrote {count} rows to {args.out or raw_path('orderinn', 'commissions_raw.csv')}")


if __name__ == "__main__":
    main()
