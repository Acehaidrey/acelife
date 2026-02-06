#!/usr/bin/env python3
import argparse
import datetime as dt
import io
import mailbox
import os
from email.utils import parsedate_to_datetime
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.constants import raw_path, takeout_path


def read_report(payload: bytes) -> pd.DataFrame:
    return pd.read_excel(io.BytesIO(payload))


def is_order_row(row: pd.Series) -> bool:
    order_id = row.get("Order Id")
    if pd.isna(order_id):
        return False
    if str(order_id).strip() == "":
        return False
    return True


def normalize_order_id(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text == "":
        return ""
    try:
        return str(int(float(text)))
    except (ValueError, TypeError):
        return text


def parse_mbox(mbox_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        email_date = ""
        if msg.get("Date"):
            try:
                email_date = parsedate_to_datetime(msg.get("Date")).isoformat()
            except (TypeError, ValueError):
                email_date = ""
        if not msg.is_multipart():
            continue
        for part in msg.walk():
            filename = part.get_filename()
            if not filename:
                continue
            if not filename.lower().endswith(".xls"):
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            df = read_report(payload)
            for _, row in df.iterrows():
                if not is_order_row(row):
                    continue
                record = row.to_dict()
                record["Order Id"] = normalize_order_id(record.get("Order Id"))
                record["source_file"] = filename
                record["email_date"] = email_date
                rows.append(record)
    return rows


def dedupe_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    def key(row: Dict[str, str]) -> str:
        return "||".join(
            str(row.get(field, "") or "").strip()
            for field in ("Order Id", "Order Date", "Subtotal", "Tax", "Disbursement Amount")
        )

    merged: Dict[str, Dict[str, str]] = {}
    for row in rows:
        k = key(row)
        current = merged.get(k)
        if current is None:
            merged[k] = row
            continue
        # keep row with more filled values
        current_score = sum(1 for v in current.values() if str(v or "").strip())
        new_score = sum(1 for v in row.values() if str(v or "").strip())
        if new_score > current_score:
            merged[k] = row
    return list(merged.values())


def write_raw(path: str, rows: List[Dict[str, str]]) -> int:
    now = dt.datetime.now().isoformat()
    for row in rows:
        row.setdefault("added_at", now)
    all_columns: List[str] = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                all_columns.append(key)
    if "added_at" not in seen:
        all_columns.append("added_at")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(rows).reindex(columns=all_columns).to_csv(path, index=False)
    return len(rows)


def run(mbox_path: str, out_path: str) -> int:
    rows = parse_mbox(mbox_path)
    rows = dedupe_rows(rows)
    count = write_raw(out_path, rows)
    print(f"Wrote {count} ChowNow billing row(s) to {out_path}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract ChowNow billings raw CSV from mbox.")
    parser.add_argument(
        "--billings-mbox",
        default=takeout_path("Mail", "Billings-ChowNow.mbox"),
        help="ChowNow billings mbox path.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("chownow", "billings_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.billings_mbox, args.out)


if __name__ == "__main__":
    main()
