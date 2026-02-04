#!/usr/bin/env python3
import argparse
import csv
import html
import mailbox
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from orders_analytics.utils.constants import takeout_path


def extract_parts(msg) -> Tuple[str, str]:
    html_part = ""
    text_part = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/html" and len(decoded) > len(html_part):
                html_part = decoded
            elif content_type == "text/plain" and len(decoded) > len(text_part):
                text_part = decoded
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_part = decoded
            else:
                text_part = decoded
    return html_part, text_part


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_tags(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return normalize_space(html.unescape(fragment))


def extract_restaurant_name(html_text: str, text_part: str) -> str:
    candidates: List[str] = []
    known = ["Aroma Pizza and Pasta", "Ameci Pizza and Pasta"]

    if html_text:
        html_text = html.unescape(html_text)
        match = re.search(
            r"Restaurant Name:\s*</td>\s*<td[^>]*>\s*([^<]+)",
            html_text,
            re.IGNORECASE,
        )
        if match:
            return normalize_space(match.group(1))
        for name in known:
            if re.search(re.escape(name), html_text, re.IGNORECASE):
                candidates.append(name)
        for dba in re.findall(r"DBA:\s*([^<\n]+)", html_text, re.IGNORECASE):
            candidates.append(normalize_space(dba))
    if text_part:
        for line in text_part.splitlines():
            if line.strip().lower().startswith("restaurant name:"):
                return normalize_space(line.split(":", 1)[1])
            if line.strip().lower().startswith("dba:"):
                candidates.append(normalize_space(line.split(":", 1)[1]))
        for name in known:
            if re.search(re.escape(name), text_part, re.IGNORECASE):
                candidates.append(name)
    unique: List[str] = []
    for value in candidates:
        for name in known:
            if value.lower() == name.lower():
                value = name
                break
        if "pizza" in value.lower() and value not in unique:
            unique.append(value)
    if len(unique) == 1:
        return unique[0]
    return ""


def normalize_provider(restaurant: str) -> str:
    name = restaurant.lower()
    if "aroma" in name:
        return "AROMA"
    if "ameci" in name:
        return "AMECI"
    return ""


def normalize_payment(value: str) -> str:
    text = value.lower()
    if "cash" in text:
        return "cash"
    if "mc" in text or "visa" in text or "amex" in text or "credit" in text:
        return "credit"
    return "unknown"


def extract_table_headers(table_html: str) -> List[str]:
    header_row = re.search(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE)
    if not header_row:
        return []
    headers = re.findall(r"<th[^>]*>(.*?)</th>", header_row.group(1), re.DOTALL | re.IGNORECASE)
    return [strip_tags(h) for h in headers if strip_tags(h)]


def extract_table_rows(table_html: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE)[1:]:
        cols = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL | re.IGNORECASE)
        if not cols:
            continue
        rows.append([strip_tags(c) for c in cols])
    return rows


