#!/usr/bin/env python3
import argparse
import os
import re
from email.utils import parsedate_to_datetime
from mailbox import mbox

import pandas as pd

from orders_analytics.utils.constants import raw_path, takeout_path


def is_zero_or_blank(series: pd.Series) -> bool:
    values = series.astype(str).str.strip()
    return values.isin({"", "0", "0.0", "0.00", "$0.00", "$0", "($0.00)", "$0.0"}).all()


SUBJECT_PATTERN = re.compile(
    r"Purchase Order for\s+(?P<event_date>\d{1,2}/\d{1,2}/\d{4})\s+Event\s*#(?P<event_number>\d+)\s+at\s+(?P<company_name>.+)$",
    re.IGNORECASE,
)


def normalize_event_number(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    normalized = digits.lstrip("0")
    return normalized or "0"


def extract_company_info(mbox_path: str, out_path: str) -> int:
    rows = []
    box = mbox(mbox_path)
    for message in box:
        subject = " ".join(str(message.get("subject", "")).split()).strip()
        match = SUBJECT_PATTERN.search(subject)
        if not match:
            continue
        event_number = match.group("event_number").strip()
        date_header = str(message.get("date", "")).strip()
        email_datetime = ""
        if date_header:
            try:
                email_datetime = parsedate_to_datetime(date_header).isoformat()
            except Exception:
                email_datetime = ""
        rows.append(
            {
                "subject": subject,
                "event_number": event_number,
                "event_number_normalized": normalize_event_number(event_number),
                "event_date": match.group("event_date").strip(),
                "company_name": match.group("company_name").strip(),
                "email_datetime": email_datetime,
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["event_number_normalized", "email_datetime", "subject"]).drop_duplicates(
            subset=["event_number_normalized"], keep="last"
        )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} row(s) -> {out_path}")
    return len(df)


def run(input_path: str, out_path: str) -> int:
    df = pd.read_csv(input_path, encoding="utf-16", sep="\t", dtype=str).fillna("")

    if not df.empty:
        first_col = df.columns[0]
        df = df[df[first_col].astype(str).str.strip().str.lower() != "grand total"].copy()

    duplicate_columns_to_drop = [
        "Tax (Restaurant to remit)",
    ]
    df = df.drop(columns=[column for column in duplicate_columns_to_drop if column in df.columns])

    keep_columns = [column for column in df.columns if not is_zero_or_blank(df[column])]
    df = df[keep_columns].copy()

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path, sep="\t", encoding="utf-16", index=False)
    print(f"Wrote {len(df)} row(s) -> {out_path}")
    extract_company_info(
        takeout_path("Mail", "Orders-Fooda.mbox"),
        raw_path("fooda", "orders_company_raw.csv"),
    )
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract cleaned Fooda raw orders CSV.")
    parser.add_argument(
        "--input",
        default=takeout_path("Mail", "fooda_sales.csv"),
        help="Path to Fooda source CSV.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("fooda", "fooda_sales.csv"),
        help="Output cleaned raw CSV path.",
    )
    args = parser.parse_args()
    run(args.input, args.out)


if __name__ == "__main__":
    main()
