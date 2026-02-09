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
  - Commission/tax logic: Foodee billings reflect the 15% commission (net 85% payout), so we divide by 0.85 to recover the true subtotal. `payout` = billings (plus adjustments), `subtotal = payout / 0.85`, `commission_fee = -(subtotal - payout)`, `tax_withheld = subtotal * 0.0775`.
  - Manual adjustments in `data/raw/foodee/adjustments_raw.csv` (applied to billings total before recomputing).
  - `payout` is mapped from billings (amount_paid/invoice_total). `total` is computed as subtotal + tax + tip + delivery_fee.

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
  - Allocates statement commission (25%) and merchant fee (2%) across all orders by subtotal, with round-robin cents to match the statement totals exactly.
  - Applies statement payout (`Balance pay`) and settlement ID to each order row.
- Normalization merges billings and overrides `subtotal/tax` when available; mismatches recorded in `errors`.
 - All orders are pickup.
 - `total` = subtotal + tax (+ tip/delivery_fee if present).
 - `payout` = total + commission_fee + processing_fee.
- Manual cancellations live in `data/raw/foodrunners/cancellations_raw.csv` and are removed from normalized output.

## Foodja
- Source: `data/raw/foodja/oex-orders-01-28-26.csv`
- Parser: `parsers/foodja/parse_foodja_orders.py`
  - Commission fee = 30% of subtotal (negative).
  - Tax withheld = 7.75% of subtotal.
  - `payout` = subtotal + commission_fee + processing_fee.

## Brygid
- Sources:
  - Email orders: `Takeout/Mail/Orders-Brygid.mbox` (HTML emails)
  - Report CSVs: `Takeout/reports2022/Ameci/**/brygid*.csv` (non-billing)
- Email parser: `parsers/brygid/extract_brygid_orders_raw.py`
  - Only ingests messages from `onlineorders@brygid.com` or `no-reply@brygid.online` to avoid support threads.
  - Captures Order#, Placed On, customer name/phone/email, payment type (cash vs card), totals (subtotal/tax/tip/delivery/total).
  - Tax parser handles `Sales Tax (7.75%)` labels.
  - Item parsing uses qty lines (e.g., `1` followed by item name) to compute `item_count`.
  - Address uses `Street` + `City/State` lines when present.
  - Order type inferred from “Online Order (Delivery/Takeout)” header.
