#!/usr/bin/env python3
import argparse
import os
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_datetime, normalize_money
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.schema import build_normalized_row


NUMERIC_SUM_COLUMNS = (
    "Subtotal",
    "Gross Tax",
    "Tax Remitted",
    "Total Commissions",
    "Total Promotions",
    "Total Adjustments",
    "Savings",
)

RECONCILED_SUM_COLUMNS = (
    "nextbite_total_commission_reconciled",
    "nextbite_base_payout_reconciled",
    "nextbite_true_payout_reconciled",
)

SUMMARY_COLS = {
    "count_fulfilled": "Number of Orders Fulfilled",
    "delivery_fulfilled": "Delivery Fulfilled Orders",
    "refunds": "Refunds",
    "gross_sales_tax": "Gross Sales Tax (Collected by DSP)",
    "sales_tax_remitted": "Sales Tax (Remitted by DSP)",
    "total_gross_sales": "Total Gross Sales",
    "total_fp_payout": "Total FP Payout",
    "delivery_contract_rate_payout": "Delivery Contract Rate Payout",
    "pickup_contract_rate_payout": "Pickup Contract Rate Payout",
    "commission_cap_savings": "Commission Cap Savings",
}

# Period-specific count behavior based on statement quirks.
# Modes:
# - unique_countable_order_ids: unique Order ID where tx is Fulfilled/Adjustments (default)
# - fulfilled_rows: count raw rows where tx is Fulfilled Orders
# - all_non_unfulfilled_rows: count all raw rows already filtered to non-unfulfilled
COUNT_MODE_OVERRIDES: Dict[Tuple[str, str], str] = {
    ("doordash", "2022-05-31"): "fulfilled_rows",
    ("doordash", "2023-01-15"): "all_non_unfulfilled_rows",
    ("grubhub", "2022-10-15"): "fulfilled_rows",
    ("grubhub", "2022-11-15"): "fulfilled_rows",
    ("ubereats", "2022-09-15"): "all_non_unfulfilled_rows",
    ("ubereats", "2023-01-31"): "all_non_unfulfilled_rows",
}

# Statement-specific gross/tax treatment overrides.
INCLUDE_UNFULFILLED_IN_GROSS_OVERRIDES: set[Tuple[str, str]] = {
    ("ubereats", "2022-09-15"),
}

REMITTED_EQUALS_GROSS_TAX_OVERRIDES: set[Tuple[str, str]] = {
    ("ubereats", "2022-09-15"),
    ("ubereats", "2023-01-31"),
}


