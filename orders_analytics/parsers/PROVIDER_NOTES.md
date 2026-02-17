# Provider Notes

## Table of Contents
- [BeyondMenu](#beyondmenu)
- [Brygid](#brygid)
- [Cater2Me](#cater2me)
- [ChowNow](#chownow)
- [delivery.com](#deliverycom)
- [EatStreet](#eatstreet)
- [ezCater](#ezcater)
- [Food Runners](#food-runners)
- [Foodee](#foodee)
- [Foodja](#foodja)
- [Grubhub](#grubhub)
- [Menufy](#menufy)
- [MenuStar](#menustar)
- [Office Caterer](#office-caterer)
- [Order Inn](#order-inn)
- [Slice](#slice)
- [Uber Eats](#uber-eats)
- [MealHi5](#mealhi5)

## BeyondMenu
- Source: `orders_analytics/data/raw/beyondmenu/beyond_menu_order_history.csv` (downloaded from Google Sheets)
- Annual billing summary: `orders_analytics/data/raw/beyondmenu/beyond_menu_annual_billing_summary.csv` (downloaded, not used yet)
- Parser: `parsers/beyondmenu/parse_beyondmenu_orders.py` (CSV import)
  - Filters `Status=active` only; inactive orders are excluded.
  - Order datetime: `Req Time` + `year` using `MM/DD HH:MM am/pm` format.
  - Provider/restaurant: provider normalized from `Store`; Aroma/Ameci names standardized.
  - Fees: `Merchant Fee` and `Commission Fee` are negated.
  - `Misc Fee` is kept as provided (may be negative).
  - `Convenience Fee` is added to `misc_fee`, and also added as a **negative** amount in `adjustments` so totals net out.
  - Notes include `convenience_fee=<amount>` for rows with a convenience fee.
  - Payment type: from `Payment Type` (or `Payment`) normalized.
  - Total-components validation uses `subtotal + tax + tip + delivery_fee + adjustments` (misc fees are handled via adjustments).
  - Additional charges (e.g., Domain Renew Annual Fee $25) are treated as annual billing adjustments and distributed across active orders as `misc_fee` for the matching provider/year.
  - Annual billing adjustments (Additional Charges + Credits):
    - Net annual adjustment per provider/year = `-(additional_charges + credits)` from the annual billing summary.
    - Net adjustment is distributed across **active** orders in that provider/year, proportional to subtotal with cent‑balancing, and applied to `misc_fee`.
    - Notes added:
      - `additional_charges_distribution` for standard allocations.
      - `partial_additional_charges_distribution` for Aroma 2024 (see below).
    - Special handling for Aroma:
      - 2023: apply the 2024 credits (`-89.25`) to offset the 2023 additional charges (`89.25`), so net is 0 in 2023.
      - 2024: apply only the remaining additional charges (`119.35 - 89.25 = 30.10`) across active orders **excluding** order `101559574`.
      - Order `101559574` (2024) already carries the chargeback amount in misc fee and should not receive further allocation.
      - If `101559574` is the only active 2024 order, it will receive the remaining additional charges so the annual totals reconcile.

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
- Google Sheet supplement: `brygid_jan202020_june262020` (sheet_id `1Z-XdTaH8xmh4hkiJPkRDlYMZh0yykH3oIBCuRJ_vuw4`, gid `63449493`)
  - Downloaded to `Takeout/reports2022/Ameci/brygid_jan202020_june262020.csv` via the registry and included in the report CSV aggregation.
  - The file is CSV (not TSV); the aggregator detects single-column CSV/TSV headers and reparses accordingly.
  - If `STATUS` is blank, rows are treated as completed (included).
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
  - If `total < subtotal + tax + tip + delivery_fee`, subtracts `delivery_fee` from `subtotal` and records `notes=subtotal_adjusted_for_delivery_fee`.
  - Merchant processing allocation:
    - Reads `orders_analytics/data/raw/brygid/brygid_merchant_processing_statements.csv` (filtered from Wave).
    - Excludes transaction id `1949452684062893206`.
    - Transaction dates apply to the previous month; fees are allocated across credit orders by `total`
      and rounded to cents to match the statement total.
    - Allocation check output: `orders_analytics/data/raw/brygid/brygid_processing_allocation_check.csv`.
  - Allocates commission per billing period:
    - Brygid billing periods run **15th → 14th** (previous month to current month).
    - Processing statements are **calendar month** based; therefore they are offset differently.
    - If totals match, commissions are allocated by subtotal to match billed service fees.
    - If totals do not match, a `PERIOD_YYYYMMDD_MANUAL` row is added when `|total_sales_diff| > 1.00` with:
      - `total` = `-total_sales_diff` (to reconcile totals),
      - `subtotal`/`tax` derived with 7.75% tax (`subtotal * 0.0775 = tax`, `subtotal + tax = total`),
      - `payment_type=credit`, `order_type=pickup`, and `order_datetime` set to the billing date.
    - Commissions are then allocated by order count across all period rows (including manual row, weighted by `max(1, |order_count_diff|)`), so `service_fees_diff_norm` should be 0 when including manual rows.
  - Cancellations file: `orders_analytics/data/raw/brygid/cancellations_raw.csv`
  - Built from holiday closures (Thanksgiving/Christmas) and manual matches of period total differences.
  - Typically populated by reviewing `commission_check.csv` and adding order_ids that exactly match `total_sales_diff` for periods where `order_count_diff > 0`.

## Cater2Me
- Sources: `Takeout/Mail/Orders-Cater2Me.mbox`, `Takeout/Mail/Billings-Cater2Me.mbox`
- Normalization: `parsers/cater2me/normalize_cater2me_from_raw.py`
  - `total` = pre_tax + tip + adjustments_delivery_fee (computed).
  - `payout` is mapped from billings `order_total`.
  - `tax_withheld` is inferred as 7.75% of `pre_tax` when tax is not provided.
  - `delivery_fee` is mapped from billings `adjustments_delivery_fee`.
  - Delivery fees are not always explicit; Cater2Me may bake delivery costs into higher item prices (so delivery_fee can be blank).
- Known caveats / expectations:
  - `orders_analytics/data/raw/cater2me/cater2me_cancellations.csv` excludes canceled/voided orders from comparison + normalization.
  - Billings can include adjustments already in `order_total` for some periods; `billings_raw.csv` includes
    `adjustments_included_in_total` to indicate this, and `order_total_after_adjustments` is used for payout.
  - Comparisons may still show a small number of expected missing order_ids (e.g., billings-only records).

## ChowNow
- Sources:
  - Orders: `Takeout/Mail/Orders-ChowNow.mbox`
  - Billings: `Takeout/Mail/Billings-ChowNow.mbox` (xls attachments)
- Orders parser: `parsers/chownow/extract_chownow_orders_raw.py`
  - Parses plain-text emails for order details, customer info, and totals.
  - Manual missing orders are appended from `orders_analytics/data/raw/chownow/chownow_manual_missing_orders.csv`.
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
    - support_local_fee is captured in orders_raw notes but is not included in billings Gross.
    - Normalized `total` uses billing Gross (no support_local_fee added).
    - support_local_fee is not added to adjustments/misc_fee/expected_payout.
    - When comparing orders_raw totals to billing, we subtract support_local_fee from orders_raw
      before computing total mismatch errors.
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

## EatStreet
- Sources: `Takeout/Mail/Orders-Eatstreet.mbox`, `Takeout/Mail/Billings-Eatstreet.mbox`
- Note: 2019 billing files are missing; 2019 records are incomplete.
- Orders parser: `parsers/eatstreet/extract_eatstreet_orders_raw.py`
  - Header extraction scans `<td>` blocks and selects the one where the first span is `PICKUP/DELIVERY` and the next span is the restaurant name.
  - Fixes cases where “Order ready for pickup at:” appeared before the restaurant line.
- Billings parser: `parsers/eatstreet/extract_eatstreet_billings_raw.py`
  - Extracts provider (AMECI/AROMA) from email subject/body when present.
  - Captures `order_date`, `order_time`, and `order_type` from the statement table rows.
  - `payment_method` is set to `CARD`/`CASH` when present in row tokens.
- Cancellations:
  - `orders_analytics/data/raw/eatstreet/eatstreet_cancellations.csv` is matched by provider + order_id.
  - Cancelled orders are excluded from normalization and missing-fees reporting.
- Normalizer: `parsers/eatstreet/normalize_eatstreet_from_raw.py` (BaseParser)
  - Commission/processing fees are always negative (if present).
  - If tax is missing and year >= 2020, `tax_withheld` is estimated at 7.75% of (subtotal + tip + delivery_fee).
  - If fees are missing, estimates: commission = 15% of subtotal; processing = 4.3% of subtotal.
  - Payment type is overridden to cash when billings `payment_method` = cash.
  - Total-components validation includes tax/tax_withheld; cash orders can show inconsistencies where tax appears in total for some periods.
  - Billings-only rows (no order record) are normalized using billings fields:
    - `order_datetime` from billings `order_date` + `order_time`.
    - `order_type` from billings (`Delivery` → delivery, `Takeout` → pickup).
    - `delivery_fee` assumed $3 for delivery, $0 for pickup.
    - `subtotal` inferred as `total - tip - delivery_fee`.
    - `tax_withheld` inferred at 7.75% of (subtotal + tip + delivery_fee) for credit orders (2020+).
    - Cash orders use `tax` instead of `tax_withheld`; for 2019 all orders use `tax`.
    - Missing payment method defaults to credit with `notes=payment_type_missing`.

## ezCater
- Source: `data/raw/ezcater/ezcater_all_orders_from_2020_2020-01-01_2026-01-01_2026-01-29 - Order Data.csv`
- Parser: `parsers/ezcater/parse_ezcater_orders.py`
  - `payout` is mapped from `Caterer Total Due`.
  - Notes overrides can be supplied via `data/raw/ezcater/ezcater_notes_overrides.csv` (by `order_id`).

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
  - Adds billings metadata to notes: `statement_payout=<amount>` and `statement_id=<id>`.
  - If billings are missing for an order, fees/tax are estimated from subtotal and the note
    `billings missing; fees/tax estimated from subtotal` is added to `notes` (not `errors`).
 - All orders are pickup.
 - `total` = subtotal + tax (+ tip/delivery_fee if present).
 - `payout` = total + commission_fee + processing_fee.
- Manual cancellations live in `data/raw/foodrunners/cancellations_raw.csv` and are removed from normalized output.

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
- Normalization merges billings and overrides `total` with billings `amount_paid` (or invoice total). Mismatches are noted (see below).
  - All orders are pickup.
  - Drops `status=canceled` / `status=inactive` from normalized output.
  - Commission/tax logic: Foodee billings reflect the 15% commission (net 85% payout), so we divide by 0.85 to recover the true subtotal.
    - `total` uses the **orders** total when present (fallback to billings total).
    - `subtotal = total / 0.85`, `commission_fee = -(subtotal - total)`, `tax_withheld = subtotal * 0.0775`.
  - Manual adjustments in `data/raw/foodee/adjustments_raw.csv` are applied **only** to the `adjustments` column; they do **not** change `total` or `subtotal`.
  - `payout` is taken directly from billings (`amount_paid`/`invoice_total`) without adjustments applied.
  - When orders total != billings total, we add a note:
    `total mismatch (orders=<orders_total>, billings=<billings_total>) handled in adjustments`.

## Foodja
- Orders source: `data/raw/foodja/orders_raw.csv`.
- Billings source: XLSX exports in `Takeout/foodja/*.xlsx` (Aroma/Ameci file name infers provider).
  - Extracted to `orders_analytics/data/raw/foodja/billings_raw.csv` by `parsers/foodja/extract_foodja_billings_raw.py`.
- Parser: `parsers/foodja/parse_foodja_orders.py`
  - Orders/billings alignment:
    - Orders-only rows (receivables) are included normally (no billings yet).
    - Billings-only rows are added to normalized output with `billings_only_record` note (and use `payment_date` for `order_datetime`).
    - Subtotal mismatches between orders vs billings add a note and error: `subtotal_mismatch_orders_vs_billings`.
  - Uses billings overrides when available:
    - `subtotal` and `payout` are taken from billings if present.
    - `commission_fee` is computed as `payout - subtotal` (exact from billings).
    - Notes include `billings_override`.
  - Fallback when billings are missing:
    - `commission_fee` = 30% of subtotal (negative).
    - `tax_withheld` = 7.75% of subtotal.
    - `payout` = subtotal + commission_fee + processing_fee.
    - Notes include `billings_missing_commission_payout_estimated`.

## Grubhub
- Source: `orders_analytics/data/raw/grubhub/orders_raw.csv` (extracted from `Takeout/grubhub/*.csv`).
- Raw extract also writes `orders_analytics/data/raw/grubhub/orders_raw_deduped.csv` (grouped by `ID`, sums numeric columns, adds `merged_rows`).
- Parser: `parsers/grubhub/parse_grubhub_orders.py`
  - Dedupe: rows are grouped by `ID` and summed; notes include `merged_rows=<count>` when duplicates exist.
  - `order_datetime` uses `Date` + `Time` (time portion before comma, e.g. `7:42 PM PDT, UTC-07:00`).
  - Provider inferred from `Restaurant` name (Aroma/Ameci/Wingshop).
  - Supplemental customer info from Google Sheet `grubhub_order_history` (downloaded to `orders_analytics/data/raw/grubhub/grubhub_order_history.csv` when available).
    - Fields used: customer_name, company_name, phone, email, address, items, item_count (matched by Order ID).
    - If no exact Order ID match, we fall back to suffix matching: we take the numeric portion after `-` in the Grubhub order_id and match it to the right-hand number in `Order Number` (e.g., `71892119 — 1078152` matches any order_id ending in `1078152`). Only unique matches are applied.
  - `order_type` mapping:
    - `Self Delivery` -> delivery
    - `Pick-Up` -> pickup
    - `Grubhub Delivery` -> pickup + note `grubhub_delivery`
    - Other values -> note `fulfillment_type_raw=<value>`
  - Payment type mapping:
    - `Prepaid Order` -> credit
    - `Phone Order` -> order_type `phone_call` + payment_type `credit`
    - `Cash Order` -> payment_type `cash`
    - `Type` containing `Adjustment` or Order IDs starting with `T-` -> payment_type `credit`
    - Other values -> note `payment_type_raw=<value>`
  - Adjustments overrides: `orders_analytics/data/raw/grubhub/grubhub_adjustments.csv`
    - Columns: `order_id`, `service_fee_override`, `note`
    - Used to zero erroneous service fees and append a note.
  - Money mapping:
    - `subtotal` = Subtotal
    - `delivery_fee` = Delivery Fee
    - `tax` = Tax Fee - Tax Fee Exemption
    - `tip` = Tip
    - `total` = Restaurant Total
    - `commission_fee` = Commission + GH+ Commission + Delivery Commission
    - `processing_fee` = Processing Fee
    - `tax_withheld` = Withheld Tax + Withheld Tax Exemption
    - `adjustments` = adjustment rows total + **Service Fee**
    - `misc_fee` = Service Fee Exemption + (flexible fees)
    - `marketing_fee` = Targeted Promotion + Rewards
  - `N/A` values are treated as null/0.
  - `Description` is appended to notes as the last segment.
  - Orders with ID prefix `W-` are commission-free corporate web orders (amecipizzaandpasta.com). Notes include `commission_free_link`.
  - Adjustment rows:
    - If the Order ID starts with `T-` or any merged row has `Type` containing `Adjustment`, the sum of `Restaurant Total` for those rows is recorded as `adjustments`.
    - Notes include `adjustment_total=<amount>` when adjustments are present.
  - Cash orders:
    - If total != subtotal + delivery_fee + tax + tip, total is adjusted and note `cash_total_adjusted_from=<raw>` is added.
    - If tip is non-zero, note `cash_tip_nonzero=<amount>` is added.
  - Prefix merge: if `W-/O-/T-` rows share the same suffix and store, they are merged into one row.
    - `order_id` keeps W- first, then O-, then T-.
    - `order_datetime` uses earliest value.
    - Numeric fields are summed.
    - Notes include `merged_orders=W-...,O-...,T-...` and are token-deduped.
  - Rows where **all financial fields are zero** are dropped (canceled pairs).
  - `T-` rows force missing numeric fields to `0.00`.
  - Total-components validation includes `adjustments` for Grubhub.
  - Adjustment totals are computed via shared helper `orders_analytics/utils/grubhub_adjustments.py` for both normalized output and the deduped raw file.
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

## Order Inn
- Source: `Takeout/wave_ameci/accounting.csv` (Wave transactions).
- Extractor: `parsers/orderinn/extract_orderinn_raw.py`
  - Filters `Account Group=expense`.
  - Matches `order.*inn` (case-insensitive) in `Transaction Description` or `Transaction Line Description`.
  - Output: `orders_analytics/data/raw/orderinn/commissions_raw.csv`.
- Normalizer: `parsers/orderinn/normalize_orderinn_from_raw.py`
  - Provider is always `AMECI`.
  - Uses `Transaction Date` as `order_datetime`.
  - Uses `Amount (One column)` (fallback to debit/credit) as `commission_fee`.
  - Other money fields are blank; only commissions are represented for this provider.

## Slice
- Sources:
  - Statements PDFs: `Takeout/Slice/*.pdf` (Order Activity Report)
  - All Orders exports: `Takeout/Slice/All Orders *.xlsx`
  - Order history (customer info): `Takeout/Slice/VA Task Sheet - Slice Order History.csv`
- PDF parser: `parsers/slice/extract_slice_orders_raw.py`
  - Reads the Orders table (page 2+).
  - Captures Date/Time, Order ID, payment type (Credit/Phone), order type (Pickup/Delivery), Subtotal, Customer Delivery Fee, Order Adjust., Tax, Tips, Order Total, Partnership Fee, Processing Fee.
  - Outputs `orders_raw_from_statements.csv` + `adjustments_raw_from_statements.csv`.
- Merge script: `orders_analytics/scripts/slice_merge_orders.py`
  - Base = All Orders Excel exports.
  - Fills missing fields from Order History and then from statement PDF raw.
  - Order datetime preference: history (has time) → PDF → Excel (date-only).
  - Adds `mismatch_<field>` notes when history/PDF disagree with Excel on subtotal/tax/tip/delivery_fee/total.
  - `order_type` inferred from delivery_fee (delivery if > 0 else pickup).
  - Commission: `Flat Shop Fee` negated to `partnership_fee`.
  - Merchant processing: `CC Fee` negated to `processing_fee`.
  - Discounts: `Shop Funded Discounts Amount` → `misc_fee` + `discount_for_order=...` note.
  - `orders_raw.csv` is the merged output used for normalization.
- Normalization: `parsers/slice/normalize_slice_from_raw.py`
  - Only includes rows where payment_status is `paid` (credit) or `authorized` (cash); refunded rows are included with `adjustments = -total`.
  - `payout` is currently blank (provider payout not available yet).
  - Processing fees are only available from the PDFs; Excel files do not include them.
  - TODO: confirm/ingest all Slice discount fields and apply them to totals.
  - TODO: obtain merchant processing costs and invoice data to reconcile payouts.
  - TODO: verify total differences after discounts are applied.
  - Tax handling: orders before 2020-06-01 use `tax` (we remit). Orders on/after 2020-06-01 use `tax_withheld`.
  - `total` includes `misc_fee` (discounts) to avoid total mismatch checks; rows note `total_includes_misc_fee`.
  - Known discrepancy: some orders have tax differences between All Orders exports and Order History (e.g., order_id 144995507 has tax 1.90 vs 1.75). We currently keep the All Orders tax and are awaiting Slice support clarification.

## Uber Eats
- Source: `Takeout/uber-bc08b66d-0603-49ef-8186-07a637505732-united_states.csv`
- Parser: `parsers/ubereats/parse_ubereats_orders.py`
  - Skips first descriptive header row (`header=1`).
  - Writes rows without `Order ID` and `Workflow ID` to `orders_analytics/data/raw/ubereats/no_order_ids.csv`.
  - Provider inferred from `Store Name` (`AMECI`, `AROMA`, `WINGSHOP`, `TRATTORIA`).
  - `order_datetime` from `Order Date` + `Order Accept Time` (00:00 AM if accept time missing).
  - `order_type` defaults to pickup; if dining mode contains `Delivery - Partner Using Uber App` -> delivery.
  - `payment_type` always credit.
  - Totals mapping:
    - `subtotal` = Sales (excl. tax)
    - `tax` = Tax on Sales + Tax on Order Error Adjustments + Tax on Price Adjustments + Tax On Offers on items +
      Tax On Delivery Offer Redemptions + Tax on Marketplace Fee + Tax on Delivery Network Fee + Tax On Delivery Fee + Markup Tax
    - `total` = Total Sales after Adjustments (incl tax)
    - `adjustments` = Order Error Adjustments + Price adjustments (excl. tax) + Other payments
    - `marketing_fee` = Offers on items (incl. tax) + Delivery Offer Redemptions (incl. tax) + Offer Redemption Fee + Marketing Adjustment + Markup Amount
    - `misc_fee` = Bag Fee + Delivery Network Fee
    - `commission_fee` = Marketplace Fee
    - `processing_fee` = Order Processing Fee
    - `delivery_fee` = Delivery Fee
    - `tip` = Tips
    - `tax_withheld` = Marketplace Facilitator Tax Adjustment + Marketplace Facilitator Tax + Backup Withholding Tax
    - `payout` = Total payout
  - Notes include dining mode, order channel, order status, marketplace fee %, order error adjustments (incl tax),
    capital payments, other payments description, and payout date.
  - Refund rows for a shared Order ID/Workflow ID are aggregated into the base order by summing money fields.
  - Backfill + stitching:
    - Base export starts at 2021-02-11; reports2022 backfill only includes rows **before** 2021-02-11 to avoid overlap.
    - Backfill scans both `Takeout/reports2022/Ameci/...` and `Takeout/reports2022/Aroma/...` including folders like
      `2021_01` and `2021_02` (underscore naming).
    - `Takeout/uber_reports2022_missing_from_base.csv` includes:
      - Rows missing in the base export (by Order ID + Workflow ID + Store + Date + Time).
      - Postmates rows (`Takeout/postmates_missing_as_uber.csv`) mapped to Uber columns.
      - Rows with empty `Order ID` (ad spend/credits/refunds) so they flow into `no_order_ids.csv`.
    - Postmates order IDs are normalized to `OrderID|YYYY_MM_DD` to avoid collisions.
  - Empty Order ID handling (ads/credits/refunds):
    - Raw rows with empty `Order ID` and `Workflow ID` are written to `orders_analytics/data/raw/ubereats/no_order_ids.csv`.
    - `Order Date` for these rows is filled using `Payout Date` when missing.
    - If both `Order Date` and `Payout Date` are missing, `Order Date` is inferred from the source file path
      (year/month in `.../YYYY/MM/...` or `.../YYYY_MM/...`) and set to the **last day of that month**.
    - Monthly aggregation file `orders_analytics/data/raw/ubereats/no_order_ids_other_payments_monthly.csv` groups
      by Store + month + other payments description and generates `UBER_OTHER_<hash>` order IDs.
  - Legacy column mapping:
    - Older reports use columns like `Tax on Food Sales`, `Uber Service Fee`, `Gratuity`, `Misc Payment Description`,
      and `Payout`. These are normalized to the modern Uber export column names during backfill/stitching.

## MealHi5
- Orders source: `Takeout/Mail/Orders-mealhi5.mbox` (PDF attachments).
  - Extracted to `orders_analytics/data/raw/mealhi5/orders_raw.csv` by `parsers/mealhi5/extract_mealhi5_orders_raw.py`.
  - Address uses the **customer** Address block (last `Address:` in the PDF) and includes the following city/state/zip line.
  - Phone uses the customer `Phone No` (ignores `Restaurant Phone No`).
  - Order totals use the `Total:` line (not `Subtotal:`); tax supports both `Tax:` and `Tax and Fee` formats.
- Billings source: `Takeout/Mail/Billings-mealhi5.mbox` (checkbook.io emails).
  - Extracted to `orders_analytics/data/raw/mealhi5/billings_raw.csv` by `parsers/mealhi5/extract_mealhi5_billings_raw.py`.
  - Billings are check amounts with payment dates; no order IDs are available, so payout allocation is manual for now.
- Normalizer: `parsers/mealhi5/parse_mealhi5_orders.py`
  - Billing allocation rules (checkbook payouts):
    - 2019-10-01 to 2019-10-31 -> payment dated 2019-11-07.
    - 2019-11-01 to 2019-11-22 -> payment dated 2019-11-23.
    - 2020-02-01 to 2020-02-28 -> payment dated 2020-03-03.
    - 2020-03-01 to 2020-03-17 -> payments dated 2020-03-18 and 2020-04-03 (combined).
    - 2021-01-01 to 2021-01-31 -> payment dated 2021-02-04.
    - For each range, we allocate the check payout across orders (proportional to order total) into the `payout` column and tag `payout_allocated=<range>`.
    - We compare payout total vs summed order totals.
      - If payout < orders total, we distribute the negative difference into `commission_fee` across orders (proportional to order total).
      - If payout >= orders total, we distribute the positive difference into `adjustments` and add `manual_offset_for_billing=<range>` note.
      - If payout allocation rounding drifts, we add `payout_allocation_mismatch=<delta>` to the first row in the range.
  - Discounts (if present) are recorded as negative `adjustments`.
  - Payment type is assumed credit; order type from the `FOR:` line.
