#!/usr/bin/env python3
import argparse
import datetime as dt
import io
import mailbox
import os
import re
from typing import Dict, List

import pandas as pd
import pdfplumber

from orders_analytics.utils.constants import raw_path, takeout_path

RAW_COLUMNS = [
    "order_id",
    "order_date",
    "customer_name",
    "company_name",
    "phone",
    "email",
    "address",
    "items",
    "item_count",
    "status",
    "added_at",
]


def extract_pdf_text(payload: bytes) -> str:
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def parse_order_text(text: str) -> Dict[str, str]:
    row: Dict[str, str] = {
        "order_id": "",
        "order_date": "",
        "customer_name": "",
        "company_name": "",
        "phone": "",
        "email": "",
        "address": "",
        "items": "",
        "item_count": "",
        "status": "delivered",
    }
    order_id = re.search(r"ID:\s*(\d+)", text)
    if not order_id:
        order_id = re.search(r"Order\s*(?:ID|#)\s*[:#]?\s*([A-Z0-9-]+)", text, re.IGNORECASE)
    if order_id:
        row["order_id"] = order_id.group(1).strip()

    contact = re.search(r"CONTACT:\s*(.+)", text, re.IGNORECASE)
    if contact:
        row["customer_name"] = contact.group(1).strip()
    company = re.search(r"COMPANY:\s*(.+)", text, re.IGNORECASE)
    if company:
        company_name = company.group(1).strip()
        company_name = re.sub(r"\bto\s*\+?\d{10,}\b", "", company_name, flags=re.IGNORECASE).strip()
        row["company_name"] = company_name
    for line in text.splitlines():
        if "EMAIL:" in line.upper():
            match = re.search(r"[\w\.-]+@[\w\.-]+", line)
            if match:
                row["email"] = match.group(0).strip()
        if "PHONE:" in line.upper():
            match = re.search(r"(\+?\d{10,})", line)
            if match:
                row["phone"] = match.group(1).strip()

    address = ""
    lines = [line.strip() for line in text.splitlines()]
    if "ADDRESS:" in lines:
        idx = lines.index("ADDRESS:")
        addr_lines = []
        for line in lines[idx + 1 :]:
            if not line:
                break
            if line.endswith(":"):
                break
            if "DELIVERY INSTRUCTIONS" in line.upper():
                break
            if "SETUP INSTRUCTIONS" in line.upper():
                break
            if "BRING ORDER INSTRUCTIONS" in line.upper():
                break
            if "CATER2.ME LABELS" in line.upper():
                break
            if line.upper().startswith("KEY"):
                break
            addr_lines.append(line)
        address = ", ".join([line for line in addr_lines if line])
        address = address.replace(",,", ",")
    if address:
        row["address"] = address

    order_date = re.search(r"ORDER DATE:\s*([A-Z]{3},\s*)?(\d{1,2}/\d{1,2}/\d{2,4})", text, re.IGNORECASE)
    if order_date:
        row["order_date"] = order_date.group(2).strip()

    items: List[str] = []
    item_count = 0
    in_cart = False
    cart_items: List[str] = []
    for line in lines:
        if line == "CART LIST":
            in_cart = True
            continue
        if in_cart and (line.startswith("KEY") or line.startswith("QUESTIONS?")):
            in_cart = False
        if in_cart:
            cart_items.append(line)

    for line in cart_items:
        match = re.search(r"(\d+)\s*x\s*([A-Z0-9]+)\s*\((.+?)\)", line)
        if match:
            qty = int(match.group(1))
            code = match.group(2).strip()
            name = match.group(3).strip()
            items.append(f"{qty} x {name} ({code})")
            item_count += qty

    if not items:
        for idx, line in enumerate(lines):
            if "ITEM DETAILS" in line or "QTY ITEM CODE" in line:
                start_idx = idx
                break
        else:
            start_idx = None

        if start_idx is not None:
            for i in range(start_idx + 1, len(lines)):
                line = lines[i].strip()
                if not line:
                    continue
                if line.startswith("KEY") or line.startswith("QUESTIONS?") or line.startswith("CART LIST"):
                    break
                match = re.search(r"(.+?)\s*\((E\d+)\)$", line)
                if not match:
                    continue
                name = match.group(1).strip()
                code = match.group(2).strip()
                qty = 1
                for j in range(i + 1, min(i + 4, len(lines))):
                    next_line = lines[j].strip()
                    if re.fullmatch(r"\d+", next_line):
                        qty = int(next_line)
                        break
                items.append(f"{qty} x {name} ({code})")
                item_count += qty

    if not items:
        for line in lines:
            match = re.match(r"^(\d+)\s+(E\d+)\s+", line)
            if match:
                qty = int(match.group(1))
                code = match.group(2)
                items.append(f"{qty} x {code}")
                item_count += qty

    if items:
        row["items"] = "; ".join(items)
        row["item_count"] = str(item_count)

    row["phone"] = ""

    return row


def parse_mbox(mbox_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        subject = msg.get("subject", "") or ""
        is_cancelled = "CANCEL" in subject.upper()
        for part in msg.walk():
            if part.get_content_type() == "application/pdf":
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                text = extract_pdf_text(payload)
                row = parse_order_text(text)
                if row.get("order_id"):
                    if is_cancelled:
                        row["status"] = "cancelled"
                    rows.append(row)
    return rows


def upsert_raw(existing_path: str, new_rows: List[Dict[str, str]]) -> int:
    now = dt.datetime.now().isoformat()
    if os.path.exists(existing_path):
        existing_df = pd.read_csv(existing_path, dtype=str).fillna("")
        existing_rows = existing_df.to_dict("records")
    else:
        existing_rows = []

    existing_map = {str(row.get("order_id", "")).strip(): row for row in existing_rows}
    updated = 0
    for row in new_rows:
        order_id = str(row.get("order_id", "")).strip()
        if not order_id:
            continue
        current = existing_map.get(order_id)
        if current is None:
            row["added_at"] = now
            existing_map[order_id] = row
            updated += 1
            continue
        # If any row shows cancelled, prefer cancelled status.
        if (row.get("status") or "").strip().lower() == "cancelled":
            current["status"] = "cancelled"
        changed = False
        for col in RAW_COLUMNS:
            if col == "added_at":
                continue
            if col == "status" and str(current.get("status", "")).strip().lower() == "cancelled":
                continue
            old_val = str(current.get(col, "") or "")
            new_val = str(row.get(col, "") or "")
            if old_val != new_val:
                current[col] = new_val
                changed = True
        if changed:
            current["added_at"] = now
            updated += 1

    final_rows = list(existing_map.values())
    for row in final_rows:
        row.setdefault("added_at", now)
    os.makedirs(os.path.dirname(existing_path), exist_ok=True)
    pd.DataFrame(final_rows).reindex(columns=RAW_COLUMNS).to_csv(existing_path, index=False)
    return updated


def run(mbox_path: str, out_path: str) -> int:
    rows = parse_mbox(mbox_path)
    updated = upsert_raw(out_path, rows)
    print(f"Upserted {updated} order row(s) into {out_path}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Cater2Me orders PDFs to raw CSV.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Orders-Cater2Me.mbox"),
        help="Path to Orders-Cater2Me.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("cater2me", "orders_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
