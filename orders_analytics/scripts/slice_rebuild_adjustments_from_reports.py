#!/usr/bin/env python3
import os
import re
from typing import List

import pandas as pd
import pdfplumber

from orders_analytics.parsers.slice.extract_slice_orders_raw import (
    ADJUSTMENT_COLUMNS,
    parse_account_id,
    parse_activity_period,
    parse_adjustment_line,
    parse_time,
)
from orders_analytics.utils.constants import raw_path


def provider_from_path(path: str) -> str:
    return "AMECI" if "/Ameci Reports/" in path else "AROMA"


def parse_order_datetime(date_str: str, time_str: str) -> str:
    if not date_str or not time_str:
        return ""
    try:
        return pd.to_datetime(f"{date_str} {time_str}", format="%b %d, %Y %I:%M %p").isoformat()
    except Exception:
        return ""


def parse_adjustments_only(pdf_path: str) -> List[dict]:
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    period = parse_activity_period(text)
    account_id = parse_account_id(text)
    provider = provider_from_path(pdf_path)
    source_file = os.path.basename(pdf_path)

    raw_lines = [line.rstrip() for line in text.splitlines()]
    lines = [line.strip() for line in raw_lines if line.strip()]

    current_date = ""
    in_adjustments = False
    rows: List[dict] = []

    for idx, line in enumerate(lines):
        if re.match(r"^[A-Z][a-z]{2}\s+\d{2},\s+\d{4}$", line):
            current_date = line
            continue
        if line in {"Adjustments", "Slice Adjustments"}:
            in_adjustments = True
            continue
        if not in_adjustments:
            continue
        if line.startswith("FAQ ") or line.startswith("How is the Slice Partnership Fee") or line.startswith("We're here to help!"):
            break
        if line.startswith("Date & Time ID Adjustment Value Description"):
            continue
        adjustment = parse_adjustment_line(line)
        if not adjustment:
            continue
        time_str = parse_time(lines[idx + 1]) if idx + 1 < len(lines) else ""
        rows.append(
            {
                **adjustment,
                "provider": provider,
                "adjustment_datetime_raw": f"{current_date} {time_str}".strip(),
                "adjustment_datetime": parse_order_datetime(current_date, time_str),
                "statement_period_start": period["statement_period_start"],
                "statement_period_end": period["statement_period_end"],
                "account_id": account_id,
                "source_file": source_file,
                "email_date": "",
            }
        )
    return rows


def run() -> str:
    existing = pd.read_csv(raw_path("slice", "adjustments_raw_from_statements.csv"), dtype=str).fillna("")
    periods = existing[["provider", "statement_period_start"]].drop_duplicates().to_dict("records")
    base_dir = os.getcwd()
    rows: List[dict] = []
    seen = set()
    for rec in periods:
        provider = rec["provider"]
        dt = pd.to_datetime(rec["statement_period_start"], errors="coerce")
        if pd.isna(dt) or provider not in {"AMECI", "AROMA"}:
            continue
        folder = "Ameci Reports" if provider == "AMECI" else "Aroma Reports"
        pdf_path = os.path.join(
            base_dir,
            "Takeout",
            "Slice Reports",
            folder,
            f"Monthly Report {dt.year}",
            f"{dt.strftime('%B %Y')}.pdf",
        )
        if not os.path.exists(pdf_path):
            continue
        for row in parse_adjustments_only(pdf_path):
            key = (
                row.get("order_id", ""),
                row.get("provider", ""),
                row.get("adjustment_amount", ""),
                row.get("adjustment_description", ""),
                row.get("statement_period_start", ""),
                row.get("source_file", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)

    pd.DataFrame(rows).reindex(columns=ADJUSTMENT_COLUMNS).to_csv(
        raw_path("slice", "adjustments_raw_from_statements.csv"), index=False
    )
    print(f"Wrote {len(rows)} row(s)")
    return raw_path("slice", "adjustments_raw_from_statements.csv")


if __name__ == "__main__":
    run()
