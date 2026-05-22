#!/usr/bin/env python3
import argparse
from pathlib import Path

import pandas as pd


RAW_COLUMNS = [
    "order_id",
    "provider",
    "restaurant_name",
    "order_datetime",
    "order_type",
    "payment_type",
    "customer_name",
    "phone",
    "email",
    "address",
    "items",
    "item_count",
    "subtotal",
    "tax",
    "tip",
    "delivery_fee",
    "total",
    "notes",
    "source_file",
    "email_date",
    "added_at",
]


def coalesce(a: pd.Series, b: pd.Series) -> pd.Series:
    a = a.fillna("")
    b = b.fillna("")
    return a.where(a.astype(str).str.strip() != "", b)


def dedupe_best(df: pd.DataFrame) -> pd.DataFrame:
    if "order_id" not in df.columns:
        return df
    def score(row) -> int:
        return sum(1 for value in row if str(value).strip())
    df = df.copy()
    df["__score"] = df.apply(score, axis=1)
    df = df.sort_values(by=["order_id", "__score", "order_datetime"], ascending=[True, False, False])
    df = df.drop_duplicates(subset=["order_id"], keep="first")
    return df.drop(columns=["__score"])


def run(
    email_path: str = "orders_analytics/data/raw/brygid/orders_raw_from_email.csv",
    csv_path: str = "orders_analytics/data/raw/brygid/orders_raw_from_csvs_normalized.csv",
    out_path: str = "orders_analytics/data/raw/brygid/orders_raw.csv",
) -> None:
    email = pd.read_csv(email_path, dtype=str).fillna("")
    csvs = pd.read_csv(csv_path, dtype=str).fillna("")

    # Ensure columns exist
    for col in RAW_COLUMNS:
        if col not in email.columns:
            email[col] = ""
        if col not in csvs.columns:
            csvs[col] = ""

    email = email[RAW_COLUMNS]
    email = dedupe_best(email)
    # Use parsed datetime from CSVs when available
    if "order_datetime_parsed" in csvs.columns:
        csvs["order_datetime"] = csvs["order_datetime_parsed"].where(
            csvs["order_datetime_parsed"].astype(str).str.strip() != "",
            csvs["order_datetime"],
        )
    csvs = csvs[RAW_COLUMNS]
    csvs = dedupe_best(csvs)

    merged = email.merge(csvs, on="order_id", how="outer", suffixes=("_email", "_csv"))

    out = pd.DataFrame()
    out["order_id"] = merged["order_id"]

    for col in RAW_COLUMNS:
        if col == "order_id":
            continue
        a = merged.get(f"{col}_email", "")
        b = merged.get(f"{col}_csv", "")
        out[col] = coalesce(a, b)

    # delivery_fee: prefer email if present, else csv
    out["delivery_fee"] = coalesce(merged.get("delivery_fee_email", ""), merged.get("delivery_fee_csv", ""))

    # preserve column order
    out = out[RAW_COLUMNS]

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    print(f"Wrote {len(out)} rows -> {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge Brygid email + CSV orders into orders_raw.csv.")
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
        default="orders_analytics/data/raw/brygid/orders_raw.csv",
        help="Output merged orders_raw.csv path.",
    )
    args = parser.parse_args()
    run(args.email, args.csv, args.out)


if __name__ == "__main__":
    main()
