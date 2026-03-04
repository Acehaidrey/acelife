#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
import re
from typing import Dict, List, Tuple

import pandas as pd

from orders_analytics.utils.constants import raw_path, wave_aroma_path
from orders_analytics.utils.normalize import normalize_money


def _money(value: object) -> str:
    if value is None:
        return ""
    return normalize_money(str(value))


def _to_float(value: str) -> float:
    text = _money(value)
    if not text:
        return 0.0
    try:
        num = float(text)
        if math.isnan(num) or math.isinf(num):
            return 0.0
        return num
    except ValueError:
        return 0.0


def _signed_row_amount(row: pd.Series) -> float:
    amount = _to_float(row.get("Amount (One column)", ""))
    if amount != 0:
        return amount
    debit = _to_float(row.get("Debit Amount (Two Column Approach)", ""))
    credit = _to_float(row.get("Credit Amount (Two Column Approach)", ""))
    if debit != 0 or credit != 0:
        return debit - credit
    return 0.0


def _build_address(row: pd.Series) -> str:
    parts = [
        str(row.get("address_line_1", "")).strip(),
        str(row.get("address_line_2", "")).strip(),
        str(row.get("city", "")).strip(),
        str(row.get("province/state", "")).strip(),
        str(row.get("postal_code/zip_code", "")).strip(),
        str(row.get("country", "")).strip(),
    ]
    return ", ".join([p for p in parts if p])


def _extract_item_label(transaction_description: str, line_description: str) -> str:
    tx = str(transaction_description or "").strip()
    line = str(line_description or "").strip()
    if not line:
        return ""
    prefix = f"{tx} - "
    if tx and line.lower().startswith(prefix.lower()):
        return line[len(prefix) :].strip()
    return line


def _extract_notes_totals(notes: str) -> Dict[str, float]:
    text = str(notes or "")
    out: Dict[str, float] = {}

    def _grab(label: str) -> float:
        pattern = rf"(?im)^\s*{label}\s*\$?\s*([0-9,]+(?:\.[0-9]+)?)\s*$"
        match = re.search(pattern, text)
        if not match:
            return 0.0
        return _to_float(match.group(1))

    out["subtotal"] = _grab("Subtotal")
    out["delivery_fee"] = _grab("Delivery Fee")
    out["tax"] = _grab("Tax")
    out["total"] = _grab("Total")
    return out


def _is_invoice_payment_row(df: pd.DataFrame) -> pd.Series:
    tx_desc = df.get("Transaction Description", "").astype(str)
    line_desc = df.get("Transaction Line Description", "").astype(str)
    pattern = r"(?:invoice\s*payment|payment\s*for\s*invoice|payment.*invoice|invoice.*payment)"
    return tx_desc.str.contains(pattern, case=False, na=False, regex=True) | line_desc.str.contains(
        pattern, case=False, na=False, regex=True
    )


def _load_customers(customers_csv: str) -> Dict[str, Dict[str, str]]:
    if not os.path.exists(customers_csv):
        return {}
    customers = pd.read_csv(customers_csv, dtype=str).fillna("")
    out: Dict[str, Dict[str, str]] = {}
    for _, row in customers.iterrows():
        company_name = str(row.get("customer_name", "")).strip()
        if not company_name:
            continue
        contact_first = str(row.get("contact_first_name", "")).strip()
        contact_last = str(row.get("contact_last_name", "")).strip()
        contact_name = " ".join([p for p in [contact_first, contact_last] if p]).strip()
        out[company_name.lower()] = {
            "company_name": company_name,
            "customer_name": contact_name,
            "email": str(row.get("email", "")).strip(),
            "phone": str(row.get("phone", "")).strip() or str(row.get("mobile", "")).strip(),
            "address": _build_address(row),
        }
    return out


def ensure_overrides_file(path: str) -> None:
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(
        columns=[
            "transaction_id",
            "invoice_number",
            "subtotal",
            "tax",
            "tip",
            "delivery_fee",
            "discounts",
            "invoice_total",
            "paid_in_amount",
            "merchant_account_fee",
            "order_type",
            "enabled",
            "notes",
        ]
    ).to_csv(path, index=False)


def load_overrides(path: str) -> Dict[Tuple[str, str], Dict[str, str]]:
    ensure_overrides_file(path)
    df = pd.read_csv(path, dtype=str).fillna("")
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    for row in df.to_dict("records"):
        enabled = str(row.get("enabled", "YES")).strip().lower()
        if enabled in {"0", "false", "no", "n"}:
            continue
        tx_id = str(row.get("transaction_id", "")).strip()
        inv = str(row.get("invoice_number", "")).strip()
        if not tx_id and not inv:
            continue
        out[(tx_id, inv)] = row
    return out


