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
