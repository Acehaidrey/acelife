#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from typing import Set

import pandas as pd

from orders_analytics.utils.constants import raw_path


def load_ids(path: str, column: str) -> Set[str]:
    if not path or not os.path.exists(path):
        return set()
    df = pd.read_csv(path, dtype=str).fillna("")
    return {
        str(val).strip()
        for val in df.get(column, pd.Series([], dtype=str)).astype(str).tolist()
        if str(val).strip()
    }


def load_cancellations(path: str) -> Set[str]:
    if not path or not os.path.exists(path):
        return set()
    df = pd.read_csv(path, dtype=str).fillna("")
    return {
        str(row.get("order_id", "")).strip()
        for row in df.to_dict("records")
        if row.get("order_id")
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare ChowNow orders_raw vs billings_raw, excluding cancellations."
    )
    parser.add_argument(
        "--orders-raw",
        default=raw_path("chownow", "orders_raw.csv"),
        help="Path to orders_raw.csv",
    )
    parser.add_argument(
        "--billings-raw",
        default=raw_path("chownow", "billings_raw.csv"),
        help="Path to billings_raw.csv",
    )
    parser.add_argument(
        "--cancellations-raw",
        default=raw_path("chownow", "cancellations_raw.csv"),
        help="Path to cancellations_raw.csv",
    )
    parser.add_argument(
        "--missing-in-billings-out",
        default=raw_path("chownow", "orders_missing_billings.csv"),
        help="Output CSV for orders missing in billings.",
    )
    parser.add_argument(
        "--missing-in-orders-out",
        default=raw_path("chownow", "billings_missing_orders.csv"),
        help="Output CSV for billings missing in orders.",
    )
    args = parser.parse_args()

    orders_ids = load_ids(args.orders_raw, "order_id")
    billings_ids = load_ids(args.billings_raw, "Order Id")
    cancellations = load_cancellations(args.cancellations_raw)

    orders_ids = {oid for oid in orders_ids if oid not in cancellations}
    billings_ids = {oid for oid in billings_ids if oid not in cancellations}

    missing_in_billings = sorted(orders_ids - billings_ids)
    missing_in_orders = sorted(billings_ids - orders_ids)

    os.makedirs(os.path.dirname(args.missing_in_billings_out), exist_ok=True)
    pd.DataFrame({"order_id": missing_in_billings}).to_csv(
        args.missing_in_billings_out, index=False
    )
    pd.DataFrame({"order_id": missing_in_orders}).to_csv(
        args.missing_in_orders_out, index=False
    )

    print(f"Orders: {len(orders_ids)}")
    print(f"Billings: {len(billings_ids)}")
    print(f"Missing in billings: {len(missing_in_billings)} -> {args.missing_in_billings_out}")
    print(f"Missing in orders: {len(missing_in_orders)} -> {args.missing_in_orders_out}")


if __name__ == "__main__":
    main()
