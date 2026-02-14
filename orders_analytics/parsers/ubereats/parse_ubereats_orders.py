#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Tuple

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path, takeout_path
from orders_analytics.utils.normalize import normalize_datetime, normalize_money
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.schema import build_normalized_row


def _normalize_columns(df: pd.DataFrame) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for col in df.columns:
        key = " ".join(str(col).replace("\n", " ").split()).strip().lower()
        mapping[key] = col
    return mapping


def _col(mapping: Dict[str, str], name: str) -> str:
    key = " ".join(str(name).replace("\n", " ").split()).strip().lower()
    return mapping.get(key, name)


def _money(value: str) -> str:
    return normalize_money(value)


def _decimal(value: str) -> Decimal:
    return Decimal(value)


def _sum_money(values: List[str]) -> str:
    total = Decimal("0")
    has_value = False
    for value in values:
        if not value:
            continue
        has_value = True
        try:
            total += _decimal(value)
        except InvalidOperation:
            continue
    if not has_value:
        return ""
    return str(total)


def _note_kv(label: str, value: str) -> str:
    if not str(value).strip():
        return ""
    return f"{label}={value}"


def _build_datetime(order_date: str, accept_time: str) -> str:
    date_text = str(order_date or "").strip()
    time_text = str(accept_time or "").strip()
    if not date_text:
        return ""
    if not time_text:
        time_text = "12:00 AM"
    combined = f"{date_text} {time_text}"
    return normalize_datetime(
        combined,
        formats=("%m/%d/%y %I:%M %p", "%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M"),
        allow_iso=True,
    )


def _merge_notes(notes: List[str]) -> str:
    items = [n for n in notes if n]
    deduped = []
    seen = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return " | ".join(deduped)


def _append_notes(existing: str, additions: List[str]) -> str:
    base = [n for n in str(existing or "").split(" | ") if n]
    return _merge_notes(base + additions)


