#!/usr/bin/env python3
import argparse
import datetime as dt
import glob
import os
import re
from typing import Dict, List

import pandas as pd
import pdfplumber

from orders_analytics.utils.constants import raw_path
from orders_analytics.utils.normalize import normalize_money
from orders_analytics.utils.providers import normalize_provider

RAW_COLUMNS = [
    "order_id",
    "provider",
    "restaurant_name",
    "order_datetime",
    "order_type",
    "payment_type",
    "payment_status",
    "customer_name",
    "phone",
    "email",
    "address",
    "subtotal",
    "customer_delivery_fee",
    "order_adjustments",
    "tax",
    "tip",
    "total",
    "partnership_fee",
    "processing_fee",
    "misc_fee",
    "notes",
    "statement_period_start",
    "statement_period_end",
    "account_id",
    "source_file",
    "email_date",
    "added_at",
]

ADJUSTMENT_COLUMNS = [
    "order_id",
    "adjustment_datetime",
    "adjustment_amount",
    "adjustment_description",
    "statement_period_start",
    "statement_period_end",
    "account_id",
    "source_file",
    "email_date",
    "added_at",
]

STATEMENT_COLUMNS = [
    "section",
    "label",
    "value",
    "statement_period_start",
    "statement_period_end",
    "account_id",
    "source_file",
    "email_date",
    "added_at",
]

WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def parse_activity_period(text: str) -> Dict[str, str]:
    match = re.search(
        r"Activity Period:\s+([A-Za-z]{3}\s+\w+\s+\d{1,2},\s+\d{4})\s+to\s+([A-Za-z]{3}\s+\w+\s+\d{1,2},\s+\d{4})",
        text,
    )
    if not match:
        return {"statement_period_start": "", "statement_period_end": ""}
    start, end = match.group(1), match.group(2)
    return {"statement_period_start": start, "statement_period_end": end}


def parse_account_id(text: str) -> str:
    match = re.search(r"Account ID:\s*(\d+)", text)
    return match.group(1) if match else ""


def parse_restaurant_name(text: str) -> str:
    for line in text.splitlines():
        if "Pizza" in line or "Pasta" in line:
            return line.strip()
    return ""


def parse_time(line: str) -> str:
    match = re.match(r"^(\d{1,2}:\d{2})(am|pm)$", line.strip(), re.IGNORECASE)
    if not match:
        return ""
    return f"{match.group(1)} {match.group(2).upper()}"


def parse_order_datetime(date_str: str, time_str: str) -> str:
    if not date_str or not time_str:
        return ""
    try:
        return dt.datetime.strptime(f"{date_str} {time_str}", "%b %d, %Y %I:%M %p").isoformat()
    except ValueError:
        return ""

def parse_adjustment_line(line: str) -> Dict[str, str]:
    parts = line.split()
    if len(parts) < 4:
        return {}
    order_id = parts[1]
    amount = parts[2]
    description = " ".join(parts[3:]).strip()
    if not order_id.isdigit():
        return {}
    return {
        "order_id": order_id,
        "adjustment_amount": normalize_money(amount),
        "adjustment_description": description,
    }


def parse_adjustment_cell_datetime(cell: str) -> str:
    if not cell:
        return ""
    date_match = re.search(r"[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}", cell)
    time_match = re.search(r"\d{1,2}:\d{2}(am|pm)", cell, re.IGNORECASE)
    if not date_match or not time_match:
        return ""
    return parse_order_datetime(date_match.group(0), time_match.group(0))


