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


def run() -> str:
    base_dir = os.getcwd()
    raw_file = raw_path("slice", "orders_raw_from_statements.csv")
    df = pd.read_csv(raw_file, dtype=str).fillna("")

    if "order_total_raw" not in df.columns:
        insert_at = list(df.columns).index("total") + 1
        df.insert(insert_at, "order_total_raw", df["total"])
    if "status" not in df.columns:
        insert_at = list(df.columns).index("order_total_raw") + 1
        df.insert(insert_at, "status", "active")
    if "voided" in df.columns:
        df.loc[df["voided"].astype(str).str.lower().eq("true"), "status"] = "voided"
        df = df.drop(columns=["voided"])
    if "notes" not in df.columns:
        df["notes"] = ""

    cache: dict[str, dict[tuple[str, str], dict[str, str]]] = {}
    updated = 0
    for idx, row in df.iterrows():
        pdf_path = monthly_report_path(base_dir, row.get("provider", ""), row.get("statement_period_start", ""))
        if not pdf_path:
            continue
        if pdf_path not in cache:
            parsed = parse_pdf(pdf_path)["orders"]
            cache[pdf_path] = {(r["order_id"], r["provider"]): r for r in parsed}
        parsed_row = cache[pdf_path].get((row.get("order_id", ""), row.get("provider", "")))
        if not parsed_row:
            continue
        changed = False
        for col in [
            "restaurant_name",
            "order_datetime",
            "order_type",
            "payment_type",
            "subtotal",
            "customer_delivery_fee",
            "order_adjustments",
            "tax",
            "tip",
            "total",
            "order_total_raw",
            "status",
            "partnership_fee",
            "processing_fee",
            "notes",
        ]:
            new_val = str(parsed_row.get(col, "") or "")
            if col == "notes":
                old_bits = [b.strip() for b in str(row.get(col, "") or "").split("|") if b.strip()]
                new_bits = [b.strip() for b in new_val.split("|") if b.strip()]
                merged_bits = old_bits[:]
                for bit in new_bits:
                    if bit not in merged_bits:
                        merged_bits.append(bit)
                new_val = " | ".join(merged_bits)
            if str(df.at[idx, col] or "") != new_val:
                df.at[idx, col] = new_val
                changed = True
        if changed:
            updated += 1

    blank_raw = df["order_total_raw"].eq("")
    df.loc[blank_raw, "order_total_raw"] = df.loc[blank_raw, "total"]
    df["status"] = df["status"].replace("", "active")
    df.to_csv(raw_file, index=False)
    print(f"Updated {updated} row(s) in {raw_file}")
    return raw_file


if __name__ == "__main__":
    run()