def _to_decimal(value: object) -> Decimal:
    text = normalize_money(str(value) if value is not None else "")
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def _format_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _nonempty(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def _first_nonempty(values: List[str]) -> str:
    for value in values:
        text = _nonempty(value)
        if text:
            return text
    return ""


def _to_date(value: object) -> Optional[date]:
    text = _nonempty(value)
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _normalized_tax_remitted_for_transaction(
    tax_remitted_value: object, transaction_type: object
) -> Decimal:
    value = _to_decimal(tax_remitted_value)
    if value == Decimal("0"):
        return Decimal("0")
    tx = _nonempty(transaction_type).lower()
    if tx == "fulfilled orders":
        return abs(value)
    return -abs(value)


def _primary_source_sheet(value: object) -> str:
    text = _nonempty(value)
    if not text:
        return ""
    return text.split("|")[0].strip().lower()


def _period_bounds(dsp: str, pay_period_ending: date) -> Tuple[date, date]:
    # Nextbite statement quirk: Postmates April 2022 was paid in one batch,
    # so the 2022-04-30 row covers the full month.
    if (
        dsp == "postmates"
        and pay_period_ending.year == 2022
        and pay_period_ending.month == 4
        and pay_period_ending.day == 30
    ):
        start = pay_period_ending.replace(day=1)
        end = pay_period_ending
        return start, end

    # Nextbite statement quirk: UberEats April 2022 refund activity is reflected
    # against the month-end payout row, so 2022-04-30 covers the full month.
    if (
        dsp == "ubereats"
        and pay_period_ending.year == 2022
        and pay_period_ending.month == 4
        and pay_period_ending.day == 30
    ):
        start = pay_period_ending.replace(day=1)
        end = pay_period_ending
        return start, end

    # Nextbite statement quirk: DoorDash June 2022 appears to split as
    # 1-14 and 15-EOM (instead of 1-15 and 16-EOM).
    if (
        dsp == "doordash"
        and pay_period_ending.year == 2022
        and pay_period_ending.month in {5, 6}
    ):
        if pay_period_ending.day == 15:
            start = pay_period_ending.replace(day=1)
            end = pay_period_ending.replace(day=14)
            return start, end
        start = pay_period_ending.replace(day=15)
        end = pay_period_ending
        return start, end

    if pay_period_ending.day == 15:
        start = pay_period_ending.replace(day=1)
        end = pay_period_ending
        return start, end
    start = pay_period_ending.replace(day=16)
    end = pay_period_ending
    return start, end


def _close_enough(a: Decimal, b: Decimal, cents: Decimal = Decimal("0.01")) -> bool:
    return abs(a - b) <= cents


def _is_all_zero_financial_row(row: pd.Series) -> bool:
    check_cols = [
        "Subtotal",
        "Gross Tax",
        "Tax Remitted",
        "Total Commissions",
        "Total Promotions",
        "Total Adjustments",
        "Savings",
        "total_gross_sales",
        "nextbite_total_commission_reconciled",
        "nextbite_base_payout_reconciled",
        "nextbite_true_payout_reconciled",
    ]
    total = Decimal("0")
    for col in check_cols:
        total += abs(_to_decimal(row.get(col, "")))
    return total == Decimal("0")


def _quantize_cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _base_payout_from_subtotal(subtotal: Decimal) -> Decimal:
    # Nextbite allocation rule: apply 55% to positive sales only.
    # Negative subtotal rows (refund-like) carry through at face value.
    if subtotal > Decimal("0"):
        return subtotal * Decimal("0.55")
    return subtotal


def _reconcile_to_target(values: List[Decimal], target: Decimal) -> List[Decimal]:
    if not values:
        return values
    reconciled = [_quantize_cents(v) for v in values]
    target_q = _quantize_cents(target)
    delta = target_q - sum(reconciled, Decimal("0"))
    cents = int((delta * 100).to_integral_value(rounding=ROUND_HALF_UP))
    if cents == 0:
        return reconciled

    # Deterministic distribution: apply residual cents to largest absolute-value rows first.
    order = sorted(range(len(values)), key=lambda i: (abs(values[i]), i), reverse=True)
    if not order:
        return reconciled
    step = Decimal("0.01") if cents > 0 else Decimal("-0.01")
    for idx in range(abs(cents)):
        target_idx = order[idx % len(order)]
        reconciled[target_idx] = _quantize_cents(reconciled[target_idx] + step)
    return reconciled


def _collapse_orders(orders_df: pd.DataFrame) -> pd.DataFrame:
    if orders_df.empty:
        return orders_df
    work = orders_df.fillna("").copy()
    work["Order ID"] = work["Order ID"].astype(str).str.strip()
    work["Transaction Type"] = work["Transaction Type"].astype(str).str.strip()
    work = work[work["Order ID"] != ""].copy()
    work = work[
        ~work["Transaction Type"].astype(str).str.lower().str.contains("unfulfilled", na=False)
    ].copy()
    if work.empty:
        return work

    for col in NUMERIC_SUM_COLUMNS:
        if col not in work.columns:
            work[col] = ""
        if col == "Tax Remitted":
            work[f"__num_{col}"] = work.apply(
                lambda r: _normalized_tax_remitted_for_transaction(
                    r.get("Tax Remitted", ""),
                    r.get("Transaction Type", ""),
                ),
                axis=1,
            )
        else:
            work[f"__num_{col}"] = work[col].astype(str).map(_to_decimal)
    for col in RECONCILED_SUM_COLUMNS:
        if col not in work.columns:
            work[col] = ""
        work[f"__num_{col}"] = work[col].astype(str).map(_to_decimal)

    tx_lower = work["Transaction Type"].astype(str).str.lower().str.strip()
    work["__is_fulfilled"] = tx_lower.isin(["fulfilled orders", "adjustments"])
    work["__is_refund"] = tx_lower.str.contains("refund", na=False)

    group_cols = ["Order ID"]
    if "period_dsp" in work.columns and "pay_period_ending" in work.columns:
        group_cols = ["Order ID", "period_dsp", "pay_period_ending"]

    collapsed_rows: List[Dict[str, str]] = []
    for group_key, group in work.groupby(group_cols, dropna=False, sort=False):
        order_id = group_key[0] if isinstance(group_key, tuple) else group_key
        row: Dict[str, str] = {}
        row["Order ID"] = str(order_id)
        row["Store Name"] = (
            _first_nonempty(group["Store Name"].tolist()) if "Store Name" in group else ""
        )
        row["Date (Reportable)"] = (
            _first_nonempty(group["Date (Reportable)"].tolist())
            if "Date (Reportable)" in group
            else ""
        )
        row["Commission Rate"] = (
            _first_nonempty(group["Commission Rate"].tolist()) if "Commission Rate" in group else ""
        )
        row["email_date"] = _first_nonempty(group["email_date"].tolist()) if "email_date" in group else ""
        row["source_file"] = _first_nonempty(group["source_file"].tolist()) if "source_file" in group else ""
        row["source_member"] = _first_nonempty(group["source_member"].tolist()) if "source_member" in group else ""
        row["period_dsp"] = _first_nonempty(group["period_dsp"].tolist()) if "period_dsp" in group else ""
        row["pay_period_ending"] = _first_nonempty(group["pay_period_ending"].tolist()) if "pay_period_ending" in group else ""
        row["pay_period_start"] = _first_nonempty(group["pay_period_start"].tolist()) if "pay_period_start" in group else ""
        row["pay_period_end"] = _first_nonempty(group["pay_period_end"].tolist()) if "pay_period_end" in group else ""

        tx_types = sorted({_nonempty(v) for v in group["Transaction Type"].tolist() if _nonempty(v)})
        row["Transaction Type"] = " | ".join(tx_types)
        source_sheets = sorted({_nonempty(v) for v in group["source_sheet"].tolist() if _nonempty(v)})
        row["source_sheet"] = " | ".join(source_sheets)

        for col in NUMERIC_SUM_COLUMNS:
            total = sum(group[f"__num_{col}"].tolist(), Decimal("0"))
            row[col] = _format_decimal(total)

        fulfilled_mask = group["__is_fulfilled"]
        refund_mask = group["__is_refund"]

        fulfilled_orders_count = Decimal("1") if bool(fulfilled_mask.any()) else Decimal("0")
        delivery_fulfilled_orders = sum(
            group.loc[fulfilled_mask, "__num_Subtotal"].tolist(), Decimal("0")
        )
        refunds = sum(group.loc[refund_mask, "__num_Subtotal"].tolist(), Decimal("0"))
        gross_sales_tax = sum(group["__num_Gross Tax"].tolist(), Decimal("0"))
        sales_tax_remitted = sum(group["__num_Tax Remitted"].tolist(), Decimal("0"))
        total_gross_sales = sum(group["__num_Subtotal"].tolist(), Decimal("0"))

        row["fulfilled_order_count"] = str(int(fulfilled_orders_count))
        row["delivery_fulfilled_orders"] = _format_decimal(delivery_fulfilled_orders)
        row["refunds"] = _format_decimal(refunds)
        row["gross_sales_tax_collected"] = _format_decimal(gross_sales_tax)
        row["sales_tax_remitted"] = _format_decimal(sales_tax_remitted)
        row["total_gross_sales"] = _format_decimal(total_gross_sales)

        nextbite_total_commission = total_gross_sales * Decimal("0.45")
        nextbite_base_payout = total_gross_sales * Decimal("0.55")
        savings = _to_decimal(row.get("Savings", ""))
        nextbite_true_payout = nextbite_base_payout + savings

        row["nextbite_total_commission"] = _format_decimal(nextbite_total_commission)
        row["nextbite_base_payout"] = _format_decimal(nextbite_base_payout)
        row["nextbite_true_payout"] = _format_decimal(nextbite_true_payout)
        row["nextbite_total_commission_reconciled"] = _format_decimal(
            sum(group["__num_nextbite_total_commission_reconciled"].tolist(), Decimal("0"))
        )
        row["nextbite_base_payout_reconciled"] = _format_decimal(
            sum(group["__num_nextbite_base_payout_reconciled"].tolist(), Decimal("0"))
        )
        row["nextbite_true_payout_reconciled"] = _format_decimal(
            sum(group["__num_nextbite_true_payout_reconciled"].tolist(), Decimal("0"))
        )

        row["collapsed_records"] = str(len(group))
        collapsed_rows.append(row)

    return pd.DataFrame(collapsed_rows)


def _apply_reconciled_true_payouts(
    assigned_df: pd.DataFrame, periods: List[Dict[str, object]]
) -> pd.DataFrame:
    if assigned_df.empty:
        return assigned_df
    out = assigned_df.copy()
    period_map: Dict[Tuple[str, str], Dict[str, object]] = {
        (str(p["dsp"]), str(p["pay_period_ending"])): p for p in periods
    }

    out["nextbite_total_commission_reconciled"] = ""
    out["nextbite_base_payout_reconciled"] = ""
    out["nextbite_true_payout_reconciled"] = ""

    grouped = out.groupby(["period_dsp", "pay_period_ending"], dropna=False, sort=False)
    for (dsp, ppe), idxs in grouped.groups.items():
        dsp_text = _nonempty(dsp)
        ppe_text = _nonempty(ppe)
        if not dsp_text or not ppe_text:
            for idx in idxs:
                subtotal = _to_decimal(out.at[idx, "__num_subtotal"])
                savings = _to_decimal(out.at[idx, "__num_savings"])
                base = _base_payout_from_subtotal(subtotal)
                comm = subtotal * Decimal("0.45")
                true = base + savings
                out.at[idx, "nextbite_total_commission_reconciled"] = _format_decimal(comm)
                out.at[idx, "nextbite_base_payout_reconciled"] = _format_decimal(base)
                out.at[idx, "nextbite_true_payout_reconciled"] = _format_decimal(true)
            continue

        period = period_map.get((dsp_text, ppe_text))
        if not period:
            for idx in idxs:
                subtotal = _to_decimal(out.at[idx, "__num_subtotal"])
                savings = _to_decimal(out.at[idx, "__num_savings"])
                base = _base_payout_from_subtotal(subtotal)
                comm = subtotal * Decimal("0.45")
                true = base + savings
                out.at[idx, "nextbite_total_commission_reconciled"] = _format_decimal(comm)
                out.at[idx, "nextbite_base_payout_reconciled"] = _format_decimal(base)
                out.at[idx, "nextbite_true_payout_reconciled"] = _format_decimal(true)
            continue

        row_idxs = list(idxs)
        eligible_row_idxs = [
            i for i in row_idxs if not bool(out.at[i, "__is_unfulfilled"])
        ]
        commission_row_idxs = [
            i
            for i in eligible_row_idxs
            if (not bool(out.at[i, "__is_refund"]))
            and (_to_decimal(out.at[i, "__num_total_commissions"]) != Decimal("0"))
        ]
        ineligible_row_idxs = [i for i in row_idxs if i not in eligible_row_idxs]
        for idx in ineligible_row_idxs:
            out.at[idx, "nextbite_total_commission_reconciled"] = "0.00"
            out.at[idx, "nextbite_base_payout_reconciled"] = "0.00"
            out.at[idx, "nextbite_true_payout_reconciled"] = "0.00"
        if not eligible_row_idxs:
            continue
        row_gross = [_to_decimal(out.at[i, "__num_subtotal"]) for i in eligible_row_idxs]
        row_savings = [_to_decimal(out.at[i, "__num_savings"]) for i in eligible_row_idxs]
        base_raw = [_base_payout_from_subtotal(g) for g in row_gross]
        commission_gross = [_to_decimal(out.at[i, "__num_subtotal"]) for i in commission_row_idxs]
        comm_raw = [g * Decimal("0.45") for g in commission_gross]

        target_gross = _to_decimal(period.get("total_gross_sales", "0"))
        target_base = _to_decimal(period.get("delivery_contract_rate_payout", "0")) + _to_decimal(
            period.get("pickup_contract_rate_payout", "0")
        )
        if target_base == Decimal("0") and target_gross != Decimal("0"):
            target_base = target_gross * Decimal("0.55")
        target_true = _to_decimal(period.get("total_fp_payout", "0"))
        target_comm = target_gross - target_base

        # Lock negative-subtotal rows at their base value; distribute residual
        # only across non-negative rows.
        fixed_positions = [i for i, subtotal in enumerate(row_gross) if subtotal < Decimal("0")]
        variable_positions = [i for i in range(len(row_gross)) if i not in fixed_positions]
        base_reconciled = [Decimal("0")] * len(row_gross)
        fixed_base_sum = Decimal("0")
        for i in fixed_positions:
            fixed_base = _quantize_cents(base_raw[i])
            base_reconciled[i] = fixed_base
            fixed_base_sum += fixed_base
        if variable_positions:
            variable_base_raw = [base_raw[i] for i in variable_positions]
            variable_base_target = target_base - fixed_base_sum
            variable_base_reconciled = _reconcile_to_target(
                variable_base_raw, variable_base_target
            )
            for j, i in enumerate(variable_positions):
                base_reconciled[i] = variable_base_reconciled[j]
        comm_reconciled = (
            _reconcile_to_target(comm_raw, target_comm) if commission_row_idxs else []
        )
        true_reconciled = [Decimal("0")] * len(row_gross)
        fixed_true_sum = Decimal("0")
        for i in fixed_positions:
            fixed_true = _quantize_cents(base_reconciled[i] + row_savings[i])
            true_reconciled[i] = fixed_true
            fixed_true_sum += fixed_true
        if variable_positions:
            variable_true_raw = [base_reconciled[i] + row_savings[i] for i in variable_positions]
            variable_true_target = target_true - fixed_true_sum
            variable_true_reconciled = _reconcile_to_target(
                variable_true_raw, variable_true_target
            )
            for j, i in enumerate(variable_positions):
                true_reconciled[i] = variable_true_reconciled[j]

        for idx in eligible_row_idxs:
            out.at[idx, "nextbite_total_commission_reconciled"] = "0.00"
        for i, idx in enumerate(eligible_row_idxs):
            out.at[idx, "nextbite_base_payout_reconciled"] = _format_decimal(base_reconciled[i])
            out.at[idx, "nextbite_true_payout_reconciled"] = _format_decimal(true_reconciled[i])
        for i, idx in enumerate(commission_row_idxs):
            out.at[idx, "nextbite_total_commission_reconciled"] = _format_decimal(comm_reconciled[i])

    return out


def _build_summary_periods(summary_df: pd.DataFrame) -> List[Dict[str, object]]:
    if summary_df.empty:
        return []
    work = summary_df.fillna("").copy()
    periods: List[Dict[str, object]] = []
    for _, row in work.iterrows():
        pay_period_ending_text = _nonempty(row.get("Pay Period Ending", ""))
        pay_period_ending = _to_date(pay_period_ending_text)
        if pay_period_ending is None:
            continue

        dsp = _nonempty(row.get("source_sheet", "")) or _nonempty(row.get("DSP", ""))
        dsp = dsp.lower().strip()
        if not dsp:
            continue

        start, end = _period_bounds(dsp, pay_period_ending)

        period: Dict[str, object] = {
            "dsp": dsp,
            "pay_period_ending": pay_period_ending,
            "window_start": start,
            "window_end": end,
            "count_fulfilled": int(float(_nonempty(row.get(SUMMARY_COLS["count_fulfilled"], "0")) or "0")),
            "delivery_fulfilled": _to_decimal(row.get(SUMMARY_COLS["delivery_fulfilled"], "")),
            "refunds": _to_decimal(row.get(SUMMARY_COLS["refunds"], "")),
            "gross_sales_tax": _to_decimal(row.get(SUMMARY_COLS["gross_sales_tax"], "")),
            "sales_tax_remitted": _to_decimal(row.get(SUMMARY_COLS["sales_tax_remitted"], "")),
            "total_gross_sales": _to_decimal(row.get(SUMMARY_COLS["total_gross_sales"], "")),
            "total_fp_payout": _to_decimal(row.get(SUMMARY_COLS["total_fp_payout"], "")),
            "delivery_contract_rate_payout": _to_decimal(
                row.get(SUMMARY_COLS["delivery_contract_rate_payout"], "")
            ),
            "pickup_contract_rate_payout": _to_decimal(
                row.get(SUMMARY_COLS["pickup_contract_rate_payout"], "")
            ),
            "commission_cap_savings": _to_decimal(
                row.get(SUMMARY_COLS["commission_cap_savings"], "")
            ),
        }
        periods.append(period)
    return periods


def _assign_pay_periods(
    frame: pd.DataFrame,
    periods: List[Dict[str, object]],
    *,
    date_col: str,
    dsp_col: str,
    split_source: bool,
) -> pd.DataFrame:
    if frame.empty:
        return frame

    assigned = frame.copy()
    period_index: Dict[str, List[Dict[str, object]]] = {}
    for period in periods:
        dsp = str(period["dsp"])
        period_index.setdefault(dsp, []).append(period)
    for dsp in period_index:
        period_index[dsp] = sorted(period_index[dsp], key=lambda x: x["window_end"])

    pay_period_ending_vals: List[str] = []
    pay_period_start_vals: List[str] = []
    pay_period_end_vals: List[str] = []
    dsp_vals: List[str] = []

    for _, row in assigned.iterrows():
        order_date = _to_date(row.get(date_col, ""))
        raw_dsp = row.get(dsp_col, "")
        dsp = _primary_source_sheet(raw_dsp) if split_source else _nonempty(raw_dsp).lower().strip()
        matched: Optional[Dict[str, object]] = None

        if order_date and dsp and dsp in period_index:
            for period in period_index[dsp]:
                start = period["window_start"]
                end = period["window_end"]
                if start <= order_date <= end:
                    matched = period
                    break

        if matched is None:
            pay_period_ending_vals.append("")
            pay_period_start_vals.append("")
            pay_period_end_vals.append("")
            dsp_vals.append(dsp)
        else:
            pay_period_ending_vals.append(str(matched["pay_period_ending"]))
            pay_period_start_vals.append(str(matched["window_start"]))
            pay_period_end_vals.append(str(matched["window_end"]))
            dsp_vals.append(str(matched["dsp"]))

    assigned["period_dsp"] = dsp_vals
    assigned["pay_period_ending"] = pay_period_ending_vals
    assigned["pay_period_start"] = pay_period_start_vals
    assigned["pay_period_end"] = pay_period_end_vals
    return assigned


def _prepare_orders_for_period_comparison(orders_df: pd.DataFrame) -> pd.DataFrame:
    if orders_df.empty:
        return orders_df
    work = orders_df.fillna("").copy()
    work["Order ID"] = work["Order ID"].astype(str).str.strip()
    work["Transaction Type"] = work["Transaction Type"].astype(str).str.strip()
    work = work[work["Order ID"] != ""].copy()
    if work.empty:
        return work

    tx_lower = work["Transaction Type"].astype(str).str.lower().str.strip()
    work["__is_unfulfilled"] = tx_lower.str.contains("unfulfilled", na=False)
    work["__is_count_fulfilled"] = tx_lower.isin(["fulfilled orders", "adjustments"])
    work["__is_refund"] = tx_lower.str.contains("refund", na=False)
    work["__num_subtotal"] = work["Subtotal"].astype(str).map(_to_decimal)
    work["__num_gross_tax"] = work["Gross Tax"].astype(str).map(_to_decimal)
    work["__num_tax_remitted"] = work.apply(
        lambda r: _normalized_tax_remitted_for_transaction(
            r.get("Tax Remitted", ""),
            r.get("Transaction Type", ""),
        ),
        axis=1,
    )
    work["__num_savings"] = work["Savings"].astype(str).map(_to_decimal)
    work["__num_total_commissions"] = work["Total Commissions"].astype(str).map(_to_decimal)
    work["__nextbite_total_commission"] = work["__num_subtotal"] * Decimal("0.45")
    work["__nextbite_base_payout"] = work["__num_subtotal"] * Decimal("0.55")
    work["__nextbite_true_payout"] = work["__nextbite_base_payout"] + work["__num_savings"]
    work["nextbite_total_commission_reconciled"] = ""
    work["nextbite_base_payout_reconciled"] = ""
    work["nextbite_true_payout_reconciled"] = ""
    return work


def _orders_period_aggregates(assigned_df: pd.DataFrame) -> Dict[Tuple[str, str], Dict[str, object]]:
    if assigned_df.empty:
        return {}
    work = assigned_df.fillna("").copy()
    work = work[(work["period_dsp"] != "") & (work["pay_period_ending"] != "")].copy()
    if work.empty:
        return {}

    out: Dict[Tuple[str, str], Dict[str, object]] = {}
    for (dsp, pay_period_ending), group in work.groupby(["period_dsp", "pay_period_ending"], sort=True):
        key = (str(dsp), str(pay_period_ending))
        mode = COUNT_MODE_OVERRIDES.get(key, "unique_countable_order_ids")
        non_unfulfilled_mask = ~group["__is_unfulfilled"].astype(bool)
        if mode == "fulfilled_rows":
            count_fulfilled = int(
                (
                    non_unfulfilled_mask
                    & (group["Transaction Type"].astype(str).str.lower().str.strip() == "fulfilled orders")
                ).sum()
            )
        elif mode == "all_non_unfulfilled_rows":
            count_fulfilled = int(non_unfulfilled_mask.sum())
        else:
            count_fulfilled = int(
                group.loc[
                    non_unfulfilled_mask & group["__is_count_fulfilled"].astype(bool),
                    "Order ID",
                ]
                .astype(str)
                .str.strip()
                .nunique()
            )
        include_unfulfilled_in_gross = key in INCLUDE_UNFULFILLED_IN_GROSS_OVERRIDES
        gross_scope_mask = (
            pd.Series([True] * len(group), index=group.index)
            if include_unfulfilled_in_gross
            else non_unfulfilled_mask
        )
        non_refund_gross_scope_mask = gross_scope_mask & (~group["__is_refund"].astype(bool))
        agg: Dict[str, object] = {
            "orders_in_period": len(group),
            "count_fulfilled": count_fulfilled,
            "delivery_fulfilled": sum(
                group.loc[
                    non_unfulfilled_mask & group["__is_count_fulfilled"].astype(bool),
                    "__num_subtotal",
                ].tolist(),
                Decimal("0"),
            ),
            "refunds": sum(
                group.loc[
                    non_unfulfilled_mask & group["__is_refund"].astype(bool),
                    "__num_subtotal",
                ].tolist(),
                Decimal("0"),
            ),
            "gross_sales_tax": sum(
                group.loc[non_refund_gross_scope_mask, "__num_gross_tax"].tolist(),
                Decimal("0"),
            ),
            "sales_tax_remitted": Decimal("0"),
            # Statement "Total Gross Sales" is treated as gross-before-refunds.
            "total_gross_sales": sum(
                group.loc[non_refund_gross_scope_mask, "__num_subtotal"].tolist(),
                Decimal("0"),
            ),
            "commission_cap_savings": sum(group["__num_savings"].tolist(), Decimal("0")),
            "total_fp_payout": sum(
                (
                    group["nextbite_true_payout_reconciled"].astype(str).map(_to_decimal).tolist()
                    if "nextbite_true_payout_reconciled" in group.columns
                    else group["__nextbite_true_payout"].tolist()
                ),
                Decimal("0"),
            ),
            "nextbite_total_commission": sum(
                (
                    group["nextbite_total_commission_reconciled"]
                    .astype(str)
                    .map(_to_decimal)
                    .tolist()
                    if "nextbite_total_commission_reconciled" in group.columns
                    else group["__nextbite_total_commission"].tolist()
                ),
                Decimal("0"),
            ),
            "nextbite_base_payout": sum(
                (
                    group["nextbite_base_payout_reconciled"]
                    .astype(str)
                    .map(_to_decimal)
                    .tolist()
                    if "nextbite_base_payout_reconciled" in group.columns
                    else group["__nextbite_base_payout"].tolist()
                ),
                Decimal("0"),
            ),
        }
        if key in REMITTED_EQUALS_GROSS_TAX_OVERRIDES:
            agg["sales_tax_remitted"] = agg["gross_sales_tax"]
        else:
            agg["sales_tax_remitted"] = sum(
                group.loc[non_refund_gross_scope_mask, "__num_tax_remitted"].tolist(),
                Decimal("0"),
            )
        out[(str(dsp), str(pay_period_ending))] = agg
    return out


def _write_period_comparison(
    comparison_out_path: str,
    assigned_df: pd.DataFrame,
    periods: List[Dict[str, object]],
) -> None:
    orders_agg = _orders_period_aggregates(assigned_df)
    summary_map: Dict[Tuple[str, str], Dict[str, object]] = {}
    for period in periods:
        key = (str(period["dsp"]), str(period["pay_period_ending"]))
        summary_map[key] = period

    keys = sorted(set(summary_map.keys()) | set(orders_agg.keys()))
    rows: List[Dict[str, str]] = []
    for key in keys:
        dsp, pay_period_ending = key
        summary = summary_map.get(key)
        orders = orders_agg.get(key, {})

        def s_dec(name: str) -> Decimal:
            if not summary:
                return Decimal("0")
            return summary.get(name, Decimal("0"))  # type: ignore[return-value]

        def o_dec(name: str) -> Decimal:
            return orders.get(name, Decimal("0"))  # type: ignore[return-value]

        def metric_row(name: str, o_value: Decimal, s_value: Decimal) -> Tuple[str, str, str]:
            delta = o_value - s_value
            return _format_decimal(o_value), _format_decimal(s_value), _format_decimal(delta)

        orders_count = int(orders.get("count_fulfilled", 0))
        summary_count = int(summary.get("count_fulfilled", 0)) if summary else 0
        count_match = orders_count == summary_count

        delivery_orders, delivery_summary, delivery_delta = metric_row(
            "delivery_fulfilled",
            o_dec("delivery_fulfilled"),
            s_dec("delivery_fulfilled"),
        )
        refunds_orders, refunds_summary, refunds_delta = metric_row(
            "refunds",
            o_dec("refunds"),
            s_dec("refunds"),
        )
        tax_orders, tax_summary, tax_delta = metric_row(
            "gross_sales_tax",
            o_dec("gross_sales_tax"),
            s_dec("gross_sales_tax"),
        )
        remitted_orders, remitted_summary, remitted_delta = metric_row(
            "sales_tax_remitted",
            o_dec("sales_tax_remitted"),
            s_dec("sales_tax_remitted"),
        )
        gross_orders, gross_summary, gross_delta = metric_row(
            "total_gross_sales",
            o_dec("total_gross_sales"),
            s_dec("total_gross_sales"),
        )
        savings_orders, savings_summary, savings_delta = metric_row(
            "commission_cap_savings",
            o_dec("commission_cap_savings"),
            s_dec("commission_cap_savings"),
        )
        payout_orders, payout_summary, payout_delta = metric_row(
            "total_fp_payout",
            o_dec("total_fp_payout"),
            s_dec("total_fp_payout"),
        )

        delivery_match = _close_enough(o_dec("delivery_fulfilled"), s_dec("delivery_fulfilled"))
        refunds_match = _close_enough(o_dec("refunds"), s_dec("refunds"))
        tax_match = _close_enough(o_dec("gross_sales_tax"), s_dec("gross_sales_tax"))
        remitted_match = _close_enough(o_dec("sales_tax_remitted"), s_dec("sales_tax_remitted"))
        gross_match = _close_enough(o_dec("total_gross_sales"), s_dec("total_gross_sales"))
        savings_match = _close_enough(o_dec("commission_cap_savings"), s_dec("commission_cap_savings"))
        payout_match = _close_enough(o_dec("total_fp_payout"), s_dec("total_fp_payout"))

        summary_55 = s_dec("total_gross_sales") * Decimal("0.55")
        summary_55_plus_savings = summary_55 + s_dec("commission_cap_savings")
        summary_formula_delta = s_dec("total_fp_payout") - summary_55_plus_savings

        row = {
            "dsp": dsp,
            "pay_period_ending": pay_period_ending,
            "pay_period_start": str(summary["window_start"]) if summary else "",
            "pay_period_end": str(summary["window_end"]) if summary else "",
            "orders_in_period": str(orders.get("orders_in_period", 0)),
            "orders_count_fulfilled": str(orders_count),
            "summary_count_fulfilled": str(summary_count),
            "delta_count_fulfilled": str(orders_count - summary_count),
            "match_count_fulfilled": str(count_match),
            "orders_delivery_fulfilled": delivery_orders,
            "summary_delivery_fulfilled": delivery_summary,
            "delta_delivery_fulfilled": delivery_delta,
            "match_delivery_fulfilled": str(delivery_match),
            "orders_refunds": refunds_orders,
            "summary_refunds": refunds_summary,
            "delta_refunds": refunds_delta,
            "match_refunds": str(refunds_match),
            "orders_gross_sales_tax": tax_orders,
            "summary_gross_sales_tax": tax_summary,
            "delta_gross_sales_tax": tax_delta,
            "match_gross_sales_tax": str(tax_match),
            "orders_sales_tax_remitted": remitted_orders,
            "summary_sales_tax_remitted": remitted_summary,
            "delta_sales_tax_remitted": remitted_delta,
            "match_sales_tax_remitted": str(remitted_match),
            "orders_total_gross_sales": gross_orders,
            "summary_total_gross_sales": gross_summary,
            "delta_total_gross_sales": gross_delta,
            "match_total_gross_sales": str(gross_match),
            "orders_savings": savings_orders,
            "summary_commission_cap_savings": savings_summary,
            "delta_savings": savings_delta,
            "match_savings": str(savings_match),
            "orders_total_fp_payout": payout_orders,
            "summary_total_fp_payout": payout_summary,
            "delta_total_fp_payout": payout_delta,
            "match_total_fp_payout": str(payout_match),
            "orders_nextbite_total_commission": _format_decimal(o_dec("nextbite_total_commission")),
            "orders_nextbite_base_payout": _format_decimal(o_dec("nextbite_base_payout")),
            "summary_delivery_contract_rate_payout": _format_decimal(
                s_dec("delivery_contract_rate_payout")
            ),
            "summary_pickup_contract_rate_payout": _format_decimal(
                s_dec("pickup_contract_rate_payout")
            ),
            "summary_55pct_of_total_gross_sales": _format_decimal(summary_55),
            "summary_55pct_plus_savings": _format_decimal(summary_55_plus_savings),
            "delta_summary_fp_vs_55pct_plus_savings": _format_decimal(summary_formula_delta),
            "all_key_metrics_match": str(
                all(
                    [
                        count_match,
                        delivery_match,
                        refunds_match,
                        tax_match,
                        remitted_match,
                        gross_match,
                        savings_match,
                    ]
                )
            ),
        }
        rows.append(row)

    os.makedirs(os.path.dirname(comparison_out_path), exist_ok=True)
    pd.DataFrame(rows).to_csv(comparison_out_path, index=False)


class NextbiteOrdersParser(BaseParser):
    platform = "NEXTBITE"
    dedupe_key = "order_id"
    provider = "AMECI"
    total_components_fields = (
        "subtotal",
        "tax",
        "tip",
        "delivery_fee",
    )

    def __init__(
        self,
        input_path: Optional[str] = None,
        out_path: Optional[str] = None,
        summary_raw_path: Optional[str] = None,
        comparison_out_path: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(input_path=input_path, out_path=out_path, **kwargs)
        self.summary_raw_path = summary_raw_path or raw_path("nextbite", "billings_raw.csv")
        self.comparison_out_path = comparison_out_path or raw_path(
            "nextbite", "pay_period_comparison.csv"
        )

    def default_input_path(self) -> str:
        return raw_path("nextbite", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("nextbite_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        if not os.path.exists(input_path):
            return pd.DataFrame()
        return pd.read_csv(input_path, dtype=str).fillna("")

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        df = inputs.copy()

        summary_df = pd.DataFrame()
        if self.summary_raw_path and os.path.exists(self.summary_raw_path):
            summary_df = pd.read_csv(self.summary_raw_path, dtype=str).fillna("")

        periods = _build_summary_periods(summary_df)
        compare_orders = _prepare_orders_for_period_comparison(df)
        compare_orders = _assign_pay_periods(
            compare_orders,
            periods,
            date_col="Date (Reportable)",
            dsp_col="source_sheet",
            split_source=False,
        )
        compare_orders = _apply_reconciled_true_payouts(compare_orders, periods)

        per_record_path = raw_path("nextbite", "orders_with_reconciled_payouts_raw.csv")
        os.makedirs(os.path.dirname(per_record_path), exist_ok=True)
        compare_orders.to_csv(per_record_path, index=False)

        collapsed = _collapse_orders(compare_orders)
        if not collapsed.empty:
            collapsed = collapsed[
                ~collapsed.apply(_is_all_zero_financial_row, axis=1)
            ].copy()

        collapsed_path = raw_path("nextbite", "orders_collapsed_raw.csv")
        os.makedirs(os.path.dirname(collapsed_path), exist_ok=True)
        collapsed.to_csv(collapsed_path, index=False)

        if self.comparison_out_path:
            _write_period_comparison(self.comparison_out_path, compare_orders, periods)

        rows: List[Dict[str, str]] = []
        collapsed_id_counts = (
            collapsed["Order ID"].astype(str).str.strip().value_counts().to_dict()
            if not collapsed.empty and "Order ID" in collapsed.columns
            else {}
        )
        for _, row in collapsed.iterrows():
            base_order_id = _nonempty(row.get("Order ID", ""))
            if not base_order_id:
                continue
            order_id = base_order_id
            if collapsed_id_counts.get(base_order_id, 0) > 1:
                period_dsp = _nonempty(row.get("period_dsp", "")).upper() or "UNK"
                period_end = _nonempty(row.get("pay_period_ending", "")).replace("-", "") or "UNK"
                order_id = f"{base_order_id}__{period_dsp}_{period_end}"

            subtotal = normalize_money(row.get("Subtotal", ""))
            tax_remitted = _to_decimal(row.get("Tax Remitted", ""))
            gross_tax = _to_decimal(row.get("Gross Tax", ""))
            if tax_remitted != Decimal("0"):
                # For Nextbite normalized output, keep tax and tax_withheld mutually exclusive.
                tax = "0.00"
                tax_withheld = _format_decimal(tax_remitted)
            else:
                tax = _format_decimal(gross_tax)
                tax_withheld = "0.00"

            commission_raw = _to_decimal(
                _nonempty(row.get("nextbite_total_commission_reconciled", ""))
                or _nonempty(row.get("Total Commissions", ""))
            )
            commission_fee = _format_decimal(-abs(commission_raw))
            marketing_fee = normalize_money(row.get("Total Promotions", ""))
            total_adjustments = _to_decimal(row.get("Total Adjustments", ""))
            savings = _to_decimal(row.get("Savings", ""))
            adjustments_dec = total_adjustments + savings
            adjustments = _format_decimal(adjustments_dec) if adjustments_dec != Decimal("0") else "0.00"

            subtotal_dec = _to_decimal(subtotal)
            tax_dec = _to_decimal(tax)
            total_dec = subtotal_dec + tax_dec
            total = _format_decimal(total_dec)

            notes: List[str] = []
            commission_rate = normalize_money(row.get("Commission Rate", ""))
            if commission_rate:
                notes.append(f"commission_rate={commission_rate}")
            if marketing_fee and marketing_fee not in {"0", "0.00"}:
                notes.append(f"promotion={marketing_fee}")
            if total_adjustments != Decimal("0"):
                notes.append(f"adjustment={_format_decimal(total_adjustments)}")
            if savings != Decimal("0"):
                notes.append(f"savings={_format_decimal(savings)}")
            source_sheet = _nonempty(row.get("source_sheet", ""))
            if source_sheet:
                notes.append(f"platform={source_sheet}")
            if order_id != base_order_id:
                notes.append(f"original_order_id={base_order_id}")
            collapsed_count = _nonempty(row.get("collapsed_records", ""))
            if collapsed_count and collapsed_count != "1":
                notes.append(f"collapsed_records={collapsed_count}")

            payout_value = normalize_money(
                _nonempty(row.get("nextbite_true_payout_reconciled", "0.00"))
            )
            # Flag cases where statement payout appears to exclude collected tax.
            payout_dec = _to_decimal(payout_value)
            commission_dec = _to_decimal(commission_fee)
            marketing_dec = _to_decimal(marketing_fee)
            expected_dec = subtotal_dec + tax_dec + commission_dec + adjustments_dec + marketing_dec
            if (
                tax_dec > Decimal("0")
                and abs((expected_dec - payout_dec) - tax_dec) <= Decimal("0.01")
            ):
                notes.append(f"tax_not_paid_in_payout={_format_decimal(tax_dec)}")
            rows.append(
                build_normalized_row(
                    Platforms.NEXTBITE.upper(),
                    order_id=order_id,
                    provider="AMECI",
                    restaurant_name=_nonempty(row.get("Store Name", "")),
                    order_datetime=normalize_datetime(_nonempty(row.get("Date (Reportable)", ""))),
                    order_type=OrderTypes.PICKUP,
                    payment_type=PaymentTypes.CREDIT,
                    subtotal=subtotal,
                    tax=tax,
                    tax_withheld=tax_withheld,
                    tip="0.00",
                    delivery_fee="0.00",
                    total=total,
                    processing_fee="0.00",
                    commission_fee=commission_fee,
                    marketing_fee=marketing_fee,
                    adjustments=adjustments,
                    payout=payout_value,
                    notes=" | ".join(notes),
                    errors="",
                )
            )
        return rows


def run(
    orders_raw_path: str,
    out_path: str,
    reset_errors: bool = False,
    summary_raw_path: Optional[str] = None,
    comparison_out_path: Optional[str] = None,
) -> int:
    parser = NextbiteOrdersParser(
        input_path=orders_raw_path,
        out_path=out_path,
        summary_raw_path=summary_raw_path,
        comparison_out_path=comparison_out_path,
        reset_errors=reset_errors,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Nextbite orders raw CSV.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("nextbite", "orders_raw.csv"),
        help="Path to Nextbite orders_raw.csv",
    )
    parser.add_argument(
        "--summary-raw",
        default=raw_path("nextbite", "billings_raw.csv"),
        help="Path to Nextbite summary billings_raw.csv",
    )
    parser.add_argument(
        "--comparison-out",
        default=raw_path("nextbite", "pay_period_comparison.csv"),
        help="Output comparison CSV path.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("nextbite_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(
        args.orders_raw,
        args.out,
        summary_raw_path=args.summary_raw,
        comparison_out_path=args.comparison_out,
    )


if __name__ == "__main__":
    main()
