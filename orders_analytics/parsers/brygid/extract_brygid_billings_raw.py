#!/usr/bin/env python3
import argparse
import io
import mailbox
import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Dict, List

import pdfplumber
import pandas as pd

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.normalize import normalize_money

RAW_COLUMNS = [
    "billing_date",
    "billing_datetime",
    "total_order_count",
    "total_sales",
    "average_check",
    "total_service_fees",
    "commission_percentage",
    "account_number",
    "invoice_number",
    "due_date",
    "invoice_total",
    "other_service_charges",
    "notes",
    "source_file",
    "invoice_source_file",
    "email_date",
    "errors",
    "added_at",
]

def normalize_date(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue
    return text


def to_iso_datetime(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%dT00:00:00")
        except ValueError:
            continue
    return ""


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

    billing_date = normalize_date(find("Billing Date"))
    total_order_count = find("Total Order Count")
    total_sales = normalize_money(find("Total Sales"))
    average_check = normalize_money(find("Average Check"))
    total_service_fees = normalize_money(find("Total Service Fees"))
    if not billing_date:
        return {}
    commission_percentage = ""
    try:
        if total_sales and total_service_fees:
            commission_percentage = f"{(float(total_service_fees) / float(total_sales) * 100):.2f}"
    except ValueError:
        commission_percentage = ""
    billing_datetime = to_iso_datetime(billing_date)
    return {
        "billing_date": billing_date,
        "billing_datetime": billing_datetime,
        "total_order_count": total_order_count,
        "total_sales": total_sales,
        "average_check": average_check,
        "total_service_fees": total_service_fees,
        "commission_percentage": commission_percentage,
        "account_number": "",
        "invoice_number": "",
        "due_date": "",
        "invoice_total": "",
        "source_file": source_file,
        "invoice_source_file": "",
        "email_date": email_date,
        "errors": "",
    }


def parse_summary_pdf_text(text: str, source_file: str, email_date: str) -> Dict[str, str]:
    def find(label: str) -> str:
        match = re.search(
            rf"{re.escape(label)}\s*:\s*([^\n]+)",
            text,
            flags=re.IGNORECASE,
        )
        return match.group(1).strip() if match else ""

    billing_date = normalize_date(find("Billing Date"))
    if not billing_date:
        return {}
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
    billing_datetime = to_iso_datetime(billing_date)
    return {
        "billing_date": billing_date,
        "billing_datetime": billing_datetime,
        "total_order_count": total_order_count,
        "total_sales": total_sales,
        "average_check": average_check,
        "total_service_fees": total_service_fees,
        "commission_percentage": commission_percentage,
        "account_number": "",
        "invoice_number": "",
        "due_date": "",
        "invoice_total": "",
        "source_file": source_file,
        "invoice_source_file": "",
        "email_date": email_date,
        "errors": "",
    }


def parse_invoice_pdf_payload(payload: bytes, source_file: str) -> Dict[str, str]:
    account_number = ""
    invoice_number = ""
    due_date = ""
    invoice_total = ""
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not invoice_number:
                match = re.search(r"Invoice\s*#\s*([A-Za-z0-9-]+)", text, flags=re.IGNORECASE)
                if match:
                    invoice_number = match.group(1).strip()
            if not account_number:
                match = re.search(r"Account\s*#\s*[:#]?\s*([A-Za-z0-9-]+)", text, flags=re.IGNORECASE)
                if match:
                    account_number = match.group(1).strip()
            if not due_date:
                match = re.search(
                    r"Due\s*Date\s*[:#]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})",
                    text,
                    flags=re.IGNORECASE,
                )
                if match:
                    due_date = normalize_date(match.group(1))
            if not invoice_total:
                match = re.search(r"Total\s+USD\s+([\d,]+\.\d{2})", text, flags=re.IGNORECASE)
                if not match:
                    match = re.search(r"Balance\s*Due\s*USD\s*([\d,]+\.\d{2})", text, flags=re.IGNORECASE)
                if not match:
                    match = re.search(
                        r"Total\s*(?:Amount\s*Due)?\s*[:#]?\s*\$?\s*([\d,]+\.\d{2})",
                        text,
                        flags=re.IGNORECASE,
                    )
                if match:
                    invoice_total = normalize_money(match.group(1))
    return {
        "account_number": account_number,
        "invoice_number": invoice_number,
        "due_date": due_date,
        "invoice_total": invoice_total,
        "invoice_source_file": source_file,
    }


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
        summary_rows: List[Dict[str, str]] = []
        invoice_rows: List[Dict[str, str]] = []
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
                    summary_rows.append(
                        parse_summary_html_text(
                            html_text,
                            filename or os.path.basename(mbox_path),
                            email_date,
                        )
                    )
                elif content_type == "application/pdf" or filename.lower().endswith(".pdf"):
                    with pdfplumber.open(io.BytesIO(payload)) as pdf:
                        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
                    if "order summary" in text.lower() or "total order count" in text.lower():
                        summary = parse_summary_pdf_text(
                            text,
                            filename or os.path.basename(mbox_path),
                            email_date,
                        )
                        if summary:
                            summary_rows.append(summary)
                        continue
                    if "statement of account" in text.lower():
                        continue
                    invoice = parse_invoice_pdf_payload(payload, filename or os.path.basename(mbox_path))
                    if invoice.get("invoice_number") or invoice.get("account_number"):
                        invoice_rows.append(invoice)

        for summary in summary_rows:
            billing_date = normalize_date(summary.get("billing_date", ""))
            total_service_fees = normalize_money(summary.get("total_service_fees", ""))
            candidates = invoice_rows[:]
            selected = None
            if billing_date:
                matches_due = [inv for inv in candidates if inv.get("due_date") == billing_date]
            else:
                matches_due = []
            matches_due_total = [
                inv for inv in matches_due if inv.get("invoice_total") and inv.get("invoice_total") == total_service_fees
            ]
            if matches_due_total:
                selected = matches_due_total[0]
            elif matches_due:
                selected = matches_due[0]
            else:
                matches_total = [
                    inv for inv in candidates if inv.get("invoice_total") and inv.get("invoice_total") == total_service_fees
                ]
                if matches_total:
                    selected = matches_total[0]
                elif len(candidates) == 1:
                    selected = candidates[0]
            if selected:
                summary["account_number"] = selected.get("account_number", "")
                summary["invoice_number"] = selected.get("invoice_number", "")
                summary["due_date"] = selected.get("due_date", "")
                summary["invoice_total"] = selected.get("invoice_total", "")
                summary["invoice_source_file"] = selected.get("invoice_source_file", "")
                errors = []
                if summary.get("due_date") and billing_date and summary.get("due_date") != billing_date:
                    errors.append("due_date_mismatch")
                if summary.get("invoice_total") and total_service_fees and summary.get("invoice_total") != total_service_fees:
                    errors.append("service_fee_total_mismatch")
                if errors:
                    summary["errors"] = " | ".join([summary.get("errors", ""), *errors]).strip(" |")
            if summary.get("billing_date"):
                rows.append(summary)
    return rows


def run(mbox_path: str, out_path: str) -> int:
    rows = [row for row in parse_mbox(mbox_path) if row.get("billing_date")]
    if not rows:
        return 0
    adjustments_path = raw_path("brygid", "adjustments_raw.csv")
    adjustments = {}
    if os.path.exists(adjustments_path):
        try:
            adj_df = pd.read_csv(adjustments_path, dtype=str).fillna("")
            for record in adj_df.to_dict("records"):
                key = normalize_date(record.get("billing_date", ""))
                if not key:
                    continue
                adjustments[key] = {
                    "other_service_charges": normalize_money(record.get("other_service_charges", "")),
                    "notes": record.get("notes", "").strip(),
                }
        except Exception:
            adjustments = {}
    def score(row: Dict[str, str]) -> int:
        return sum(1 for value in row.values() if str(value or "").strip())
    deduped: Dict[str, Dict[str, str]] = {}
    for row in rows:
        key = row.get("billing_date", "")
        if not key:
            continue
        current = deduped.get(key)
        if current is None:
            deduped[key] = row
            continue
        if score(row) > score(current):
            deduped[key] = row
            continue
        if score(row) == score(current):
            if str(row.get("email_date", "")) > str(current.get("email_date", "")):
                deduped[key] = row
    rows = list(deduped.values())
    if adjustments:
        for row in rows:
            key = normalize_date(row.get("billing_date", ""))
            adj = adjustments.get(key)
            if not adj:
                continue
            if adj.get("other_service_charges"):
                row["other_service_charges"] = adj["other_service_charges"]
            if adj.get("notes"):
                row["notes"] = " | ".join([row.get("notes", ""), adj["notes"]]).strip(" |")
    now = pd.Timestamp.utcnow().isoformat()
    for row in rows:
        row["added_at"] = now
    df = pd.DataFrame(rows).reindex(columns=RAW_COLUMNS)
    if "billing_datetime" in df.columns:
        sort_key = pd.to_datetime(
            df["billing_datetime"],
            format="%Y-%m-%dT%H:%M:%S",
            errors="coerce",
        )
        df = df.assign(_sort_key=sort_key).sort_values(
            by="_sort_key",
            ascending=True,
            kind="stable",
        ).drop(columns=["_sort_key"])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path, index=False)
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
