#!/usr/bin/env python3
import argparse
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_datetime, normalize_money
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.providers import Providers
from orders_analytics.utils.schema import build_normalized_row, compute_expected_payout


ORDER_ID_COLUMNS = ["Order Id", "Order ID", "OrderId"]
DATE_COLUMNS = ["Date", "Order Date"]
SUBTOTAL_COLUMNS = ["Order Invoice Amount", "Invoice Amount", "Subtotal", "OrderInvoiceAm"]
TAX_COLUMNS = ["Tax (Calc from Original Sale Price", "Tax", "Toauxn(tCalc from O"]
TOTAL_COLUMNS = ["Paid", "Total Paid", "rPigaiindal Sale Pric"]
DSP_COLUMNS = ["Platform", "Delivery Partner", "eP)latform"]
STORE_COLUMNS = ["Store Name"]


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def _first_nonempty(row: Dict[str, str], columns: List[str]) -> str:
    for col in columns:
        value = str(row.get(col, "")).strip()
        if value and value.lower() != "nan":
            return value
    return ""


def _normalize_order_id(value: str, dsp: str = "") -> str:
    order_id = str(value or "").strip()
    if not order_id:
        return ""
    if re.search(r"\s", order_id):
        return ""
    if re.match(r"^\d{6,}$", order_id) and str(dsp).strip().lower() == "grubhub":
        return f"O-{order_id}"
    if re.match(r"^O-\d+$", order_id, flags=re.IGNORECASE):
        return order_id.upper()
    if re.match(r"^#[A-Za-z0-9\-]+$", order_id):
        return order_id.upper()
    if re.match(r"^[A-Za-z0-9]{5,}$", order_id):
        return order_id.upper()
    return ""


def _repair_split_hash_order_id(order_id: str, subtotal_raw: str) -> str:
    oid = str(order_id or "").strip()
    subtotal_text = str(subtotal_raw or "").strip()
    if not re.match(r"^#\d+$", oid):
        return oid
    match = re.match(r"^(\d{2,4})\s+\$", subtotal_text)
    if not match:
        return oid
    return f"{oid}{match.group(1)}"


def _normalize_date(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"-\s+", "-", text)
    return normalize_datetime(
        text,
        formats=[
            "%Y-%m-%d",
            "%m/%d/%y",
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%m-%d-%y",
        ],
    )


