#!/usr/bin/env python3
import argparse
import datetime as dt
import html
import mailbox
import os
import re
from email.utils import parsedate_to_datetime
from typing import Dict, List, Tuple

import pandas as pd

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.normalize import normalize_money

RAW_COLUMNS = [
    "order_id",
    "order_datetime",
    "subtotal",
    "tip",
    "tax",
    "tax_note",
    "delivery_fee",
    "service_fee",
    "account_credit_card_payment",
    "account_promo_gift_card_redemption",
    "account_service_fee",
    "account_dcom_promotion",
    "account_marketplace_facilitator_tax_withhold",
    "account_cc_percent_fee",
    "account_cc_transaction_fee",
    "payment",
    "total_invoice_amount",
    "invoice_id",
    "account_number",
    "restaurant_name",
    "raw_tokens",
    "source_file",
    "email_date",
    "added_at",
]


def extract_html(msg) -> str:
    parts = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                parts.append(payload.decode(charset, errors="replace"))
    if msg.get_content_type() == "text/html":
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            parts.append(payload.decode(charset, errors="replace"))
    return "\n".join(parts)


def clean_cell(cell_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", cell_html)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_label(label: str) -> str:
    return re.sub(r"[^a-z]+", "", label.lower())


LABEL_MAP = {
    "oid": "order_id",
    "time": "order_datetime",
    "subt": "subtotal",
    "tip": "tip",
    "tax": "tax",
    "df": "delivery_fee",
    "sf": "service_fee",
    "payment": "payment",
    "tia": "total_invoice_amount",
}

SUMMARY_LABEL_MAP = {
    "creditcardpayment": "account_credit_card_payment",
    "promotionalgiftcardredemption": "account_promo_gift_card_redemption",
    "servicefee": "account_service_fee",
    "dcompromotion": "account_dcom_promotion",
    "marketplacefacilitatorsalestaxwithhold": "account_marketplace_facilitator_tax_withhold",
    "ccpercentfee": "account_cc_percent_fee",
    "cctransactionfee": "account_cc_transaction_fee",
}


def extract_money(value: str) -> str:
    if not value:
        return ""
    match = re.findall(r"\(?-?\$?\d+(?:,\d{3})*(?:\.\d{2})?\)?", value)
    if not match:
        return normalize_money(value)
    return normalize_money(match[-1])


def extract_tax_note(value: str) -> str:
    if not value:
        return ""
    match = re.search(r"\[([^\]]+)\]", value)
    return match.group(1) if match else ""


def parse_invoice_meta(text: str) -> Tuple[str, str, str]:
    invoice_id = ""
    account_number = ""
    restaurant_name = ""

    match = re.search(r"INVOICE\s*#\s*(\d+)", text, re.IGNORECASE)
    if match:
        invoice_id = match.group(1)

    match = re.search(
        r"Account Number\s*&nbsp;\s*</td>\s*<td[^>]*>\s*<b>([^<]+)</b>",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        account_number = clean_cell(match.group(1))

    match = re.search(
        r"colspan=\"2\"[^>]*>\s*([^<]+)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        restaurant_name = clean_cell(match.group(1))

    return invoice_id, account_number, restaurant_name


def parse_charge_table(table_html: str) -> Tuple[List[str], List[List[str]]]:
    headers = [clean_cell(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", table_html, re.DOTALL)]
    rows: List[List[str]] = []
    for row_html in re.findall(r"<tr[^>]*bgcolor[^>]*>.*?</tr>", table_html, re.DOTALL | re.IGNORECASE):
        if "summary" in row_html.lower():
            continue
        cells = [clean_cell(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)]
        if not cells:
            continue
        rows.append(cells)
    return headers, rows


def parse_account_summary(text: str) -> Dict[str, str]:
    summary: Dict[str, str] = {}
    for table_html in re.findall(r"<table[^>]*>.*?</table>", text, re.DOTALL | re.IGNORECASE):
        headers = [clean_cell(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", table_html, re.DOTALL)]
        if len(headers) < 3:
            continue
        normalized_headers = [normalize_label(h) for h in headers[:3]]
        if normalized_headers[:3] != ["date", "description", "amount"]:
            continue
        _, table_rows = parse_charge_table(table_html)
        for cells in table_rows:
            if len(cells) < 3:
                continue
            description = cells[1]
            key = SUMMARY_LABEL_MAP.get(normalize_label(description))
            if not key:
                continue
            summary[key] = extract_money(cells[2])
        break
    return summary


def parse_billings_html(html_text: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    text = html.unescape(html_text)
    invoice_id, account_number, restaurant_name = parse_invoice_meta(text)
    account_summary = parse_account_summary(text)

    for table_html in re.findall(
        r"<table[^>]*class=\"charge-table\"[^>]*>.*?</table>",
        text,
        re.DOTALL | re.IGNORECASE,
    ):
        headers, table_rows = parse_charge_table(table_html)
        header_keys = [LABEL_MAP.get(normalize_label(h), "") for h in headers]

        for cells in table_rows:
            if not cells:
                continue
            row = {
                "order_id": "",
                "order_datetime": "",
                "subtotal": "",
                "tip": "",
                "tax": "",
                "tax_note": "",
                "delivery_fee": "",
                "service_fee": "",
                "account_credit_card_payment": account_summary.get(
                    "account_credit_card_payment", ""
                ),
                "account_promo_gift_card_redemption": account_summary.get(
                    "account_promo_gift_card_redemption", ""
                ),
                "account_service_fee": account_summary.get("account_service_fee", ""),
                "account_dcom_promotion": account_summary.get("account_dcom_promotion", ""),
                "account_marketplace_facilitator_tax_withhold": account_summary.get("account_marketplace_facilitator_tax_withhold", ""),
                "account_cc_percent_fee": account_summary.get("account_cc_percent_fee", ""),
                "account_cc_transaction_fee": account_summary.get(
                    "account_cc_transaction_fee", ""
                ),
                "payment": "",
                "total_invoice_amount": "",
                "invoice_id": invoice_id,
                "account_number": account_number,
                "restaurant_name": restaurant_name,
                "raw_tokens": " | ".join([c for c in cells if c]),
            }
            if header_keys and len(header_keys) == len(cells):
                for key, value in zip(header_keys, cells):
                    if not key:
                        continue
                    if key in (
                        "subtotal",
                        "tip",
                        "tax",
                        "delivery_fee",
                        "service_fee",
                        "payment",
                        "total_invoice_amount",
                    ):
                        row[key] = extract_money(value)
                        if key == "tax":
                            row["tax_note"] = extract_tax_note(value)
                    else:
                        row[key] = value
            else:
                # Fallback when headers are missing or mismatched.
                values = cells + [""] * (9 - len(cells))
                row.update(
                    {
                        "order_id": values[0],
                        "order_datetime": values[1],
                        "subtotal": extract_money(values[2]),
                        "tip": extract_money(values[3]),
                        "tax": extract_money(values[4]),
                        "tax_note": extract_tax_note(values[4]),
                        "delivery_fee": extract_money(values[5]),
                        "service_fee": extract_money(values[6]),
                        "payment": extract_money(values[7]),
                        "total_invoice_amount": extract_money(values[8]),
                    }
                )
            if row["order_id"]:
                rows.append(row)
    return rows


def parse_billings_mbox(mbox_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        email_date = ""
        if msg.get("Date"):
            try:
                email_date = parsedate_to_datetime(msg.get("Date")).isoformat()
            except (TypeError, ValueError):
                email_date = ""
        html_text = extract_html(msg)
        if not html_text:
            continue
        parsed_rows = parse_billings_html(html_text)
        for row in parsed_rows:
            row["source_file"] = os.path.basename(mbox_path)
            row["email_date"] = email_date
        rows.extend(parsed_rows)
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
        changed = False
        for col in RAW_COLUMNS:
            if col == "added_at":
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


def run(mbox: str, out: str) -> int:
    rows = parse_billings_mbox(mbox)
    rows = [row for row in rows if row.get("order_id")]
    updated = upsert_raw(out, rows)
    print(f"Upserted {updated} billing row(s) into {out}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract delivery.com billings mbox to raw CSV."
    )
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Billings-DeliveryCom.mbox"),
        help="Path to Billings-DeliveryCom.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("deliverycom", "billings_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()

    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