- Report CSV aggregation: `orders_analytics/scripts/brygid_aggregate_report_csvs.py`
  - Keeps only `STATUS=Completed`.
  - Adds `source_file`, `added_at`, `delivery_fee` (zip rules; delivery only), and `import_notes=unseen_zip` (delivery only).
  - Delivery fee rules (when CSVs don't include one): ZIP `92618`=$5, `92610`=$4, `92691`=$4, `92630`=$3, else $3 + `unseen_zip` note.
- Report CSV normalization (for review): `orders_analytics/scripts/brygid_normalize_report_csvs.py`
  - Maps report columns into raw schema; `order_type` → delivery/pickup, `payment_type` cash vs credit.
  - Adds `order_datetime_parsed` (ISO) for CSV date strings like `MM/DD/YYYY HH:MM`.
- Merge logic (source of truth is email): `orders_analytics/scripts/brygid_merge_email_csv_orders.py`
  - Dedupes each source by `order_id` before merging.
  - Coalesces missing fields from CSVs; `delivery_fee` prefers email if present.
  - Produces merged `orders_analytics/data/raw/brygid/orders_raw.csv`.
- Normalizer: `parsers/brygid/normalize_brygid_from_raw.py`
  - Parses email `Placed On` format and CSV `MM/DD/YYYY HH:MM` format.
  - Excludes cancellations listed in `orders_analytics/data/raw/brygid/cancellations_raw.csv`.
  - Allocates commission per billing period:
    - If totals match, commissions are allocated by subtotal to match billed service fees.
    - If totals do not match, a `PERIOD_YYYYMMDD_MANUAL` row is added when `|total_sales_diff| > 1.00` with:
      - `total` = `-total_sales_diff` (to reconcile totals),
      - `subtotal`/`tax` derived with 7.75% tax (`subtotal * 0.0775 = tax`, `subtotal + tax = total`),
      - `payment_type=credit`, `order_type=pickup`, and `order_datetime` set to the billing date.
    - Commissions are then allocated by order count across all period rows (including manual row, weighted by `max(1, |order_count_diff|)`), so `service_fees_diff_norm` should be 0 when including manual rows.
- Cancellations file: `orders_analytics/data/raw/brygid/cancellations_raw.csv`
  - Built from holiday closures (Thanksgiving/Christmas) and manual matches of period total differences.
  - Typically populated by reviewing `commission_check.csv` and adding order_ids that exactly match `total_sales_diff` for periods where `order_count_diff > 0`.

## BeyondMenu
- Source: `orders_analytics/data/raw/beyondmenu/BeyondMenu_Order_History.csv`
- Parser: `parsers/beyondmenu/parse_beyondmenu_orders.py` (CSV import)
  - Filters `Status=active` only; inactive orders are excluded.
  - Order datetime: `Req Time` + `year` using `MM/DD HH:MM am/pm` format.
  - Provider/restaurant: provider normalized from `Store`; Aroma/Ameci names standardized.
  - Address: title-cased with state abbreviation preserved.
  - Fees: `Merchant Fee`, `Commission Fee`, and `Misc Fee` are negated.
  - Payment type: from `Payment Type` (or `Payment`) normalized.

## EatStreet
- Sources: `Takeout/Mail/Orders-Eatstreet.mbox`, `Takeout/Mail/Billings-Eatstreet.mbox`
- Orders parser: `parsers/eatstreet/extract_eatstreet_orders_raw.py`
  - Header extraction scans `<td>` blocks and selects the one where the first span is `PICKUP/DELIVERY` and the next span is the restaurant name.
  - Fixes cases where “Order ready for pickup at:” appeared before the restaurant line.
- Normalizer: `parsers/eatstreet/normalize_eatstreet_from_raw.py` (BaseParser)
  - Commission/processing fees are always negative (if present).
  - If tax is missing and year >= 2020, `tax_withheld` is estimated at 7.75% of subtotal.
  - If fees are missing, estimates: commission = 15% of subtotal; processing = 4.3% of subtotal.
  - Payment type is overridden to cash when billings `payment_method` = cash.

## MenuStar
- Sources: `Takeout/Mail/Orders-Menustar.mbox`, `Takeout/Mail/Billings-Menustar.mbox`
- Orders parser: `parsers/menustar/extract_menustar_orders_raw.py` (email HTML)
- Billings parser: `parsers/menustar/extract_menustar_billings_raw.py` (CSV/XLSX attachments)
  - Statement summary fields captured: all orders, prepaid orders, fees, adjustments, net payout.
  - Statement fees are allocated across orders by subtotal with round‑robin cents to match statement totals.
  - Filters out non‑Aroma Ameci locations: allows `Ameci Pizza & Pasta` (plain), allows numeric suffixes (e.g., “(1)”), allows `(...Trabuco...)`, and excludes known other locations (Castaic, Newhall, Woodland Hills, San Fernando, Mission Blvd).
  - Dedupes statement rows by provider + order_datetime + order_type + payment_type + amounts (subtotal/tax/delivery_fee/tip/total). Date string is normalized before comparison.
  - When duplicate rows collide, prefers the row with the most non‑blank fields; if tied, prefers the latest `statement_email_date`.
  - Skipped statements are printed with email date + filename for audit.
- Normalizer: `parsers/menustar/normalize_menustar_from_raw.py`
  - Billings do not include order_id; matching uses provider + order_date and strict amount/type/payment matching.
  - Second‑pass matching fixes bad billing dates: for unmatched orders and billings, matches on strict amounts/types and closest date, then records `notes=order_date=... billing_date=...` and uses order date for normalized output.
  - Writes back matched order_id into `billings_raw.csv` for audit.
  - Commission is 70% of MenuStar fees and processing is 30% (cash orders get commission only).
  - Drops rows with missing order_id after merge (billing‑only rows with no match).
  - Statement adjustments are statement‑level; applied once per statement to a single matched order with `notes=statement_adjustment_applied`.
  - Missing-match reports are written to `data/raw/menustar/orders_missing_billings.csv` and `data/raw/menustar/billings_missing_orders.csv` (rows with all zero/blank amounts are filtered).

## Office Caterer
- Sources: `Takeout/Mail/Orders-OfficeCaterer.mbox`, `Takeout/Mail/Billings-OfficeCaterer.mbox` (PDF attachments)
- Parser: `parsers/officecaterer/extract_officecaterer_orders_raw.py`
  - Order ID: `P.O. NO.`
  - Order date/time: `DATE` + `PICK UP TIME`
  - Tax: line containing `Tax` / `Taxes` (e.g., “California Department of Tax…”)
  - Total: `TOTAL $...`
  - Subtotal: sum of line-item amounts if possible, else `total - tax`
  - Commission: Office Caterer charges a flat 30% on subtotal; we split as 27% commission + 3% processing (both negative) in normalized output.
- Billings parser: `parsers/officecaterer/extract_officecaterer_billings_raw.py`
  - Pulls per-order `amount` (subtotal), `tax`, `commission`, and `payable amount` from statement PDFs.
  - Captures statement date, period start/end, and restaurant name.
- Normalization: `parsers/officecaterer/normalize_officecaterer_from_raw.py`
  - Billings `payout` is mapped to normalized `payout` (removed from notes).

## ezCater
- Source: `data/raw/ezcater/ezcater_all_orders_from_2020_2020-01-01_2026-01-01_2026-01-29 - Order Data.csv`
- Parser: `parsers/ezcater/parse_ezcater_orders.py`
  - `payout` is mapped from `Caterer Total Due`.

## Cater2Me
- Sources: `Takeout/Mail/Orders-Cater2Me.mbox`, `Takeout/Mail/Billings-Cater2Me.mbox`
- Normalization: `parsers/cater2me/normalize_cater2me_from_raw.py`
  - `total` = pre_tax + tip + adjustments_delivery_fee (computed).
  - `payout` is mapped from billings `order_total`.

## Menufy
- Sources: `Takeout/Menufy/orders/**/Orders Paid Online*.csv`, `Takeout/Menufy/orders/**/Orders Paid In-Store*.csv`
- Customers: `Takeout/Menufy/Customer_Emails_02-05-2026.csv`, `Takeout/Menufy/Customer_Delivery_Addresses_02-05-2026.csv`
- Refunds: `Takeout/Menufy/orders/**/Refunds.csv` (matched by date + location + customer name)
- Parser: `parsers/menufy/extract_menufy_orders_raw.py`
  - Payment type: “Paid Online” → credit, “Paid In‑Store” → cash.
  - Order type: delivery if `Customer Carryout or Delivery Charge` > 0, else pickup.
  - Refunds: stored as `adjustments` with `notes=refund=<amount>`.
  - Customer email/address matched by phone if available, else by full name.
  - `order_id` is a deterministic hash of date+location+customer+amounts+payment_type (since Menufy exports lack order ids).
 - Normalizer: `parsers/menufy/normalize_menufy_from_raw.py`
   - `upcharges` + `customer_fees` → `adjustments` (positive).
   - `customer_fees` → `commission_fee` (negative).
   - `restaurant_fees` → `processing_fee` (negative).
   - `delivery_service` → `misc_fee`.
   - `tax_withholdings` → `tax_withheld`.
 - `tax_payout` should match `tax`; mismatch adds `errors=tax_payout_mismatch`.
  - `total_payout` is mapped to `payout`.

## Slice
- Source: `Takeout/Slice/*.pdf` (Order Activity Report)
- Parser: `parsers/slice/extract_slice_orders_raw.py`
  - Reads the Orders table (page 2+).
  - Captures Date/Time, Order ID, payment type (Credit/Phone), order type (Pickup/Delivery), Subtotal, Customer Delivery Fee, Order Adjust., Tax, Tips, Order Total, Partnership Fee, Processing Fee.
- Normalization: `parsers/slice/normalize_slice_from_raw.py`
  - `payout` = total + partnership_fee + processing_fee - tax_withheld (tax column).
  - Order datetime is built from the date line + the time line beneath each row.

## ChowNow
- Sources:
  - Orders: `Takeout/Mail/Orders-ChowNow.mbox`
  - Billings: `Takeout/Mail/Billings-ChowNow.mbox` (xls attachments)
- Orders parser: `parsers/chownow/extract_chownow_orders_raw.py`
  - Parses plain-text emails for order details, customer info, and totals.
  - Order type is inferred from `Order Type` (Pickup/Delivery/Uber).
  - Support Local Fee (if present) is appended to `notes` and captured for totals math.
  - Promotions:
    - `Promotions:` line captured when present.
    - If the email shows “$X of your credit has been applied…”, promotions are set to `-X.XX`.
    - When both “Grand Total” and “Total” appear, `Grand Total` wins for `total`.
    - If promotions are present and no explicit customer paid line exists, `total` is recomputed as
      subtotal + tax + tip + delivery_fee + support_local_fee, and `customer_paid` is set to the
      original total (customer paid).
  - Adds `customer_paid` column when present in the email.
  - Customer emails are enriched from:
    - `Takeout/Chownow/CustomerOrders_lastran_06Feb26.xls`
    - `Takeout/Chownow/CustomerOrders_lastran_06Feb26 (1).xls`
    - Match is case/whitespace-insensitive on customer name.
- Billings parser: `parsers/chownow/extract_chownow_billings_raw.py`
  - Reads DisbursementReport/Daily/Weekly/Monthly XLS attachments.
  - Keeps only rows with `Order Id` (drops daily summary/Net Disbursement rows).
  - Normalizes Order Id as integer string (no .0).
- Normalization: `parsers/chownow/normalize_chownow_from_raw.py`
  - Billings is source of truth; orders_raw used for customer info + order notes.
  - Order datetime prefers billings `Order Date` + `Order Time (PST)`; fallback to orders_raw.
  - Provider/restaurant fall back to billings `Restaurant Name` if missing; provider inferred from restaurant.
  - `Order Type = Full Refund` rows are not emitted as separate records; refund amounts are summed into
    `adjustments` for the matching order_id, with `refund_total=...` in notes.
  - `payout` is taken from Disbursement Amount, including any Full Refund disbursement rows rolled into
    the original order_id payout.
  - Support Local Fee handling:
    - If support_local_fee exists in orders_raw notes, `total` = billing Gross + support_local_fee.
    - `adjustments` includes a negative support_local_fee to offset payout.
    - `expected_payout` adds support_local_fee on top of the base payout math (ChowNow-only override).
  - Promotions / Bucks:
    - `Bucks` in billings are treated as positive and mapped to `marketing_fee` as negative.
    - If Bucks is present, it overrides promotions from orders; otherwise promotions are used.
  - Flex delivery:
    - Delivery fee = `Delivery Fee` + `Flex Delivery Fee`.
    - Flex delivery fee + flex tips are added to notes (only when non-zero).
    - If Flex Delivery Fee is present and order_type is delivery, the order is treated as pickup.
  - Payment type:
    - If Card Type includes “cash” or “collect”, payment_type = cash; else credit.
  - Test orders:
    - Any order where customer_name contains “test order” is dropped from normalized output.