def _normalize_amount(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    cleaned = text.replace("$", "").replace(",", "")
    matches = re.findall(r"-?\d+(?:\.\d+)?", cleaned)
    if matches:
        cleaned = matches[-1]
    return normalize_money(cleaned)


def _to_decimal(value: str) -> Decimal:
    text = str(value or "").strip()
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def _fmt_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _row_score(row: Dict[str, str]) -> int:
    score_cols = ["order_datetime", "subtotal", "tax", "total", "restaurant_name", "notes"]
    return sum(1 for col in score_cols if str(row.get(col, "")).strip())


def _order_id_numeric_core(order_id: str) -> str:
    text = str(order_id or "").strip().upper()
    match = re.match(r"^O-(\d+)$", text)
    if not match:
        return ""
    digits = match.group(1)
    return digits.lstrip("0") or "0"


def _pick_primary_order_id(ids: List[str]) -> str:
    def sort_key(order_id: str):
        text = str(order_id or "").strip().upper()
        match = re.match(r"^O-(\d+)$", text)
        if not match:
            return (0, text)
        digits = match.group(1)
        return (len(digits), digits)

    return sorted(ids, key=sort_key, reverse=True)[0]


def _merge_alias_order_ids(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    if not rows:
        return rows

    grouped: Dict[tuple, List[Dict[str, str]]] = {}
    for row in rows:
        core = _order_id_numeric_core(row.get("order_id", ""))
        if not core:
            grouped[(None, id(row))] = [row]
            continue
        key = (
            core,
            row.get("provider", ""),
            row.get("order_datetime", ""),
            row.get("order_type", ""),
            row.get("payment_type", ""),
            row.get("subtotal", ""),
            row.get("tax", ""),
            row.get("tax_withheld", ""),
            row.get("tip", ""),
            row.get("delivery_fee", ""),
            row.get("total", ""),
            row.get("processing_fee", ""),
            row.get("commission_fee", ""),
            row.get("adjustments", ""),
            row.get("marketing_fee", ""),
            row.get("misc_fee", ""),
            row.get("payout", ""),
            row.get("expected_payout", ""),
            row.get("restaurant_name", ""),
        )
        grouped.setdefault(key, []).append(row)

    merged_rows: List[Dict[str, str]] = []
    for group in grouped.values():
        if len(group) == 1:
            merged_rows.append(group[0])
            continue
        ids = sorted({str(r.get("order_id", "")).strip() for r in group if str(r.get("order_id", "")).strip()})
        primary = _pick_primary_order_id(ids)
        primary_row = next((r for r in group if str(r.get("order_id", "")).strip() == primary), group[0]).copy()
        aliases = [oid for oid in ids if oid != primary]
        if aliases:
            notes = str(primary_row.get("notes", "")).strip()
            alias_note = f"merged_order_id_aliases={','.join(aliases)}"
            primary_row["notes"] = f"{notes} | {alias_note}".strip(" |")
        merged_rows.append(primary_row)
    return merged_rows


def _dedupe_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    by_order: Dict[str, Dict[str, str]] = {}
    for row in rows:
        order_id = row["order_id"]
        existing = by_order.get(order_id)
        if existing is None:
            by_order[order_id] = row
            continue
        current_key = (_row_score(row), str(row.get("order_datetime", "")), str(row.get("notes", "")))
        existing_key = (
            _row_score(existing),
            str(existing.get("order_datetime", "")),
            str(existing.get("notes", "")),
        )
        if current_key > existing_key:
            by_order[order_id] = row
    return list(by_order.values())


def normalize_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for row in rows:
        dsp = _first_nonempty(row, DSP_COLUMNS).lower()
        raw_order_id = _first_nonempty(row, ORDER_ID_COLUMNS)
        raw_subtotal_text = _first_nonempty(row, SUBTOTAL_COLUMNS)
        repaired_order_id = _repair_split_hash_order_id(raw_order_id, raw_subtotal_text)
        order_id = _normalize_order_id(repaired_order_id, dsp=dsp)
        if not order_id:
            continue

        order_datetime = _normalize_date(_first_nonempty(row, DATE_COLUMNS))
        subtotal = _normalize_amount(_first_nonempty(row, SUBTOTAL_COLUMNS))
        tax = _normalize_amount(_first_nonempty(row, TAX_COLUMNS))
        total = _normalize_amount(_first_nonempty(row, TOTAL_COLUMNS))
        if not total and (subtotal or tax):
            try:
                total = f"{(float(subtotal or 0) + float(tax or 0)):.2f}"
            except ValueError:
                total = ""

        # Mayaeats accounting model: subtotal represents 57% of true sales.
        # Record offsetting entries so payout remains unchanged while preserving the model.
        subtotal_dec = _to_decimal(subtotal)
        if subtotal_dec != Decimal("0"):
            modeled_true_subtotal = subtotal_dec / Decimal("0.57")
            adjustments = _fmt_decimal(modeled_true_subtotal)
            commission_fee = _fmt_decimal(-modeled_true_subtotal)
        else:
            adjustments = "0.00"
            commission_fee = "0.00"

        store_name = _first_nonempty(row, STORE_COLUMNS)
        notes_parts = []
        if dsp:
            notes_parts.append(f"platform={dsp}")

        normalized_row = build_normalized_row(
            Platforms.MAYAEATS.upper(),
            order_id=order_id,
            provider=Providers.AROMA,
            order_datetime=order_datetime,
            order_type=OrderTypes.PICKUP,
            payment_type=PaymentTypes.CREDIT,
            subtotal=subtotal,
            tax=tax,
            tax_withheld="0.00" if tax else "",
            tip="0.00",
            delivery_fee="0.00",
            total=total,
            processing_fee="0.00",
            commission_fee=commission_fee,
            adjustments=adjustments,
            payout=total,
            restaurant_name="Fire Pizza",
            notes=" | ".join(notes_parts),
        )
        normalized_row["expected_payout"] = compute_expected_payout(normalized_row)
        normalized.append(normalized_row)

    merged_aliases = _merge_alias_order_ids(normalized)
    return _dedupe_rows(merged_aliases)


class MayaeatsNormalizer(BaseParser):
    platform = "MAYAEATS"
    provider = "AROMA"

    def default_input_path(self) -> str:
        return raw_path("mayaeats", "billings_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("mayaeats_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return {"billings_raw": load_raw(input_path)}

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        rows = inputs["billings_raw"].to_dict("records")
        return normalize_rows(rows)


def run(
    billings_raw_path: str,
    out_path: str,
    reset_errors: bool = False,
) -> int:
    parser = MayaeatsNormalizer(
        input_path=billings_raw_path,
        out_path=out_path,
        reset_errors=reset_errors,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Mayaeats raw CSV.")
    parser.add_argument(
        "--billings-raw",
        default=raw_path("mayaeats", "billings_raw.csv"),
        help="Path to Mayaeats billings raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("mayaeats_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.billings_raw, args.out)


if __name__ == "__main__":
    main()
