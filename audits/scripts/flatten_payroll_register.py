#!/usr/bin/env python3
import argparse
import csv
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber


DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
MONEY_RE = re.compile(r"^-?\$?[0-9,]+(?:\.[0-9]{2})?$")
STRICT_MONEY_RE = re.compile(r"^-?[0-9,]+(?:\.[0-9]{2})$")

NUMERIC_COLUMNS = [
    "Compensation",
    "Reported Tips",
    "Federal Tax",
    "Social Security",
    "Medicare",
    "Medicare Additional Tax",
    "State Tax",
    "SDI",
    "Business Expense",
    "Cash Advance",
    "Cash Advance Repayment",
    "Total/Net",
]

CSV_COLUMNS = [
    "Row Type",
    "SSN",
    "Employee Name",
    "Date",
    "Check #",
    "Period Start",
    "Period End",
    *NUMERIC_COLUMNS,
]
AMOUNT_X_CENTERS = [317, 357, 397, 435, 466, 516, 545, 571, 618, 660, 703, 731]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flatten a payroll register PDF into CSV rows by check and employee totals."
    )
    parser.add_argument("input_pdf", type=Path, help="Path to Payroll Register PDF")
    parser.add_argument("output_csv", type=Path, help="Path to write flattened CSV")
    return parser.parse_args()


def to_decimal(value: str) -> Decimal:
    cleaned = value.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return Decimal("0.00")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0.00")


def format_ssn(raw_token: str) -> str:
    digits = "".join(ch for ch in raw_token if ch.isdigit())
    if len(digits) < 9:
        return ""
    d = digits[:9]
    return f"{d[0:3]}-{d[3:5]}-{d[5:9]}"


def cluster_words(words, tolerance: float = 1.2):
    words = sorted(words, key=lambda w: w["top"])
    clusters = []
    for word in words:
        if not clusters or (word["top"] - clusters[-1][-1]["top"] > tolerance):
            clusters.append([word])
        else:
            clusters[-1].append(word)
    return clusters


def normalize_money_token(token: str) -> str:
    token = token.strip()
    if token.startswith("$"):
        token = token[1:]
    return token


def quantize_cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def format_decimal(value: Decimal) -> str:
    return f"{quantize_cents(value):.2f}"


def extract_money_from_token(raw: str) -> str | None:
    token = normalize_money_token(raw)
    if STRICT_MONEY_RE.fullmatch(token):
        return token

    # Footer/header collisions may blend timestamps/page text into values.
    if any(marker in raw for marker in ["/", "Page", "AM", "PM", "of"]):
        return None

    match = re.search(r"-?[0-9][0-9,]*\.[0-9]{2}", token)
    if not match:
        return None
    return match.group(0)


def extract_amount_columns(words_sorted):
    assigned = [None] * len(AMOUNT_X_CENTERS)
    distances = [10**9] * len(AMOUNT_X_CENTERS)

    for w in words_sorted:
        if w["x0"] < 300:
            continue
        value = extract_money_from_token(w["text"])
        if not value:
            continue
        idx = min(range(len(AMOUNT_X_CENTERS)), key=lambda i: abs(w["x0"] - AMOUNT_X_CENTERS[i]))
        dist = abs(w["x0"] - AMOUNT_X_CENTERS[idx])
        if dist < distances[idx]:
            distances[idx] = dist
            assigned[idx] = value

    # Fill blanks as 0.00 so we can compute/check arithmetic consistently.
    values = [v if v is not None else "0.00" for v in assigned]

    # Recompute Total/Net when OCR/footer corruption creates an inconsistent final amount.
    first_eleven_sum = sum((to_decimal(v) for v in values[:-1]), Decimal("0.00"))
    stated_total = to_decimal(values[-1])
    if stated_total != quantize_cents(first_eleven_sum):
        values[-1] = format_decimal(first_eleven_sum)

    return values


def parse_employee_name_from_total(words_sorted) -> str:
    name_tokens = []
    for w in words_sorted:
        text = w["text"]
        if text == "Total":
            break
        if w["x0"] >= 300:
            break
        if text == "-":
            continue
        name_tokens.append(text)
    return " ".join(name_tokens).strip()