def parse_adjustments_table(page) -> List[Dict[str, str]]:
    hits = page.search("Slice Adjustments")
    if not hits:
        return parse_adjustments_table_ocr(page)
    words = page.extract_words() or []
    header_words = {
        "date": None,
        "time": None,
        "id": None,
        "adjustment": None,
        "value": None,
        "description": None,
    }
    for w in words:
        key = w["text"].strip().lower()
        if key in header_words and header_words[key] is None:
            header_words[key] = w
    if not (header_words["date"] and header_words["id"] and header_words["adjustment"]):
        return parse_adjustments_table_ocr(page)

    header_bottom = max(
        w["bottom"] for w in header_words.values() if w is not None
    )
    x_id = header_words["id"]["x0"]
    x_adjust = header_words["adjustment"]["x0"]
    x_desc = header_words["description"]["x0"] if header_words["description"] else page.width

    def column_for_word(word) -> str:
        x = word["x0"]
        if x < x_id:
            return "date"
        if x < x_adjust:
            return "id"
        if x < x_desc:
            return "amount"
        return "desc"

    rows_by_line: List[Dict[str, str]] = []
    current = {"date": [], "id": [], "amount": [], "desc": []}
    current_y = None
    for w in words:
        if w["top"] <= header_bottom + 2:
            continue
        y = w["top"]
        if current_y is None:
            current_y = y
        if abs(y - current_y) > 2:
            rows_by_line.append(current)
            current = {"date": [], "id": [], "amount": [], "desc": []}
            current_y = y
        col = column_for_word(w)
        current[col].append(w["text"])
    if any(current.values()):
        rows_by_line.append(current)

    rows: List[Dict[str, str]] = []
    buffer: Dict[str, List[str]] = {"date": [], "id": [], "amount": [], "desc": []}
    for line in rows_by_line:
        for key in buffer:
            buffer[key].extend(line.get(key, []))
        # Date/time lines include month or weekday/time; description often ends row.
        if buffer["amount"] and buffer["desc"]:
            date_cell = " ".join(buffer["date"]).strip()
            order_id = " ".join(buffer["id"]).strip()
            amount = " ".join(buffer["amount"]).strip()
            description = " ".join(buffer["desc"]).strip()
            if date_cell or order_id or amount or description:
                rows.append(
                    {
                        "order_id": order_id,
                        "adjustment_datetime": parse_adjustment_cell_datetime(date_cell),
                        "adjustment_amount": normalize_money(amount),
                        "adjustment_description": description,
                    }
                )
            buffer = {"date": [], "id": [], "amount": [], "desc": []}
    return rows


def parse_adjustments_table_ocr(page) -> List[Dict[str, str]]:
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return []

    image = page.to_image(resolution=300).original
    if not isinstance(image, Image.Image):
        return []
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    n = len(data.get("text", []))
    if n == 0:
        return []

    words = []
    for i in range(n):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        words.append(
            {
                "text": text,
                "left": data["left"][i],
                "top": data["top"][i],
                "width": data["width"][i],
                "height": data["height"][i],
                "line_num": data.get("line_num", [0] * n)[i],
            }
        )
    if not words:
        return []

    header_words = {}
    for w in words:
        key = w["text"].strip().lower()
        if key in {"date", "time", "id", "adjustment", "value", "description"}:
            header_words.setdefault(key, w)
    if not (header_words.get("date") and header_words.get("id") and header_words.get("adjustment")):
        return []

    header_bottom = max(
        header_words[key]["top"] + header_words[key]["height"]
        for key in header_words
        if header_words[key] is not None
    )
    x_date = header_words["date"]["left"]
    x_id = header_words["id"]["left"]
    x_adjust = header_words["adjustment"]["left"]
    x_desc = header_words.get("description", {"left": image.width})["left"]
    b_date_id = (x_date + x_id) / 2
    b_id_amt = (x_id + x_adjust) / 2
    b_amt_desc = (x_adjust + x_desc) / 2

    def column_for_word(word) -> str:
        x = word["left"]
        if x < b_date_id:
            return "date"
        if x < b_id_amt:
            return "id"
        if x < b_amt_desc:
            return "amount"
        return "desc"

    filtered = [w for w in words if w["top"] > header_bottom + 2]
    filtered.sort(key=lambda w: (w["top"], w["left"]))
    lines: List[Dict[str, List[str]]] = []
    current_line = {"date": [], "id": [], "amount": [], "desc": []}
    current_top = None
    for w in filtered:
        if current_top is None:
            current_top = w["top"]
        if abs(w["top"] - current_top) > 8:
            lines.append(current_line)
            current_line = {"date": [], "id": [], "amount": [], "desc": []}
            current_top = w["top"]
        current_line[column_for_word(w)].append(w["text"])
    if any(current_line.values()):
        lines.append(current_line)

    parsed: List[Dict[str, str]] = []
    current_date = ""
    current_time = ""
    current_id = ""
    current_amount = ""
    current_desc = ""

    def flush_current() -> None:
        nonlocal current_date, current_time, current_id, current_amount, current_desc
        if current_amount and current_desc:
            order_id = str(current_id or "").strip()
            description = current_desc.strip().rstrip("-").strip()
            parsed.append(
                {
                    "order_id": order_id,
                    "adjustment_datetime": parse_order_datetime(current_date, current_time),
                    "adjustment_amount": normalize_money(current_amount),
                    "adjustment_description": description,
                }
            )
        current_date = ""
        current_time = ""
        current_id = ""
        current_amount = ""
        current_desc = ""

    for line in lines:
        date_text = " ".join(line["date"]).strip()
        id_text = " ".join(line["id"]).strip()
        amount_text = " ".join(line["amount"]).strip()
        desc_text = " ".join(line["desc"]).strip()

        date_match = re.search(r"[A-Za-z]{3}\s+\d{1,2},\s+\d{4}", date_text)
        if date_match:
            if current_date and (current_amount or current_desc or current_id):
                flush_current()
            current_date = date_match.group(0)
        time_match = re.search(r"\d{1,2}:\d{2}(am|pm)", date_text, re.IGNORECASE)
        if time_match:
            current_time = parse_time(time_match.group(0))
        if id_text and not current_id:
            current_id = id_text
        if amount_text and not current_amount:
            current_amount = amount_text
        if desc_text:
            if current_desc:
                current_desc = f"{current_desc} {desc_text}"
            else:
                current_desc = desc_text

        # wait for time or next date line before flushing

    if current_amount and current_desc:
        flush_current()
    return parsed


