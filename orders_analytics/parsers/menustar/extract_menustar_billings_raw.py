#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import io
import mailbox
import os
import re
from email.utils import parsedate_to_datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List, Optional

import pandas as pd

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.normalize import normalize_money

RAW_COLUMNS = [
    "order_id",
    "provider",
    "restaurant_name",
    "order_datetime",
    "order_type",
    "payment_type",
    "subtotal",
    "tax",
    "delivery_fee",
    "tip",
    "total",
    "statement_email_date",
    "statement_all_orders",
    "statement_prepaid_orders",
    "statement_menustar_fees",
    "statement_menustar_fees_allocated",
    "statement_adjustments",
    "statement_net_payout",
    "statement_source_file",
    "added_at",
]

FORBIDDEN_AMECI_LOCATIONS = [
    "castaic",
    "newhall",
    "woodland hills",
    "san fernando",
    "mission blvd",
]


def allowed_menustar_restaurant(name: str) -> tuple[bool, str]:
    text = str(name or "").strip()
    lowered = text.lower()
    if "ameci pizza & pasta" not in lowered:
        return True, ""
    if any(loc in lowered for loc in FORBIDDEN_AMECI_LOCATIONS):
        return False, "forbidden_ameci_location"
    paren_match = re.search(r"\(([^)]*)\)", text)
    if paren_match:
        content = paren_match.group(1).strip()
        if content.isdigit():
            return True, ""
        if "trabuco" in content.lower():
            return True, ""
        return False, "non_trabuco_ameci_location"
    return True, ""


