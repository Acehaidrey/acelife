#!/usr/bin/env python3
import argparse
import html
import json
import mailbox
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from orders_analytics.utils.schema import write_normalized_rows


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

    td_match = re.search(
        r"<td[^>]*>(?:(?!</td>).)*(DELIVERY|PICKUP)(?:(?!</td>).)*</td>",
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    if not td_match:
        fields["order_type"] = type_match.group(1).strip().lower()
        return fields

    spans = extract_spans_from_block(td_match.group(0))
    if spans:
        order_type = spans[0].strip().lower()
        fields["order_type"] = order_type
        if len(spans) > 1:
            fields["restaurant"] = spans[1]
        if len(spans) > 2:
            fields["order_date"] = spans[2]
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


def normalize_provider(restaurant: str) -> str:
    name = restaurant.lower()
    if "aroma" in name:
        return "AROMA"
    if "ameci" in name:
        return "AMECI"
    return ""


def parse_orders(mbox_path: str) -> (List[Dict[str, str]], int):
    orders: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    total_messages = 0
    for msg in mbox:
        total_messages += 1
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
            order_type = "delivery" if order_info.get("delivery") else order_type
            if order_info.get("delivery") is False:
                order_type = "pickup"
            order_date = order_info.get("deliverAt", "") or order_date
            payment_raw = order_info.get("payment", "") or ""
            items_summary = summarize_items(order_info)
            if order_info.get("items") is not None:
                items_count = str(len(order_info.get("items", [])))
            if order_info.get("delivery"):
                address = format_address_from_info(order_info)

        if not address and order_type == "delivery":
            address_lines = extract_delivery_address(html_text)
            address = format_address_from_lines(address_lines)

        payment_type = classify_payment(payment_detail, payment_raw)

        orders.append(
            {
                "order_id": order_id,
                "platform": "EATSTREET",
                "provider": normalize_provider(restaurant),
                "restaurant_name": restaurant,
                "order_datetime": normalize_order_datetime(order_date),
                "order_type": order_type,
                "customer_name": customer_name,
                "phone": phone,
                "address": address,
                "payment_type": payment_type,
                "subtotal": fees.get("SUBTOTAL", ""),
                "tax": fees.get("TAX", ""),
                "tip": fees.get("TIP", ""),
                "delivery_fee": fees.get("DELIVERY", ""),
                "total": fees.get("TOTAL", ""),
                "items": items_summary,
                "item_count": items_count,
                "processing_fee": "",
                "commission_fee": "",
                "tax_withheld": "",
                "adjustments": "",
                "marketing_fee": "",
                "misc_fee": "",
                "email": "",
                "notes": "",
            }
        )
    return orders, total_messages


def normalize_order_datetime(value: str) -> str:
    if not value:
        return ""
    text = value.strip()
    try:
        if text.endswith("Z"):
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt.isoformat()
        if "T" in text:
            dt = datetime.fromisoformat(text)
            return dt.isoformat()
    except ValueError:
        pass
    for fmt in ("%I:%M %p %m/%d/%Y", "%m/%d/%Y %I:%M %p"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.isoformat()
        except ValueError:
            continue
    return text


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse EatStreet order emails from an mbox into CSV."
    )
    parser.add_argument(
        "--mbox",
        default="TakeoutESBM/Mail/Orders-Eatstreet.mbox",
        help="Path to Orders-Eatstreet.mbox",
    )
    parser.add_argument(
        "--out",
        default="orders_analytics/data/normalized/eatstreet_orders_normalized.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    orders, total_messages = parse_orders(args.mbox)
    if not orders:
        print(f"No orders found. Read {total_messages} messages.")
        return

    orders = [
        row
        for row in orders
        if row.get("order_id")
        and "test" not in (row.get("customer_name") or "").lower()
    ]
    deduped, conflicts, duplicates_removed = dedupe_rows(orders, "order_id")

    write_normalized_rows(deduped, args.out)

    print(
        f"Read {total_messages} messages, wrote {len(deduped)} orders to {args.out}"
    )
    if duplicates_removed:
        print(f"Removed {duplicates_removed} duplicate rows by order_id")
    if conflicts:
        print("Conflicts found for duplicate order_id values:")
        for conflict in conflicts:
            print(f"- order_id {conflict['order_id']}")
            for diff in conflict["diffs"]:
                print(
                    f"  field {diff['field']}: first='{diff['first']}' other='{diff['other']}'"
                )


if __name__ == "__main__":
    main()
