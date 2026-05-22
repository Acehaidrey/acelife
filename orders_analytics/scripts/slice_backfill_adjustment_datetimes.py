#!/usr/bin/env python3
import os

import pandas as pd

from orders_analytics.parsers.slice.extract_slice_orders_raw import parse_pdf
from orders_analytics.utils.constants import raw_path


def monthly_report_path(base_dir: str, provider: str, statement_period_start: str) -> str | None:
    dt = pd.to_datetime(statement_period_start, errors="coerce")
    if pd.isna(dt):
        return None
    folder = "Ameci Reports" if provider == "AMECI" else "Aroma Reports"
    path = os.path.join(
        base_dir,
        "Takeout",
        "Slice Reports",
        folder,
        f"Monthly Report {dt.year}",
        f"{dt.strftime('%B %Y')}.pdf",
    )
    return path if os.path.exists(path) else None


def key_from_row(row: pd.Series | dict) -> tuple[str, str, str, str, str, str]:
    return (
        str(row.get("order_id", "") or "").strip(),
        str(row.get("provider", "") or "").strip(),
        str(row.get("adjustment_amount", "") or "").strip(),
        str(row.get("adjustment_description", "") or "").strip(),
        str(row.get("statement_period_start", "") or "").strip(),
        str(row.get("source_file", "") or "").strip(),
    )


def run() -> str:
    base_dir = os.getcwd()
    path = raw_path("slice", "adjustments_raw_from_statements.csv")
    df = pd.read_csv(path, dtype=str).fillna("")

    if "provider" not in df.columns:
        df.insert(1, "provider", "")
    if "adjustment_datetime_raw" not in df.columns:
        insert_at = list(df.columns).index("adjustment_datetime")
        df.insert(insert_at, "adjustment_datetime_raw", "")

    parsed_cache: dict[str, dict[tuple[str, str, str, str, str, str], dict[str, str]]] = {}
    updated = 0

    targets = df[(df["adjustment_datetime"].eq("")) | (df["adjustment_datetime_raw"].eq(""))].copy()
    for idx, row in targets.iterrows():
        pdf_path = monthly_report_path(base_dir, row.get("provider", ""), row.get("statement_period_start", ""))
        if not pdf_path:
            continue
        if pdf_path not in parsed_cache:
            parsed_rows = parse_pdf(pdf_path)["adjustments"]
            parsed_cache[pdf_path] = {key_from_row(parsed): parsed for parsed in parsed_rows}
        parsed = parsed_cache[pdf_path].get(key_from_row(row))
        if not parsed:
            continue
        changed = False
        for col in ["adjustment_datetime_raw", "adjustment_datetime"]:
            new_val = str(parsed.get(col, "") or "")
            if new_val and str(df.at[idx, col] or "") != new_val:
                df.at[idx, col] = new_val
                changed = True
        if changed:
            updated += 1

    df.to_csv(path, index=False)
    print(f"Updated {updated} row(s) in {path}")
    return path


if __name__ == "__main__":
    run()