def parse_csv_rows(
    text: str, provider: str, filename: str, statement_email_date: str
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    summary = {
        "statement_all_orders": "",
        "statement_prepaid_orders": "",
        "statement_menustar_fees": "",
        "statement_adjustments": "",
        "statement_net_payout": "",
    }
    reader = list(csv.reader(io.StringIO(text)))
    header_idx = None
    for idx, row in enumerate(reader):
        if row and row[0].strip() == "Date":
            header_idx = idx
            break
    if header_idx is None:
        return rows

    # First pass: capture summary rows anywhere in the file.
    for row in reader:
        if not row or not row[0]:
            continue
        label = row[0].strip().lower()
        if label == "all orders":
            summary["statement_all_orders"] = normalize_money(row[1] if len(row) > 1 else "")
        elif label == "pre-paid orders":
            summary["statement_prepaid_orders"] = normalize_money(row[1] if len(row) > 1 else "")
        elif label == "menustar fees":
            summary["statement_menustar_fees"] = normalize_money(row[1] if len(row) > 1 else "")
        elif label == "adjustments":
            summary["statement_adjustments"] = normalize_money(row[1] if len(row) > 1 else "")
        elif label == "net payout":
            summary["statement_net_payout"] = normalize_money(row[1] if len(row) > 1 else "")

    headers = reader[header_idx]
    data_rows = reader[header_idx + 1 :]
    for row in data_rows:
        if not row or not row[0]:
            continue
        label = row[0].strip()
        if label.lower() in ("total", "all orders", "pre-paid orders", "menustar fees", "adjustments", "net payout"):
            continue
        if label.lower() == "total":
            continue
        try:
            date_str = row[0]
        except IndexError:
            continue
        record = dict(zip(headers, row))
        order_datetime = ""
        try:
            order_datetime = dt.datetime.strptime(date_str, "%m/%d/%Y %H:%M:%S").isoformat()
        except ValueError:
            try:
                order_datetime = dt.datetime.strptime(date_str, "%m/%d/%Y %H:%M").isoformat()
            except ValueError:
                order_datetime = date_str
        rows.append(
            {
                "order_id": "",
                "provider": provider,
                "restaurant_name": filename.replace(".csv", "").replace(".xlsx", "").strip(),
                "order_datetime": order_datetime,
                "order_type": record.get("Order Type", "").strip(),
                "payment_type": record.get("Payment Type", "").strip(),
                "subtotal": normalize_money(record.get("Subtotal", "")),
                "tax": normalize_money(record.get("Tax", "")),
                "delivery_fee": normalize_money(record.get("Delivery Fee", "")),
                "tip": normalize_money(record.get("Tip", "")),
                "total": normalize_money(record.get("Total", "")),
                "statement_email_date": statement_email_date,
                **summary,
                "statement_menustar_fees_allocated": "",
                "statement_source_file": filename,
            }
        )
    # Allocate MenuStar Fees across all orders by subtotal.
    fee_raw = summary.get("statement_menustar_fees", "")
    if fee_raw and rows:
        try:
            fee_total = Decimal(fee_raw)
            subtotal_sum = sum(Decimal(r.get("subtotal") or "0") for r in rows)
        except InvalidOperation:
            subtotal_sum = Decimal("0")
        if subtotal_sum:
            allocs = []
            for row in rows:
                try:
                    subtotal = Decimal(row.get("subtotal") or "0")
                except InvalidOperation:
                    subtotal = Decimal("0")
                share = (subtotal / subtotal_sum) * fee_total
                allocs.append(share.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            remainder = (fee_total - sum(allocs)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cent = Decimal("0.01")
            cents = int((abs(remainder) / cent).to_integral_value(rounding=ROUND_HALF_UP))
            step = cent if remainder > 0 else -cent
            for i in range(cents):
                allocs[i % len(allocs)] = (allocs[i % len(allocs)] + step).quantize(
                    cent, rounding=ROUND_HALF_UP
                )
            for row, alloc in zip(rows, allocs):
                row["statement_menustar_fees_allocated"] = str(alloc)
    return rows


def read_attachment_rows(
    payload: bytes, filename: str, statement_email_date: str
) -> List[Dict[str, str]]:
    lower = filename.lower()
    provider = normalize_provider(filename)
    if lower.endswith(".csv"):
        text = payload.decode(errors="ignore")
        return parse_csv_rows(text, provider, filename, statement_email_date)
    if lower.endswith(".xlsx"):
        try:
            df = pd.read_excel(io.BytesIO(payload))
        except ImportError:
            print("Missing openpyxl; skipping xlsx attachment:", filename)
            return []
        text = df.to_csv(index=False)
        return parse_csv_rows(text, provider, filename, statement_email_date)
    return []


def parse_mbox(mbox_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []
    mbox = mailbox.mbox(mbox_path)
    for msg in mbox:
        msg_date = msg.get("date", "")
        statement_email_date = ""
        if msg_date:
            try:
                statement_email_date = parsedate_to_datetime(msg_date).isoformat()
            except Exception:
                statement_email_date = ""
        for part in msg.walk():
            filename = part.get_filename()
            if not filename:
                continue
            if not filename.lower().endswith((".csv", ".xlsx")):
                continue
            restaurant_name = filename.replace(".csv", "").replace(".xlsx", "").strip()
            allowed, reason = allowed_menustar_restaurant(restaurant_name)
            if not allowed:
                skipped.append(
                    {
                        "email_date": msg_date,
                        "statement_source_file": filename,
                        "restaurant_name": restaurant_name,
                        "reason": reason,
                    }
                )
                continue
            payload = part.get_payload(decode=True) or b""
            rows.extend(read_attachment_rows(payload, filename, statement_email_date))
    if skipped:
        df = pd.DataFrame(skipped)
        print("Skipped MenuStar billing statements:")
        print(df.to_string(index=False))
    return rows


def upsert_raw(existing_path: str, new_rows: List[Dict[str, str]]) -> int:
    now = dt.datetime.now().isoformat()
    if os.path.exists(existing_path):
        existing_df = pd.read_csv(existing_path, dtype=str).fillna("")
        existing_rows = existing_df.to_dict("records")
    else:
        existing_rows = []

    # Drop previously stored rows from non-Trabuco Ameci locations.
    if existing_rows:
        filtered_rows = []
        skipped_existing = 0
        for row in existing_rows:
            restaurant_name = row.get("restaurant_name", "")
            allowed, _ = allowed_menustar_restaurant(restaurant_name)
            if not allowed:
                skipped_existing += 1
                continue
            filtered_rows.append(row)
        if skipped_existing:
            print(f"Removed {skipped_existing} existing MenuStar billing row(s) from non-target locations.")
        existing_rows = filtered_rows

    def normalize_dt_key(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
        except ValueError:
            for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
                try:
                    return dt.datetime.strptime(text, fmt).isoformat()
                except ValueError:
                    continue
        return text

    def dedupe_key(row: Dict[str, str]) -> str:
        return "|".join(
            [
                str(row.get("provider", "")).strip(),
                normalize_dt_key(row.get("order_datetime", "")),
                str(row.get("order_type", "")).strip(),
                str(row.get("payment_type", "")).strip(),
                str(row.get("subtotal", "")).strip(),
                str(row.get("tax", "")).strip(),
                str(row.get("delivery_fee", "")).strip(),
                str(row.get("tip", "")).strip(),
                str(row.get("total", "")).strip(),
            ]
        )

    def non_blank_count(row: Dict[str, str]) -> int:
        return sum(1 for value in row.values() if str(value or "").strip())

    def parse_email_dt(value: str) -> Optional[dt.datetime]:
        if not value:
            return None
        try:
            return dt.datetime.fromisoformat(value)
        except ValueError:
            return None

    existing_map = {dedupe_key(row): row for row in existing_rows}
    updated = 0
    for row in new_rows:
        key = dedupe_key(row)
        current = existing_map.get(key)
        if current is None:
            row["added_at"] = now
            existing_map[key] = row
            updated += 1
            continue
        # Prefer the row with the most non-blank fields; if tied, prefer latest email date.
        current_score = non_blank_count(current)
        new_score = non_blank_count(row)
        replace = False
        if new_score > current_score:
            replace = True
        elif new_score == current_score:
            current_dt = parse_email_dt(str(current.get("statement_email_date", "")))
            new_dt = parse_email_dt(str(row.get("statement_email_date", "")))
            if new_dt and (not current_dt or new_dt > current_dt):
                replace = True
        if replace:
            row["added_at"] = now
            existing_map[key] = row
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
    print(f"Upserted {updated} billing row(s) into {out_path}")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Menustar billings from mbox attachments.")
    parser.add_argument(
        "--mbox",
        default=takeout_path("Mail", "Billings-Menustar.mbox"),
        help="Path to Billings-Menustar.mbox",
    )
    parser.add_argument(
        "--out",
        default=raw_path("menustar", "billings_raw.csv"),
        help="Output raw CSV path.",
    )
    args = parser.parse_args()
    run(args.mbox, args.out)


if __name__ == "__main__":
    main()
