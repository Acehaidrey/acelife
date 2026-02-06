#!/usr/bin/env python3
import argparse
import glob
import os
import re
from typing import Dict, List

import pdfplumber
import pandas as pd

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.normalize import normalize_money

RAW_COLUMNS = [
    "invoice_number",
    "billing_date",
    "total_order_count",
    "total_sales",
    "average_check",
    "total_service_fees",
    "commission_percentage",
    "source_file",
    "email_date",
    "added_at",
]


def parse_summary_html(path: str) -> Dict[str, str]:
    with open(path, encoding="utf-8", errors="replace") as handle:
        html = handle.read()
    def find(label: str) -> str:
        match = re.search(
            rf"{re.escape(label)}\s*:?</b></td>\s*<td[^>]*>\s*([^<]+)",
            html,
            flags=re.IGNORECASE,
        )
        if not match:
            match = re.search(rf"{re.escape(label)}\s*:?\\s*([^<\\n]+)", html, flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""
    billing_date = find("Billing Date")
    total_order_count = find("Total Order Count")
    total_sales = normalize_money(find("Total Sales"))
    average_check = normalize_money(find("Average Check"))
    total_service_fees = normalize_money(find("Total Service Fees"))
    commission_percentage = ""
    try:
        if total_sales and total_service_fees:
            commission_percentage = f"{(float(total_service_fees) / float(total_sales) * 100):.2f}"
    except ValueError:
        commission_percentage = ""
    return {
        "invoice_number": "",
        "billing_date": billing_date,
        "total_order_count": total_order_count,
        "total_sales": total_sales,
        "average_check": average_check,
        "total_service_fees": total_service_fees,
        "commission_percentage": commission_percentage,
        "source_file": os.path.basename(path),
        "email_date": "",
    }


def parse_invoice_pdf(path: str) -> str:
    invoice = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            match = re.search(r"Invoice\s*#\s*([A-Za-z0-9-]+)", text, flags=re.IGNORECASE)
            if match:
                invoice = match.group(1)
                break
    return invoice


def run(mail_dir: str, out_path: str) -> int:
    rows: List[Dict[str, str]] = []
    html_files = glob.glob(os.path.join(mail_dir, "*Order-Summary*.html"))
    for path in html_files:
        rows.append(parse_summary_html(path))
    invoice_files = glob.glob(os.path.join(mail_dir, "*Invoice*.pdf"))
    invoice_numbers = []
    for path in invoice_files:
        invoice = parse_invoice_pdf(path)
        if invoice:
            invoice_numbers.append(invoice)
    if invoice_numbers:
        # If multiple summaries, just attach first invoice number to each summary row.
        for row in rows:
            row["invoice_number"] = invoice_numbers[0]
    if not rows:
        return 0
    now = pd.Timestamp.utcnow().isoformat()
    for row in rows:
        row["added_at"] = now
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pd.DataFrame(rows).reindex(columns=RAW_COLUMNS).to_csv(out_path, index=False)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Brygid billings summary from HTML/PDF files.")
    parser.add_argument(
        "--mail-dir",
        default=takeout_path("Mail"),
        help="Directory containing Brygid summary HTML/PDF files.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("brygid", "billings_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    count = run(args.mail_dir, args.out)
    print(f"Wrote {count} rows to {args.out}")


if __name__ == "__main__":
    main()
