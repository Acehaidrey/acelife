#!/usr/bin/env python3
import argparse
import datetime as dt
import mailbox
import os
import re
from pathlib import Path
from typing import Dict, List

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.normalize import normalize_datetime, normalize_money

CHECK_RE = re.compile(r"check for \$([0-9,.]+)", re.IGNORECASE)
PAYMENT_RE = re.compile(r"sent a payment\s*for\s*\$([0-9,.]+)", re.IGNORECASE)


def extract_amount(text: str) -> str:
    match = CHECK_RE.search(text) or PAYMENT_RE.search(text)
    if not match:
        return ""
    return normalize_money(match.group(1))


def parse_mbox(mbox_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        body_text = ""
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_content_type() in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                body_text = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                if body_text:
                    break
        if not body_text:
            continue
        amount = extract_amount(body_text)
        if not amount:
            continue
        email_date = msg.get('Date', '')
        rows.append(
            {
                "payment_date": normalize_datetime(email_date) if email_date else "",
                "amount": amount,
                "source_file": os.path.basename(mbox_path),
            }
        )
    return rows


def run(mbox_path: str, out_path: str) -> int:
    rows = parse_mbox(mbox_path)
    if not rows:
        return 0
    now = dt.datetime.now().isoformat()
    for row in rows:
        row["added_at"] = now
    import pandas as pd

    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract MealHi5 billings from mbox.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Billings-mealhi5.mbox"),
        help="Path to Billings-mealhi5.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("mealhi5", "billings_raw.csv"),
        help="Output billings raw CSV path.",
    )
    args = parser.parse_args()

    Path(os.path.dirname(args.out)).mkdir(parents=True, exist_ok=True)
    count = run(args.mbox, args.out)
    print(f"Wrote {count} rows -> {args.out}")


if __name__ == "__main__":
    main()