def parse_statement_section(lines: List[str], header: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    in_section = False
    for line in lines:
        if line.strip() == header:
            in_section = True
            continue
        if in_section and line.strip() == "":
            break
        if not in_section:
            continue
        if ":" not in line:
            continue
        label, value = line.split(":", 1)
        rows.append({"section": header, "label": label.strip(), "value": value.strip()})
    return rows


def parse_statement_summary(text: str) -> List[Dict[str, str]]:
    if not text:
        return []
    lower = text.lower()
    phone_idx = lower.find("phone orders")
    if phone_idx == -1:
        phone_block = ""
        main_block = text
    else:
        phone_block = text[phone_idx:]
        main_block = text[:phone_idx]

    def find_amount(label: str, block: str) -> str:
        pattern = re.compile(rf"{re.escape(label)}\s*(-?\$?\d[\d,]*\.\d{{2}})", re.IGNORECASE)
        match = pattern.search(block)
        return match.group(1) if match else ""

    rows: List[Dict[str, str]] = []

    order_matches = re.findall(r"(\d+)\s*orders?\s*\$([\d,]+\.\d{2})", main_block, flags=re.IGNORECASE)
    if order_matches:
        count, amount = max(order_matches, key=lambda v: float(v[1].replace(",", "")))
        rows.append({"section": "summary", "label": "orders_count", "value": count})
        rows.append({"section": "summary", "label": "orders_total_amount", "value": amount})

    phone_match = re.search(r"(\d+)\s+Phone Orders\s*\$([\d,]+\.\d{2})", text, flags=re.IGNORECASE)
    if phone_match:
        rows.append({"section": "summary", "label": "phone_orders_count", "value": phone_match.group(1)})
        rows.append({"section": "summary", "label": "phone_orders_total_amount", "value": phone_match.group(2)})

    for label, out_label in [
        ("Processing fee", "processing_fee"),
        ("Slice partnership fee", "slice_partnership_fee"),
        ("Slice adjustments/fees sales tax", "slice_adjustments_fees_sales_tax"),
        ("Sales tax withholding", "sales_tax_withholding"),
        ("Net Sales", "net_sales"),
        ("Taxes", "taxes"),
        ("Cust. Delivery fee", "cust_delivery_fee"),
        ("Tips", "tips"),
        ("Slice Adjustments", "slice_adjustments"),
        ("Slice Fees", "slice_fees"),
        ("Total Earnings", "total_earnings"),
    ]:
        amount = find_amount(label, main_block)
        if not amount and label in {"Slice Fees", "Total Earnings"}:
            amount = find_amount(label, text)
        if amount:
            rows.append({"section": "activity_details", "label": out_label, "value": amount})

    for label, out_label in [
        ("Slice partnership fee", "slice_partnership_fee_phone_orders"),
        ("Slice Adjustments/Fees Sales Tax", "slice_adjustments_fees_sales_tax_phone_orders"),
        ("Slice Adjustments", "slice_adjustments_phone_orders"),
    ]:
        amount = find_amount(label, phone_block)
        if amount:
            rows.append({"section": "phone_orders", "label": out_label, "value": amount})

    return rows


def parse_pdf(
    path: str,
) -> Dict[str, List[Dict[str, str]]]:
    orders: List[Dict[str, str]] = []
    adjustments: List[Dict[str, str]] = []
    statements: List[Dict[str, str]] = []
    with pdfplumber.open(path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        restaurant_name = parse_restaurant_name(text)
        provider = normalize_provider(restaurant_name)
        period = parse_activity_period(text)
        account_id = parse_account_id(text)

        for page_index, page in enumerate(pdf.pages):
            for adjustment in parse_adjustments_table(page):
                adjustments.append(
                    {
                        **adjustment,
                        "statement_period_start": period["statement_period_start"],
                        "statement_period_end": period["statement_period_end"],
                        "account_id": account_id,
                        "source_file": os.path.basename(path),
                        "email_date": "",
                    }
                )

            if page_index == 0:
                page_text = page.extract_text() or ""
                if not page_text:
                    try:
                        import pytesseract
                        from PIL import Image
                    except Exception:
                        page_text = ""
                    else:
                        image = page.to_image(resolution=300).original
                        if isinstance(image, Image.Image):
                            page_text = pytesseract.image_to_string(image)
                for statement in parse_statement_summary(page_text):
                    statements.append(
                        {
                            **statement,
                            "statement_period_start": period["statement_period_start"],
                            "statement_period_end": period["statement_period_end"],
                            "account_id": account_id,
                            "source_file": os.path.basename(path),
                            "email_date": "",
                        }
                    )

    raw_lines = [line.rstrip() for line in text.splitlines()]
    lines = [line.strip() for line in raw_lines if line.strip()]
    current_date = ""
    in_adjustments = False
    for idx, line in enumerate(lines):
        if re.match(r"^[A-Z][a-z]{2}\s+\d{2},\s+\d{4}$", line):
            current_date = line
            continue
        if line.strip() == "Adjustments":
            in_adjustments = True
            continue
        if in_adjustments:
            if line.strip() == "" or line.startswith("Summary"):
                in_adjustments = False
                continue
            adjustment = parse_adjustment_line(line)
            if adjustment:
                time_str = ""
                if idx + 1 < len(lines):
                    time_str = parse_time(lines[idx + 1])
                adjustment_datetime = parse_order_datetime(current_date, time_str)
                adjustment["adjustment_datetime"] = adjustment_datetime
                adjustments.append(
                    {
                        **adjustment,
                        "statement_period_start": period["statement_period_start"],
                        "statement_period_end": period["statement_period_end"],
                        "account_id": account_id,
                        "source_file": os.path.basename(path),
                        "email_date": "",
                    }
                )
            continue
        if not current_date:
            continue
        if not line.startswith(WEEKDAYS):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        weekday = parts[0]
        order_id = parts[1]
        if not order_id.isdigit():
            continue
        payment_type = parts[2]
        order_type = parts[3] if parts[3] in ("Pickup", "Delivery") else ""
        remainder = " ".join(parts[4:])
        money_tokens = re.findall(r"-?\$?\d+\.\d{2}|-", remainder)
        money_tokens += [""] * (8 - len(money_tokens))
        subtotal, cust_delivery_fee, order_adjust, tax, tip, total, pship_fee, proc_fee = money_tokens[:8]
        if not subtotal or not total:
            continue

        time_str = ""
        if idx + 1 < len(lines):
            time_str = parse_time(lines[idx + 1])
        order_datetime = parse_order_datetime(current_date, time_str)

        if payment_type.lower() == "phone":
            order_type = "phone_call"
        orders.append(
            {
                "order_id": order_id,
                "provider": provider,
                "restaurant_name": restaurant_name,
                "order_datetime": order_datetime,
                "order_type": order_type.lower(),
                "payment_type": "credit" if payment_type.lower() == "credit" else "cash",
                "subtotal": normalize_money(subtotal),
                "customer_delivery_fee": normalize_money(cust_delivery_fee),
                "order_adjustments": normalize_money(order_adjust),
                "tax": normalize_money(tax),
                "tip": normalize_money(tip),
                "total": normalize_money(total),
                "partnership_fee": normalize_money(pship_fee),
                "processing_fee": normalize_money(proc_fee),
                "statement_period_start": period["statement_period_start"],
                "statement_period_end": period["statement_period_end"],
                "account_id": account_id,
                "source_file": os.path.basename(path),
                "email_date": "",
            }
        )

    return {"orders": orders, "adjustments": adjustments, "statements": statements}


def parse_dir(root: str) -> Dict[str, List[Dict[str, str]]]:
    orders: List[Dict[str, str]] = []
    adjustments: List[Dict[str, str]] = []
    statements: List[Dict[str, str]] = []
    for path in glob.glob(os.path.join(root, "*.pdf")):
        parsed = parse_pdf(path)
        orders.extend(parsed["orders"])
        adjustments.extend(parsed["adjustments"])
        statements.extend(parsed["statements"])
    return {"orders": orders, "adjustments": adjustments, "statements": statements}


def upsert_raw(
    existing_path: str,
    new_rows: List[Dict[str, str]],
    columns: List[str],
    key_fields: List[str],
) -> int:
    now = dt.datetime.now().isoformat()
    if os.path.exists(existing_path):
        existing_df = pd.read_csv(existing_path, dtype=str).fillna("")
        existing_rows = existing_df.to_dict("records")
    else:
        existing_rows = []
    def make_key(row: Dict[str, str]) -> str:
        return "||".join(str(row.get(field, "") or "") for field in key_fields)

    existing_map = {make_key(row): row for row in existing_rows}
    updated = 0
    for row in new_rows:
        key = make_key(row)
        current = existing_map.get(key)
        if current is None:
            row["added_at"] = now
            existing_map[key] = row
            updated += 1
            continue
        changed = False
        for col in columns:
            if col == "added_at":
                continue
            old_val = str(current.get(col, "") or "")
            new_val = str(row.get(col, "") or "")
            if old_val != new_val:
                current[col] = new_val
                changed = True
        if changed:
            current["added_at"] = now
            updated += 1

    final_rows = list(existing_map.values())
    for row in final_rows:
        row.setdefault("added_at", now)
    os.makedirs(os.path.dirname(existing_path), exist_ok=True)
    pd.DataFrame(final_rows).reindex(columns=columns).to_csv(existing_path, index=False)
    return updated


def write_raw(path: str, rows: List[Dict[str, str]], columns: List[str]) -> int:
    now = dt.datetime.now().isoformat()
    for row in rows:
        row.setdefault("added_at", now)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(rows).reindex(columns=columns).to_csv(path, index=False)
    return len(rows)


def run(
    root: str,
    orders_out: str,
    adjustments_out: str = None,
    statements_out: str = None,
) -> int:
    parsed = parse_dir(root)
    adjustments_out = adjustments_out or raw_path("slice", "adjustments_raw.csv")
    statements_out = statements_out or raw_path("slice", "statements_raw.csv")

    updated_orders = write_raw(orders_out, parsed["orders"], RAW_COLUMNS)
    updated_adjustments = write_raw(adjustments_out, parsed["adjustments"], ADJUSTMENT_COLUMNS)
    updated_statements = write_raw(statements_out, parsed["statements"], STATEMENT_COLUMNS)
    orders_count = None
    phone_orders_count = None
    for row in parsed["statements"]:
        if row.get("label") == "orders_count":
            try:
                orders_count = int(str(row.get("value", "")).replace(",", ""))
            except ValueError:
                orders_count = None
        if row.get("label") == "phone_orders_count":
            try:
                phone_orders_count = int(str(row.get("value", "")).replace(",", ""))
            except ValueError:
                phone_orders_count = None
    if orders_count is not None and phone_orders_count is not None:
        expected_total = orders_count + phone_orders_count
        actual_total = len(parsed["orders"])
        if expected_total != actual_total:
            print(
                "WARNING: Slice orders count mismatch "
                f"(statement {expected_total} vs extracted {actual_total})."
            )
    print(f"Upserted {updated_orders} Slice order row(s) into {orders_out}")
    print(f"Upserted {updated_adjustments} Slice adjustment row(s) into {adjustments_out}")
    print(f"Upserted {updated_statements} Slice statement row(s) into {statements_out}")
    return updated_orders + updated_adjustments + updated_statements


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Slice orders raw CSV from PDFs.")
    parser.add_argument(
        "--orders-root",
        default="Takeout/Slice",
        help="Directory containing Slice PDF reports.",
    )
    parser.add_argument(
        "--orders-out",
        default=raw_path("slice", "orders_raw.csv"),
        help="Output orders raw CSV path.",
    )
    parser.add_argument(
        "--adjustments-out",
        default=raw_path("slice", "adjustments_raw.csv"),
        help="Output adjustments raw CSV path.",
    )
    parser.add_argument(
        "--statements-out",
        default=raw_path("slice", "statements_raw.csv"),
        help="Output statements raw CSV path.",
    )
    args = parser.parse_args()
    run(args.orders_root, args.orders_out, args.adjustments_out, args.statements_out)


if __name__ == "__main__":
    main()
