#!/usr/bin/env python3
import argparse
import io
import mailbox
import os
import re
from email.utils import parsedate_to_datetime
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


def parse_summary_html_text(html: str, source_file: str, email_date: str) -> Dict[str, str]:
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
        "source_file": source_file,
        "email_date": email_date,
    }


def parse_invoice_pdf_payload(payload: bytes) -> str:
    invoice = ""
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            match = re.search(r"Invoice\s*#\s*([A-Za-z0-9-]+)", text, flags=re.IGNORECASE)
            if match:
                invoice = match.group(1)
                break
    return invoice


def parse_mbox(mbox_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        email_date = ""
        if msg.get("Date"):
            try:
                email_date = parsedate_to_datetime(msg.get("Date")).isoformat()
            except (TypeError, ValueError):
                email_date = ""
        html_rows: List[Dict[str, str]] = []
        invoice_numbers: List[str] = []
        if msg.is_multipart():
            for part in msg.walk():
                filename = part.get_filename() or ""
                content_type = part.get_content_type()
                payload = part.get_payload(decode=True) or b""
                if not payload:
                    continue
                if content_type == "text/html" or filename.lower().endswith(".html"):
                    try:
                        html_text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    except (LookupError, TypeError):
                        html_text = payload.decode(errors="replace")
                    html_rows.append(
                        parse_summary_html_text(
                            html_text,
                            filename or os.path.basename(mbox_path),
                            email_date,
                        )
                    )
                elif content_type == "application/pdf" or filename.lower().endswith(".pdf"):
                    invoice = parse_invoice_pdf_payload(payload)
                    if invoice:
                        invoice_numbers.append(invoice)
        # Attach invoice number from same email when available.
        if invoice_numbers:
            for row in html_rows:
                row["invoice_number"] = invoice_numbers[0]
        rows.extend(html_rows)
    return rows


def run(mbox_path: str, out_path: str) -> int:
    rows = parse_mbox(mbox_path)
    if not rows:
        return 0
    now = pd.Timestamp.utcnow().isoformat()
    for row in rows:
        row["added_at"] = now
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pd.DataFrame(rows).reindex(columns=RAW_COLUMNS).to_csv(out_path, index=False)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Brygid billings summary from mbox attachments.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Billings-Brygid.mbox"),
        help="Path to Billings-Brygid.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("brygid", "billings_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    count = run(args.mbox, args.out)
    print(f"Wrote {count} rows to {args.out}")


if __name__ == "__main__":
    main()
