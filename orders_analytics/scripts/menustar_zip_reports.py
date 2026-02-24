#!/usr/bin/env python3
import argparse
import io
import os
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import pdfplumber

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.parsers.menustar.extract_menustar_billings_raw import (
    parse_csv_rows,
    RAW_COLUMNS as BILLING_COLUMNS,
    allowed_menustar_restaurant,
    upsert_raw,
)


def extract_orders_from_zip(zip_path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            lower = name.lower()
            if not lower.endswith((".csv", ".xlsx")):
                continue
            payload = zf.read(name)
            if lower.endswith(".csv"):
                text = payload.decode(errors="ignore")
            else:
                df = pd.read_excel(io.BytesIO(payload))
                text = df.to_csv(index=False)
            basename = os.path.basename(name)
            allowed, _ = allowed_menustar_restaurant(basename.replace(".csv", "").replace(".xlsx", ""))
            if not allowed:
                continue
            provider = normalize_provider(basename)
            parsed = parse_csv_rows(text, provider, basename, "")
            for row in parsed:
                row["statement_source_file"] = basename
                row["source_file"] = f"{zip_path.name}:{name}"
            rows.extend(parsed)
    return rows


def parse_pdf_summary(pdf_bytes: bytes, source_name: str) -> Dict[str, str] | None:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if not pdf.pages:
            return None
        page = pdf.pages[0]
        text = page.extract_text() or ""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return None
        year = ""
        m = re.search(r"MenuStar\s+(\d{4})", lines[0])
        if m:
            year = m.group(1)
        restaurant_name = ""
        if len(lines) > 1:
            restaurant_name = lines[1]
        provider = normalize_provider(restaurant_name)
        tables = page.extract_tables() or []
        if not tables:
            return None
        values = None
        for table in tables:
            if len(table) >= 2:
                values = table[1]
                break
        if not values or len(values) < 5:
            return None
        return {
            "year": year,
            "provider": provider,
            "restaurant_name": restaurant_name,
            "all_orders_total": values[0],
            "prepaid_orders": values[1],
            "cash_orders": values[2],
            "menustar_fees": values[3],
            "total_payout": values[4],
            "source_file": source_name,
        }


def extract_yearly_from_zip(zip_path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".pdf"):
                continue
            payload = zf.read(name)
            summary = parse_pdf_summary(payload, f"{zip_path.name}:{name}")
            if summary:
                rows.append(summary)
    return rows


def collect_zip_rows(zip_dir: Path) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    order_rows: List[Dict[str, str]] = []
    yearly_rows: List[Dict[str, str]] = []
    for zip_path in sorted(zip_dir.glob("*.zip")):
        order_rows.extend(extract_orders_from_zip(zip_path))
        yearly_rows.extend(extract_yearly_from_zip(zip_path))
    return order_rows, yearly_rows


def run(
    zip_dir: str,
    orders_out: str,
    yearly_out: str,
    merge_into_billings: bool = False,
    billings_out: str = "",
) -> Tuple[int, int]:
    zip_dir_path = Path(zip_dir)
    order_rows, yearly_rows = collect_zip_rows(zip_dir_path)

    if order_rows:
        os.makedirs(os.path.dirname(orders_out), exist_ok=True)
        pd.DataFrame(order_rows).reindex(columns=BILLING_COLUMNS).to_csv(orders_out, index=False)
        print(f"Wrote {len(order_rows)} order row(s) -> {orders_out}")
    else:
        print("No order rows found in zip files.")

    if yearly_rows:
        os.makedirs(os.path.dirname(yearly_out), exist_ok=True)
        pd.DataFrame(yearly_rows).to_csv(yearly_out, index=False)
        print(f"Wrote {len(yearly_rows)} yearly summary row(s) -> {yearly_out}")
    else:
        print("No yearly summary PDFs found in zip files.")

    if merge_into_billings and billings_out and order_rows:
        upserted = upsert_raw(billings_out, order_rows)
        print(f"Upserted {upserted} zip-derived billing row(s) into {billings_out}")

    return len(order_rows), len(yearly_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract MenuStar zip reports (orders + yearly summaries).")
    parser.add_argument(
        "--zip-dir",
        default=takeout_path("Mail", "menustar"),
        help="Directory containing MenuStar zip files.",
    )
    parser.add_argument(
        "--orders-out",
        default=raw_path("menustar", "orders_from_zip_reports.csv"),
        help="Output CSV path for order rows.",
    )
    parser.add_argument(
        "--yearly-out",
        default=raw_path("menustar", "yearly_summaries_from_zip_reports.csv"),
        help="Output CSV path for yearly summaries.",
    )
    parser.add_argument(
        "--merge-into-billings",
        action="store_true",
        help="Also merge zip-derived rows into MenuStar billings_raw.csv.",
    )
    parser.add_argument(
        "--billings-out",
        default=raw_path("menustar", "billings_raw.csv"),
        help="MenuStar billings_raw CSV path used when --merge-into-billings is set.",
    )
    args = parser.parse_args()
    run(
        zip_dir=args.zip_dir,
        orders_out=args.orders_out,
        yearly_out=args.yearly_out,
        merge_into_billings=args.merge_into_billings,
        billings_out=args.billings_out,
    )


if __name__ == "__main__":
    main()
