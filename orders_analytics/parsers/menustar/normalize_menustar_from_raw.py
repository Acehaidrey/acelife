#!/usr/bin/env python3
import argparse
import hashlib
import os
from datetime import datetime
import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List, Tuple, Optional

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import (
    normalize_address,
    normalize_order_type,
    normalize_payment_type,
)
from orders_analytics.utils.providers import Providers, normalize_provider, normalize_datetime
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.schema import build_normalized_row




def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def ensure_adjustments_file(path: str) -> None:
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(
        columns=[
            "order_id",
            "status",
            "adjustments",
            "notes",
        ]
    ).to_csv(path, index=False)


def load_adjustments(path: str) -> Dict[str, Dict[str, str]]:
    ensure_adjustments_file(path)
    df = pd.read_csv(path, dtype=str).fillna("")
    out: Dict[str, Dict[str, str]] = {}
    for row in df.to_dict("records"):
        order_id = str(row.get("order_id", "")).strip()
        if not order_id:
            continue
        out[order_id] = {
            "status": str(row.get("status", "")).strip().lower(),
            "adjustments": str(row.get("adjustments", "")).strip(),
            "notes": str(row.get("notes", "")).strip(),
        }
    return out


def ensure_billings_overrides_file(path: str) -> None:
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(
        columns=[
            "provider",
            "order_datetime",
            "subtotal",
            "tax",
            "delivery_fee",
            "tip",
            "total",
            "new_order_datetime",
            "notes",
            "enabled",
        ]
    ).to_csv(path, index=False)


def load_billings_overrides(path: str) -> Dict[Tuple[str, str, str, str, str, str, str], Dict[str, str]]:
    ensure_billings_overrides_file(path)
    df = pd.read_csv(path, dtype=str).fillna("")
    out: Dict[Tuple[str, str, str, str, str, str, str], Dict[str, str]] = {}
    for row in df.to_dict("records"):
        enabled = str(row.get("enabled", "YES")).strip().lower()
        if enabled in {"0", "false", "no", "n"}:
            continue
        provider = str(row.get("provider", "")).strip().upper()
        order_datetime = str(row.get("order_datetime", "")).strip()
        new_order_datetime = str(row.get("new_order_datetime", "")).strip()
        if not provider or not order_datetime or not new_order_datetime:
            continue
        key = (
            provider,
            order_datetime,
            str(row.get("subtotal", "")).strip(),
            str(row.get("tax", "")).strip(),
            str(row.get("delivery_fee", "")).strip(),
            str(row.get("tip", "")).strip(),
            str(row.get("total", "")).strip(),
        )
        out[key] = {
            "new_order_datetime": new_order_datetime,
            "notes": str(row.get("notes", "")).strip(),
        }
    return out


def date_key(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10]


def normalize_provider_key(value: str) -> str:
    return str(value or "").strip().lower()


def parse_decimal(value: str) -> Optional[Decimal]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def amount_equal(left: Optional[Decimal], right: Optional[Decimal]) -> bool:
    if left is None or right is None:
        return False
    return left.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == right.quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def format_fee(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if quantized == Decimal("0.00"):
        return "0.00"
    return str(quantized)


def billing_identity_key(row: Dict[str, str]) -> str:
    return "|".join(
        [
            str(row.get("provider", "")).strip(),
            str(row.get("order_datetime", "")).strip(),
            str(row.get("order_type", "")).strip(),
            str(row.get("payment_type", "")).strip(),
            str(row.get("subtotal", "")).strip(),
            str(row.get("tax", "")).strip(),
            str(row.get("delivery_fee", "")).strip(),
            str(row.get("tip", "")).strip(),
            str(row.get("total", "")).strip(),
        ]
    )


def billing_loose_key(row: Dict[str, str]) -> str:
    return "|".join(
        [
            str(row.get("provider", "")).strip(),
            str(row.get("order_datetime", "")).strip(),
            str(row.get("subtotal", "")).strip(),
            str(row.get("tax", "")).strip(),
            str(row.get("delivery_fee", "")).strip(),
            str(row.get("tip", "")).strip(),
            str(row.get("total", "")).strip(),
        ]
    )


def billing_day_amount_key(row: Dict[str, str]) -> str:
    return "|".join(
        [
            str(row.get("provider", "")).strip(),
            date_key(str(row.get("order_datetime", "")).strip()),
            str(row.get("subtotal", "")).strip(),
            str(row.get("tax", "")).strip(),
            str(row.get("delivery_fee", "")).strip(),
            str(row.get("tip", "")).strip(),
            str(row.get("total", "")).strip(),
        ]
    )


def billing_synthetic_suppress_key(row: Dict[str, str]) -> str:
    return "|".join(
        [
            str(row.get("provider", "")).strip(),
            date_key(str(row.get("order_datetime", "")).strip()),
            str(row.get("order_type", "")).strip(),
            str(row.get("payment_type", "")).strip(),
            str(row.get("subtotal", "")).strip(),
            str(row.get("tax", "")).strip(),
            str(row.get("delivery_fee", "")).strip(),
            str(row.get("tip", "")).strip(),
            str(row.get("total", "")).strip(),
            str(row.get("processing_fee", "")).strip(),
            str(row.get("commission_fee", "")).strip(),
        ]
    )


def canonical_statement_file(value: str) -> str:
    filename = " ".join(os.path.basename(str(value or "").strip()).split())
    stem, ext = os.path.splitext(filename)
    if stem.endswith(")") and " (" in stem:
        prefix, suffix = stem.rsplit(" (", 1)
        if suffix[:-1].isdigit():
            stem = prefix
    return f"{stem}{ext.lower()}".strip()


def has_nonzero_amounts(row: Dict[str, str]) -> bool:
    for field in ("subtotal", "tax", "delivery_fee", "tip", "total"):
        text = str(row.get(field, "")).strip()
        if not text:
            continue
        try:
            if Decimal(text) != Decimal("0"):
                return True
        except InvalidOperation:
            return True
    return False


def synthetic_order_id_for_billing(row: Dict[str, str]) -> str:
    key = billing_identity_key(row)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    provider = str(row.get("provider", "")).strip().upper() or "MENUSTAR"
    return f"MENUSTAR_BILLONLY_{provider}_{digest}"


def extract_year(value: str) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).year
    except ValueError:
        prefix = text[:4]
        if prefix.isdigit():
            return int(prefix)
    return 0


