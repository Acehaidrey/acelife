#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import io
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Dict, List

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from orders_analytics.parsers.menustar.extract_menustar_billings_raw import (
    allowed_menustar_restaurant,
    parse_csv_rows,
)
from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.normalize import normalize_money
from orders_analytics.utils.providers import normalize_provider


def infer_year(zip_name: str) -> str:
    m = re.search(r"(20\d{2})", zip_name)
    return m.group(1) if m else ""


def infer_month(order_rows: List[Dict[str, str]], statement_file: str) -> str:
    if order_rows:
        dt_text = str(order_rows[0].get("order_datetime", "")).strip()
        if dt_text:
            try:
                return dt.datetime.fromisoformat(dt_text.replace("Z", "+00:00")).strftime("%Y-%m")
            except ValueError:
                pass
    # Fallback: parse month token from filename (e.g. "... Apr.csv")
    token = Path(statement_file).stem.split()[-1].strip(" -")
    month_map = {
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    mm = month_map.get(token.lower()[:3])
    return f"0000-{mm}" if mm else ""


def extract_summary_from_text(text: str) -> Dict[str, str]:
    summary = {
        "all_orders": "",
        "prepaid_orders": "",
        "menustar_fees": "",
        "adjustments": "",
        "net_payout": "",
    }
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if not row or not row[0]:
            continue
        label = row[0].strip().lower()
        value = normalize_money(row[1] if len(row) > 1 else "")
        if label == "all orders":
            summary["all_orders"] = value
        elif label == "pre-paid orders":
            summary["prepaid_orders"] = value
        elif label == "menustar fees":
            summary["menustar_fees"] = value
        elif label == "adjustments":
            summary["adjustments"] = value
        elif label == "net payout":
            summary["net_payout"] = value
    return summary


def parse_statement_payload(payload: bytes, filename: str) -> tuple[str, List[Dict[str, str]], Dict[str, str]]:
    lower = filename.lower()
    if lower.endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(payload))
        text = df.to_csv(index=False)
    else:
        text = payload.decode(errors="ignore")
    provider = normalize_provider(filename)
    order_rows = parse_csv_rows(text, provider, filename, "")
    summary = extract_summary_from_text(text)
    return provider, order_rows, summary


def run(zip_dir: str, out_path: str) -> int:
    rows: List[Dict[str, str]] = []
    for zip_path in sorted(Path(zip_dir).glob("*.zip")):
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                lower = member.lower()
                if not lower.endswith((".csv", ".xlsx")):
                    continue
                statement_file = os.path.basename(member)
                allowed, _ = allowed_menustar_restaurant(
                    statement_file.replace(".csv", "").replace(".xlsx", "")
                )
                if not allowed:
                    continue
                payload = zf.read(member)
                provider, order_rows, summary = parse_statement_payload(payload, statement_file)
                rows.append(
                    {
                        "provider": provider,
                        "year": infer_year(zip_path.name),
                        "month": infer_month(order_rows, statement_file),
                        "statement_source_file": statement_file,
                        "zip_file": zip_path.name,
                        "zip_member_path": member,
                        "all_orders": summary["all_orders"],
                        "prepaid_orders": summary["prepaid_orders"],
                        "menustar_fees": summary["menustar_fees"],
                        "adjustments": summary["adjustments"],
                        "net_payout": summary["net_payout"],
                    }
                )

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"Wrote {len(rows)} statement summary row(s) -> {out_path}")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract per-statement MenuStar summaries from zip files."
    )
    parser.add_argument(
        "--zip-dir",
        default=takeout_path("Mail", "menustar"),
        help="Directory containing MenuStar zip files.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("menustar", "statement_summaries_from_zip_reports.csv"),
        help="Output CSV path.",
    )
    args = parser.parse_args()
    run(args.zip_dir, args.out)


if __name__ == "__main__":
    main()
