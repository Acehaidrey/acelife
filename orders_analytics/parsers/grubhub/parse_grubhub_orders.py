#!/usr/bin/env python3
import argparse
import re
from typing import Dict, List

import pandas as pd
import os

from orders_analytics.utils.base_parser import BaseParser
from orders_analytics.utils.constants import normalized_path, raw_path, takeout_path
from orders_analytics.utils.grubhub_adjustments import compute_adjustment_total
from orders_analytics.utils.google_sheets import download_sheet_entry
from orders_analytics.utils.google_sheets_registry import SHEETS
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes
from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.providers import normalize_provider
from orders_analytics.utils.schema import build_normalized_row


NULL_LIKE = {"", "N/A", "n/a", "nan", "NaN"}


def _clean_str(value: str) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text in NULL_LIKE:
        return ""
    return text


def _to_num(value: str) -> float:
    text = _clean_str(value)
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _first_non_empty(values: List[str]) -> str:
    for val in values:
        if val:
            return val
    return ""


def _join_distinct(values: List[str]) -> str:
    return " | ".join(sorted({v for v in values if v}))




def _pick_col(row: dict, options: list[str]) -> str:
    for key in options:
        if key in row:
            val = str(row.get(key, "") or "").strip()
            if val:
                return val
    return ""

def _build_datetime(date_str: str, time_str: str) -> str:
    if " | " in date_str:
        date_str = date_str.split(" | ", 1)[0]
    if " | " in time_str:
        time_str = time_str.split(" | ", 1)[0]
    date_clean = _clean_str(date_str)
    time_clean = _clean_str(time_str)
    if not date_clean:
        return ""
    if "," in time_clean:
        time_clean = time_clean.split(",", 1)[0].strip()
    # Drop trailing timezone abbreviations like PDT/PST to avoid parse warnings.
    time_clean = re.sub(r"\s+(PDT|PST)$", "", time_clean)
    combined = f"{date_clean} {time_clean}".strip()
    parsed = pd.to_datetime(combined, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%dT%H:%M:%S")


class GrubhubOrdersParser(BaseParser):
    platform = Platforms.GRUBHUB.upper()
    total_components_fields = (
        "subtotal",
        "tax",
        "tip",
        "delivery_fee",
        "misc_fee",
        "adjustments",
    )

    def default_input_path(self) -> str:
        return raw_path("grubhub", "orders_raw.csv")

    def default_out_path(self) -> str:
        return normalized_path("grubhub_orders_normalized.csv")

    def load_inputs(self, input_path: str):
        df = pd.read_csv(input_path, dtype=str).fillna("")
        return {"orders": df}

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        df = inputs["orders"].copy()
        supplemental_sheet = SHEETS.get("grubhub_order_history")
        supplemental_path = supplemental_sheet["out"] if supplemental_sheet else raw_path("grubhub", "grubhub_order_history.csv")
        if supplemental_sheet:
            try:
                download_sheet_entry(supplemental_sheet)
            except Exception:
                if not os.path.exists(supplemental_path):
                    raise
        supplement = {}
        supplement_suffix = {}
        adjustments_overrides = {}
        overrides_path = raw_path("grubhub", "grubhub_adjustments.csv")
        if os.path.exists(overrides_path):
            overrides_df = pd.read_csv(overrides_path, dtype=str).fillna("")
            for _, override in overrides_df.iterrows():
                oid = str(override.get("order_id", "")).strip()
                if not oid:
                    continue
                service_fee_override = override.get("service_fee_override", "")
                try:
                    service_fee_override = float(service_fee_override)
                except (TypeError, ValueError):
                    service_fee_override = None
                note = str(override.get("note", "")).strip()
                adjustments_overrides[oid] = {
                    "service_fee_override": service_fee_override,
                    "note": note,
                }

        if supplemental_path and os.path.exists(supplemental_path):
            sup_df = pd.read_csv(supplemental_path, dtype=str).fillna("")
            for _, sup_row in sup_df.iterrows():
                order_id = _pick_col(sup_row, ["Order ID", "Order Number", "Order #", "Order", "ID"])
                if not order_id:
                    continue
                order_id_clean = order_id.strip()
                parts = [p for p in re.split(r"\s*[–—\-]\s*|\s+—\s+", order_id_clean) if p.strip()]
                right = re.sub(r"\D", "", parts[1]) if len(parts) >= 2 else ""

                email_value = _pick_col(sup_row, ["Email", "Email Address", "Customer Email"])
                if email_value.strip().lower() == "aroma-pizza+unsubscribe@googlegroups.com":
                    email_value = ""
                payload = {
                    "customer_name": _pick_col(sup_row, ["Customer Name", "Customer", "Name"]),
                    "company_name": _pick_col(sup_row, ["Company", "Company Name"]),
                    "phone": _pick_col(sup_row, ["Phone", "Phone Number", "Customer Phone"]),
                    "email": email_value,
                    "address": _pick_col(sup_row, ["Address", "Address ", "Customer Address", "Delivery Address"]),
                    "items": _pick_col(sup_row, ["Items", "Order Items", "Item Summary"]),
                    "item_count": _pick_col(sup_row, ["Item Count", "Items Count", "Item Qty"]),
                }
                supplement[order_id_clean] = payload
                if right:
                    supplement_suffix.setdefault(right, []).append(payload)
        # normalize column names
        df.columns = [c.strip() for c in df.columns]

        # aggregate duplicates by Order ID
        grouped = []
        for order_id, group in df.groupby("ID", dropna=False):
            rows = group.to_dict("records")
            merged_count = len(rows)

            order_id_clean = _clean_str(order_id)

            restaurants = [_clean_str(r.get("Restaurant", "")) for r in rows]
            fulfillment_types = [_clean_str(r.get("Fulfillment Type", "")) for r in rows]
            order_types_raw = [_clean_str(r.get("Type", "")) for r in rows]
            descriptions = [_clean_str(r.get("Description", "")) for r in rows]

            date_str = _join_distinct([_clean_str(r.get("Date", "")) for r in rows])
            time_str = _join_distinct([_clean_str(r.get("Time", "")) for r in rows])


            subtotal = sum(_to_num(r.get("Subtotal", "")) for r in rows)
            delivery_fee = sum(_to_num(r.get("Delivery Fee", "")) for r in rows)
            service_fee = sum(_to_num(r.get("Service Fee", "")) for r in rows)
            override_note = ""
            override = adjustments_overrides.get(order_id_clean)
            if override is not None and override.get("service_fee_override") is not None:
                service_fee = override["service_fee_override"]
                override_note = override.get("note", "")
            service_fee_exemption = sum(_to_num(r.get("Service Fee Exemption", "")) for r in rows)
            flexible_fees = sum(_to_num(r.get("(flexible fees)", "")) for r in rows)
            tax_fee = sum(_to_num(r.get("Tax Fee", "")) for r in rows)
            tax_fee_exemption = sum(_to_num(r.get("Tax Fee Exemption", "")) for r in rows)
            tip = sum(_to_num(r.get("Tip", "")) for r in rows)
            total = sum(_to_num(r.get("Restaurant Total", "")) for r in rows)
            commission = sum(_to_num(r.get("Commission", "")) for r in rows)
            gh_plus_commission = sum(_to_num(r.get("GH+ Commission", "")) for r in rows)
            delivery_commission = sum(_to_num(r.get("Delivery Commission", "")) for r in rows)
            processing_fee = sum(_to_num(r.get("Processing Fee", "")) for r in rows)
            withheld_tax = sum(_to_num(r.get("Withheld Tax", "")) for r in rows)
            withheld_tax_exemption = sum(_to_num(r.get("Withheld Tax Exemption", "")) for r in rows)
            targeted_promo = sum(_to_num(r.get("Targeted Promotion", "")) for r in rows)
            rewards = sum(_to_num(r.get("Rewards", "")) for r in rows)

            # computed fields
            tax = tax_fee - tax_fee_exemption
            tax_withheld = withheld_tax + withheld_tax_exemption
            misc_fee = service_fee_exemption + flexible_fees
            commission_fee = commission + gh_plus_commission + delivery_commission
            marketing_fee = targeted_promo + rewards

            has_adjustment_rows, adjustment_total = compute_adjustment_total(order_id_clean, rows)
            if abs(service_fee) >= 0.01:
                adjustment_total += service_fee

            restaurant = _join_distinct(restaurants)
            provider = normalize_provider(restaurant)

            fulfillment = _join_distinct(fulfillment_types).lower()
            order_type = ""
            notes: List[str] = []
            if merged_count > 1:
                notes.append(f"merged_rows={merged_count}")
            if order_id_clean.startswith("W-"):
                notes.append("commission_free_link")
            if override_note:
                notes.append(override_note)
            if has_adjustment_rows:
                notes.append(f"adjustment_total={adjustment_total:.2f}")
            if fulfillment == "self delivery":
                order_type = OrderTypes.DELIVERY
            elif fulfillment == "pick-up":
                order_type = OrderTypes.PICKUP
            elif fulfillment == "grubhub delivery":
                order_type = OrderTypes.PICKUP
                notes.append("grubhub_delivery")
            elif fulfillment:
                notes.append(f"fulfillment_type_raw={fulfillment}")

            order_type_raw = _join_distinct(order_types_raw)
            payment_type = ""
            order_type_raw_l = order_type_raw.lower()
            if order_id_clean.startswith("T-"):
                payment_type = PaymentTypes.CREDIT
            if "adjustment" in order_type_raw_l:
                payment_type = PaymentTypes.CREDIT
            if "prepaid order" in order_type_raw_l:
                payment_type = PaymentTypes.CREDIT
            elif "phone order" in order_type_raw_l:
                order_type = OrderTypes.PHONE_CALL
                payment_type = PaymentTypes.CREDIT
            elif "cash order" in order_type_raw_l:
                payment_type = PaymentTypes.CASH
                expected_total = subtotal + delivery_fee + tax + tip
                if abs(expected_total - total) >= 0.01:
                    notes.append(f"cash_total_adjusted_from={total:.2f}")
                    total = expected_total
                if abs(tip) >= 0.01:
                    notes.append(f"cash_tip_nonzero={tip:.2f}")
            elif order_type_raw:
                notes.append(f"payment_type_raw={order_type_raw}")

            description = _join_distinct(descriptions)
            if description:
                notes.append(description)

            order_datetime = _build_datetime(date_str, time_str)

            zero_financials = all(
                abs(value) < 0.01
                for value in (
                    subtotal,
                    tax,
                    tax_withheld,
                    tip,
                    delivery_fee,
                    total,
                    commission_fee,
                    processing_fee,
                    marketing_fee,
                    misc_fee,
                    adjustment_total,
                )
            )
            if zero_financials:
                continue

            sup = supplement.get(order_id_clean)
            if sup is None and "-" in order_id_clean:
                suffix_raw = order_id_clean.split("-", 1)[1]
                suffix_digits = re.sub(r"\D", "", suffix_raw)
                candidates = []
                if suffix_digits:
                    for right, payloads in supplement_suffix.items():
                        if suffix_digits.endswith(right):
                            candidates.extend(payloads)
                if len(candidates) == 1:
                    sup = candidates[0]
            if sup is None:
                sup = {}

            def _fmt(value: float, force_zero: bool = False) -> str:
                if value:
                    return f"{value:.2f}"
                return "0.00" if force_zero else ""

            force_zero_values = order_id_clean.startswith("T-")

            grouped.append(build_normalized_row(
                Platforms.GRUBHUB.upper(),
                order_id=order_id_clean,
                provider=provider,
                restaurant_name=restaurant,
                order_datetime=order_datetime,
                order_type=order_type,
                payment_type=payment_type,
                subtotal=_fmt(subtotal, force_zero_values),
                tax=_fmt(tax, force_zero_values),
                tax_withheld=_fmt(tax_withheld, force_zero_values),
                tip=_fmt(tip, force_zero_values),
                delivery_fee=_fmt(delivery_fee, force_zero_values),
                total=_fmt(total, force_zero_values),
                commission_fee=_fmt(commission_fee, force_zero_values),
                processing_fee=_fmt(processing_fee, force_zero_values),
                marketing_fee=_fmt(marketing_fee, force_zero_values),
                misc_fee=_fmt(misc_fee, force_zero_values),
                adjustments=_fmt(adjustment_total, force_zero_values),
                payout="",
                customer_name=sup.get("customer_name", ""),
                company_name=sup.get("company_name", ""),
                phone=sup.get("phone", ""),
                email=sup.get("email", ""),
                address=sup.get("address", ""),
                items=sup.get("items", ""),
                item_count=sup.get("item_count", ""),
                notes=" | ".join([n for n in notes if n]),
            ))


        def _merge_prefix_orders(rows):
            def base_id(value: str) -> str:
                base = re.sub(r"^[A-Za-z]+-", "", str(value))
                if re.search(r"[A-Za-z]", base):
                    return base
                return re.sub(r"\D", "", base)

            def prefix_rank(value: str) -> int:
                value = str(value)
                if value.startswith("W-"):
                    return 0
                if value.startswith("O-"):
                    return 1
                if value.startswith("T-"):
                    return 2
                return 3

            numeric_fields = [
                "subtotal",
                "tax",
                "tax_withheld",
                "tip",
                "delivery_fee",
                "total",
                "commission_fee",
                "processing_fee",
                "marketing_fee",
                "misc_fee",
                "adjustments",
                "expected_payout",
                "payout",
            ]

            grouped_rows = {}
            for row in rows:
                key = (
                    row.get("provider", ""),
                    row.get("restaurant_name", ""),
                    base_id(row.get("order_id", "")),
                )
                grouped_rows.setdefault(key, []).append(row)

            merged_rows = []
            for (_, _, _), items in grouped_rows.items():
                if len(items) == 1:
                    merged_rows.append(items[0])
                    continue

                items_sorted = sorted(items, key=lambda r: prefix_rank(r.get("order_id", "")))
                merged = dict(items_sorted[0])

                merged_ids = [r.get("order_id", "") for r in items_sorted if r.get("order_id", "")]
                merge_note = f"merged_orders={','.join(merged_ids)}" if merged_ids else ""

                # earliest order_datetime
                parsed_dates = []
                for r in items_sorted:
                    value = str(r.get("order_datetime", "")).strip()
                    if not value:
                        continue
                    parsed = pd.to_datetime(value, errors="coerce")
                    if pd.notna(parsed):
                        parsed_dates.append(parsed)
                if parsed_dates:
                    merged["order_datetime"] = min(parsed_dates).isoformat()

                # merge enum fields
                for enum_field, note_key in ("order_type", "order_type_mismatch"), ("payment_type", "payment_type_mismatch"):
                    values = [str(r.get(enum_field, "")).strip() for r in items_sorted if str(r.get(enum_field, "")).strip()]
                    if values:
                        merged[enum_field] = values[0]
                        if len(set(values)) > 1:
                            merged.setdefault("notes", "")
                            merged["notes"] = " | ".join([v for v in [merged.get("notes", ""), note_key] if v])

                # sum numeric fields
                for field in numeric_fields:
                    total_value = 0.0
                    for r in items_sorted:
                        raw = str(r.get(field, "")).strip()
                        if not raw:
                            continue
                        try:
                            total_value += float(raw)
                        except ValueError:
                            continue
                    merged[field] = f"{total_value:.2f}" if abs(total_value) >= 0.01 else ""

                # first non-empty for other fields
                for field in ["customer_name", "company_name", "phone", "email", "address", "items", "item_count"]:
                    if merged.get(field):
                        continue
                    for r in items_sorted:
                        value = str(r.get(field, "")).strip()
                        if value:
                            merged[field] = value
                            break

                notes = [str(r.get("notes", "")).strip() for r in items_sorted if str(r.get("notes", "")).strip()]
                if merge_note:
                    notes.append(merge_note)
                note_tokens = []
                for note in notes:
                    for token in [t.strip() for t in note.split("|")]:
                        if token:
                            note_tokens.append(token)
                merged["notes"] = " | ".join(dict.fromkeys(note_tokens))

                # Drop merged rows that net to zero across financial fields.
                all_zero = True
                for field in numeric_fields:
                    raw = str(merged.get(field, "")).strip()
                    if raw:
                        try:
                            if abs(float(raw)) >= 0.01:
                                all_zero = False
                                break
                        except ValueError:
                            all_zero = False
                            break
                if all_zero:
                    continue

                merged_rows.append(merged)

            return merged_rows

        grouped = _merge_prefix_orders(grouped)

        return grouped



def run(input_path: str, out_path: str) -> int:
    parser = GrubhubOrdersParser(input_path=input_path, out_path=out_path)
    stats = parser.run()
    print(f"Wrote {stats.rows_written} rows to {parser.resolve_paths()[1]}")
    return stats.rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse Grubhub CSV to normalized output.")
    parser.add_argument(
        "--input",
        default=raw_path("grubhub", "orders_raw.csv"),
        help="Input Grubhub CSV path.",
    )
    parser.add_argument(
        "--out",
        default=normalized_path("grubhub_orders_normalized.csv"),
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()
    run(args.input, args.out)


if __name__ == "__main__":
    main()