def _invoice_tax_map(accounting: pd.DataFrame) -> Dict[str, float]:
    work = accounting.copy()
    work["invoice_number"] = work.get("Invoice Number", "").astype(str).str.strip()
    work = work[work["invoice_number"] != ""].copy()
    if work.empty:
        return {}
    work["account_name_l"] = work.get("Account Name", "").astype(str).str.strip().str.lower()
    tax_rows = work[
        work["account_name_l"].str.contains(r"sales tax|^ca\s*\d", na=False, regex=True)
    ].copy()
    if tax_rows.empty:
        return {}
    tax_rows["amount_num"] = tax_rows.get("Amount (One column)", "").astype(str).map(_to_float).abs()
    grouped = tax_rows.groupby("invoice_number", dropna=False)["amount_num"].sum()
    return grouped.to_dict()


def _payment_by_invoice(accounting: pd.DataFrame) -> Dict[str, Tuple[float, float, str]]:
    work = accounting.copy()
    work["invoice_number"] = work.get("Invoice Number", "").astype(str).str.strip()
    work["transaction_id"] = work.get("Transaction ID", "").astype(str).str.strip()
    if work.empty:
        return {}

    mask = _is_invoice_payment_row(work)
    pay_all = work[mask].copy()
    if pay_all.empty:
        return {}

    # Invoice number is often present only on the AR leg of the payment transaction.
    ar_payment = pay_all[
        (pay_all["invoice_number"] != "")
        & (pay_all.get("Account Name", "").astype(str).str.strip().str.lower() == "accounts receivable")
    ].copy()
    if ar_payment.empty:
        return {}

    result: Dict[str, Tuple[float, float, str]] = {}
    for _, ar_row in ar_payment.iterrows():
        invoice = str(ar_row.get("invoice_number", "")).strip()
        tx_id = str(ar_row.get("transaction_id", "")).strip()
        if not invoice or not tx_id:
            continue
        group = pay_all[pay_all["transaction_id"] == tx_id].copy()
        if group.empty:
            continue
        group["account_name_l"] = group.get("Account Name", "").astype(str).str.strip().str.lower()
        group["signed_num"] = group.apply(_signed_row_amount, axis=1)

        wave_rows = group[
            (group.get("Account Group", "").astype(str).str.strip().str.lower() == "asset")
            & (~group["account_name_l"].str.contains("accounts receivable", na=False))
        ]
        fee_rows = group[group["account_name_l"].str.contains("merchant account fees", na=False)]
        paid_in = float(wave_rows["signed_num"].sum())
        merchant_fee = float(fee_rows["signed_num"].sum())
        has_wave_payments = bool(
            group["account_name_l"].str.contains("wave payments", na=False).any()
        )
        has_cash_on_hand = bool(
            group["account_name_l"].str.contains("cash on hand", na=False).any()
        )
        payment_type_hint = ""
        if has_wave_payments or abs(merchant_fee) > 0.0001:
            payment_type_hint = "credit"
        elif has_cash_on_hand:
            payment_type_hint = "cash"

        prev_paid, prev_fee, prev_hint = result.get(invoice, (0.0, 0.0, ""))
        merged_hint = prev_hint
        if payment_type_hint == "credit" or prev_hint == "credit":
            merged_hint = "credit"
        elif payment_type_hint == "cash" or prev_hint == "cash":
            merged_hint = "cash"
        result[invoice] = (prev_paid + paid_in, prev_fee + merchant_fee, merged_hint)
    return result


