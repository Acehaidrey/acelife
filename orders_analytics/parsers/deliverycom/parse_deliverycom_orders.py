#!/usr/bin/env python3
import argparse
import os
import re
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional, Tuple
import html as html_lib

import pandas as pd
import mailbox

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path
from orders_analytics.utils.normalize import normalize_datetime, normalize_money
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.validation import normalize_order_type, normalize_payment_type
from orders_analytics.utils.constants import takeout_path
from orders_analytics.utils.order_types import OrderTypes


PHONE_RE = re.compile(r"(\d{3})[\s\-\.]?(\d{3})[\s\-\.]?(\d{4})")
TIME_RE = re.compile(r"\d{1,2}:\d{2}\s*(am|pm)", re.IGNORECASE)
DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2})\b")


def extract_html(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True) or b""
                return payload.decode(errors="ignore")
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                text = payload.decode(errors="ignore")
                if "<html" in text.lower():
                    return text
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(errors="ignore")


def html_to_lines(html: str) -> List[str]:
    text = html_lib.unescape(html or "")
    text = re.sub(r"<br\\s*/?>", "\\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|tr|td|div)>", "\\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "\\n", text)
    text = re.sub(r"\\n+", "\\n", text)
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_email_year(msg_date: str) -> int:
    try:
        dt = parsedate_to_datetime(msg_date)
        return dt.year
    except Exception:
        return datetime.now().year


def parse_order_datetime(lines: List[str], msg_date: str) -> str:
    year = parse_email_year(msg_date)
    for line in lines:
        if "order placed:" in line.lower():
            raw = line.split(":", 1)[1].strip()
            raw = raw.strip("() ")
            return normalize_datetime(
                f"{raw} {year}",
                formats=("%m/%d %I:%M %p %Y", "%m/%d %I:%M%p %Y"),
                allow_iso=False,
            )

    date_idx = None
    for idx, line in enumerate(lines):
        if DATE_RE.search(line):
            date_idx = idx
            break
    if date_idx is not None:
        date_match = DATE_RE.search(lines[date_idx])
        date_part = date_match.group(1) if date_match else ""
        time_part = ""
        for offset in range(1, 4):
            if date_idx + offset >= len(lines):
                break
            if TIME_RE.search(lines[date_idx + offset]):
                time_part = TIME_RE.search(lines[date_idx + offset]).group(0)
                break
        if date_part and time_part:
            return normalize_datetime(
                f"{date_part} {time_part} {year}",
                formats=("%m/%d %I:%M %p %Y", "%m/%d %I:%M%p %Y"),
                allow_iso=False,
            )
    return ""


def parse_payment_type(lines: List[str]) -> str:
    for line in lines:
        lower = line.lower()
        if "prepaid" in lower or "do not collect payment" in lower:
            return "credit"
        if "cash" in lower and "collect" in lower:
            return "cash"
    return ""


def parse_order_type(lines: List[str]) -> str:
    for line in lines:
        lower = line.lower()
        if "delivery.com" in lower:
            continue
        if "for delivery" in lower or lower.startswith("delivery"):
            return OrderTypes.DELIVERY
        if lower.startswith("deliver"):
            return OrderTypes.DELIVERY
        if "deliver asap" in lower:
            return OrderTypes.DELIVERY
        if "pickup" in lower:
            return OrderTypes.PICKUP
    return ""


def parse_money_field(lines: List[str], label: str) -> str:
    for idx, line in enumerate(lines):
        if line.lower().startswith(label.lower()):
            if idx + 1 < len(lines):
                value = lines[idx + 1].strip()
                if not (
                    value.startswith("$") or value.startswith("(") or value.startswith("-")
                ):
                    return ""
                return normalize_money(value.rstrip(":"))
    return ""


def _add_discount(summary: Dict[str, str], value: str) -> None:
    if not value or summary.get("dcom_promo"):
        return
    existing = summary.get("discount", "")
    try:
        from decimal import Decimal, InvalidOperation
        def to_dec(v: str) -> Decimal:
            v = v.replace("$", "").replace(",", "").strip()
            if v.startswith("(") and v.endswith(")"):
                v = "-" + v[1:-1]
            return Decimal(v)
        new_val = to_dec(value)
        if existing:
            total = to_dec(existing) + new_val
            summary["discount"] = f"{total.quantize(Decimal('0.01'))}"
        else:
            summary["discount"] = f"{new_val.quantize(Decimal('0.01'))}"
    except Exception:
        summary["discount"] = value


def parse_summary(lines: List[str]) -> Dict[str, str]:
    summary = {
        "subtotal": "",
        "tax": "",
        "tip": "",
        "delivery_fee": "",
        "total": "",
        "discount": "",
        "dcom_credit": "",
        "dcom_promo": "",
    }
    if "Customer paid:" in lines:
        summary["total"] = parse_money_field(lines, "Customer paid")
        idx = lines.index("Customer paid:")
        values = []
        for line in lines[idx + 1 : idx + 4]:
            value = line.strip()
            if value.startswith("$") or value.startswith("-") or value.startswith("("):
                values.append(normalize_money(value))
        if len(values) >= 2:
            # handle promo block: negative promo then actual total
            for val in reversed(values):
                if not val.startswith("-"):
                    summary["total"] = val
                    break

    # delivery.com credit
    for idx, line in enumerate(lines):
        if line.lower().startswith("delivery.com credit"):
            for j in range(idx + 1, min(idx + 4, len(lines))):
                value = lines[j].strip()
                if value.startswith("$") or value.startswith("-") or value.startswith("("):
                    summary["dcom_credit"] = normalize_money(value).lstrip("-")
                    break
            break

    # delivery.com promo (do not treat as discount)
    for idx, line in enumerate(lines):
        if line.lower().startswith("delivery.com promo"):
            for j in range(idx + 1, min(idx + 4, len(lines))):
                value = lines[j].strip()
                if value.startswith("$") or value.startswith("-") or value.startswith("("):
                    summary["dcom_promo"] = normalize_money(value).lstrip("-")
                    break
            break
    # promo/credit variations that include delivery.com promo text
    for idx, line in enumerate(lines):
        lower = line.lower()
        if "promo" in lower and "delivery" in lower:
            for j in range(idx + 1, min(idx + 4, len(lines))):
                value = lines[j].strip()
                if value.startswith("$") or value.startswith("-") or value.startswith("("):
                    summary["dcom_promo"] = normalize_money(value).lstrip("-")
                    break
            break

    # Discount (X% off):
    for idx, line in enumerate(lines):
        if line.lower().startswith("discount") and line.strip().endswith(":"):
            for j in range(idx + 1, min(idx + 10, len(lines))):
                value = lines[j].strip()
                if not (value.startswith("-") or value.startswith("(")):
                    continue
                _add_discount(summary, normalize_money(value))
                break
            break


    label_values: Dict[str, str] = {}
    start_idx = None
    for idx, line in enumerate(lines):
        if line.lower().startswith("subtotal:"):
            start_idx = idx
            break
    if start_idx is not None:
        labels: List[str] = []
        values: List[str] = []
        idx = start_idx
        while idx < len(lines):
            line = lines[idx]
            if line.endswith(":") and "customer paid" not in line.lower():
                labels.append(line.rstrip(":").strip())
                idx += 1
                continue
            break
        while idx < len(lines) and len(values) < len(labels):
            value = lines[idx].strip()
            if value.startswith("$") or value.startswith("(") or value.startswith("-"):
                values.append(normalize_money(value.rstrip(":")))
            idx += 1
        for label, value in zip(labels, values):
            key = re.sub(r"\s*\(.*\)", "", label.lower()).strip()
            label_values[key] = value

    if not label_values:
        for idx, line in enumerate(lines):
            if not line.endswith(":"):
                continue
            if idx + 1 >= len(lines):
                continue
            value = lines[idx + 1].strip()
            if not (value.startswith("$") or value.startswith("(") or value.startswith("-")):
                continue
            label = line.rstrip(":").strip().lower()
            label = re.sub(r"\s*\(.*\)", "", label).strip()
            label_values[label] = normalize_money(value.rstrip(":"))

    if label_values:
        summary["subtotal"] = label_values.get("subtotal", summary["subtotal"])
        summary["delivery_fee"] = label_values.get("delivery fee", summary["delivery_fee"])
        summary["tax"] = label_values.get("tax", summary["tax"])
        summary["tip"] = label_values.get("tip", summary["tip"])
        if "discount" in label_values and not summary.get("discount"):
            _add_discount(summary, label_values.get("discount", ""))
        summary["total"] = summary["total"] or label_values.get(
            "customer paid", label_values.get("merchant receives", "")
        )

    values: List[str] = []
    if "Merchant receives:" in lines:
        idx = lines.index("Merchant receives:")
        for line in lines[idx + 1 :]:
            if line.lower().startswith("confirmation"):
                break
            if line.lower().startswith("questions"):
                break
            if line.startswith("$") or line.startswith("(") or line.startswith("-"):
                values.append(normalize_money(line.rstrip(":")))
            elif values:
                break
    if values and not summary["subtotal"]:
        if "Delivery fee:" in lines and len(values) >= 5:
            summary["subtotal"] = values[0]
            summary["delivery_fee"] = values[1]
            summary["tax"] = values[2]
            summary["tip"] = values[3]
            summary["total"] = summary["total"] or values[4]
        elif len(values) >= 4:
            summary["subtotal"] = values[0]
            summary["tax"] = values[1]
            summary["tip"] = values[2]
            summary["total"] = summary["total"] or values[3]
    if not summary["subtotal"]:
        summary["subtotal"] = parse_money_field(lines, "Subtotal")
    if not summary["tax"]:
        summary["tax"] = parse_money_field(lines, "Tax")
    if not summary["tip"]:
        summary["tip"] = parse_money_field(lines, "Tip")
    if not summary["delivery_fee"]:
        summary["delivery_fee"] = parse_money_field(lines, "Delivery fee")
    if not summary["discount"]:
        summary["discount"] = parse_money_field(lines, "Discount")

    # if promo/credit present, do not treat as discount
    if summary.get("dcom_promo") or summary.get("dcom_credit"):
        summary["discount"] = ""

    if summary.get("dcom_promo") or summary.get("dcom_credit"):
        summary["discount"] = ""
    return summary


def parse_customer_block(lines: List[str]) -> Tuple[str, str, str]:
    name = ""
    phone = ""
    address_lines: List[str] = []

    payment_idx = None
    for idx, line in enumerate(lines):
        if "prepaid" in line.lower() or "cash" in line.lower():
            payment_idx = idx
            break
    start_idx = payment_idx + 1 if payment_idx is not None else 0

    for idx in range(start_idx, len(lines)):
        if PHONE_RE.search(lines[idx]):
            phone = PHONE_RE.search(lines[idx]).group(0)
            addr_block = []
            for addr_line in lines[start_idx:idx]:
                if addr_line.startswith("("):
                    continue
                if addr_line.lower().startswith("order placed"):
                    continue
                if not name:
                    name = addr_line
                    continue
                addr_block.append(addr_line)
            address_lines = addr_block
            break
    address = ", ".join([l for l in address_lines if l])
    return name, phone, address


def parse_items(lines: List[str]) -> Tuple[str, str]:
    items: List[str] = []
    item_count = 0
    if "Qty" not in lines:
        return "", ""
    start = lines.index("Qty")
    end = None
    for idx in range(start, len(lines)):
        if lines[idx].lower().startswith("customer paid"):
            end = idx
            break
        if lines[idx].lower().startswith("subtotal"):
            end = idx
            break
    block = lines[start:end] if end else lines[start:]
    last_item = ""
    for line in block:
        if line in ("Qty", "Item", "Price"):
            continue
        if line.startswith("&nbsp;"):
            continue
        if line.startswith("$"):
            if last_item:
                items.append(last_item)
                item_count += 1
                last_item = ""
            continue
        if re.match(r"^\\d+$", line):
            continue
        if line.startswith("-"):
            continue
        if line.startswith("SPECIAL INSTRUCTIONS"):
            continue
        last_item = line
    if last_item:
        items.append(last_item)
        item_count += 1
    return "; ".join(items), str(item_count) if item_count else ""


def parse_order(msg) -> Optional[Dict[str, str]]:
    html = extract_html(msg)
    if not html:
        return None
    lines = html_to_lines(html)

    order_id = ""
    for line in lines:
        match = re.search(r"Order\s*#(\d+)", line)
        if match:
            order_id = match.group(1)
            break
    if not order_id:
        return None

    restaurant_name = ""
    for idx, line in enumerate(lines):
        if line.lower() == "delivery.com order confirmation" and idx + 1 < len(lines):
            restaurant_name = lines[idx + 1]
            break

    order_type = parse_order_type(lines)
    payment_type = parse_payment_type(lines)
    customer_name, phone, address = parse_customer_block(lines)
    order_datetime = parse_order_datetime(lines, msg.get("date", ""))

    summary = parse_summary(lines)
    subtotal = summary["subtotal"]
    tax = summary["tax"]
    tip = summary["tip"]
    delivery_fee = summary["delivery_fee"]
    total = summary["total"]
    discount = summary["discount"]
    dcom_credit = summary.get("dcom_credit", "")
    dcom_promo = summary.get("dcom_promo", "")

    items, item_count = parse_items(lines)

    notes = []
    if dcom_credit:
        notes.append(f"delivery_com_credit={dcom_credit}")
    if dcom_promo:
        notes.append(f"delivery_com_promo={dcom_promo}")
    for idx, line in enumerate(lines):
        if line.lower().startswith("special instructions"):
            block = []
            for j in range(idx + 1, len(lines)):
                if lines[j].lower().startswith("qty"):
                    break
                block.append(lines[j])
            if block:
                notes.append("special_instructions=" + " ".join(block))
            break

    return {
        "order_id": order_id,
        "platform": "DELIVERYCOM",
        "provider": normalize_provider(restaurant_name),
        "restaurant_name": restaurant_name,
        "order_datetime": order_datetime,
        "order_type": normalize_order_type(order_type),
        "customer_name": customer_name,
        "company_name": "",
        "phone": phone,
        "email": "",
        "address": address,
        "address_formatted": "",
        "lat": "",
        "lng": "",
        "payment_type": normalize_payment_type(payment_type),
        "subtotal": subtotal,
        "tax": tax,
        "tax_withheld": "",
        "tip": tip,
        "delivery_fee": delivery_fee,
        "total": total,
        "item_count": item_count,
        "processing_fee": "",
        "commission_fee": "",
        "items": items,
        "adjustments": discount,
        "marketing_fee": "",
        "misc_fee": "",
        "errors": "",
        "notes": " | ".join(notes),
        "discount": discount,
        "dcom_credit": dcom_credit,
        "dcom_promo": dcom_promo,
    }


class DeliveryComOrdersParser(BaseParser):
    platform = "DELIVERYCOM"
    dedupe_key = "order_id"

    def default_input_path(self) -> str:
        return takeout_path("Mail", "Orders-DeliveryCom.mbox")

    def default_out_path(self) -> str:
        return normalized_path("deliverycom_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return mailbox.mbox(input_path)

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        for msg in inputs:
            parsed = parse_order(msg)
            if parsed:
                rows.append(parsed)
        return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize delivery.com orders from mbox.")
    parser.add_argument("--mbox", default=None, help="Path to Orders-DeliveryCom.mbox")
    parser.add_argument("--out", default=None, help="Output normalized CSV path")
    args = parser.parse_args()

    runner = DeliveryComOrdersParser(input_path=args.mbox, out_path=args.out)
    stats = runner.run()
    if not stats.rows_written:
        print("No rows parsed.")
        return
    out_path = runner.resolve_paths()[1]
    print(f"Wrote {stats.rows_written} rows to {out_path}")


if __name__ == "__main__":
    main()