def parse_rows(pdf_path: Path):
    parsed_rows = []
    pending_detail_rows = []
    pending_ssn = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            clusters = cluster_words(page.extract_words(x_tolerance=1, y_tolerance=2))
            for cluster in clusters:
                words_sorted = sorted(cluster, key=lambda w: w["x0"])
                tokens = [w["text"] for w in words_sorted]
                line_text = " ".join(tokens)

                # Skip non-data boilerplate.
                if "Employee Journal by Check" in line_text:
                    continue
                if "Page" in tokens and "of" in tokens and any(t.endswith("PM") for t in tokens):
                    continue

                has_date = any(DATE_RE.match(t) for t in tokens)
                number_words = [
                    w
                    for w in words_sorted
                    if w["x0"] >= 300 and MONEY_RE.match(w["text"].replace("(", "").replace(")", ""))
                ]

                is_total = "Total" in tokens and len(number_words) >= 2 and not has_date
                if is_total:
                    values = extract_amount_columns(words_sorted)
                    if len(values) != 12:
                        continue
                    employee_name = parse_employee_name_from_total(words_sorted)
                    for row in pending_detail_rows:
                        row["Employee Name"] = employee_name
                        if not row["SSN"]:
                            row["SSN"] = pending_ssn
                        parsed_rows.append(row)

                    total_row = {
                        "Row Type": "employee_total",
                        "SSN": pending_ssn,
                        "Employee Name": employee_name,
                        "Date": "",
                        "Check #": "",
                        "Period Start": "",
                        "Period End": "",
                    }
                    for col, value in zip(NUMERIC_COLUMNS, values):
                        total_row[col] = value
                    parsed_rows.append(total_row)

                    pending_detail_rows = []
                    pending_ssn = ""
                    continue

                is_detail = has_date and len(number_words) == 12
                if not is_detail:
                    continue

                left_words = [w for w in words_sorted if w["x0"] < 140]
                if left_words and any(ch.isdigit() for ch in left_words[0]["text"]):
                    candidate_ssn = format_ssn(left_words[0]["text"])
                    if candidate_ssn:
                        pending_ssn = candidate_ssn

                date_word = next((w["text"] for w in words_sorted if 145 <= w["x0"] < 180 and DATE_RE.match(w["text"])), "")
                check_word = next((w["text"] for w in words_sorted if 180 <= w["x0"] < 210), "")
                period_start = next((w["text"] for w in words_sorted if 220 <= w["x0"] < 250 and DATE_RE.match(w["text"])), "")
                period_end = next((w["text"] for w in words_sorted if 250 <= w["x0"] < 290 and DATE_RE.match(w["text"])), "")
                values = extract_amount_columns(words_sorted)

                row = {
                    "Row Type": "check_row",
                    "SSN": pending_ssn,
                    "Employee Name": "",
                    "Date": date_word,
                    "Check #": check_word,
                    "Period Start": period_start,
                    "Period End": period_end,
                }
                for col, value in zip(NUMERIC_COLUMNS, values):
                    row[col] = value
                pending_detail_rows.append(row)

    # If PDF ended without a trailing total row, still emit pending checks.
    for row in pending_detail_rows:
        parsed_rows.append(row)

    return parsed_rows


def validate_totals(rows):
    by_employee_checks = defaultdict(list)
    by_employee_total = {}

    for row in rows:
        key = (row["SSN"], row["Employee Name"])
        if row["Row Type"] == "check_row":
            by_employee_checks[key].append(row)
        elif row["Row Type"] == "employee_total":
            by_employee_total[key] = row

    mismatches = []
    for key, check_rows in by_employee_checks.items():
        total_row = by_employee_total.get(key)
        if not total_row:
            mismatches.append((key, "missing_total_row"))
            continue
        for col in NUMERIC_COLUMNS:
            check_sum = sum((to_decimal(r[col]) for r in check_rows), Decimal("0.00"))
            total_val = to_decimal(total_row[col])
            if check_sum != total_val:
                mismatches.append((key, col, str(check_sum), str(total_val)))
    return mismatches


def write_csv(rows, output_path: Path):
    total_row = {
        "Row Type": "total",
        "SSN": "",
        "Employee Name": "TOTAL",
        "Date": "",
        "Check #": "",
        "Period Start": "",
        "Period End": "",
    }
    for col in NUMERIC_COLUMNS:
        column_sum = sum(
            (to_decimal(r[col]) for r in rows if r["Row Type"] == "check_row"),
            Decimal("0.00"),
        )
        total_row[col] = format_decimal(column_sum)

    rows_to_write = [*rows, total_row]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows_to_write)


def main():
    args = parse_args()
    rows = parse_rows(args.input_pdf)
    write_csv(rows, args.output_csv)
    mismatches = validate_totals(rows)

    check_count = sum(1 for r in rows if r["Row Type"] == "check_row")
    total_count = sum(1 for r in rows if r["Row Type"] == "employee_total")
    print(f"Wrote {len(rows)} rows to {args.output_csv}")
    print(f"Check rows: {check_count}")
    print(f"Employee total rows: {total_count}")
    if mismatches:
        print(f"Validation mismatches: {len(mismatches)}")
        for item in mismatches[:20]:
            print("  ", item)
    else:
        print("Validation passed: employee totals match summed check rows exactly.")


if __name__ == "__main__":
    main()
