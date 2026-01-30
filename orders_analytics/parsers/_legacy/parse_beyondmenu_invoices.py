#!/usr/bin/env python3
import argparse
import csv
import html
import mailbox
import os
import re
from typing import Dict, List, Optional, Tuple


def extract_parts(msg) -> Tuple[str, str]:
    html_part = ""
    text_part = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/html" and len(decoded) > len(html_part):
                html_part = decoded
            elif content_type == "text/plain" and len(decoded) > len(text_part):
                text_part = decoded
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_part = decoded
            else:
                text_part = decoded
    return html_part, text_part


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_tags(fragment: str) -> str:
    fragment = re.sub(r"<br\\s*/?>", "\n", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return normalize_space(html.unescape(fragment))


def normalize_money(value: str) -> str:
    cleaned = value.replace("$", "").replace(",", "").strip()
    return cleaned


def extract_restaurant_name(html_text: str, text_part: str) -> str:
    candidates: List[str] = []
    known = ["Aroma Pizza and Pasta", "Ameci Pizza and Pasta"]

    if html_text:
        html_text = html.unescape(html_text)
        for label in ["Restaurant Name:", "Company:", "DBA:"]:
            match = re.search(
                rf"{label}\s*</td>\s*<td[^>]*>\s*([^<]+)",
                html_text,
                re.IGNORECASE,
            )
            if match:
                candidates.append(normalize_space(match.group(1)))
        for name in known:
            if re.search(re.escape(name), html_text, re.IGNORECASE):
                candidates.append(name)
        for dba in re.findall(r"DBA:\\s*([^<\\n]+)", html_text, re.IGNORECASE):
            candidates.append(normalize_space(dba))
    if text_part:
        for line in text_part.splitlines():
            if line.strip().lower().startswith("restaurant name:"):
                candidates.append(normalize_space(line.split(":", 1)[1]))
            if line.strip().lower().startswith("company:"):
                candidates.append(normalize_space(line.split(":", 1)[1]))
            if line.strip().lower().startswith("dba:"):
                candidates.append(normalize_space(line.split(":", 1)[1]))
        for name in known:
            if re.search(re.escape(name), text_part, re.IGNORECASE):
                candidates.append(name)
    for name in known:
        if name in candidates:
            return name
    return candidates[0] if candidates else ""


def normalize_provider(restaurant: str) -> str:
    name = restaurant.lower()
    if "aroma" in name:
        return "AROMA"
    if "ameci" in name:
        return "AMECI"
    return ""


def html_to_lines(html_text: str) -> List[str]:
    text = html.unescape(html_text)
    text = re.sub(r"<br\\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</td>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</tr>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\r", "")
    lines = [normalize_space(line) for line in text.split("\n")]
    return [line for line in lines if line]


LABEL_PATTERNS = {
    "Start Date:": ["Start Date:"],
    "End Date:": ["End Date:"],
    "Billing Date:": ["Billing Date:"],
    "Balance:": ["Balance:"],
    "Total Amount:": ["Total Amount:"],
    "Active Order Count:": ["Active Order Count:", "Active Orders"],
    "Void Order Count:": ["Void Order Count:", "Void Orders"],
    "Tip Total:": ["Tip Total:"],
    "Delivery Fee Total:": ["Delivery Fee Total:"],
    "Tax Total:": ["Tax Total:"],
    "Order Amount Total:": ["Order Amount Total:"],
    "Order Amount Subtotal:": ["Order Amount Subtotal:"],
    "3% Before Tax:": ["3% Before Tax:"],
    "Fax Count:": ["Fax Count:"],
    "Fax Fee ($0.12/fax)": ["Fax Fee ($0.12/fax)", "Fax Fees"],
    "Phone Count:": ["Phone Count:"],
    "Phone Fee ($0.08/call)": ["Phone Fee ($0.08/call)", "Phone Fees"],
    "Online CC Collected": ["Online CC Collected", "Online CC Amount:"],
    "Online CC Processing Fee": ["Online CC Processing Fee", "Online CC Fee:"],
    "BeyondMenu Convenience Fee": ["BeyondMenu Convenience Fee", "Convenience Fee:"],
    "Order Commissions": ["Order Commissions"],
    "Payment Due By:": ["Payment Due By:"],
    "Pay Method:": ["Pay Method:"],
}


def extract_label_map(lines: List[str]) -> Dict[str, str]:
    labels: Dict[str, str] = {}
    lower_lines = [line.lower() for line in lines]

    def is_label(line: str) -> bool:
        line_lower = line.lower()
        for patterns in LABEL_PATTERNS.values():
            for pat in patterns:
                if line_lower.startswith(pat.lower()):
                    return True
        return False

    for idx, line in enumerate(lines):
        for canon, patterns in LABEL_PATTERNS.items():
            for pat in patterns:
                if line.lower().startswith(pat.lower()):
                    rest = normalize_space(line[len(pat):])
                    if rest:
                        labels[canon] = rest
                    else:
                        if idx + 1 < len(lines) and not is_label(lines[idx + 1]):
                            labels[canon] = lines[idx + 1]
                    break
    return labels


def extract_invoice_row(html_text: str, text_part: str) -> Optional[Dict[str, str]]:
    if "Order Summary" not in html_text and "Billing Date" not in html_text:
        return None
    restaurant = extract_restaurant_name(html_text, text_part)
    provider = normalize_provider(restaurant)
    lines = html_to_lines(html_text)
    if text_part:
        lines += [normalize_space(l) for l in text_part.splitlines() if normalize_space(l)]
    flat_text = " ".join(lines)
    labels = extract_label_map(lines)

    def get(label: str) -> str:
        return labels.get(label, "")

    def find_first(patterns: List[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, flat_text, re.IGNORECASE)
            if match:
                return normalize_space(match.group(1))
        return ""

    row = {
        "platform": "BEYONDMENU",
        "provider": provider,
        "restaurant": restaurant,
        "start_date": find_first([r"Start Date:\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})"]) or get("Start Date:"),
        "end_date": find_first([r"End Date:\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})"]) or get("End Date:"),
        "billing_date": find_first([r"Billing Date:\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})"]) or get("Billing Date:"),
        "balance": normalize_money(find_first([r"Balance:\s*\$?(-?[0-9,\.]+)"]) or get("Balance:")),
        "total_amount": normalize_money(find_first([r"Total Amount:\s*\$?(-?[0-9,\.]+)"]) or get("Total Amount:")),
        "active_order_count": find_first([r"Active Order Count:\s*([0-9-]+)", r"Active Orders\s*([0-9-]+)"]) or get("Active Order Count:"),
        "void_order_count": find_first([r"Void Order Count:\s*([0-9-]+)", r"Void Orders\s*([0-9-]+)"]) or get("Void Order Count:"),
        "tip_total": normalize_money(find_first([r"Tip Total:\s*\$?(-?[0-9,\.]+)"])),
        "delivery_fee_total": normalize_money(find_first([r"Delivery Fee Total:\s*\$?(-?[0-9,\.]+)"])),
        "tax_total": normalize_money(find_first([r"Tax Total:\s*\$?(-?[0-9,\.]+)"])),
        "order_amount_total": normalize_money(find_first([r"Order Amount Total:\s*\$?(-?[0-9,\.]+)"])),
        "order_amount_subtotal": normalize_money(find_first([r"Order Amount Subtotal:\s*\$?(-?[0-9,\.]+)"])),
        "percent_before_tax": normalize_money(find_first([r"3% Before Tax:\s*\$?(-?[0-9,\.]+)"])),
        "fax_count": find_first([r"Fax Count:\s*([0-9-]+)"]),
        "fax_fee": normalize_money(find_first([r"Fax Fee \(\$0\.12/fax\)\s*\$?(-?[0-9,\.]+)", r"Fax Fees\s*\$?(-?[0-9,\.]+)"])),
        "phone_count": find_first([r"Phone Count:\s*([0-9-]+)"]),
        "phone_fee": normalize_money(find_first([r"Phone Fee \(\$0\.08/call\)\s*\$?(-?[0-9,\.]+)", r"Phone Fees\s*\$?(-?[0-9,\.]+)"])),
        "misc_fee": normalize_money(find_first([r"Misc /[^\s]*\s*\$?(-?[0-9,\.]+)"])),
        "online_cc_collected": normalize_money(find_first([r"Online CC Collected\s*\$?(-?[0-9,\.]+)", r"Online CC Amount:\s*\$?(-?[0-9,\.]+)"])),
        "online_cc_processing_fee": normalize_money(find_first([r"Online CC Processing Fee\s*\$?(-?[0-9,\.]+)", r"Online CC Fee:\s*\$?(-?[0-9,\.]+)"])),
        "beyondmenu_convenience_fee": normalize_money(find_first([r"BeyondMenu Convenience Fee\s*\$?(-?[0-9,\.]+)", r"Convenience Fee:\s*\$?(-?[0-9,\.]+)"])),
        "order_commissions": normalize_money(find_first([r"Order Commissions\s*\$?(-?[0-9,\.]+)"])),
        "payment_due_by": get("Payment Due By:"),
        "pay_method": get("Pay Method:"),
        "send_to_restaurant": normalize_money(find_first([r"Send to Restaurant:\s*\$?(-?[0-9,\.]+)"])),
    }
    if not row["start_date"] or not row["end_date"]:
        match = re.search(
            r"Orders from\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})\s*to\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})",
            flat_text,
            re.IGNORECASE,
        )
        if match:
            row["start_date"] = row["start_date"] or match.group(1)
            row["end_date"] = row["end_date"] or match.group(2)
    for key in ["payment_due_by", "pay_method"]:
        val = row.get(key, "")
        if not val or ":" in val or val.lower() in {"order summary", "fax"}:
            row[key] = ""
    return row


def dedupe_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = {}
    deduped = []
    for row in rows:
        key = "|".join(
            [
                row.get("restaurant", ""),
                row.get("start_date", ""),
                row.get("end_date", ""),
                row.get("billing_date", ""),
            ]
        )
        if key in seen:
            continue
        seen[key] = True
        deduped.append(row)
    return deduped


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse BeyondMenu billing/invoice summaries into CSV."
    )
    parser.add_argument(
        "--mbox",
        default="TakeoutESBM/Mail/Billings-BeyondMenu.mbox",
        help="Path to Billings-BeyondMenu.mbox",
    )
    parser.add_argument(
        "--out",
        default="orders_analytics/data/normalized/beyondmenu_invoice_summaries.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    rows: List[Dict[str, str]] = []
    total_messages = 0
    mbox = mailbox.mbox(args.mbox)
    for msg in mbox:
        total_messages += 1
        html_text, text_part = extract_parts(msg)
        if not html_text:
            continue
        row = extract_invoice_row(html_text, text_part)
        if row:
            rows.append(row)

    rows = dedupe_rows(rows)

    fieldnames = [
        "platform",
        "provider",
        "restaurant",
        "start_date",
        "end_date",
        "billing_date",
        "balance",
        "total_amount",
        "send_to_restaurant",
        "active_order_count",
        "void_order_count",
        "tip_total",
        "delivery_fee_total",
        "tax_total",
        "order_amount_total",
        "order_amount_subtotal",
        "percent_before_tax",
        "online_cc_collected",
        "online_cc_processing_fee",
        "beyondmenu_convenience_fee",
        "order_commissions",
        "fax_count",
        "fax_fee",
        "phone_count",
        "phone_fee",
        "misc_fee",
        "payment_due_by",
        "pay_method",
    ]
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Read {total_messages} messages, wrote {len(rows)} invoices to {args.out}")


if __name__ == "__main__":
    main()