class UberEatsOrdersParser(BaseParser):
    platform = "UBEREATS"
    dedupe_key = "order_id"
    tax_validation_skip_negative_payout = True
    total_components_fields = (
        "subtotal",
        "tax",
        "tip",
        "delivery_fee",
        "adjustments",
        "marketing_fee",
        "misc_fee",
    )

    def default_input_path(self) -> str:
        return raw_path("ubereats", "ubereats_stitched_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("ubereats_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        return pd.read_csv(input_path, dtype=str, encoding="utf-8-sig").fillna("")

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        df = inputs.copy()
        mapping = _normalize_columns(df)

        status_col = _col(mapping, "Order Status")
        if status_col in df.columns:
            status_values = df[status_col].astype(str).str.strip().str.lower()
            df = df[~status_values.str.contains("cancel|unfulfilled", na=False)].copy()

        order_id_col = _col(mapping, "Order ID")
        workflow_col = _col(mapping, "Workflow ID")

        if workflow_col in df.columns and order_id_col in df.columns:
            df["__order_key"] = df[workflow_col].where(
                df[workflow_col].str.strip() != "", df[order_id_col]
            )
        elif workflow_col in df.columns:
            df["__order_key"] = df[workflow_col].astype(str)
        elif order_id_col in df.columns:
            df["__order_key"] = df[order_id_col].astype(str)
        elif "order_id" in df.columns:
            df["__order_key"] = df["order_id"].astype(str)
        else:
            df["__order_key"] = ""

        groups = df.groupby("__order_key", dropna=False)
        rows: List[Dict[str, str]] = []

        for order_key, group in groups:
            row = group.iloc[0]
            store_name = row.get(_col(mapping, "Store Name"), "")
            provider = normalize_provider(store_name)

            dining_modes = group[_col(mapping, "Dining Mode")].unique().tolist()
            order_types = []
            for mode in dining_modes:
                if "delivery" in str(mode).lower() and "partner" in str(mode).lower():
                    order_types.append(OrderTypes.DELIVERY)
            order_type = OrderTypes.PICKUP

            order_dates = group[_col(mapping, "Order Date")].astype(str).tolist()
            accept_times = group[_col(mapping, "Order Accept Time")].astype(str).tolist()
            datetimes = [
                _build_datetime(date, time)
                for date, time in zip(order_dates, accept_times)
            ]
            order_datetime = ""
            parsed = pd.to_datetime([d if d else None for d in datetimes], errors="coerce")
            if parsed.notna().any():
                order_datetime = parsed.min().isoformat()
            else:
                order_datetime = datetimes[0] if datetimes else ""

            subtotal = _sum_money([_money(v) for v in group[_col(mapping, "Sales (excl. tax)")].tolist()])
            tax = _sum_money(
                [
                    _money(v)
                    for v in group[_col(mapping, "Tax on Sales")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Tax on Order Error Adjustments")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Tax on Price Adjustments")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Tax On Offers on items")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Tax On Delivery Offer Redemptions")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Tax on Marketplace Fee")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Tax on Delivery Network Fee")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Tax On Delivery Fee")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Markup Tax")].tolist()
                ]
            )

            adjustments = _sum_money(
                [
                    _money(v)
                    for v in group[_col(mapping, "Order Error Adjustments")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Price adjustments (excl. tax)")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Other payments")].tolist()
                ]
            )

            offers_incl = _sum_money(
                [_money(v) for v in group[_col(mapping, "Offers on items (incl. tax)")].tolist()]
            )
            offers_tax = _sum_money(
                [_money(v) for v in group[_col(mapping, "Tax On Offers on items")].tolist()]
            )
            offers_excl = ""
            if offers_incl and offers_tax:
                try:
                    offers_excl = str(Decimal(offers_incl) - Decimal(offers_tax))
                except Exception:
                    offers_excl = offers_incl
            else:
                offers_excl = offers_incl or ""

            marketing_fee = _sum_money(
                [offers_excl]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Delivery Offer Redemptions (incl. tax)")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Offer Redemption Fee")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Marketing Adjustment")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Markup Amount")].tolist()
                ]
            )

            misc_fee = _sum_money(
                [
                    _money(v)
                    for v in group[_col(mapping, "Bag Fee")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Delivery Network Fee")].tolist()
                ]
            )

            commission_fee = _sum_money(
                [_money(v) for v in group[_col(mapping, "Marketplace Fee")].tolist()]
            )
            processing_fee = _sum_money(
                [_money(v) for v in group[_col(mapping, "Order Processing Fee")].tolist()]
            )
            delivery_fee = _sum_money(
                [_money(v) for v in group[_col(mapping, "Delivery Fee")].tolist()]
            )
            tip = _sum_money([_money(v) for v in group[_col(mapping, "Tips")].tolist()])
            total = _sum_money(
                [_money(v) for v in group[_col(mapping, "Total Sales after Adjustments (incl tax)")].tolist()]
            )
            payout = _sum_money(
                [_money(v) for v in group[_col(mapping, "Total payout")].tolist()]
            )
            tax_note = tax
            tax_withheld = _sum_money(
                [
                    _money(v)
                    for v in group[_col(mapping, "Marketplace Facilitator Tax Adjustment")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Marketplace Facilitator Tax")].tolist()
                ]
                + [
                    _money(v)
                    for v in group[_col(mapping, "Backup Withholding Tax")].tolist()
                ]
            )
            tax_withheld_value = None
            if tax_withheld:
                try:
                    tax_withheld_value = abs(Decimal(tax_withheld))
                except Exception:
                    tax_withheld_value = None
            if tax_withheld_value is not None and tax_withheld_value > 0:
                tax_withheld = str(tax_withheld_value)
                tax = ""
                if total:
                    try:
                        total = str(Decimal(total) - tax_withheld_value)
                    except Exception:
                        pass
            else:
                tax_withheld = ""

            notes: List[str] = []
            if tax_withheld and tax_note:
                notes.append(_note_kv("tax", tax_note))
            for mode in dining_modes:
                mode_text = str(mode).strip()
                if mode_text.lower().startswith('delivery'):
                    mode_text = 'Delivery'
                if mode_text:
                    notes.append(_note_kv('dining_mode', mode_text))
            for value in group[_col(mapping, "Order Channel")].unique().tolist():
                channel_text = str(value).strip()
                if channel_text and channel_text.lower() != "unknown":
                    notes.append(_note_kv("order_channel", channel_text))
            for value in group[_col(mapping, "Order Status")].unique().tolist():
                status_text = str(value).strip()
                if status_text and status_text.lower() != 'completed':
                    notes.append(_note_kv('order_status', status_text))

            order_error_incl_tax = _sum_money(
                [_money(v) for v in group[_col(mapping, "Order Error Adjustments (incl. tax)")].tolist()]
            )
            if order_error_incl_tax:
                try:
                    if Decimal(order_error_incl_tax) > 0:
                        notes.append(_note_kv('order_error_adjustments_incl_tax', order_error_incl_tax))
                except Exception:
                    notes.append(_note_kv('order_error_adjustments_incl_tax', order_error_incl_tax))

            marketplace_fee_pct = _sum_money(
                [_money(v) for v in group[_col(mapping, "Marketplace fee %")].tolist()]
            )
            if marketplace_fee_pct:
                notes.append(_note_kv("marketplace_fee_pct", marketplace_fee_pct))

            capital_payments = _sum_money(
                [_money(v) for v in group[_col(mapping, "Capital payments")].tolist()]
            )
            if capital_payments:
                try:
                    if Decimal(capital_payments) > 0:
                        notes.append(_note_kv('capital_payments', capital_payments))
                except Exception:
                    notes.append(_note_kv('capital_payments', capital_payments))

            other_desc = _merge_notes(
                [str(v).strip() for v in group[_col(mapping, "Other payments description")].tolist()]
            )
            if other_desc:
                notes.append(_note_kv("other_payments_description", other_desc))

            payout_dates = _merge_notes(
                [str(v).strip() for v in group[_col(mapping, "Payout Date")].tolist()]
            )
            if payout_dates:
                notes.append(_note_kv("payout_date", payout_dates))

            merged_count = row.get(_col(mapping, "merged_row_count"), "")
            if str(merged_count).strip():
                try:
                    merged_count = str(int(float(merged_count)))
                except Exception:
                    merged_count = str(merged_count).strip()
                notes.append(_note_kv("merged_row_count", merged_count))

            order_id_value = str(order_key)
            if order_id_value.startswith("UBER_OTHER_"):
                final_order_id = order_id_value
            else:
                raw_order_id = str(row.get(order_id_col, "")).strip()
                raw_workflow = str(row.get(workflow_col, "")).strip()
                if raw_order_id and raw_workflow:
                    final_order_id = f"{raw_order_id}|{raw_workflow}"
                else:
                    final_order_id = order_id_value

            customer_col = _col(mapping, "customer_name")
            items_col = _col(mapping, "items")
            customer_name = ""
            items_value = ""
            if customer_col in group.columns:
                customer_name = _merge_notes([str(v).strip() for v in group[customer_col].tolist() if str(v).strip()])
            if items_col in group.columns:
                items_value = _merge_notes([str(v).strip() for v in group[items_col].tolist() if str(v).strip()])

            row_data = build_normalized_row(
                Platforms.UBEREATS.upper(),
                order_id=final_order_id,
                provider=provider,
                restaurant_name=store_name,
                order_datetime=order_datetime,
                order_type=order_type,
                payment_type=PaymentTypes.CREDIT,
                subtotal=subtotal,
                tax=tax,
                tax_withheld=tax_withheld,
                tip=tip,
                delivery_fee=delivery_fee,
                total=total,
                commission_fee=commission_fee,
                processing_fee=processing_fee,
                adjustments=adjustments,
                marketing_fee=marketing_fee,
                misc_fee=misc_fee,
                payout=payout,
                customer_name=customer_name,
                items=items_value,
                notes=_merge_notes(notes),
            )
            rows.append(row_data)

        return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Uber Eats orders CSV.")
    parser.add_argument(
        "--csv",
        default=None,
        help="Path to Uber Eats CSV export.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()

    runner = UberEatsOrdersParser(input_path=args.csv, out_path=args.out)
    stats = runner.run()
    out_path = runner.resolve_paths()[1]
    print(f"[{Platforms.UBEREATS}] normalized -> {out_path} ({stats.rows_written} rows)")


if __name__ == "__main__":
    main()
