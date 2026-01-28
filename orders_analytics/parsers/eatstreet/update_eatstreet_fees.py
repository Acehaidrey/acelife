#!/usr/bin/env python3
import argparse
import datetime as dt
import html
import mailbox
import os
import re
import shutil
from typing import Dict, List, Tuple

import pandas as pd


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


def parse_fee_rows(html_text: str) -> List[Tuple[str, str, str]]:
    rows: List[Tuple[str, str, str]] = []
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
        rows.append((order_id, proc, comm))
    return rows


def parse_billings_mbox(mbox_path: str) -> Dict[str, Dict[str, str]]:
    mapping: Dict[str, Dict[str, str]] = {}
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        html_text = extract_html(msg)
        if not html_text:
            continue
        for order_id, proc, comm in parse_fee_rows(html_text):
            mapping[order_id] = {"processing_fee": proc, "commission_fee": comm}
    return mapping


def run(
    mbox: str,
    orders: str,
    out: str,
    missing_out: str,
    backup_dir: str,
) -> int:
    fees = parse_billings_mbox(mbox)
    if not fees:
        print("No fee rows found in billings.")
        return 0

    df = pd.read_csv(orders)
    df["order_id"] = df["order_id"].astype(str)
    df = df[df["order_id"].notna() & (df["order_id"].str.strip() != "")]
    fees_df = pd.DataFrame([{"order_id": k, **v} for k, v in fees.items()])
    merged = df.merge(fees_df, on="order_id", how="left", suffixes=("_x", "_y"))
    # Normalize fee columns into canonical names, preferring newly parsed billings values.
    proc_candidates = [
        "processing_fee_y",
        "processing_fee",
        "processing_fee_x",
        "proc_fee",
    ]
    comm_candidates = [
        "commission_fee_y",
        "commission_fee",
        "commission_fee_x",
        "comm_fee",
    ]
    for canonical, candidates in (
        ("processing_fee", proc_candidates),
        ("commission_fee", comm_candidates),
    ):
        values = None
        for col in candidates:
            if col in merged.columns:
                series = merged[col]
                values = series if values is None else values.combine_first(series)
        if values is None:
            merged[canonical] = pd.NA
        else:
            merged[canonical] = values
    for col in ("processing_fee_x", "processing_fee_y", "commission_fee_x", "commission_fee_y"):
        if col in merged.columns:
            merged.drop(columns=[col], inplace=True)
    for col in ("proc_fee", "comm_fee"):
        if col in merged.columns:
            merged.drop(columns=[col], inplace=True)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.abspath(out) == os.path.abspath(orders):
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(backup_dir, exist_ok=True)
        base = os.path.basename(orders)
        backup_path = os.path.join(backup_dir, f"{base}.{stamp}.bak")
        shutil.copy2(orders, backup_path)
        print(f"Backed up original CSV -> {backup_path}")
    merged.to_csv(out, index=False)
    print(f"Updated {len(merged)} rows with proc/comm fees -> {out}")
    missing_mask = merged["processing_fee"].isna() | merged["commission_fee"].isna()
    missing_rows = merged.loc[missing_mask, ["order_id", "order_datetime", "provider"]].copy()
    missing_rows["order_id"] = missing_rows["order_id"].astype(str)
    missing_rows = missing_rows[missing_rows["order_id"].notna() & (missing_rows["order_id"].str.strip() != "")]
    missing_rows = missing_rows.drop_duplicates(subset=["order_id"]).sort_values("order_id")
    if not missing_rows.empty:
        os.makedirs(os.path.dirname(missing_out), exist_ok=True)
        missing_rows.to_csv(missing_out, index=False)
        print(
            f"Missing proc/comm fees for {len(missing_rows)} order_id(s). "
            f"Wrote list -> {missing_out}"
        )
        print("Order IDs missing fees:")
        for order_id in missing_rows["order_id"]:
            print(order_id)
    else:
        print("All orders have proc/comm fees.")
    return len(missing_rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update EatStreet normalized orders with proc/comm fees from billings."
    )
    parser.add_argument(
        "--mbox",
        default="TakeoutESBM/Mail/Billings-Eatstreet.mbox",
        help="Path to Billings-Eatstreet.mbox",
    )
    parser.add_argument(
        "--orders",
        default="orders_analytics/data/normalized/eatstreet_orders_normalized.csv",
        help="Path to EatStreet orders CSV",
    )
    parser.add_argument(
        "--out",
        default="orders_analytics/data/normalized/eatstreet_orders_normalized.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--missing-out",
        default="orders_analytics/data/raw/eatstreet/eatstreet_orders_missing_fees.csv",
        help="Output CSV path for order_ids missing proc/comm fees",
    )
    parser.add_argument(
        "--backup-dir",
        default="orders_analytics/data/raw/eatstreet/backups",
        help="Directory for backups when overwriting the output CSV",
    )
    args = parser.parse_args()

    run(
        mbox=args.mbox,
        orders=args.orders,
        out=args.out,
        missing_out=args.missing_out,
        backup_dir=args.backup_dir,
    )


if __name__ == "__main__":
    main()
