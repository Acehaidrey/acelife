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
    "provider",
    "order_date",
    "order_time",
    "order_type",
    "payment_method",
    "tip",
    "total",
    "processing_fee",
    "commission_fee",
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


def parse_fee_rows(html_text: str, order_date: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    text = html.unescape(html_text)
    for row_html in re.findall(
        r"<tr[^>]*summary-table--orders__row[^>]*>.*?</tr>",
        text,
        re.IGNORECASE | re.DOTALL,
    ):
        spans = re.findall(r"<span[^>]*>([^<]*)</span>", row_html, re.DOTALL)
        spans = [html.unescape(s).strip() for s in spans]
        spans = [s for s in spans if s != ""]
        is_cash = any("cash" in s.lower() for s in spans)
        is_card = any("card" in s.lower() or "credit" in s.lower() for s in spans)
        order_time = ""
        order_type = ""
        for token in spans:
            if re.match(r"^\d{1,2}:\d{2}\s*[AP]M$", token, re.IGNORECASE):
                order_time = token
            if "delivery" in token.lower():
                order_type = "Delivery"
            if "takeout" in token.lower() or "pickup" in token.lower():
                order_type = "Takeout"
        order_id_idx = None
        for idx, token in enumerate(spans):
            if token.isdigit():
                order_id_idx = idx
                break
        if order_id_idx is None:
            continue
        order_id = spans[order_id_idx]
        money = [s for s in spans[order_id_idx + 1 :] if "$" in s]
        if len(money) >= 4:
            tip, total, proc, comm = [normalize_money(m) for m in money[:4]]
        elif len(money) == 3 and is_cash:
            tip, total, comm = [normalize_money(m) for m in money[:3]]
            proc = "0.00"
        else:
            continue
        rows.append(
            {
                "order_id": order_id,
                "order_date": order_date,
                "order_time": order_time,
                "order_type": order_type,
                "payment_method": "CASH" if is_cash else ("CARD" if is_card else ""),
                "tip": tip,
                "total": total,
                "processing_fee": proc,
                "commission_fee": comm,
                "raw_tokens": " | ".join(spans),
            }
        )
    return rows


def detect_provider(text: str, subject: str) -> str:
    haystack = f"{subject} {text}".lower()
    if "ameci" in haystack:
        return "AMECI"
    if "aroma" in haystack:
        return "AROMA"
    return ""


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
        provider = detect_provider(html_text, msg.get("Subject", "") or "")
        date_matches = list(re.finditer(r"\b\d{1,2}/\d{1,2}/\d{4}\b", html_text))
        if not date_matches:
            parsed_rows = parse_fee_rows(html_text, "")
        else:
            parsed_rows = []
            for idx, match in enumerate(date_matches):
                start = match.start()
                end = date_matches[idx + 1].start() if idx + 1 < len(date_matches) else len(html_text)
                segment = html_text[start:end]
                order_date = match.group(0)
                parsed_rows.extend(parse_fee_rows(segment, order_date))
        for row in parsed_rows:
            row["provider"] = provider
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
        description="Extract EatStreet billings mbox to raw CSV."
    )
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Billings-Eatstreet.mbox"),
        help="Path to Billings-Eatstreet.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("eatstreet", "billings_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()

    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
