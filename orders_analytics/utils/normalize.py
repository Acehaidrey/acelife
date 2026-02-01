from __future__ import annotations

from datetime import datetime
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Iterable, List, Optional

from orders_analytics.utils.validation import normalize_order_type, normalize_payment_type


def normalize_datetime(
    value: str,
    formats: Optional[Iterable[str]] = None,
    allow_iso: bool = True,
) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in ("nan", "none"):
        return ""
    if allow_iso:
        try:
            if text.endswith("Z"):
                return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
            return datetime.fromisoformat(text).isoformat()
        except ValueError:
            pass
    for fmt in formats or []:
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return text


def normalize_money(value: str) -> str:
    text = str(value or "").strip()
    if text == "":
        return ""
    neg = False
    if text.startswith("(") and text.endswith(")"):
        neg = True
        text = text[1:-1]
    text = text.replace("$", "").replace(",", "").strip()
    if text == "":
        return ""
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return text
    if neg:
        amount = -amount
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount == Decimal("0.00"):
        return "0.00"
    return str(amount)


def clean_text(value: str) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()


def join_address_parts(parts: Iterable[str], sep: str = ", ") -> str:
    cleaned = [str(part or "").strip() for part in parts]
    return sep.join([part for part in cleaned if part])


def title_with_state(address: str) -> str:
    value = str(address or "").strip()
    if not value:
        return value
    titled = value.title()

    def repl(match: re.Match[str]) -> str:
        return f", {match.group(1).upper()} {match.group(2)}"

    return re.sub(r",\s*([A-Za-z]{2})\s+(\d{5}(?:-\d{4})?)$", repl, titled)


def normalize_address(value: str) -> str:
    return clean_text(value)