def run(
    accounting_csv: str,
    customers_csv: str,
    out_path: str,
    overrides_csv: str | None = None,
) -> int:
    accounting = pd.read_csv(accounting_csv, dtype=str).fillna("")
    customer_map = _load_customers(customers_csv)
    invoice_tax = _invoice_tax_map(accounting)
    payment_info = _payment_by_invoice(accounting)
    overrides_path = overrides_csv or raw_path("wave", "overrides_raw.csv")
    overrides = load_overrides(overrides_path)

    work = accounting.copy()
    work["invoice_number"] = work.get("Invoice Number", "").astype(str).str.strip()
    work = work[work["invoice_number"] != ""].copy()
    work["account_name_l"] = work.get("Account Name", "").astype(str).str.strip().str.lower()
    work["transaction_id"] = work.get("Transaction ID", "").astype(str).str.strip()
    work["is_invoice_payment"] = _is_invoice_payment_row(work)

    ar_candidates = work[
        (work["account_name_l"] == "accounts receivable") & (~work["is_invoice_payment"])
    ].copy()
    if ar_candidates.empty:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        pd.DataFrame().to_csv(out_path, index=False)
        print(f"Wrote 0 Wave invoice row(s) to {out_path}")
        return 0

    ar_candidates["mod_ts"] = pd.to_datetime(
        ar_candidates.get("Transaction Date Last Modified", ""), errors="coerce"
    )
    ar_candidates["add_ts"] = pd.to_datetime(
        ar_candidates.get("Transaction Date Added", ""), errors="coerce"
    )
    ar_candidates = ar_candidates.sort_values(
        by=["invoice_number", "mod_ts", "add_ts", "transaction_id"],
        ascending=[True, False, False, False],
    )
    primary_ar = ar_candidates.drop_duplicates(subset=["invoice_number"], keep="first")

    output: List[Dict[str, str]] = []
    now = pd.Timestamp.now().isoformat()
    for _, ar_row in primary_ar.iterrows():
        invoice_number = str(ar_row.get("invoice_number", "")).strip()
        tx_id = str(ar_row.get("transaction_id", "")).strip()
        group = work[
            (work["invoice_number"] == invoice_number)
            & (work["transaction_id"] == tx_id)
        ].copy()
        if group.empty:
            continue

        sales_rows = group[group["account_name_l"] == "sales"].copy()
        discount_rows = group[group["account_name_l"].str.contains("sales discounts", na=False)].copy()
        tax_rows = group[group["account_name_l"].str.contains(r"sales tax|^ca\s*\d", na=False, regex=True)].copy()

        sales_rows["amount_num"] = sales_rows.get("Amount (One column)", "").astype(str).map(_to_float)
        discount_rows["amount_num"] = discount_rows.get("Amount (One column)", "").astype(str).map(_to_float)
        tax_rows["amount_num"] = tax_rows.get("Amount (One column)", "").astype(str).map(_to_float)

        sales_total = float(sales_rows["amount_num"].sum()) if not sales_rows.empty else 0.0
        discount_total = float(discount_rows["amount_num"].sum()) if not discount_rows.empty else 0.0
        tip = 0.0
        delivery_fee = 0.0
        has_delivery_keyword = False
        items = ""
        item_count = 0
        subtotal_base = 0.0
        if not sales_rows.empty:
            tx_desc = sales_rows.get("Transaction Description", "").astype(str)
            line_desc = sales_rows.get("Transaction Line Description", "").astype(str)
            label_series = pd.Series(
                [
                    _extract_item_label(td, ld)
                    for td, ld in zip(tx_desc.tolist(), line_desc.tolist())
                ],
                index=sales_rows.index,
            )
            label_norm = label_series.astype(str).str.strip().str.lower()
            has_delivery_keyword = bool(label_norm.str.contains("delivery", na=False).any())
            tip_mask = label_norm.str.contains(r"\btip\b$", case=False, na=False, regex=True)
            delivery_fee_mask = label_norm.str.fullmatch(
                r"delivery|delivery\s*fee", case=False
            )
            tip = float(sales_rows[tip_mask]["amount_num"].sum())
            delivery_fee = float(
                sales_rows[delivery_fee_mask]["amount_num"].sum()
            )
            subtotal_base = float(sales_rows[(~tip_mask) & (~delivery_fee_mask)]["amount_num"].sum())
            item_rows = sales_rows[(~tip_mask) & (~delivery_fee_mask)].copy()
            item_rows = item_rows[item_rows["amount_num"] != 0].copy()
            labels: List[str] = []
            seen = set()
            for _, r in item_rows.iterrows():
                label = _extract_item_label(
                    str(r.get("Transaction Description", "")),
                    str(r.get("Transaction Line Description", "")),
                )
                if not label:
                    continue
                norm = " ".join(label.split()).lower()
                if norm in seen:
                    continue
                seen.add(norm)
                labels.append(label)
            items = " | ".join(labels)
            item_count = len(labels)

        invoice_total = abs(_to_float(ar_row.get("Amount (One column)", "")))
        paid_in, merchant_fee, settlement_payment_hint = payment_info.get(
            invoice_number, (0.0, 0.0, "")
        )
        tax_value = invoice_tax.get(invoice_number, 0.0)
        if pd.isna(tax_value):
            tax_value = 0.0
        tax = abs(float(tax_value))
        if tax == 0 and not tax_rows.empty:
            tax = float(tax_rows["amount_num"].abs().sum())
        subtotal = subtotal_base
        if subtotal == 0:
            # Balance fallback: total = subtotal + tax + tip + delivery_fee + discounts
            subtotal = invoice_total - tax - tip - delivery_fee - discount_total
        if subtotal < 0:
            subtotal = 0.0

        # If the credit-card settlement gross (paid_in + merchant fee) exceeds
        # the invoice AR total, treat the positive overage as tip.
        settlement_gross = paid_in + merchant_fee
        overage_tip = settlement_gross - invoice_total
        if overage_tip > 0.01:
            tip += overage_tip

        customer_name = str(ar_row.get("Customer", "")).strip()
        customer_info = customer_map.get(customer_name.lower(), {})
        notes_memo = str(ar_row.get("Notes / Memo", "")).strip()
        notes_totals = _extract_notes_totals(notes_memo)

        # Conservative fallback for special-case invoice entries that only expose
        # delivery/tax/subtotal in notes text, while AR total includes tip separately.
        if has_delivery_keyword and delivery_fee == 0 and notes_totals.get("delivery_fee", 0) > 0:
            note_sub = notes_totals.get("subtotal", 0.0)
            note_del = notes_totals.get("delivery_fee", 0.0)
            note_tax = notes_totals.get("tax", 0.0)
            note_total = notes_totals.get("total", 0.0)
            if note_sub > 0:
                if note_total > 0 and abs((note_total + tip) - invoice_total) <= 0.05:
                    subtotal = note_sub
                    delivery_fee = note_del
                    tax = note_tax
                elif abs(note_total - invoice_total) <= 0.05:
                    subtotal = note_sub
                    delivery_fee = note_del
                    tax = note_tax

        order_type = "delivery" if (delivery_fee > 0 or has_delivery_keyword) else "pickup"
        payment_type_hint = settlement_payment_hint

        override = overrides.get((tx_id, invoice_number)) or overrides.get((tx_id, "")) or overrides.get(("", invoice_number))
        if override:
            value = str(override.get("subtotal", "")).strip()
            if value != "":
                subtotal = _to_float(value)
            value = str(override.get("tax", "")).strip()
            if value != "":
                tax = _to_float(value)
            value = str(override.get("tip", "")).strip()
            if value != "":
                tip = _to_float(value)
            value = str(override.get("delivery_fee", "")).strip()
            if value != "":
                delivery_fee = _to_float(value)
            value = str(override.get("discounts", "")).strip()
            if value != "":
                discount_total = _to_float(value)
            value = str(override.get("invoice_total", "")).strip()
            if value != "":
                invoice_total = _to_float(value)
            value = str(override.get("paid_in_amount", "")).strip()
            if value != "":
                paid_in = _to_float(value)
            value = str(override.get("merchant_account_fee", "")).strip()
            if value != "":
                merchant_fee = _to_float(value)
            override_order_type = str(override.get("order_type", "")).strip().lower()
            if override_order_type in {"delivery", "pickup"}:
                order_type = override_order_type

        order_id = f"WAVE_INV_{invoice_number}_{tx_id}"
        output.append(
            {
                "order_id": order_id,
                "transaction_id": str(tx_id).strip(),
                "invoice_number": invoice_number,
                "transaction_date": str(ar_row.get("Transaction Date", "")).strip(),
                "customer_name": customer_info.get("customer_name", ""),
                "company_name": customer_info.get("company_name", customer_name),
                "email": customer_info.get("email", ""),
                "phone": customer_info.get("phone", ""),
                "address": customer_info.get("address", ""),
                "subtotal": _money(subtotal),
                "tax": _money(tax),
                "tip": _money(tip),
                "delivery_fee": _money(delivery_fee),
                "discounts": _money(discount_total),
                "invoice_total": _money(invoice_total),
                "paid_in_amount": _money(paid_in),
                "merchant_account_fee": _money(merchant_fee),
                "payment_overage_to_tip": _money(overage_tip if overage_tip > 0.01 else 0.0),
                "order_type": order_type,
                "payment_type_hint": payment_type_hint,
                "items": items,
                "item_count": str(item_count),
                "provider": "AROMA",
                "platform": "WAVE",
                "notes_memo": notes_memo,
                "source_accounting_file": accounting_csv,
                "source_customers_file": customers_csv,
                "source_overrides_file": overrides_path,
                "added_at": now,
            }
        )

    output.sort(key=lambda r: (r.get("transaction_date", ""), r.get("invoice_number", "")))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pd.DataFrame(output).to_csv(out_path, index=False)
    print(f"Wrote {len(output)} Wave invoice payment row(s) to {out_path}")
    return len(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Wave invoice-payment rows for Aroma.")
    parser.add_argument(
        "--accounting",
        default=wave_aroma_path("accounting.csv"),
        help="Path to Wave accounting.csv export.",
    )
    parser.add_argument(
        "--customers",
        default=wave_aroma_path("customers.csv"),
        help="Path to Wave customers.csv export.",
    )
    parser.add_argument(
        "--out",
        default=raw_path("wave", "orders_raw.csv"),
        help="Output raw CSV path.",
    )
    parser.add_argument(
        "--overrides",
        default=raw_path("wave", "overrides_raw.csv"),
        help="Path to manual Wave overrides CSV.",
    )
    args = parser.parse_args()
    run(args.accounting, args.customers, args.out, args.overrides)


if __name__ == "__main__":
    main()
