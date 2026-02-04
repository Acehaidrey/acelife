# Provider Notes

## delivery.com
- Source: `Takeout/Mail/Orders-DeliveryCom.mbox` (HTML in text/html or text/plain)
- Parser: `orders_analytics/parsers/deliverycom/parse_deliverycom_orders.py`
- Order ID: `Order #<digits>` from email body.
- Restaurant name: line after “Delivery.com Order Confirmation”.
- Order type: line containing `Pickup` or `For delivery` / `Delivery`.
- Payment type: `Prepaid (Do not collect payment)` → credit; `Cash` lines with “collect” → cash.
- Order datetime: prefers `Order placed: MM/DD HH:MM am/pm` (year inferred from email date); fallback uses date+time lines (e.g., “Today 10/19” + “11:45 am”).
- Customer name/phone/address: name after payment line; address lines before phone number (if present). Pickup orders often have no address.
- Totals: Subtotal / Tax / Tip / Delivery fee / Customer paid extracted from label lines.
- Items: naive parse between `Qty` and `Customer paid` / `Subtotal`; captures item names and counts; options lines may be skipped.
- Notes: “SPECIAL INSTRUCTIONS” block appended to notes.
- Known quirk: some “FUTURE DELIVERY (Hold)” lines can be captured as an item; needs refinement if you want to drop those.

Billings:
- Source: `Takeout/Mail/Billings-DeliveryCom.mbox`
- Parser: `orders_analytics/parsers/deliverycom/extract_deliverycom_billings_raw.py`
- Pulls per-order rows from the “charge-table” (`OID`, `Time`, `SubT`, `Tip`, `Tax`, `DF`, `SF`, `Payment`, `TIA`).
- Captures invoice metadata when available: invoice ID, account number, and restaurant name.
- Service Fee is stored in `service_fee` (raw only), Payment/Total Invoice are captured as provided (may be negative).
- Tax rows sometimes show tags like `[EXPT]`; parser captures `tax_note` and normalizes the numeric tax.

Concerns / follow-ups:
- Address extraction for delivery orders is heuristic; if delivery orders are missing addresses, need to inspect additional samples.
- Item parsing is simplistic; may miss modifiers or quantities.
- Email sometimes has “FUTURE DELIVERY (Hold)” blocks; currently not captured in notes.
- Billings rows are merged into normalized output; billings values override orders values for subtotal/tax/tip/delivery_fee/total and mismatches are recorded in `errors`.

## Foodee
- Sources: `Takeout/Mail/Orders-Foodee.mbox`, `Takeout/Mail/Billings-Foodee.mbox`
- Orders parser: `parsers/foodee/extract_foodee_orders_raw.py` (email text, no PDF attachments)
  - Order ID: `IRV-xxxxxx` tokens in “Order Summary” section.
  - Order datetime: from `Order Pickup time` line (month/day + time) with year inferred from email date.
  - Subtotal/Total: lines `Subtotal $...`, `Total $...` (tax often missing).
  - Items: parsed from Qty/Item/Price block; item_count from “Number of items”.
  - Notes: marks canceled orders as `status=canceled`.
- Billings parser: `parsers/foodee/extract_foodee_billings_raw.py` (PDF remittance advice)
  - Pulls `invoice_date`, `payment_date`, `invoice_total`, `amount_paid`, `still_owing` by reference order ID.
  - Adds provider/restaurant/address from remittance advice (Aroma Pizza & Pasta, 20491 Alton Parkway).
- Normalization merges billings and overrides `total` with billings `amount_paid` (or invoice total). Mismatches recorded in `errors`.
  - All orders are pickup.
  - Drops `status=canceled` / `status=inactive` from normalized output.
  - Commission/tax logic: Foodee billings reflect the 15% commission (net 85% payout), so we divide by 0.85 to recover the true subtotal. `total` = billings (plus adjustments), `subtotal = total / 0.85`, `commission_fee = -(subtotal - total)`, `tax_withheld = subtotal * 0.0775`.
  - Manual adjustments in `data/raw/foodee/adjustments_raw.csv` (applied to billings total before recomputing).

## Food Runners
- Sources: `Takeout/Mail/Orders-FoodRunners.mbox`, `Takeout/Mail/Billings-FoodRunners.mbox`
- Orders parser: `parsers/foodrunners/extract_foodrunners_orders_raw.py` (PDF attachments)
  - Order ID: `INVOICE #<digits>`
  - Order date/time: `Date:` + `Pick-up Time:`
  - Subtotal: `Food Total $...`
  - Restaurant name: from `Restaurant Information` block; provider inferred from name.
- Notes: `Restaurant Instructions` block (if present)
- Billings parser: `parsers/foodrunners/extract_foodrunners_billings_raw.py` (PDF payments summary)
  - Pulls per-order `subtotal` and `tax` from statement table.
  - Captures commission/merchant fee and payout only when statement has a single order.
- Normalization merges billings and overrides `subtotal/tax` when available; mismatches recorded in `errors`.
 - All orders are pickup.
 - Manual cancellations live in `data/raw/foodrunners/cancellations_raw.csv` and are removed from normalized output.

## Office Caterer
- Source: `Takeout/Mail/Orders-Office Caterer.mbox` (PDF attachments)
- Parser: `parsers/officecaterer/extract_officecaterer_orders_raw.py`
  - Order ID: `P.O. NO.`
  - Order date/time: `DATE` + `PICK UP TIME`
  - Tax: line containing `Tax` / `Taxes` (e.g., “California Department of Tax…”)
  - Total: `TOTAL $...`
  - Subtotal: sum of line-item amounts if possible, else `total - tax`
  - Commission: Office Caterer charges a flat 30% on subtotal; we split as 27% commission + 3% processing (both negative) in normalized output.
