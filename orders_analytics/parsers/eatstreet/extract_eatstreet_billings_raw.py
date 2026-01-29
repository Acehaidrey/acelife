#!/usr/bin/env python3
import argparse
import datetime as dt
import html
import mailbox
import os
import re
from typing import Dict, List, Tuple

import pandas as pd

from orders_analytics.utils.constants import raw_path

RAW_COLUMNS = [
    "order_id",
    "payment_method",
    "tip",
    "total",
    "processing_fee",
    "commission_fee",
    "raw_tokens",
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


def normalize_money(value: str) -> str:
    return value.replace("$", "").replace(",", "").strip()


def parse_fee_rows(html_text: str) -> List[Dict[str, str]]:
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
                "payment_method": "cash" if is_cash else "",
                "tip": tip,
                "total": total,
                "processing_fee": proc,
                "commission_fee": comm,
                "raw_tokens": " | ".join(spans),
            }
        )
    return rows


def parse_billings_mbox(mbox_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        html_text = extract_html(msg)
        if not html_text:
            continue
        rows.extend(parse_fee_rows(html_text))
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
        default="TakeoutESBM/Mail/Billings-Eatstreet.mbox",
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
