#!/usr/bin/env python3
import argparse
import datetime as dt
import io
import mailbox
import os
import re
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

import pandas as pd
import pdfplumber

from orders_analytics.utils.constants import raw_path, takeout_path


def _clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).replace("\n", " ").strip()


def _is_header_row(row: List[object]) -> bool:
    cells = [_clean(cell).lower() for cell in row]
    return any("order id" in cell or "orderid" in cell for cell in cells)


def _header_columns(row: List[object]) -> List[str]:
    cols: List[str] = []
    for idx, cell in enumerate(row):
        value = _clean(cell)
        if not value:
            value = f"column_{idx + 1}"
        cols.append(value)
    return cols


def _extract_order_id(record: Dict[str, str]) -> str:
    for key, value in record.items():
        key_lower = key.lower().replace("_", " ")
        if "order id" in key_lower or "orderid" in key_lower:
            return _clean(value)
    return ""


def _parse_pdf_tables(
    payload: bytes,
    filename: str,
    email_date: str,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            for table in tables:
                if not table:
                    continue
                header_idx: Optional[int] = None
                for idx, table_row in enumerate(table):
                    if _is_header_row(table_row):
                        header_idx = idx
                        break
                if header_idx is None:
                    continue
                headers = _header_columns(table[header_idx])
                for raw_row in table[header_idx + 1 :]:
                    values = [_clean(cell) for cell in raw_row]
                    if not any(values):
                        continue
                    if values and values[0].lower().startswith("grand total"):
                        continue
                    if any(cell.lower().startswith("grand total") for cell in values):
                        continue
                    padded = values + [""] * max(0, len(headers) - len(values))
                    record = {headers[i]: padded[i] if i < len(padded) else "" for i in range(len(headers))}
                    order_id = _extract_order_id(record)
                    if not order_id:
                        continue
                    record["provider"] = "AROMA"
                    record["source_file"] = filename
                    record["source_sheet"] = f"pdf_page_{page_number}"
                    record["email_date"] = email_date
                    rows.append(record)
    return rows


def _parse_pdf_text_blocks(
    payload: bytes,
    filename: str,
    email_date: str,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)

    block_pattern = re.compile(r"OrderId\s*:\s*(.+?)(?=\nOrderId\s*:|\Z)", re.IGNORECASE | re.DOTALL)
    for match in block_pattern.finditer(text):
        block = match.group(0)
        order_id = _clean(match.group(1).splitlines()[0])
        if not order_id:
            continue
        customer = ""
        platform = ""
        pickup_time = ""
        subtotal = ""
        tax = ""
        grand_total = ""

        customer_match = re.search(r"Customer\s*:\s*(.+)", block, flags=re.IGNORECASE)
        if customer_match:
            customer = _clean(customer_match.group(1))
        platform_match = re.search(r"Platform\s*:\s*(.+)", block, flags=re.IGNORECASE)
        if platform_match:
            platform = _clean(platform_match.group(1))
        pickup_match = re.search(r"Pickup time\s*:\s*(.+)", block, flags=re.IGNORECASE)
        if pickup_match:
            pickup_time = _clean(pickup_match.group(1))
        subtotal_match = re.search(r"Sub Total\s*\$([0-9.,]+)", block, flags=re.IGNORECASE)
        if subtotal_match:
            subtotal = _clean(subtotal_match.group(1))
        tax_match = re.search(r"Tax[^\n]*\s\$([0-9.,]+)", block, flags=re.IGNORECASE)
        if tax_match:
            tax = _clean(tax_match.group(1))
        total_match = re.search(r"Grand Total\s*\$([0-9.,]+)", block, flags=re.IGNORECASE)
        if total_match:
            grand_total = _clean(total_match.group(1))

        rows.append(
            {
                "OrderId": order_id,
                "Customer": customer,
                "Platform": platform,
                "Pickup time": pickup_time,
                "Sub Total": subtotal,
                "Tax": tax,
                "Grand Total": grand_total,
                "provider": "AROMA",
                "source_file": filename,
                "source_sheet": "pdf_text_block",
                "email_date": email_date,
            }
        )
    return rows


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
        if not msg.is_multipart():
            continue
        for part in msg.walk():
            filename = part.get_filename()
            if not filename or not filename.lower().endswith(".pdf"):
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            pdf_rows = _parse_pdf_tables(payload, filename, email_date)
            if not pdf_rows:
                pdf_rows = _parse_pdf_text_blocks(payload, filename, email_date)
            rows.extend(pdf_rows)
    return rows


def write_raw(path: str, rows: List[Dict[str, str]]) -> int:
    now = dt.datetime.now().isoformat()
    for row in rows:
        row.setdefault("added_at", now)

    all_columns: List[str] = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                all_columns.append(key)
    if "added_at" not in seen:
        all_columns.append("added_at")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(rows).reindex(columns=all_columns).to_csv(path, index=False)
    return len(rows)


def run(mbox_path: str, out_path: str) -> int:
    rows = parse_mbox(mbox_path)
    count = write_raw(out_path, rows)
    print(f"Wrote {count} Mayaeats billing row(s) to {out_path}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Mayaeats billings raw CSV from mbox PDFs.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Billings-Mayaeats.mbox"),
        help="Path to Billings-Mayaeats.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("mayaeats", "billings_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