def apply_billings_overrides_df(
    billings_df: pd.DataFrame,
    overrides: Dict[Tuple[str, str, str, str, str, str, str], Dict[str, str]],
) -> Tuple[pd.DataFrame, int]:
    if billings_df.empty or not overrides:
        return billings_df, 0
    out = billings_df.copy()
    count = 0
    for idx, row in out.iterrows():
        key = (
            str(row.get("provider", "")).strip().upper(),
            str(row.get("order_datetime", "")).strip(),
            str(row.get("subtotal", "")).strip(),
            str(row.get("tax", "")).strip(),
            str(row.get("delivery_fee", "")).strip(),
            str(row.get("tip", "")).strip(),
            str(row.get("total", "")).strip(),
        )
        override = overrides.get(key)
        if not override:
            continue
        out.at[idx, "order_datetime"] = override.get("new_order_datetime", "")
        count += 1
    return out, count


def dedupe_billings_df(billings_df: pd.DataFrame) -> pd.DataFrame:
    if billings_df.empty:
        return billings_df

    def score(row: Dict[str, str]) -> int:
        return sum(1 for value in row.values() if str(value or "").strip())

    def parse_email_dt(value: str) -> Optional[dt.datetime]:
        if not value:
            return None
        try:
            return dt.datetime.fromisoformat(value)
        except ValueError:
            return None

    chosen: Dict[str, Dict[str, str]] = {}
    for row in billings_df.to_dict("records"):
        key = billing_identity_key(row)
        current = chosen.get(key)
        if current is None:
            chosen[key] = row
            continue
        current_score = score(current)
        new_score = score(row)
        replace = False
        if new_score > current_score:
            replace = True
        elif new_score == current_score:
            current_dt = parse_email_dt(str(current.get("statement_email_date", "")))
            new_dt = parse_email_dt(str(row.get("statement_email_date", "")))
            if new_dt and (not current_dt or new_dt > current_dt):
                replace = True
        if replace:
            chosen[key] = row

    return pd.DataFrame(list(chosen.values())).reindex(columns=billings_df.columns)


