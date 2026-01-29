from __future__ import annotations

from typing import Dict, List, Tuple


def _is_real(value: str) -> bool:
    if value == "":
        return False
    try:
        return float(value) != 0.0
    except ValueError:
        return False


def validate_required_fields(
    rows: List[Dict[str, str]],
    source: str,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    required = ["order_id", "platform", "provider", "order_datetime", "order_type"]
    errors: List[Dict[str, str]] = []
    for row in rows:
        missing = [key for key in required if not str(row.get(key) or "").strip()]
        if missing:
            notes = str(row.get("notes") or "").strip()
            flag = "missing_required_fields"
            row["notes"] = f"{notes} | {flag}".strip(" |")
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
        if order_type != "delivery":
            continue
        fee = str(row.get("delivery_fee") or "").strip()
        if not _is_real(fee):
            notes = str(row.get("notes") or "").strip()
            flag = "delivery_fee_missing_for_delivery"
            row["notes"] = f"{notes} | {flag}".strip(" |")
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
    if text.startswith("pick"):
        return "pickup"
    if text.startswith("deliv"):
        return "delivery"
    return text


def normalize_payment_type(value: str) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    if "cash" in text:
        return "cash"
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

        if raw_order_type and norm_order_type not in ("pickup", "delivery"):
            notes = str(row.get("notes") or "").strip()
            flag = "invalid_order_type"
            row["notes"] = f"{notes} | {flag}".strip(" |")
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

        if raw_payment_type and norm_payment_type not in ("credit", "cash"):
            notes = str(row.get("notes") or "").strip()
            flag = "invalid_payment_type"
            row["notes"] = f"{notes} | {flag}".strip(" |")
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
            notes = str(row.get("notes") or "").strip()
            flag = "test_customer_name"
            row["notes"] = f"{notes} | {flag}".strip(" |")
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
        if tax_real == tw_real:
            notes = str(row.get("notes") or "").strip()
            flag = "tax_tax_withheld_needs_review"
            row["notes"] = f"{notes} | {flag}".strip(" |")
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
