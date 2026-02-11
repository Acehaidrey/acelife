#!/usr/bin/env python3
from __future__ import annotations

import pandas as pd

from orders_analytics.utils.constants import raw_path, normalized_path


def main() -> None:
    statements_path = raw_path("brygid", "brygid_merchant_processing_statements.csv")
    orders_path = normalized_path("brygid_orders_normalized.csv")

    sdf = pd.read_csv(statements_path, dtype=str).fillna("")
    sdf = sdf[sdf.get("Transaction ID", "").astype(str) != "1949452684062893206"]
    sdf["tx_date"] = pd.to_datetime(sdf.get("Transaction Date", ""), errors="coerce")
    sdf["amount"] = pd.to_numeric(sdf.get("Amount (One column)", ""), errors="coerce").fillna(0.0)
    sdf = sdf.dropna(subset=["tx_date"])
    sdf["alloc_month"] = (sdf["tx_date"] - pd.DateOffset(months=1)).dt.to_period("M").astype(str)
    stmt_totals = sdf.groupby("alloc_month")["amount"].sum().to_dict()

    odf = pd.read_csv(orders_path, dtype=str).fillna("")
    odf = odf[odf.get("payment_type", "").str.lower() == "credit"]
    odf["order_dt"] = pd.to_datetime(odf.get("order_datetime", ""), errors="coerce")
    odf["proc_fee"] = pd.to_numeric(odf.get("processing_fee", ""), errors="coerce").fillna(0.0)
    odf = odf.dropna(subset=["order_dt"])
    odf["order_month"] = odf["order_dt"].dt.to_period("M").astype(str)
    alloc_totals = odf.groupby("order_month")["proc_fee"].sum().to_dict()

    rows = []
    for month, stmt_total in sorted(stmt_totals.items()):
        alloc_total = alloc_totals.get(month, 0.0)
        diff = round((alloc_total + abs(stmt_total)), 2)
        rows.append((month, stmt_total, alloc_total, diff))

    mismatches = [row for row in rows if abs(row[3]) > 0.01]
    print(f"months checked: {len(rows)}")
    print(f"mismatches: {len(mismatches)}")
    if mismatches:
        print("first mismatches:")
        for row in mismatches[:12]:
            print(row)


if __name__ == "__main__":
    main()