def allocate_commission(
    billing_rows: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    # Allocate MenuStar Fees proportionally across all orders by subtotal.
    # If billing rows already have an allocated value, use it.
    has_allocated = any(row.get("statement_menustar_fees_allocated") for row in billing_rows)
    if has_allocated:
        for row in billing_rows:
            alloc = row.get("statement_menustar_fees_allocated", "")
            if alloc:
                try:
                    alloc_dec = Decimal(alloc)
                    payment_type = normalize_payment_type(str(row.get("payment_type", "")))
                    if payment_type == "cash":
                        commission = alloc_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        processing = Decimal("0.00")
                    else:
                        commission = (alloc_dec * Decimal("0.70")).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                        processing = (alloc_dec - commission).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                    row["commission_fee"] = str(
                        format_fee(commission * Decimal("-1"))
                    )
                    row["processing_fee"] = str(
                        format_fee(processing * Decimal("-1"))
                    )
                except InvalidOperation:
                    row["commission_fee"] = ""
                    row["processing_fee"] = ""
        return billing_rows
    grouped: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
    for row in billing_rows:
        key = (row.get("provider", ""), row.get("statement_source_file", ""))
        grouped.setdefault(key, []).append(row)

    for key, rows in grouped.items():
        fee_raw = rows[0].get("statement_menustar_fees", "")
        if not fee_raw:
            continue
        try:
            fee_total = Decimal(fee_raw)
        except InvalidOperation:
            continue
        try:
            subtotal_sum = sum(
                Decimal(r.get("subtotal") or "0") for r in rows
            )
        except InvalidOperation:
            continue
        if subtotal_sum == 0:
            continue
        allocs: List[Decimal] = []
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
            payment_type = normalize_payment_type(str(row.get("payment_type", "")))
            if payment_type == "cash":
                commission = alloc.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                processing = Decimal("0.00")
            else:
                commission = (alloc * Decimal("0.70")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                processing = (alloc - commission).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            row["commission_fee"] = str(
                format_fee(commission * Decimal("-1"))
            )
            row["processing_fee"] = str(
                format_fee(processing * Decimal("-1"))
            )
    return billing_rows


def merge_rows(
    orders_raw: pd.DataFrame, billings_raw: pd.DataFrame
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
    if billings_raw.empty:
        return [], [], []
    billing_rows = billings_raw.to_dict("records")
    billing_rows = allocate_commission(billing_rows)

    orders_by_day: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
    for _, row in orders_raw.iterrows():
        row_dict = row.to_dict()
        key = (
            normalize_provider_key(row_dict.get("provider", "")),
            date_key(str(row_dict.get("order_datetime", "")).strip()),
        )
        if key[0] and key[1]:
            orders_by_day.setdefault(key, []).append(row_dict)

    merged: List[Dict[str, str]] = []
    unmatched_billings: List[Dict[str, str]] = []

    def parse_dt_local(value: str) -> Optional[dt.datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
                try:
                    return dt.datetime.strptime(text, fmt)
                except ValueError:
                    continue
        return None

    def strict_match(row: Dict[str, str], candidate: Dict[str, str]) -> bool:
        billing_amounts = {
            "subtotal": parse_decimal(row.get("subtotal", "")),
            "tax": parse_decimal(row.get("tax", "")),
            "delivery_fee": parse_decimal(row.get("delivery_fee", "")),
            "tip": parse_decimal(row.get("tip", "")),
            "total": parse_decimal(row.get("total", "")),
        }
        candidate_amounts = {
            "subtotal": parse_decimal(candidate.get("subtotal", "")),
            "tax": parse_decimal(candidate.get("tax", "")),
            "delivery_fee": parse_decimal(candidate.get("delivery_fee", "")),
            "tip": parse_decimal(candidate.get("tip", "")),
            "total": parse_decimal(candidate.get("total", "")),
        }
        for field in ("subtotal", "tax", "delivery_fee", "tip", "total"):
            if billing_amounts[field] is None or candidate_amounts[field] is None:
                continue
            if not amount_equal(billing_amounts[field], candidate_amounts[field]):
                return False
        billing_order_type = normalize_order_type(str(row.get("order_type", ""))).strip()
        candidate_order_type = normalize_order_type(str(candidate.get("order_type", ""))).strip()
        if billing_order_type and candidate_order_type and billing_order_type != candidate_order_type:
            return False
        billing_payment_type = normalize_payment_type(str(row.get("payment_type", ""))).strip()
        candidate_payment_type = normalize_payment_type(str(candidate.get("payment_type", ""))).strip()
        if billing_payment_type and candidate_payment_type and billing_payment_type != candidate_payment_type:
            return False
        return True
    for row in billing_rows:
        key = (
            normalize_provider_key(row.get("provider", "")),
            date_key(str(row.get("order_datetime", "")).strip()),
        )
        candidates = orders_by_day.get(key, [])
        best_idx = None
        best_score = -1
        best_total_diff = None
        best_subtotal_diff = None
        best_time_diff = None

        billing_amounts = {
            "subtotal": parse_decimal(row.get("subtotal", "")),
            "tax": parse_decimal(row.get("tax", "")),
            "delivery_fee": parse_decimal(row.get("delivery_fee", "")),
            "tip": parse_decimal(row.get("tip", "")),
            "total": parse_decimal(row.get("total", "")),
        }
        billing_order_type = normalize_order_type(str(row.get("order_type", ""))).strip()
        billing_payment_type = normalize_payment_type(str(row.get("payment_type", ""))).strip()

        for idx, candidate in enumerate(candidates):
            score = 0
            candidate_amounts = {
                "subtotal": parse_decimal(candidate.get("subtotal", "")),
                "tax": parse_decimal(candidate.get("tax", "")),
                "delivery_fee": parse_decimal(candidate.get("delivery_fee", "")),
                "tip": parse_decimal(candidate.get("tip", "")),
                "total": parse_decimal(candidate.get("total", "")),
            }
            strict_ok = True
            for field in ("subtotal", "tax", "delivery_fee", "tip", "total"):
                if billing_amounts[field] is None or candidate_amounts[field] is None:
                    continue
                if not amount_equal(billing_amounts[field], candidate_amounts[field]):
                    strict_ok = False
                    break
                score += 2

            candidate_order_type = normalize_order_type(str(candidate.get("order_type", ""))).strip()
            if billing_order_type and candidate_order_type and billing_order_type == candidate_order_type:
                score += 1
            elif billing_order_type and candidate_order_type and billing_order_type != candidate_order_type:
                strict_ok = False
            candidate_payment_type = normalize_payment_type(
                str(candidate.get("payment_type", ""))
            ).strip()
            if billing_payment_type and candidate_payment_type and billing_payment_type == candidate_payment_type:
                score += 1
            elif billing_payment_type and candidate_payment_type and billing_payment_type != candidate_payment_type:
                strict_ok = False

            if not strict_ok:
                continue

            total_diff = None
            if billing_amounts["total"] is not None and candidate_amounts["total"] is not None:
                total_diff = abs(billing_amounts["total"] - candidate_amounts["total"])
            subtotal_diff = None
            if (
                billing_amounts["subtotal"] is not None
                and candidate_amounts["subtotal"] is not None
            ):
                subtotal_diff = abs(billing_amounts["subtotal"] - candidate_amounts["subtotal"])
            time_diff = None
            billing_dt = parse_dt_local(str(row.get("order_datetime", "")))
            candidate_dt = parse_dt_local(str(candidate.get("order_datetime", "")))
            if billing_dt and candidate_dt:
                time_diff = abs((billing_dt - candidate_dt).total_seconds())

            is_better = False
            if score > best_score:
                is_better = True
            elif score == best_score:
                if best_total_diff is None and total_diff is not None:
                    is_better = True
                elif best_total_diff is not None and total_diff is not None and total_diff < best_total_diff:
                    is_better = True
                elif best_total_diff == total_diff:
                    if best_subtotal_diff is None and subtotal_diff is not None:
                        is_better = True
                    elif (
                        best_subtotal_diff is not None
                        and subtotal_diff is not None
                        and subtotal_diff < best_subtotal_diff
                    ):
                        is_better = True
                    elif best_subtotal_diff == subtotal_diff:
                        if best_time_diff is None and time_diff is not None:
                            is_better = True
                        elif (
                            best_time_diff is not None
                            and time_diff is not None
                            and time_diff < best_time_diff
                        ):
                            is_better = True

            if is_better:
                best_idx = idx
                best_score = score
                best_total_diff = total_diff
                best_subtotal_diff = subtotal_diff
                best_time_diff = time_diff

        order = {}
        if best_idx is not None:
            order = candidates.pop(best_idx)
        else:
            unmatched_billings.append(row)
        merged.append({**row, **{f"{k}_order": v for k, v in order.items()}})
    # Second pass: match remaining orders to remaining billings by strict amounts/types and closest date.
    if unmatched_billings:
        def parse_dt(value: str) -> Optional[dt.datetime]:
            if not value:
                return None
            try:
                return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
                    try:
                        return dt.datetime.strptime(value, fmt)
                    except ValueError:
                        continue
            return None

        def billing_key(row: Dict[str, str]) -> str:
            return "|".join(
                [
                    str(row.get("provider", "")).strip(),
                    str(row.get("order_datetime", "")).strip(),
                    str(row.get("order_type", "")).strip(),
                    str(row.get("payment_type", "")).strip(),
                    str(row.get("subtotal", "")).strip(),
                    str(row.get("tax", "")).strip(),
                    str(row.get("delivery_fee", "")).strip(),
                    str(row.get("tip", "")).strip(),
                    str(row.get("total", "")).strip(),
                ]
            )

        merged_index = {billing_key(row): row for row in merged}
        unmatched_orders = []
        for candidates in orders_by_day.values():
            unmatched_orders.extend(candidates)
        remaining_billings = list(unmatched_billings)
        still_unmatched_orders: List[Dict[str, str]] = []

        for order in unmatched_orders:
            order_provider = normalize_provider_key(order.get("provider", ""))
            order_dt = parse_dt(str(order.get("order_datetime", "")))
            best_idx = None
            best_diff = None
            for idx, billing in enumerate(remaining_billings):
                if normalize_provider_key(billing.get("provider", "")) != order_provider:
                    continue
                if not strict_match(billing, order):
                    continue
                billing_dt = parse_dt(str(billing.get("order_datetime", "")))
                if order_dt and billing_dt:
                    diff = abs((order_dt - billing_dt).total_seconds())
                else:
                    diff = float("inf")
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_idx = idx
            if best_idx is None:
                still_unmatched_orders.append(order)
                continue
            billing = remaining_billings.pop(best_idx)
            key = billing_key(billing)
            target = merged_index.get(key)
            note = f"order_date={order.get('order_datetime','')} billing_date={billing.get('order_datetime','')}"
            if target is not None:
                for k, v in order.items():
                    target[f"{k}_order"] = v
                target["date_mismatch_note"] = note
            else:
                merged.append({**billing, **{f"{k}_order": v for k, v in order.items()}, "date_mismatch_note": note})
        unmatched_billings = remaining_billings
        unmatched_orders = still_unmatched_orders
        return merged, unmatched_billings, unmatched_orders

    unmatched_orders: List[Dict[str, str]] = []
    for candidates in orders_by_day.values():
        unmatched_orders.extend(candidates)
    return merged, unmatched_billings, unmatched_orders


def normalize_rows(
    rows: List[Dict[str, str]],
    manual_adjustments: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    adjustments_seen: set[Tuple[str, str]] = set()
    manual_adjustments = manual_adjustments or {}
    for row in rows:
        order_id = str(row.get("order_id_order") or row.get("order_id") or "").strip()
        if not order_id:
            continue
        manual = manual_adjustments.get(order_id, {})
        if manual.get("status") == "cancelled":
            continue
        customer_name = str(row.get("customer_name_order") or "")
        if customer_name and "test" in customer_name.lower():
            continue
        order_datetime = normalize_datetime(row.get("order_datetime_order") or row.get("order_datetime", ""))
        provider = row.get("provider") or normalize_provider(row.get("restaurant_name", ""))
        address_raw = row.get("address_order", "") or row.get("address", "")
        statement_adjustment = str(row.get("statement_adjustments", "") or "").strip()
        statement_source = str(row.get("statement_source_file", "") or "").strip()
        statement_key = (statement_source, statement_adjustment)
        adjustments_value = ""
        notes = ""
        if statement_adjustment and statement_adjustment not in ("0", "0.00"):
            if statement_key not in adjustments_seen:
                adjustments_seen.add(statement_key)
                adjustments_value = statement_adjustment
                notes = "statement_adjustment_applied"
        if row.get("date_mismatch_note"):
            note = row.get("date_mismatch_note", "")
            notes = " | ".join([notes, note]).strip(" |")
        if row.get("missing_billing_record_note"):
            notes = " | ".join([notes, "missing_billing_record"]).strip(" |")
        if row.get("synthetic_billing_only_note"):
            notes = " | ".join([notes, "synthetic_billing_only_record"]).strip(" |")
        marketing_fee_value = str(
            row.get("discount_order", "") or row.get("marketing_fee_order", "") or ""
        ).strip()
        if marketing_fee_value:
            notes = " | ".join([notes, "marketing_fee_from_order_discount"]).strip(" |")
        manual_adjustment = str(manual.get("adjustments", "")).strip()
        if manual_adjustment:
            adjustments_value = manual_adjustment
            notes = " | ".join([notes, "manual_adjustment_applied"]).strip(" |")
        manual_notes = str(manual.get("notes", "")).strip()
        if manual_notes:
            notes = " | ".join([notes, manual_notes]).strip(" |")
        total_dec = parse_decimal(row.get("total", ""))
        commission_dec = parse_decimal(row.get("commission_fee", "")) or Decimal("0")
        processing_dec = parse_decimal(row.get("processing_fee", "")) or Decimal("0")
        payment_type_norm = normalize_payment_type(row.get("payment_type", ""))
        payout_value = ""
        payout_dec: Optional[Decimal] = None
        if payment_type_norm == "cash":
            payout_dec = commission_dec + processing_dec
        elif total_dec is not None:
            payout_dec = total_dec + commission_dec + processing_dec
        if payout_dec is not None and adjustments_value:
            adj_dec = parse_decimal(adjustments_value)
            if adj_dec is not None:
                payout_dec += adj_dec
        if payout_dec is not None:
            payout_value = format_fee(payout_dec)
        normalized.append(
            build_normalized_row(
                Platforms.MENUSTAR.upper(),
                order_id=order_id,
                provider=provider,
                restaurant_name=row.get("restaurant_name", ""),
                order_datetime=order_datetime,
                order_type=normalize_order_type(row.get("order_type", "")),
                customer_name=row.get("customer_name_order", ""),
                phone=row.get("phone_order", ""),
                email=row.get("email_order", ""),
                address=normalize_address(address_raw) or address_raw,
                payment_type=normalize_payment_type(row.get("payment_type", "")),
                subtotal=row.get("subtotal", ""),
                tax=row.get("tax", ""),
                tax_withheld="",
                tip=row.get("tip", ""),
                delivery_fee=row.get("delivery_fee", ""),
                total=row.get("total", ""),
                item_count=row.get("item_count_order", ""),
                processing_fee=row.get("processing_fee", ""),
                commission_fee=row.get("commission_fee", ""),
                marketing_fee=marketing_fee_value,
                items=row.get("items_order", ""),
                adjustments=adjustments_value,
                payout=payout_value,
                errors="",
                notes=notes,
            )
        )
    return normalized


def write_statement_payout_reconciliation(
    merged_rows: List[Dict[str, str]],
    normalized_rows: List[Dict[str, str]],
    out_path: str,
) -> None:
    payout_by_order_id: Dict[str, Decimal] = {}
    for row in normalized_rows:
        order_id = str(row.get("order_id", "")).strip()
        if not order_id:
            continue
        payout = parse_decimal(str(row.get("payout", "")))
        payout_by_order_id[order_id] = payout or Decimal("0")

    grouped: Dict[Tuple[str, str, str], Dict[str, object]] = {}
    for row in merged_rows:
        statement_file = str(row.get("statement_source_file", "")).strip()
        if not statement_file:
            continue
        order_id = str(row.get("order_id_order") or row.get("order_id") or "").strip()
        if not order_id or order_id not in payout_by_order_id:
            continue
        provider = str(row.get("provider", "")).strip().upper()
        statement_file_canonical = canonical_statement_file(statement_file)
        statement_email_date = str(row.get("statement_email_date", "")).strip()
        statement_period = date_key(str(row.get("order_datetime_order") or row.get("order_datetime") or ""))[:7]
        statement_net_payout = str(row.get("statement_net_payout", "")).strip()
        date_group = (
            f"{statement_email_date}:{statement_period}"
            if statement_email_date
            else f"MISSING:{statement_period}:{statement_net_payout}"
        )
        key = (provider, statement_file_canonical, date_group)
        bucket = grouped.setdefault(
            key,
            {
                "provider": provider,
                "statement_source_file": statement_file_canonical,
                "statement_email_date": statement_email_date,
                "statement_period": statement_period,
                "statement_net_payout": statement_net_payout,
                "orders_count": 0,
                "sum_order_payout": Decimal("0"),
                "source_files": set(),
            },
        )
        bucket["source_files"].add(statement_file)
        bucket["orders_count"] = int(bucket["orders_count"]) + 1
        bucket["sum_order_payout"] = Decimal(bucket["sum_order_payout"]) + payout_by_order_id[order_id]

    grouped_items = list(grouped.items())
    # Some statements are split across multiple source files (often one with blank email date)
    # but carry the same provider/period/net-payout total. Collapse those fragments into one bucket.
    collapse_candidates: Dict[Tuple[str, str, str], List[Dict[str, object]]] = {}
    passthrough: List[Dict[str, object]] = []
    for _, agg in grouped_items:
        collapse_key = (
            str(agg.get("provider", "")),
            str(agg.get("statement_period", "")),
            str(agg.get("statement_net_payout", "")),
        )
        collapse_candidates.setdefault(collapse_key, []).append(agg)

    final_aggs: List[Dict[str, object]] = []
    for _, aggs in collapse_candidates.items():
        has_blank_email = any(not str(agg.get("statement_email_date", "")).strip() for agg in aggs)
        if len(aggs) <= 1 or not has_blank_email:
            passthrough.extend(aggs)
            continue
        merged = {
            "provider": str(aggs[0].get("provider", "")),
            "statement_source_file": " | ".join(
                sorted({str(agg.get("statement_source_file", "")) for agg in aggs if str(agg.get("statement_source_file", "")).strip()})
            ),
            "statement_email_date": " | ".join(
                sorted({str(agg.get("statement_email_date", "")).strip() for agg in aggs if str(agg.get("statement_email_date", "")).strip()})
            ),
            "statement_period": str(aggs[0].get("statement_period", "")),
            "statement_net_payout": str(aggs[0].get("statement_net_payout", "")),
            "orders_count": 0,
            "sum_order_payout": Decimal("0"),
            "source_files": set(),
        }
        for agg in aggs:
            merged["orders_count"] = int(merged["orders_count"]) + int(agg.get("orders_count", 0))
            merged["sum_order_payout"] = Decimal(merged["sum_order_payout"]) + Decimal(
                agg.get("sum_order_payout", Decimal("0"))
            )
            merged["source_files"].update(agg.get("source_files", set()))
        final_aggs.append(merged)

    final_aggs.extend(passthrough)

    records: List[Dict[str, str]] = []
    for agg in sorted(
        final_aggs,
        key=lambda x: (
            str(x.get("provider", "")),
            str(x.get("statement_period", "")),
            str(x.get("statement_source_file", "")),
            str(x.get("statement_email_date", "")),
        ),
    ):
        statement_payout = parse_decimal(str(agg["statement_net_payout"])) or Decimal("0")
        payout_sum = Decimal(agg["sum_order_payout"])
        delta = (payout_sum - statement_payout).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        records.append(
            {
                "provider": str(agg["provider"]),
                "statement_source_file": str(agg["statement_source_file"]),
                "statement_email_date": str(agg["statement_email_date"]),
                "statement_period": str(agg["statement_period"]),
                "source_file_count": str(len(agg["source_files"])),
                "source_files": " | ".join(sorted(str(v) for v in agg["source_files"])),
                "orders_count": str(agg["orders_count"]),
                "sum_order_payout": format_fee(payout_sum),
                "statement_net_payout": str(agg["statement_net_payout"]),
                "payout_delta": str(delta),
                "matches_statement": "YES" if delta == Decimal("0.00") else "NO",
            }
        )

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pd.DataFrame(records).to_csv(out_path, index=False)


def merged_row_order_id(row: Dict[str, str]) -> str:
    return str(row.get("order_id_order") or row.get("order_id") or "").strip()


def merged_row_quality_score(row: Dict[str, str]) -> int:
    score = 0
    if str(row.get("order_id_order", "")).strip():
        # Prefer rows linked directly from orders_raw.
        score += 100
    if str(row.get("synthetic_billing_only_note", "")).strip():
        score -= 100
    score += sum(
        1
        for field in (
            "customer_name_order",
            "phone_order",
            "email_order",
            "address_order",
            "items_order",
            "item_count_order",
            "discount_order",
        )
        if str(row.get(field, "")).strip()
    )
    if str(row.get("statement_email_date", "")).strip():
        score += 1
    return score


def dedupe_merged_rows_by_order_id(
    rows: List[Dict[str, str]],
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    chosen: Dict[str, Dict[str, str]] = {}
    dropped: List[Dict[str, str]] = []

    for row in rows:
        order_id = merged_row_order_id(row)
        if not order_id:
            continue
        current = chosen.get(order_id)
        if current is None:
            chosen[order_id] = row
            continue

        current_score = merged_row_quality_score(current)
        new_score = merged_row_quality_score(row)
        keep_new = False
        if new_score > current_score:
            keep_new = True
        elif new_score == current_score:
            current_email = str(current.get("statement_email_date", "")).strip()
            new_email = str(row.get("statement_email_date", "")).strip()
            if new_email and (not current_email or new_email > current_email):
                keep_new = True

        if keep_new:
            dropped.append(
                {
                    "order_id": order_id,
                    "kept_order_datetime": str(
                        row.get("order_datetime_order") or row.get("order_datetime") or ""
                    ).strip(),
                    "kept_statement_source_file": str(row.get("statement_source_file", "")).strip(),
                    "dropped_order_datetime": str(
                        current.get("order_datetime_order") or current.get("order_datetime") or ""
                    ).strip(),
                    "dropped_statement_source_file": str(
                        current.get("statement_source_file", "")
                    ).strip(),
                    "reason": f"higher_quality_score:{new_score}>{current_score}",
                }
            )
            chosen[order_id] = row
        else:
            dropped.append(
                {
                    "order_id": order_id,
                    "kept_order_datetime": str(
                        current.get("order_datetime_order") or current.get("order_datetime") or ""
                    ).strip(),
                    "kept_statement_source_file": str(current.get("statement_source_file", "")).strip(),
                    "dropped_order_datetime": str(
                        row.get("order_datetime_order") or row.get("order_datetime") or ""
                    ).strip(),
                    "dropped_statement_source_file": str(row.get("statement_source_file", "")).strip(),
                    "reason": f"lower_quality_score:{new_score}<={current_score}",
                }
            )

    deduped_rows = list(chosen.values())
    return deduped_rows, dropped


class MenuStarNormalizer(BaseParser):
    platform = "MENUSTAR"
    provider = ""
    total_components_fields: Tuple[str, ...] = (
        "subtotal",
        "tax",
        "tip",
        "delivery_fee",
        "misc_fee",
        "marketing_fee",
    )

    def __init__(
        self,
        orders_raw_path: str = "",
        billings_raw_path: str = "",
        out_path: str = "",
        **kwargs,
    ):
        super().__init__(
            input_path=orders_raw_path, out_path=out_path, billings_raw=billings_raw_path, **kwargs
        )

    def default_input_path(self) -> str:
        return raw_path("menustar", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("menustar_orders_normalized.csv")

    def resolve_paths(self) -> Tuple[str, str]:
        input_path = self.input_path or self.default_input_path()
        out_path = self.out_path or self.default_out_path()
        return input_path, out_path

    def load_inputs(self, input_path: str) -> Dict[str, pd.DataFrame]:
        billings_path = self.extra.get("billings_raw") or raw_path("menustar", "billings_raw.csv")
        adjustments_path = self.extra.get("adjustments_raw") or raw_path(
            "menustar", "adjustments_raw.csv"
        )
        billings_overrides_path = self.extra.get("billings_overrides_raw") or raw_path(
            "menustar", "billings_overrides.csv"
        )
        return {
            "orders_raw": load_raw(input_path),
            "billings_raw": load_raw(billings_path),
            "adjustments_raw": load_adjustments(adjustments_path),
            "billings_overrides_raw": load_billings_overrides(billings_overrides_path),
        }

    def parse_rows(self, inputs: Dict[str, pd.DataFrame]) -> List[Dict[str, str]]:
        min_include_year = int(str(self.extra.get("include_unmatched_min_year") or "0"))
        billings_working = inputs["billings_raw"]
        billings_overrides = inputs.get("billings_overrides_raw", {})
        billings_working, overrides_applied = apply_billings_overrides_df(
            billings_working, billings_overrides
        )
        if overrides_applied:
            print(f"Applied {overrides_applied} MenuStar billing override(s).")
        before_dedupe = len(billings_working)
        billings_working = dedupe_billings_df(billings_working)
        deduped_count = before_dedupe - len(billings_working)
        if deduped_count > 0:
            print(f"Deduped {deduped_count} MenuStar billing row(s) after overrides.")
        rows, unmatched_billings, unmatched_orders = merge_rows(
            inputs["orders_raw"], billings_working
        )
        # Write back matched order_id into billings_raw for audit.
        billings_path = self.extra.get("billings_raw") or raw_path("menustar", "billings_raw.csv")
        if not inputs["billings_raw"].empty:
            billings_df = inputs["billings_raw"].copy()
            billings_for_match, _ = apply_billings_overrides_df(
                billings_df, billings_overrides
            )

            def billing_key(row: Dict[str, str]) -> str:
                return "|".join(
                    [
                        str(row.get("provider", "")).strip(),
                        str(row.get("order_datetime", "")).strip(),
                        str(row.get("order_type", "")).strip(),
                        str(row.get("payment_type", "")).strip(),
                        str(row.get("subtotal", "")).strip(),
                        str(row.get("tax", "")).strip(),
                        str(row.get("delivery_fee", "")).strip(),
                        str(row.get("tip", "")).strip(),
                        str(row.get("total", "")).strip(),
                    ]
                )

            # Keep one preferred billing key per order_id, then project to key->order_id map.
            preferred_row_by_order_id: Dict[str, Dict[str, str]] = {}
            for merged_row in rows:
                order_id = str(merged_row.get("order_id_order", "")).strip()
                if not order_id:
                    continue
                current = preferred_row_by_order_id.get(order_id)
                if current is None:
                    preferred_row_by_order_id[order_id] = merged_row
                    continue
                current_score = merged_row_quality_score(current)
                new_score = merged_row_quality_score(merged_row)
                if new_score > current_score:
                    preferred_row_by_order_id[order_id] = merged_row
                    continue
                if new_score == current_score:
                    current_email = str(current.get("statement_email_date", "")).strip()
                    new_email = str(merged_row.get("statement_email_date", "")).strip()
                    if new_email and (not current_email or new_email > current_email):
                        preferred_row_by_order_id[order_id] = merged_row
            match_map = {
                billing_key(merged_row): order_id
                for order_id, merged_row in preferred_row_by_order_id.items()
            }
            updated = False
            stale_cleared = 0
            assigned = 0
            for idx, row in billings_for_match.iterrows():
                key = billing_key(row)
                match_id = match_map.get(key, "")
                current = str(billings_df.iloc[idx].get("order_id", "") or "").strip()
                if current != match_id:
                    billings_df.at[idx, "order_id"] = match_id
                    updated = True
                    if match_id:
                        assigned += 1
                    elif current:
                        stale_cleared += 1
            if updated:
                billings_df.to_csv(billings_path, index=False)
                if stale_cleared:
                    print(f"Cleared {stale_cleared} stale MenuStar billing order_id assignment(s).")
                if assigned:
                    print(f"Assigned {assigned} MenuStar billing order_id value(s).")
        if unmatched_orders:
            orders_report = [
                {
                    "order_id": row.get("order_id", ""),
                    "provider": row.get("provider", ""),
                    "restaurant_name": row.get("restaurant_name", ""),
                    "order_datetime": row.get("order_datetime", ""),
                    "subtotal": row.get("subtotal", ""),
                    "tax": row.get("tax", ""),
                    "total": row.get("total", ""),
                }
                for row in unmatched_orders
            ]
            orders_report = [
                row
                for row in orders_report
                if any(
                    str(row.get(field, "")).strip() not in ("", "0", "0.00")
                    for field in ("subtotal", "tax", "total")
                )
                and extract_year(row.get("order_datetime", "")) >= min_include_year
            ]
            orders_path = raw_path("menustar", "orders_missing_billings.csv")
            pd.DataFrame(orders_report).to_csv(orders_path, index=False)
            for row in unmatched_orders:
                if extract_year(row.get("order_datetime", "")) < min_include_year:
                    continue
                order_id = str(row.get("order_id", "")).strip()
                manual = inputs.get("adjustments_raw", {}).get(order_id, {}) if order_id else {}
                if manual.get("status") == "cancelled":
                    continue
                rows.append(
                    {
                        "provider": row.get("provider", ""),
                        "restaurant_name": row.get("restaurant_name", ""),
                        "order_datetime": row.get("order_datetime", ""),
                        "order_type": row.get("order_type", ""),
                        "payment_type": row.get("payment_type", ""),
                        "subtotal": row.get("subtotal", ""),
                        "tax": row.get("tax", ""),
                        "delivery_fee": row.get("delivery_fee", ""),
                        "tip": row.get("tip", ""),
                        "total": row.get("total", ""),
                        "order_id_order": order_id,
                        "customer_name_order": row.get("customer_name", ""),
                        "phone_order": row.get("phone", ""),
                        "email_order": row.get("email", ""),
                        "address_order": row.get("address", ""),
                        "item_count_order": row.get("item_count", ""),
                        "items_order": row.get("items", ""),
                        "processing_fee": "",
                        "commission_fee": "",
                        "discount_order": row.get("discount", "") or row.get("marketing_fee", ""),
                        "missing_billing_record_note": "1",
                    }
                )
        if unmatched_billings:
            billings_report = [
                {
                    "provider": row.get("provider", ""),
                    "restaurant_name": row.get("restaurant_name", ""),
                    "order_datetime": row.get("order_datetime", ""),
                    "subtotal": row.get("subtotal", ""),
                    "tax": row.get("tax", ""),
                    "total": row.get("total", ""),
                    "statement_source_file": row.get("statement_source_file", ""),
                }
                for row in unmatched_billings
            ]
            billings_report = [
                row
                for row in billings_report
                if any(
                    str(row.get(field, "")).strip() not in ("", "0", "0.00")
                    for field in ("subtotal", "tax", "total")
                )
                and extract_year(row.get("order_datetime", "")) >= min_include_year
            ]
            billings_path = raw_path("menustar", "billings_missing_orders.csv")
            pd.DataFrame(billings_report).to_csv(billings_path, index=False)
            candidates: List[Dict[str, str]] = []
            candidate_columns = [
                "synthetic_order_id",
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
                "statement_source_file",
                "statement_email_date",
                "include_in_normalized",
            ]
            seen_identity: set[str] = set()
            seen_synthetic_suppress: set[str] = set()
            matched_loose_keys = {
                billing_loose_key(row)
                for row in rows
                if str(row.get("order_id_order", "")).strip() or str(row.get("order_id", "")).strip()
            }
            matched_day_amount_keys = {
                billing_day_amount_key(row)
                for row in rows
                if str(row.get("order_id_order", "")).strip() or str(row.get("order_id", "")).strip()
            }
            for billing_row in unmatched_billings:
                if extract_year(billing_row.get("order_datetime", "")) < min_include_year:
                    continue
                if not has_nonzero_amounts(billing_row):
                    continue
                if billing_loose_key(billing_row) in matched_loose_keys:
                    continue
                if billing_day_amount_key(billing_row) in matched_day_amount_keys:
                    continue
                identity = billing_identity_key(billing_row)
                if identity in seen_identity:
                    continue
                suppress_key = billing_synthetic_suppress_key(billing_row)
                if suppress_key in seen_synthetic_suppress:
                    continue
                seen_identity.add(identity)
                seen_synthetic_suppress.add(suppress_key)
                synthetic_id = synthetic_order_id_for_billing(billing_row)
                manual = inputs.get("adjustments_raw", {}).get(synthetic_id, {})
                cancelled = manual.get("status") == "cancelled"
                candidates.append(
                    {
                        "synthetic_order_id": synthetic_id,
                        "provider": billing_row.get("provider", ""),
                        "restaurant_name": billing_row.get("restaurant_name", ""),
                        "order_datetime": billing_row.get("order_datetime", ""),
                        "order_type": billing_row.get("order_type", ""),
                        "payment_type": billing_row.get("payment_type", ""),
                        "subtotal": billing_row.get("subtotal", ""),
                        "tax": billing_row.get("tax", ""),
                        "delivery_fee": billing_row.get("delivery_fee", ""),
                        "tip": billing_row.get("tip", ""),
                        "total": billing_row.get("total", ""),
                        "statement_source_file": billing_row.get("statement_source_file", ""),
                        "statement_email_date": billing_row.get("statement_email_date", ""),
                        "include_in_normalized": "NO" if cancelled else "YES",
                    }
                )
                if cancelled:
                    continue
                rows.append(
                    {
                        **billing_row,
                        "order_id": synthetic_id,
                        "synthetic_billing_only_note": "1",
                    }
                )
            candidate_path = raw_path("menustar", "billings_missing_orders_candidates.csv")
            pd.DataFrame(candidates).reindex(columns=candidate_columns).to_csv(
                candidate_path, index=False
            )
        rows, duplicate_drops = dedupe_merged_rows_by_order_id(rows)
        if duplicate_drops:
            print(f"Deduped {len(duplicate_drops)} MenuStar merged row(s) by order_id.")
            dropped_path = raw_path("menustar", "normalized_duplicate_order_ids_dropped.csv")
            pd.DataFrame(duplicate_drops).to_csv(dropped_path, index=False)
        normalized_rows = normalize_rows(rows, manual_adjustments=inputs.get("adjustments_raw", {}))
        reconciliation_path = raw_path("menustar", "statement_payout_reconciliation.csv")
        write_statement_payout_reconciliation(rows, normalized_rows, reconciliation_path)
        return normalized_rows


def run(
    orders_raw_path: str,
    billings_raw_path: str,
    adjustments_raw_path: str,
    billings_overrides_raw_path: str,
    out_path: str,
    reset_errors: bool = False,
) -> int:
    parser = MenuStarNormalizer(
        orders_raw_path=orders_raw_path,
        billings_raw_path=billings_raw_path,
        adjustments_raw=adjustments_raw_path,
        billings_overrides_raw=billings_overrides_raw_path,
        out_path=out_path,
        reset_errors=reset_errors,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize MenuStar raw CSVs.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("menustar", "orders_raw.csv"),
        help="Path to MenuStar orders raw CSV.",
    )
    parser.add_argument(
        "--billings-raw",
        default=raw_path("menustar", "billings_raw.csv"),
        help="Path to MenuStar billings raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("menustar_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    parser.add_argument(
        "--adjustments-raw",
        default=raw_path("menustar", "adjustments_raw.csv"),
        help="Path to MenuStar adjustments/cancellations CSV.",
    )
    parser.add_argument(
        "--billings-overrides-raw",
        default=raw_path("menustar", "billings_overrides.csv"),
        help="Path to MenuStar billing overrides CSV.",
    )
    args = parser.parse_args()
    run(
        args.orders_raw,
        args.billings_raw,
        args.adjustments_raw,
        args.billings_overrides_raw,
        args.out,
    )


if __name__ == "__main__":
    main()
