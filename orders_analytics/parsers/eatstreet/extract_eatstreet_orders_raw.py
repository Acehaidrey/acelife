#!/usr/bin/env python3
import argparse
import datetime as dt
import html
import json
import mailbox
import os
import re
from typing import Dict, List, Optional

import pandas as pd

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.normalize import normalize_datetime
from orders_analytics.utils.order_types import OrderTypes

RAW_COLUMNS = [
    "order_id",
    "platform",
    "provider",
    "restaurant_name",
    "order_datetime_raw",
    "order_datetime_iso",
    "order_type",
    "customer_name",
    "phone",
    "email",
    "address",
    "payment_detail",
    "payment_raw",
    "payment_type",
    "subtotal",
    "tax",
    "tip",
    "delivery_fee",
    "total",
    "items",
    "item_count",
    "added_at",
]


def extract_html(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    if msg.get_content_type() == "text/html":
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def extract_order_info(html_text: str) -> Optional[Dict]:
    match = re.search(
        r'<div[^>]*id=["\']orderInfo["\'][^>]*>(.*?)</div>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    raw = html.unescape(match.group(1)).strip()
    if not raw:
        return None
    json_match = re.search(r"({.*})", raw, re.DOTALL)
    if not json_match:
        return None
    try:
        return json.loads(json_match.group(1))
    except json.JSONDecodeError:
        return None


def extract_spans_from_block(block: str) -> List[str]:
    spans = re.findall(
        r"<span[^>]*>\s*([^<]+?)\s*</span>",
        block,
        re.IGNORECASE | re.DOTALL,
    )
    cleaned = [normalize_space(html.unescape(s)) for s in spans]
    return [s for s in cleaned if s]


def extract_td_block(html_text: str, label: str) -> Optional[str]:
    match = re.search(
        rf"<td[^>]*>(?:(?!</td>).)*{label}(?:(?!</td>).)*</td>",
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    return match.group(0) if match else None


def extract_header_fields(html_text: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    type_match = re.search(r"\b(DELIVERY|PICKUP)\b", html_text, re.IGNORECASE)
    if not type_match:
        return fields

    td_blocks = re.findall(r"<td[^>]*>.*?</td>", html_text, re.IGNORECASE | re.DOTALL)
    candidate_spans = []
    for block in td_blocks:
        if not re.search(r"\b(DELIVERY|PICKUP)\b", block, re.IGNORECASE):
            continue
        spans = extract_spans_from_block(block)
        if not spans:
            continue
        first = spans[0].strip().lower()
        if first in (OrderTypes.PICKUP, OrderTypes.DELIVERY):
            candidate_spans.append(spans)

    selected = None
    for spans in candidate_spans:
        if len(spans) < 2:
            continue
        second = spans[1].strip().lower()
        if "pickup" in second or "delivery" in second or "order ready" in second:
            continue
        selected = spans
        break
    if not selected and candidate_spans:
        selected = candidate_spans[0]

    if selected:
        fields["order_type"] = selected[0].strip().lower()
        if len(selected) > 1:
            fields["restaurant"] = selected[1]
        if len(selected) > 2:
            fields["order_date"] = selected[2]
        return fields

    fields["order_type"] = type_match.group(1).strip().lower()
    return fields


def extract_customer_info(html_text: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    block = extract_td_block(html_text, "Customer Info:")
    if not block:
        return fields
    spans = extract_spans_from_block(block)
    spans = [s for s in spans if "Customer Info" not in s]
    if spans:
        fields["customer_name"] = spans[0]
    if len(spans) > 1:
        fields["phone"] = spans[1]
    return fields


def extract_delivery_address(html_text: str) -> List[str]:
    block = extract_td_block(html_text, "Delivery Address:")
    if not block:
        return []
    spans = extract_spans_from_block(block)
    spans = [s for s in spans if "Delivery Address" not in s]
    return spans


def extract_payment_info(html_text: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    payment_block = re.search(
        r"Payment Info:.*?</td>",
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    if not payment_block:
        return fields
    block = payment_block.group(0)
    big = re.search(
        r'class="big_text[^"]*"\s*>\s*([^<]+?)\s*</span>',
        block,
        re.IGNORECASE | re.DOTALL,
    )
    medium = re.search(
        r'class="medium_text"\s*>\s*([^<]+?)\s*</span>',
        block,
        re.IGNORECASE | re.DOTALL,
    )
    detail_parts = []
    if big:
        detail_parts.append(normalize_space(big.group(1)))
    if medium:
        detail_parts.append(normalize_space(medium.group(1)))
    if detail_parts:
        fields["payment_detail"] = " | ".join(detail_parts)
    return fields


def classify_payment(detail: str, payment_raw: str) -> str:
    combined = f"{detail} {payment_raw}".lower()
    if "collect payment" in combined:
        return "cash"
    if "cash" in combined:
        return "cash"
    if "credit" in combined or "card" in combined or "do not charge" in combined:
        return "credit"
    return "unknown"


def extract_fees(html_text: str) -> Dict[str, str]:
    fees: Dict[str, str] = {}
    for label, amount in re.findall(
        r'fee_label[^>]*>\s*(?:<span>)?\s*([A-Z ]+):\s*(?:</span>)?\s*</td>\s*'
        r'<td[^>]*fee[^>]*>\s*(?:<span>)?\s*([0-9]+\.[0-9]{2})',
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        fees[normalize_space(label).upper()] = amount
    total_match = re.search(
        r'<b>\s*TOTAL:\s*</b>.*?<b>\s*([0-9]+\.[0-9]{2})\s*</b>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    if total_match:
        fees["TOTAL"] = total_match.group(1)
    return fees


def format_address_from_info(info: Dict) -> str:
    parts: List[str] = []
    building = normalize_space(info.get("buildingName", "") or "")
    street = normalize_space(info.get("streetAddress", "") or "")
    apartment = normalize_space(info.get("apartment", "") or "")
    city = normalize_space(info.get("city", "") or "")
    state = normalize_space(info.get("state", "") or "")
    zip_code = normalize_space(info.get("zip", "") or "")
    if building:
        parts.append(building)
    if street:
        parts.append(street)
    if apartment:
        parts.append(apartment)
    city_line = ", ".join(part for part in [city, state] if part)
    if zip_code:
        city_line = f"{city_line} {zip_code}".strip()
    if city_line:
        parts.append(city_line)
    return " | ".join(parts)


def format_address_from_lines(lines: List[str]) -> str:
    return " | ".join(lines)


def summarize_items(info: Optional[Dict]) -> str:
    if not info:
        return ""
    items = info.get("items", [])
    names = [normalize_space(item.get("name", "")) for item in items if item.get("name")]
    return "; ".join(n for n in names if n)


def normalize_order_datetime(value: str) -> str:
    if not value:
        return ""
    text = value.strip()
    return normalize_datetime(
        text,
        formats=("%I:%M %p %m/%d/%Y", "%m/%d/%Y %I:%M %p"),
        allow_iso=True,
    )


def parse_orders(mbox_path: str) -> List[Dict[str, str]]:
    orders: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        html_text = extract_html(msg)
        if not html_text:
            continue
        order_info = extract_order_info(html_text)
        header_fields = extract_header_fields(html_text)
        customer_fields = extract_customer_info(html_text)
        payment_fields = extract_payment_info(html_text)
        fees = extract_fees(html_text)

        order_type = header_fields.get("order_type", "")
        restaurant = header_fields.get("restaurant", "")
        order_date = header_fields.get("order_date", "")
        order_id = ""
        phone = customer_fields.get("phone", "")
        customer_name = customer_fields.get("customer_name", "")
        address = ""
        payment_detail = payment_fields.get("payment_detail", "")
        payment_raw = ""
        items_summary = ""
        items_count = ""

        if order_info:
            order_id = str(order_info.get("id", "") or "")
            phone = order_info.get("phoneNumber", "") or phone
            order_type = OrderTypes.DELIVERY if order_info.get("delivery") else order_type
            if order_info.get("delivery") is False:
                order_type = OrderTypes.PICKUP
            order_date = order_info.get("deliverAt", "") or order_date
            payment_raw = order_info.get("payment", "") or ""
            items_summary = summarize_items(order_info)
            if order_info.get("items") is not None:
                items_count = str(len(order_info.get("items", [])))
            if order_info.get("delivery"):
                address = format_address_from_info(order_info)

        if not address and order_type == OrderTypes.DELIVERY:
            address_lines = extract_delivery_address(html_text)
            address = format_address_from_lines(address_lines)
        if address:
            address = address.replace(" | ", ", ").replace("|", ", ")

        payment_type = classify_payment(payment_detail, payment_raw)

        orders.append(
            {
                "order_id": order_id,
                "platform": "EATSTREET",
                "provider": normalize_provider(restaurant),
                "restaurant_name": restaurant,
                "order_datetime_raw": order_date,
                "order_datetime_iso": normalize_order_datetime(order_date),
                "order_type": order_type,
                "customer_name": customer_name,
                "phone": phone,
                "email": "",
                "address": address,
                "payment_detail": payment_detail,
                "payment_raw": payment_raw,
                "payment_type": payment_type,
                "subtotal": fees.get("SUBTOTAL", ""),
                "tax": fees.get("TAX", ""),
                "tip": fees.get("TIP", ""),
                "delivery_fee": fees.get("DELIVERY", ""),
                "total": fees.get("TOTAL", ""),
                "items": items_summary,
                "item_count": items_count,
            }
        )
    return orders


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
    rows = parse_orders(mbox)
    rows = [row for row in rows if row.get("order_id")]
    updated = upsert_raw(out, rows)
    print(f"Upserted {updated} order(s) into {out}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract EatStreet orders mbox to raw CSV.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Orders-Eatstreet.mbox"),
        help="Path to Orders-Eatstreet.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("eatstreet", "orders_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()

    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
