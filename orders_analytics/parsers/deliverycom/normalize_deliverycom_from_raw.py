#!/usr/bin/env python3
import argparse
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Tuple

import pandas as pd

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path
from orders_analytics.utils.normalize import normalize_money, normalize_datetime
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.validation import normalize_order_type, normalize_payment_type
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.schema import build_normalized_row


def to_decimal(value: str) -> Decimal | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return Decimal(text.replace("$", "").replace(",", ""))
    except InvalidOperation:
        return None


def load_raw(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def load_canceled_ids(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    df = pd.read_csv(path, dtype=str).fillna("")
    return {str(v).strip() for v in df.get("order_id", []) if str(v).strip()}


def load_adjustments_overrides(path: str) -> dict[str, dict[str, str]]:
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path, dtype=str).fillna("")
    overrides = {}
    for _, row in df.iterrows():
        oid = str(row.get("order_id", "")).strip()
        if not oid:
            continue
        overrides[oid] = {
            "adjustments": str(row.get("adjustments", "")).strip(),
            "payout": str(row.get("payout", "")).strip(),
            "notes": str(row.get("notes", "")).strip(),
        }
    return overrides


def merge_billings(
    orders: List[Dict[str, str]],
    billings: List[Dict[str, str]],
    canceled_ids: set[str],
) -> List[Dict[str, str]]:
    if not billings:
        return orders
    invoice_counts: Dict[str, int] = {}
    for row in billings:
        invoice_id = str(row.get("invoice_id", "")).strip()
        order_id = str(row.get("order_id", "")).strip()
        if invoice_id and order_id:
            invoice_counts[invoice_id] = invoice_counts.get(invoice_id, 0) + 1
    billings_map = {
        str(row.get("order_id", "")).strip(): row for row in billings if row.get("order_id")
    }
    for row in orders:
        order_id = str(row.get("order_id", "")).strip()
        billing = billings_map.get(order_id)
        if not billing:
            continue
        mismatches = []
        for field, bill_field in (
            ("subtotal", "subtotal"),
            ("tax", "tax"),
            ("tip", "tip"),
            ("delivery_fee", "delivery_fee"),
            ("total", "payment"),
        ):
            order_val = row.get(field, "")
            billing_val = billing.get(bill_field, "")
            if field == "total" and billing_val:
                payment_dec = to_decimal(billing_val)
                if payment_dec is not None:
                    row[field] = f"{abs(payment_dec):.2f}"
            elif billing_val:
                row[field] = billing_val
            if order_val and billing_val:
                compare_val = billing_val
                if field == "total":
                    payment_dec = to_decimal(billing_val)
                    compare_val = f"{abs(payment_dec):.2f}" if payment_dec is not None else billing_val
                    if row.get("dcom_credit") or row.get("discount"):
                        continue
                if normalize_money(order_val) != normalize_money(compare_val):
                    mismatches.append(
                        f"{field} mismatch (orders={order_val}, billings={compare_val})"
                    )
        if mismatches:
            row["errors"] = " | ".join([row.get("errors", ""), *mismatches]).strip(" |")
        row["billing_payment"] = billing.get("payment", "")
        row["billing_service_fee"] = billing.get("service_fee", "")
        row["billing_total_invoice_amount"] = billing.get("total_invoice_amount", "")
        row["billing_invoice_id"] = billing.get("invoice_id", "")
        cc_percent = billing.get("account_cc_percent_fee", "")
        cc_tx = billing.get("account_cc_transaction_fee", "")
        invoice_id = str(billing.get("invoice_id", "")).strip()
        if invoice_id and invoice_counts.get(invoice_id):
            if cc_percent:
                pct_dec = to_decimal(cc_percent)
                if pct_dec is not None:
                    per_order_pct = (pct_dec / Decimal(str(invoice_counts[invoice_id]))).quantize(
                        Decimal("0.01")
                    )
                    cc_percent = f"{per_order_pct:.2f}"
            if cc_tx:
                tx_dec = to_decimal(cc_tx)
                if tx_dec is not None:
                    per_order_tx = (tx_dec / Decimal(str(invoice_counts[invoice_id]))).quantize(
                        Decimal("0.01")
                    )
                    cc_tx = f"{per_order_tx:.2f}"
        row["account_cc_percent_fee"] = cc_percent
        row["account_cc_transaction_fee"] = cc_tx
        row["account_marketplace_facilitator_tax_withhold"] = billing.get(
            "account_marketplace_facilitator_tax_withhold", ""
        )

    existing_ids = {str(row.get("order_id", "")).strip() for row in orders if row.get("order_id")}
    for billing in billings:
        order_id = str(billing.get("order_id", "")).strip()
        if not order_id or order_id in existing_ids or order_id in canceled_ids:
            continue
        orders.append(
            {
                "order_id": order_id,
                "provider": normalize_provider(billing.get("restaurant_name", "")),
                "restaurant_name": billing.get("restaurant_name", ""),
                "order_datetime": normalize_datetime(
                    billing.get("order_datetime", ""),
                    formats=("%m/%d/%Y %I:%M%p", "%m/%d/%Y %I:%M %p"),
                    allow_iso=False,
                ),
                "order_type": "",
                "payment_type": "",
                "customer_name": "",
                "phone": "",
                "address": "",
                "items": "",
                "item_count": "",
                "subtotal": billing.get("subtotal", ""),
                "tax": billing.get("tax", ""),
                "tip": billing.get("tip", ""),
                "delivery_fee": billing.get("delivery_fee", ""),
                "total": billing.get("payment", ""),
                "discount": billing.get("account_dcom_promotion", ""),
                "notes": "missing_order_record",
                "billing_payment": billing.get("payment", ""),
                "billing_service_fee": billing.get("service_fee", ""),
                "billing_total_invoice_amount": billing.get("total_invoice_amount", ""),
                "billing_invoice_id": billing.get("invoice_id", ""),
                "account_cc_percent_fee": billing.get("account_cc_percent_fee", ""),
                "account_cc_transaction_fee": billing.get("account_cc_transaction_fee", ""),
                "account_marketplace_facilitator_tax_withhold": billing.get(
                    "account_marketplace_facilitator_tax_withhold", ""
                ),
            }
        )
    return orders


def normalize_rows(
    rows: List[Dict[str, str]],
    canceled_ids: set[str],
    overrides: dict[str, dict[str, str]],
) -> List[Dict[str, str]]:
    normalized = []

    invoice_tax_data: dict[str, dict[str, Decimal | int | None]] = {}
    invoice_counts: Dict[str, int] = {}
    for row in rows:
        inv = row.get("billing_invoice_id", "") or row.get("invoice_id", "")
        if inv:
            invoice_counts[inv] = invoice_counts.get(inv, 0) + 1
        if not inv:
            continue
        withheld = to_decimal(row.get("account_marketplace_facilitator_tax_withhold", ""))
        if withheld is None:
            continue
        tax_val = to_decimal(row.get("tax", "")) or Decimal("0.00")
        order_dt = str(row.get("order_datetime", "")).strip()
        year = None
        try:
            if order_dt.endswith("Z"):
                order_dt = order_dt[:-1] + "+00:00"
            year = datetime.fromisoformat(order_dt).year
        except Exception:
            year = None
        data = invoice_tax_data.setdefault(
            inv, {"withheld": withheld, "tax_sum": Decimal("0.00"), "year": year}
        )
        data["tax_sum"] = data["tax_sum"] + tax_val
        if data.get("year") is None and year is not None:
            data["year"] = year

    for row in rows:
        order_id = str(row.get("order_id", "")).strip()
        if order_id and order_id in canceled_ids:
            continue
        status = row.get("status", "")
        if status and "cancel" in status.lower():
            continue
        discount = row.get("discount", "")
        if row.get("dcom_promo") or row.get("dcom_credit"):
            discount = ""
        promo = to_decimal(row.get("account_dcom_promotion", ""))
        if promo is not None:
            base = to_decimal(discount) or Decimal("0.00")
            discount = f"{(base + promo).quantize(Decimal('0.01'))}"
        if "missing_order_record" in (row.get("notes", "") or ""):
            if not row.get("order_type"):
                delivery_fee = to_decimal(row.get("delivery_fee", "")) or Decimal("0.00")
                row["order_type"] = "delivery" if delivery_fee > Decimal("0.00") else "pickup"
                notes = " | ".join([row.get("notes", ""), "order_type_inferred"]).strip(" |")
                row["notes"] = notes
            if not row.get("payment_type"):
                row["payment_type"] = "credit"
                notes = " | ".join([row.get("notes", ""), "payment_type_inferred"]).strip(" |")
                row["notes"] = notes
        notes = row.get("notes", "")
        if "daily_order_summary" in notes and (row.get("items") or row.get("customer_name") or row.get("address")):
            notes = " | ".join([part for part in notes.split("|") if "daily_order_summary" not in part]).strip(" |")
        if "special_instructions" in notes.lower():
            notes = ""
        invoice_id = row.get("billing_invoice_id", "") or row.get("invoice_id", "")
        if invoice_id:
            notes = " | ".join([notes, f"invoice_id={invoice_id}"]).strip(" |")
        if status and status.lower() not in ("confirmed", "complete", "completed"):
            notes = " | ".join([notes, f"status={status}"]).strip(" |")

        payment = to_decimal(row.get("billing_payment", "") or row.get("payment", ""))
        total_invoice_amount = to_decimal(row.get("billing_total_invoice_amount", ""))
        service_fee = to_decimal(row.get("billing_service_fee", "") or row.get("service_fee", ""))

        total = row.get("total", "")
        payout = ""
        override = overrides.get(order_id, {})
        if override.get("adjustments"):
            discount = override.get("adjustments")

        marketing_fee = discount
        if row.get("dcom_promo") or row.get("dcom_credit"):
            marketing_fee = ""
        if override.get("adjustments"):
            marketing_fee = ""
        if override.get("notes"):
            notes = " | ".join([notes, override.get("notes")]).strip(" |")

        if payment is not None and abs(payment) >= Decimal("0.01"):
            total = f"{(-payment).quantize(Decimal('0.01'))}"
        else:
            component_sum = sum(
                to_decimal(row.get(field, "")) or Decimal("0.00")
                for field in ("subtotal", "tax", "tip", "delivery_fee", "discount")
            )
            if component_sum != Decimal("0.00"):
                total = f"{component_sum.quantize(Decimal('0.01'))}"
                notes = " | ".join([notes, "total_from_components"]).strip(" |")
        if total_invoice_amount is not None:
            payout = f"{(-total_invoice_amount).quantize(Decimal('0.01'))}"
        if override.get("payout"):
            payout = override.get("payout")

        tax_val = row.get("tax", "")
        tax_withheld_val = ""
        if row.get("account_marketplace_facilitator_tax_withhold"):
            data = invoice_tax_data.get(invoice_id) if invoice_id else None
            if data and abs(data["tax_sum"] - data["withheld"]) <= Decimal("0.01"):
                tax_withheld_val = tax_val
            elif data and invoice_id in invoice_counts:
                per_order = (data["withheld"] / Decimal(str(invoice_counts[invoice_id]))).quantize(Decimal("0.01"))
                tax_withheld_val = f"{per_order:.2f}"
            else:
                tax_withheld_val = tax_val
            tax_val = ""
            if data and data.get("year") and data["year"] >= 2024:
                if abs(data["tax_sum"] - data["withheld"]) > Decimal("0.01"):
                    notes = " | ".join(
                        [
                            notes,
                            f"marketplace_tax_withheld_mismatch invoice_withheld={data['withheld']:.2f} sum_tax={data['tax_sum']:.2f}",
                        ]
                    ).strip(" |")
            notes = " | ".join([notes, "tax_withheld_marketplace_facilitator"]).strip(" |")

        commission_fee = ""
        processing_fee = ""
        if service_fee is not None:
            fee_total = abs(service_fee)
            cc_percent = to_decimal(row.get("account_cc_percent_fee", "")) or Decimal("0.00")
            cc_tx = to_decimal(row.get("account_cc_transaction_fee", "")) or Decimal("0.00")
            processing_calc = (cc_percent + cc_tx).quantize(Decimal("0.01"))
            commission_calc = (fee_total - processing_calc).quantize(Decimal("0.01"))
            if commission_calc + processing_calc != fee_total:
                commission_calc = fee_total - processing_calc
            commission_fee = f"{-commission_calc:.2f}"
            processing_fee = f"{-processing_calc:.2f}"

        normalized.append(
            build_normalized_row(
                Platforms.DELIVERYCOM.upper(),
                order_id=row.get("order_id", ""),
                provider=row.get("provider", ""),
                restaurant_name=row.get("restaurant_name", ""),
                order_datetime=row.get("order_datetime", ""),
                order_type=normalize_order_type(row.get("order_type", "")),
                customer_name=row.get("customer_name", ""),
                phone=row.get("phone", ""),
                address=row.get("address", ""),
                payment_type=normalize_payment_type(row.get("payment_type", "")),
                subtotal=row.get("subtotal", ""),
                tax=tax_val,
                tax_withheld=tax_withheld_val,
                tip=row.get("tip", ""),
                delivery_fee=row.get("delivery_fee", ""),
                total=total,
                item_count=row.get("item_count", ""),
                items=row.get("items", ""),
                adjustments=override.get("adjustments", ""),
                marketing_fee=marketing_fee,
                commission_fee=commission_fee,
                processing_fee=processing_fee,
                payout=payout,
                errors=row.get("errors", ""),
                notes=notes,
            )
        )
    return normalized


class DeliveryComNormalizer(BaseParser):
    platform = "DELIVERYCOM"
    provider = ""
    total_components_fields = ("subtotal", "tax", "tax_withheld", "tip", "delivery_fee", "adjustments", "marketing_fee")

    def default_input_path(self) -> str:
        return raw_path("deliverycom", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("deliverycom_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        billings_path = self.extra.get("billings_raw") or raw_path(
            "deliverycom", "billings_raw.csv"
        )
        canceled_path = raw_path("deliverycom", "canceled_orders.csv")
        overrides_path = raw_path("deliverycom", "deliverycom_adjustments.csv")
        return {
            "orders_raw": load_raw(input_path),
            "billings_raw": load_raw(billings_path),
            "canceled_ids": load_canceled_ids(canceled_path),
            "adjustments_overrides": load_adjustments_overrides(overrides_path),
        }

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        orders = inputs["orders_raw"].to_dict("records")
        billings = inputs["billings_raw"].to_dict("records")
        canceled_ids = inputs.get("canceled_ids", set())
        merged = merge_billings(orders, billings, canceled_ids)
        overrides = inputs.get("adjustments_overrides", {})
        return normalize_rows(merged, canceled_ids, overrides)


def run(
    orders_raw_path: str,
    billings_raw_path: str,
    out_path: str,
    reset_errors: bool = False,
) -> int:
    parser = DeliveryComNormalizer(
        input_path=orders_raw_path,
        out_path=out_path,
        billings_raw=billings_raw_path,
        reset_errors=reset_errors,
    )
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize delivery.com raw CSV.")
    parser.add_argument(
        "--orders-raw",
        default=raw_path("deliverycom", "orders_raw.csv"),
        help="Path to delivery.com orders raw CSV.",
    )
    parser.add_argument(
        "--billings-raw",
        default=raw_path("deliverycom", "billings_raw.csv"),
        help="Path to delivery.com billings raw CSV.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("deliverycom_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_raw, args.billings_raw, args.out)


if __name__ == "__main__":
    main()
