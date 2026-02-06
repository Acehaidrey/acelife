from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple

from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.schema import CANONICAL_COLUMNS
from orders_analytics.utils.payment_types import PaymentTypes


def _is_real(value: str) -> bool:
    if value == "":
        return False
    try:
        return float(value) != 0.0
    except ValueError:
        return False


def _append_error(row: Dict[str, str], flag: str) -> None:
    existing = str(row.get("errors") or "").strip()
    if existing:
        existing_flags = [e.strip() for e in existing.split("|")]
        if flag in existing_flags:
            return
        row["errors"] = f"{existing} | {flag}"
    else:
        row["errors"] = flag


def validate_required_fields(
    rows: List[Dict[str, str]],
    source: str,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    required = ["order_id", "platform", "provider", "order_datetime", "order_type"]
    errors: List[Dict[str, str]] = []
    for row in rows:
        missing = [key for key in required if not str(row.get(key) or "").strip()]
        if missing:
            flag = "missing_required_fields"
            _append_error(row, flag)
            errors.append(
                {
                    "order_id": row.get("order_id", ""),
                    "platform": row.get("platform", ""),
                    "provider": row.get("provider", ""),
                    "error_code": flag,
                    "message": f"missing={','.join(missing)}",
                    "source": source,
                }
            )
    return rows, errors


def validate_delivery_fee(
    rows: List[Dict[str, str]],
    source: str,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    errors: List[Dict[str, str]] = []
    for row in rows:
        order_type = str(row.get("order_type") or "").strip().lower()
        if order_type != OrderTypes.DELIVERY:
            continue
        fee = str(row.get("delivery_fee") or "").strip()
        if not _is_real(fee):
            flag = "delivery_fee_missing_for_delivery"
            _append_error(row, flag)
            errors.append(
                {
                    "order_id": row.get("order_id", ""),
                    "platform": row.get("platform", ""),
                    "provider": row.get("provider", ""),
                    "error_code": flag,
                    "message": f"delivery_fee={fee}",
                    "source": source,
                }
            )
    return rows, errors


def normalize_order_type(value: str) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    if text == OrderTypes.PHONE_CALL:
        return OrderTypes.PHONE_CALL
    if text.startswith("pick"):
        return OrderTypes.PICKUP
    if text.startswith("deliv"):
        return OrderTypes.DELIVERY
    return text


def normalize_payment_type(value: str) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    if "cash" in text:
        return "cash"
    if "not paid" in text:
        return "cash"
    if "prepaid" in text:
        return "credit"
    if "credit" in text or "card" in text:
        return "credit"
    return text


def validate_enum_fields(
    rows: List[Dict[str, str]],
    source: str,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    errors: List[Dict[str, str]] = []
    for row in rows:
        raw_order_type = str(row.get("order_type") or "").strip()
        raw_payment_type = str(row.get("payment_type") or "").strip()
        norm_order_type = normalize_order_type(raw_order_type)
        norm_payment_type = normalize_payment_type(raw_payment_type)

        if raw_order_type and norm_order_type not in OrderTypes.get_all():
            flag = "invalid_order_type"
            _append_error(row, flag)
            errors.append(
                {
                    "order_id": row.get("order_id", ""),
                    "platform": row.get("platform", ""),
                    "provider": row.get("provider", ""),
                    "error_code": flag,
                    "message": f"order_type={raw_order_type}",
                    "source": source,
                }
            )

        if raw_payment_type and norm_payment_type not in PaymentTypes.get_all():
            flag = "invalid_payment_type"
            _append_error(row, flag)
            errors.append(
                {
                    "order_id": row.get("order_id", ""),
                    "platform": row.get("platform", ""),
                    "provider": row.get("provider", ""),
                    "error_code": flag,
                    "message": f"payment_type={raw_payment_type}",
                    "source": source,
                }
            )
    return rows, errors


def validate_test_customer_names(
    rows: List[Dict[str, str]],
    source: str,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    errors: List[Dict[str, str]] = []
    for row in rows:
        name = str(row.get("customer_name") or "").strip()
        if not name:
            continue
        if "test" in name.lower():
            flag = "test_customer_name"
            _append_error(row, flag)
            errors.append(
                {
                    "order_id": row.get("order_id", ""),
                    "platform": row.get("platform", ""),
                    "provider": row.get("provider", ""),
                    "error_code": flag,
                    "message": f"customer_name={name}",
                    "source": source,
                }
            )
    return rows, errors


def validate_tax_fields(
    rows: List[Dict[str, str]],
    source: str,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    errors: List[Dict[str, str]] = []
    for row in rows:
        tax_raw = str(row.get("tax") or "").strip()
        tw_raw = str(row.get("tax_withheld") or "").strip()
        tax_real = _is_real(tax_raw)
        tw_real = _is_real(tw_raw)
        order_type = str(row.get("order_type") or "").strip().lower()
        if order_type == OrderTypes.PHONE_CALL and not tax_real and not tw_real:
            continue
        if tax_real == tw_real:
            flag = "tax_tax_withheld_needs_review"
            _append_error(row, flag)
            errors.append(
                {
                    "order_id": row.get("order_id", ""),
                    "platform": row.get("platform", ""),
                    "provider": row.get("provider", ""),
                    "error_code": flag,
                    "message": f"tax={tax_raw} tax_withheld={tw_raw}",
                    "source": source,
                }
            )
    return rows, errors


def validate_negative_fees(
    rows: List[Dict[str, str]],
    source: str,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    fee_fields = ["commission_fee", "processing_fee", "marketing_fee", "misc_fee"]
    errors: List[Dict[str, str]] = []
    for row in rows:
        for field in fee_fields:
            raw = str(row.get(field) or "").strip()
            if raw == "":
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            if value > 0:
                flag = "fee_should_be_negative"
                _append_error(row, flag)
                errors.append(
                    {
                        "order_id": row.get("order_id", ""),
                        "platform": row.get("platform", ""),
                        "provider": row.get("provider", ""),
                        "error_code": flag,
                        "message": f"{field}={raw}",
                        "source": source,
                    }
                )
    return rows, errors


def validate_canonical_columns(
    rows: List[Dict[str, str]],
    source: str,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    errors: List[Dict[str, str]] = []
    for row in rows:
        missing = [col for col in CANONICAL_COLUMNS if col not in row]
        if not missing:
            continue
        flag = "missing_canonical_columns"
        _append_error(row, flag)
        errors.append(
            {
                "order_id": row.get("order_id", ""),
                "platform": row.get("platform", ""),
                "provider": row.get("provider", ""),
                "error_code": flag,
                "message": f"missing={','.join(missing)}",
                "source": source,
            }
        )
    return rows, errors


def validate_cash_processing_fee(
    rows: List[Dict[str, str]],
    source: str,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    errors: List[Dict[str, str]] = []
    for row in rows:
        payment_type = normalize_payment_type(str(row.get("payment_type") or ""))
        if payment_type != "cash":
            continue
        processing_fee = str(row.get("processing_fee") or "").strip()
        if _is_real(processing_fee):
            flag = "cash_processing_fee_should_be_zero"
            _append_error(row, flag)
            errors.append(
                {
                    "order_id": row.get("order_id", ""),
                    "platform": row.get("platform", ""),
                    "provider": row.get("provider", ""),
                    "error_code": flag,
                    "message": f"processing_fee={processing_fee}",
                    "source": source,
                }
            )
    return rows, errors


def _is_iso_datetime(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        datetime.fromisoformat(text)
        return True
    except ValueError:
        return False


def validate_order_datetime_iso(
    rows: List[Dict[str, str]],
    source: str,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    errors: List[Dict[str, str]] = []
    for row in rows:
        value = row.get("order_datetime", "")
        if not _is_iso_datetime(value):
            flag = "order_datetime_not_iso"
            _append_error(row, flag)
            errors.append(
                {
                    "order_id": row.get("order_id", ""),
                    "platform": row.get("platform", ""),
                    "provider": row.get("provider", ""),
                    "error_code": flag,
                    "message": f"order_datetime={value}",
                    "source": source,
                }
            )
    return rows, errors
