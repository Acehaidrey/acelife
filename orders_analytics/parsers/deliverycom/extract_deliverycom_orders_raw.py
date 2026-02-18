#!/usr/bin/env python3
import argparse
import email
import datetime as dt
from datetime import datetime
import mailbox
from pathlib import Path
import os
import re
from email.utils import parsedate_to_datetime
from typing import Dict, List

import pandas as pd


from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.normalize import normalize_money, normalize_datetime
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.parsers.deliverycom.parse_deliverycom_orders import parse_order

RAW_COLUMNS = [
    "order_id",
    "provider",
    "restaurant_name",
    "order_datetime",
    "order_type",
    "payment_type",
    "customer_name",
    "phone",
    "address",
    "items",
    "item_count",
    "subtotal",
    "tax",
    "tip",
    "delivery_fee",
    "total",
    "discount",
    "status",
    "notes",
    "source_file",
    "email_date",
    "added_at",
]






def clean_cell(cell_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", cell_html)
    text = re.sub(r"\s+", " ", text).strip()
    return text

DATE_LINE_RE = re.compile(r"([A-Za-z]+,\s*)?([A-Za-z]+\s+\d{1,2})(st|nd|rd|th)?\s+\d{4}")




def parse_daily_summary_html(html: str) -> list[dict]:
    if not html:
        return []
    # extract report date
    date_match = re.search(r">([^<]+)Order Report", html, re.IGNORECASE)
    report_date = ""
    if date_match:
        report_date = parse_daily_summary_date(date_match.group(1))
    if not report_date:
        m = DATE_LINE_RE.search(html)
        if m:
            report_date = parse_daily_summary_date(m.group(0))
    if not report_date:
        m = re.search(r"<td[^>]*align\s*=\s*\"right\"[^>]*>([^<]+)</td>", html, re.IGNORECASE)
        if m:
            report_date = parse_daily_summary_date(m.group(1))
    restaurant_name = ""
    m = re.search(r"Daily Order Report for\s+([^<]+)", html, re.IGNORECASE)
    if m:
        restaurant_name = m.group(1).strip()
    orders = []
    for table_html in re.findall(r"<table[^>]*>.*?</table>", html, re.DOTALL | re.IGNORECASE):
        headers = [clean_cell(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", table_html, re.DOTALL)]
        if "Order Number" not in headers or "Status" not in headers:
            continue
        for row_html in re.findall(r"<tr[^>]*>.*?</tr>", table_html, re.DOTALL | re.IGNORECASE):
            cells = [clean_cell(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)]
            if not cells or len(cells) < len(headers):
                continue
            row = {headers[i]: cells[i] for i in range(len(headers))}
            order_id = str(row.get("Order Number", "")).strip()
            if not order_id or order_id.lower() == "grand total":
                continue
            payment_raw = str(row.get("Payment Type", "")).strip()
            payment_norm = payment_raw
            if payment_raw.lower() in ("cash", "cash order"):
                payment_norm = "cash"
            elif payment_raw.lower() in ("house account", "credit card", "prepaid"):
                payment_norm = "credit"
            time_val = str(row.get("Time", "")).strip()
            order_datetime = ""
            if report_date and time_val:
                order_datetime = normalize_datetime(
                    f"{report_date} {time_val}", formats=("%Y-%m-%d %I:%M %p",)
                )
            orders.append(
                {
                    "order_id": order_id,
                    "provider": normalize_provider(restaurant_name),
                    "restaurant_name": restaurant_name,
                    "order_datetime": order_datetime,
                    "order_type": str(row.get("Order Type", "")).strip(),
                    "payment_type": payment_norm,
                    "customer_name": "",
                    "phone": "",
                    "address": "",
                    "items": "",
                    "item_count": "",
                    "subtotal": normalize_money(str(row.get("Subtotal", ""))),
                    "tax": normalize_money(str(row.get("Tax", ""))),
                    "tip": normalize_money(str(row.get("Tip", ""))),
                    "delivery_fee": "",
                    "total": normalize_money(str(row.get("Total", ""))),
                    "discount": "",
                    "status": str(row.get("Status", "")).strip(),
                    "notes": "daily_order_summary",
                }
            )
        break
    return orders


def extract_html_from_msg(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                return (part.get_payload(decode=True) or b"").decode(
                    part.get_content_charset() or "utf-8", errors="ignore"
                )
    if msg.get_content_type() == "text/html":
        return (msg.get_payload(decode=True) or b"").decode(
            msg.get_content_charset() or "utf-8", errors="ignore"
        )
    return ""

def parse_daily_summary_date(value: str) -> str:
    if not value:
        return ""
    match = DATE_LINE_RE.search(value)
    if not match:
        return ""
    cleaned = match.group(0)
    cleaned = re.sub(r"^[A-Za-z]+,\s*", "", cleaned)
    cleaned = re.sub(r"(\d{1,2})(st|nd|rd|th)", r"\1", cleaned)
    cleaned = cleaned.replace(",", "")
    try:
        return datetime.strptime(cleaned.strip(), "%B %d %Y").date().isoformat()
    except ValueError:
        return ""


def parse_daily_summary_eml(eml_path: str) -> list[dict]:
    msg = email.message_from_bytes(Path(eml_path).read_bytes())
    html = extract_html_from_msg(msg)
    return parse_daily_summary_html(html)

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


def run(mbox_path: str, out_path: str) -> int:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        parsed = parse_order(msg)
        if not parsed:
            html = extract_html_from_msg(msg)
            parsed_rows = parse_daily_summary_html(html)
            if parsed_rows:
                email_date = ""
                if msg.get("Date"):
                    try:
                        email_date = parsedate_to_datetime(msg.get("Date")).isoformat()
                    except Exception:
                        email_date = ""
                for row in parsed_rows:
                    row["source_file"] = os.path.basename(mbox_path)
                    row["email_date"] = email_date
                rows.extend(parsed_rows)
            continue
        email_date = ""
        if msg.get("Date"):
            try:
                email_date = parsedate_to_datetime(msg.get("Date")).isoformat()
            except Exception:
                email_date = ""
        rows.append(
            {
                "order_id": parsed.get("order_id", ""),
                "provider": parsed.get("provider", ""),
                "restaurant_name": parsed.get("restaurant_name", ""),
                "order_datetime": parsed.get("order_datetime", ""),
                "order_type": parsed.get("order_type", ""),
                "payment_type": parsed.get("payment_type", ""),
                "customer_name": parsed.get("customer_name", ""),
                "phone": parsed.get("phone", ""),
                "address": parsed.get("address", ""),
                "items": parsed.get("items", ""),
                "item_count": parsed.get("item_count", ""),
                "subtotal": parsed.get("subtotal", ""),
                "tax": parsed.get("tax", ""),
                "tip": parsed.get("tip", ""),
                "delivery_fee": parsed.get("delivery_fee", ""),
                "total": parsed.get("total", ""),
                "discount": parsed.get("discount", ""),
                "notes": parsed.get("notes", ""),
                "source_file": os.path.basename(mbox_path),
                "email_date": email_date,
            }
        )
    mail_dir = os.path.dirname(mbox_path)
    if os.path.isdir(mail_dir):
        for fname in os.listdir(mail_dir):
            if not fname.lower().endswith(".eml"):
                continue
            if not fname.lower().startswith("daily order summary"):
                continue
            eml_path = os.path.join(mail_dir, fname)
            try:
                parsed_rows = parse_daily_summary_eml(eml_path)
            except Exception:
                parsed_rows = []
            if not parsed_rows:
                continue
            email_date = ""
            try:
                msg = email.message_from_bytes(Path(eml_path).read_bytes())
                if msg.get("Date"):
                    email_date = parsedate_to_datetime(msg.get("Date")).isoformat()
            except Exception:
                email_date = ""
            for row in parsed_rows:
                row["source_file"] = fname
                row["email_date"] = email_date
            rows.extend(parsed_rows)

    updated = upsert_raw(out_path, rows)
    print(f"Upserted {updated} order row(s) into {out_path}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract delivery.com orders from mbox.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Orders-DeliveryCom.mbox"),
        help="Path to Orders-DeliveryCom.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("deliverycom", "orders_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