def parse_html_tables(html_text: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    html_text = html.unescape(html_text)
    for table in re.findall(r"<table[^>]*>.*?</table>", html_text, re.DOTALL | re.IGNORECASE):
        if "Order #" not in table or "Paid By" not in table:
            continue
        headers = extract_table_headers(table)
        if not headers:
            continue
        table_rows = extract_table_rows(table)
        for row in table_rows:
            if len(row) < len(headers):
                continue
            rows.append({headers[i]: row[i] for i in range(len(headers))})
    return rows


def split_row(line: str) -> List[str]:
    if "\t" in line:
        parts = [p.strip() for p in line.split("\t")]
    else:
        parts = [p.strip() for p in re.split(r"\s{2,}", line) if p.strip()]
    return parts


def parse_text_tables(text: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    lines = [ln.strip() for ln in text.splitlines()]
    i = 0
    while i < len(lines):
        if lines[i].lower().startswith("online order information"):
            i += 1
            while i < len(lines) and not lines[i]:
                i += 1
            if i >= len(lines):
                break
            headers = split_row(lines[i])
            i += 1
            while i < len(lines) and lines[i]:
                values = split_row(lines[i])
                if len(values) >= len(headers):
                    rows.append({headers[j]: values[j] for j in range(len(headers))})
                i += 1
        else:
            i += 1
    return rows


def parse_beyondmenu(mbox_path: str) -> Tuple[List[Dict[str, str]], int]:
    all_rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    total_messages = 0
    for msg in mbox:
        total_messages += 1
        html_text, text_part = extract_parts(msg)
        restaurant_name = extract_restaurant_name(html_text, text_part)
        rows = parse_html_tables(html_text) if html_text else []
        if not rows and text_part:
            rows = parse_text_tables(text_part)
        for row in rows:
            row["restaurant"] = restaurant_name
        all_rows.extend(rows)
    return all_rows, total_messages


def normalize_order_datetime(date_value: str, time_value: str) -> str:
    if not date_value or not time_value:
        return ""
    text = f"{date_value.strip()} {time_value.strip()}"
    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%y %I:%M %p"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.isoformat()
        except ValueError:
            continue
    return ""


def add_order_datetime(rows: List[Dict[str, str]]) -> None:
    for row in rows:
        date_value = row.get("Date", "")
        time_value = row.get("Time", "")
        row["order_datetime"] = normalize_order_datetime(date_value, time_value)


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for row in rows:
        restaurant = row.get("restaurant", "")
        normalized.append(
            {
                "order_id": row.get("Order #", ""),
                "platform": "BEYONDMENU",
                "provider": normalize_provider(restaurant),
                "order_datetime": row.get("order_datetime", ""),
                "order_type": row.get("Type", ""),
                "customer_name": row.get("Name", ""),
                "phone": "",
                "email": "",
                "address": "",
                "payment_type": normalize_payment(row.get("Paid By", "")),
                "subtotal": row.get("Subtotal", ""),
                "tax": "",
                "tip": "",
                "delivery_fee": "",
                "total": row.get("Amount", ""),
                "item_count": "",
                "processing_fee": "",
                "commission_fee": "",
                "items": "",
                "restaurant_name": restaurant,
                "tax_withheld": "",
                "adjustments": "",
                "marketing_fee": "",
                "misc_fee": "",
                "notes": "",
            }
        )
    return normalized


def dedupe_rows(
    rows: List[Dict[str, str]], key_field: str
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], int]:
    seen: Dict[str, Dict[str, str]] = {}
    conflicts_map: Dict[str, Dict[str, Dict[str, str]]] = {}
    duplicates_removed = 0
    for row in rows:
        key = row.get(key_field, "").strip()
        if not key:
            seen_key = f"__missing__{len(seen)}"
            seen[seen_key] = row
            continue
        if key not in seen:
            seen[key] = row
            continue
        duplicates_removed += 1
        existing = seen[key]
        for field in set(existing.keys()).union(row.keys()):
            old = existing.get(field, "")
            new = row.get(field, "")
            if not old and new:
                existing[field] = new
                continue
            if old and new and old != new:
                if key not in conflicts_map:
                    conflicts_map[key] = {}
                if field not in conflicts_map[key]:
                    conflicts_map[key][field] = {"first": old, "other": new}
    conflicts = [
        {"order_id": key, "diffs": [{"field": f, **vals} for f, vals in fields.items()]}
        for key, fields in conflicts_map.items()
    ]
    return list(seen.values()), conflicts, duplicates_removed


def normalize_headers(rows: List[Dict[str, str]]) -> List[str]:
    if not rows:
        return []
    headers = []
    for row in rows:
        for key in row.keys():
            if key not in headers:
                headers.append(key)
    return headers


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse BeyondMenu billing emails into CSV."
    )
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Billings-BeyondMenu.mbox"),
        help="Path to Billings-BeyondMenu.mbox",
    )
    parser.add_argument(
        "--out",
        default="orders_analytics/data/normalized/beyondmenu_orders_normalized.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    rows, total_messages = parse_beyondmenu(args.mbox)
    if not rows:
        print(f"No rows found. Read {total_messages} messages.")
        return

    deduped, conflicts, duplicates_removed = dedupe_rows(rows, "Order #")
    add_order_datetime(deduped)
    normalized = normalize_rows(deduped)

    fieldnames = [
        "order_id",
        "platform",
        "provider",
        "order_datetime",
        "order_type",
        "customer_name",
        "phone",
        "email",
        "address",
        "payment_type",
        "subtotal",
        "tax",
        "tip",
        "delivery_fee",
        "total",
        "item_count",
        "processing_fee",
        "commission_fee",
        "items",
        "restaurant_name",
        "tax_withheld",
        "adjustments",
        "marketing_fee",
        "misc_fee",
        "notes",
    ]
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in normalized:
            writer.writerow(row)

    print(f"Read {total_messages} messages, wrote {len(normalized)} rows to {args.out}")
    if duplicates_removed:
        print(f"Removed {duplicates_removed} duplicate rows by Order #")
    if conflicts:
        print("Conflicts found for duplicate Order # values:")
        for conflict in conflicts:
            print(f"- Order # {conflict['order_id']}")
            for diff in conflict["diffs"]:
                print(
                    f"  field {diff['field']}: first='{diff['first']}' other='{diff['other']}'"
                )


if __name__ == "__main__":
    main()