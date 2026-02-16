from __future__ import annotations

from typing import Dict, Iterable, Tuple


def _to_num(value: str) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if text in {"", "N/A", "n/a", "nan", "NaN"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def compute_adjustment_total(order_id: str, rows: Iterable[Dict[str, str]]) -> Tuple[bool, float]:
    order_id_clean = str(order_id or "").strip()
    has_adjustment = False
    adjustment_total = 0.0

    for row in rows:
        type_raw = str(row.get("Type", "") or "").strip().lower()
        is_adjustment = order_id_clean.startswith("T-") or ("adjustment" in type_raw)
        if not is_adjustment:
            continue
        has_adjustment = True
        row_total = _to_num(row.get("Restaurant Total", ""))
        row_tip = _to_num(row.get("Tip", ""))
        row_tax = _to_num(row.get("Tax Fee", "")) - _to_num(row.get("Tax Fee Exemption", ""))
        row_delivery = _to_num(row.get("Delivery Fee", ""))
        row_subtotal = _to_num(row.get("Subtotal", ""))
        remaining = row_total - (row_tip + row_tax + row_delivery + row_subtotal)
        if abs(remaining) > 0.005:
            adjustment_total += remaining

    return has_adjustment, adjustment_total
