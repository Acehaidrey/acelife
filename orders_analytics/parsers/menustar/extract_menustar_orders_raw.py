#!/usr/bin/env python3
import argparse
import datetime as dt
import mailbox
import os
import re
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.constants import raw_path
from orders_analytics.utils.providers import normalize_provider

RAW_COLUMNS = [
    "order_id",
    "provider",
    "restaurant_name",
    "order_datetime",
    "order_type",
    "payment_type",
    "customer_name",
    "phone",
    "email",
    "address",
    "items",
    "item_count",
    "subtotal",
    "tax",
    "delivery_fee",
    "tip",
    "total",
    "added_at",
]


def strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", "\n", html or "")
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def next_nonempty(lines: List[str], start: int) -> str:
    for i in range(start, len(lines)):
        if lines[i].strip():
            return lines[i].strip()
    return ""


def parse_datetime(text: str) -> str:
    # Example: "Estimated Pickup Time: 5:39 - 5:49 PM Nov.5, 2024"
    match = re.search(
        r"Estimated\s+(Pickup|Delivery)\s+Time:\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*(AM|PM)\s*([A-Za-z]+)\.?\s*(\d{1,2}),\s*(\d{4})",
        text,
        re.IGNORECASE,
    )
    if match:
        start_time = f"{match.group(2)} {match.group(4)}"
        month = match.group(5)
        day = match.group(6)
        year = match.group(7)
        raw = f"{month} {day} {year} {start_time}"
        for fmt in ("%b %d %Y %I:%M %p", "%B %d %Y %I:%M %p"):
            try:
                return dt.datetime.strptime(raw, fmt).isoformat()
            except ValueError:
                continue
    return ""


def parse_order_type(text: str) -> str:
    if re.search(r"\bDelivery\b", text, re.IGNORECASE):
        return "delivery"
    if re.search(r"\bPickup\b", text, re.IGNORECASE):
        return "pickup"
    return ""


def parse_order(html: str, subject: str) -> Dict[str, str]:
    text = strip_html(html)
    lines = [l for l in text.splitlines()]
    order_id = ""
    order_match = re.search(r"Order\s*Number:\s*([A-Z0-9_\-]+)", text, re.IGNORECASE)
    if order_match:
        order_id = order_match.group(1).strip()
    if not order_id:
        subj_match = re.search(r"Order#\s*([A-Z0-9_\-]+)", subject or "", re.IGNORECASE)
        if subj_match:
            order_id = subj_match.group(1).strip()

    restaurant = ""
    for line in text.splitlines():
        if "Pizza" in line or "Pasta" in line:
            restaurant = line.strip()
            if restaurant:
                break
    provider = normalize_provider(restaurant)

    order_type = parse_order_type(text)
    order_datetime = parse_datetime(text)

    customer_name = ""
    phone = ""
    payment_type = ""
    customer_match = re.search(r"Customer:\s*(.+)", text, re.IGNORECASE)
    if customer_match:
        customer_name = customer_match.group(1).strip()
    phone_match = re.search(r"Phone\s*Number:\s*(.+)", text, re.IGNORECASE)
    if phone_match:
        phone = phone_match.group(1).strip()
    if re.search(r"\bPrepaid\b", text, re.IGNORECASE):
        payment_type = "Prepaid"
    elif re.search(r"Not Paid Yet", text, re.IGNORECASE):
        payment_type = "Not Paid Yet"

    items = []
    item_count = 0
    in_items = False
    for idx, line in enumerate(lines):
        if line.strip() == "Qty":
            in_items = True
            continue
        if in_items:
            if line.strip().lower().startswith(("subtotal", "tax", "total")):
                break
            qty_only = re.match(r"^(\d+)x$", line.strip())
            qty_name = re.match(r"^(\d+)x\s*(.+)$", line.strip())
            if qty_only:
                qty = int(qty_only.group(1))
                name = next_nonempty(lines, idx + 1)
                if name:
                    items.append(f"{qty} x {name}")
                    item_count += qty
            elif qty_name:
                qty = int(qty_name.group(1))
                name = qty_name.group(2).strip()
                if name:
                    items.append(f"{qty} x {name}")
                    item_count += qty

    subtotal = ""
    tax = ""
    total = ""
    delivery_fee = ""
    tip = ""
    for i, line in enumerate(lines):
        if line.strip().lower() == "subtotal:" and i + 1 < len(text.splitlines()):
            subtotal = next_nonempty(lines, i + 1).replace("$", "").replace(",", "")
        if line.strip().lower() == "tax:" and i + 1 < len(text.splitlines()):
            tax = next_nonempty(lines, i + 1).replace("$", "").replace(",", "")
        if line.strip().lower() == "delivery:" and i + 1 < len(text.splitlines()):
            delivery_fee = next_nonempty(lines, i + 1).replace("$", "").replace(",", "")
        if line.strip().lower() == "tip:" and i + 1 < len(text.splitlines()):
            tip = next_nonempty(lines, i + 1).replace("$", "").replace(",", "")
        if line.strip().lower() == "total:" and i + 1 < len(text.splitlines()):
            total = next_nonempty(lines, i + 1).replace("$", "").replace(",", "")

    count_match = re.search(r"End of Order - (\d+) Items? Total", text, re.IGNORECASE)
    if count_match:
        try:
            item_count = int(count_match.group(1))
        except ValueError:
            pass

    # Delivery Address block
    address = ""
    stripped = [l.strip() for l in lines]
    if "Delivery Address:" in stripped:
        idx = stripped.index("Delivery Address:")
        addr_lines = []
        for line in stripped[idx + 1 :]:
            if not line:
                continue
            lower = line.lower()
            if "cross street:" in lower:
                before = line[: lower.index("cross street:")].strip().rstrip(",")
                if before:
                    addr_lines.append(before)
                break
            if line.endswith(":"):
                break
            if line.lower().startswith(("subtotal", "tax", "total", "order number", "customer", "phone number")):
                break
            addr_lines.append(line)
        address = ", ".join(addr_lines).replace(",,", ",")

    return {
        "order_id": order_id,
        "provider": provider,
        "restaurant_name": restaurant,
        "order_datetime": order_datetime,
        "order_type": order_type,
        "payment_type": payment_type,
        "customer_name": customer_name,
        "phone": phone,
        "email": "",
        "address": address,
        "items": "; ".join(items),
        "item_count": str(item_count) if item_count else "",
        "subtotal": subtotal,
        "tax": tax,
        "delivery_fee": delivery_fee,
        "tip": tip,
        "total": total,
    }


def parse_mbox(mbox_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        subject = msg.get("subject", "")
        html = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True) or b""
                    html = payload.decode(errors="ignore")
                    break
        if html.strip():
            row = parse_order(html, subject)
            if row.get("order_id"):
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
    rows = parse_mbox(mbox_path)
    updated = upsert_raw(out_path, rows)
    print(f"Upserted {updated} order row(s) into {out_path}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Menustar orders from mbox HTML.")
    parser.add_argument(
        "--mbox",
        default="TakeoutESBM/Mail/Orders-Menustar.mbox",
        help="Path to Orders-Menustar.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("menustar", "orders_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
