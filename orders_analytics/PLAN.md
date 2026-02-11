# Orders Analytics Plan

## Current State / Handoff Notes (2026-02-11)
- BeyondMenu is complete end-to-end and should not be changed unless requested.
- BeyondMenu sources now download from Google Sheets into raw:
  - `orders_analytics/data/raw/beyondmenu/beyond_menu_order_history.csv`
  - `orders_analytics/data/raw/beyondmenu/beyond_menu_annual_billing_summary.csv`
- BeyondMenu normalization rules (parsers/beyondmenu/parse_beyondmenu_orders.py):
  - Filters `Status=active`.
  - Convenience fee: added to `misc_fee` and also added as a negative value in `adjustments`.
  - Notes include `convenience_fee=<amount>` for rows with convenience fees.
  - Annual billing additional charges + credits are distributed across active orders per provider/year (proportional to subtotal with cent balancing) and applied to `misc_fee`.
  - Aroma special handling:
    - 2023: apply 2024 credits (`-89.25`) to offset 2023 additional charges (`89.25`), net 0 in 2023.
    - 2024: apply only remaining additional charges (`119.35 - 89.25 = 30.10`) across active orders, excluding order `101559574` when possible.
    - If `101559574` is the only active 2024 order, it receives the remaining additional charges to reconcile.
- BeyondMenu annual comparison script:
  - `orders_analytics/scripts/beyondmenu_annual_compare.py`
  - Output: `orders_analytics/data/raw/beyondmenu/beyondmenu_annual_billing_check.csv`
  - Compares counts, totals, commission (commission+fax+phone), processing (merchant fee), and totals net of convenience fee.
- ChowNow manual missing orders now download to raw:
  - `orders_analytics/data/raw/chownow/chownow_manual_missing_orders.csv`
  - Extract step uses the Google Sheets downloader and appends these orders.
  - Manual missing orders notes are now just `manual_missing_order` (no redundant `source=...`).
- ChowNow orders vs billings comparison script:
  - `orders_analytics/parsers/chownow/compare_chownow_orders_billings.py`
  - Output CSVs:
    - `orders_analytics/data/raw/chownow/orders_missing_billings.csv`
    - `orders_analytics/data/raw/chownow/billings_missing_orders.csv`
  - Comparison excludes cancellations from `orders_analytics/data/raw/chownow/cancellations_raw.csv`.
- Brygid:
  - `total_components_mismatch_adjusted` is no longer an error; only note `subtotal_adjusted_for_delivery_fee` when delivery fee is moved out of subtotal.
  - TODO: obtain Vantiv processing fee totals (still pending).
- BaseParser now normalizes phone numbers (strip non-digits, drop leading 1 for 11-digit numbers).
- CLI now skips inactive platforms by default when `--platform all`. Use `--include-inactive` to include:
  - `cater2me`, `deliverycom`, `fooda`, `foodee`, `brygid`.
- Streamlit app updates:
  - Customer search tab (partial match on name/phone/email/address).
  - Delivery map includes AMECI/AROMA reference pins (black dots) using `geocode_cache.csv`.
  - Phone display normalized in app ingest to avoid `.0` floats.
- Google Sheets registry:
  - `orders_analytics/utils/google_sheets_registry.py` is the source of truth for sheet ids + output paths.
  - Added `download_sheet_entry` helper in `orders_analytics/utils/google_sheets.py`.

## Goals
- Normalize order/invoice exports from multiple providers into a single model.
- Store normalized data in DuckDB for fast analytics and reporting.
- Provide a Streamlit dashboard for filtering and aggregation by date grain, platform, and provider.

## Proposed Layout
- `orders_analytics/`
  - `parsers/` (provider-specific parsers that output normalized CSVs)
    - `<platform>/` (platform-specific parsers, e.g. `eatstreet/`, `beyondmenu/`)
    - `_template_parser.py` (starter template for new providers)
  - `data/` (raw + normalized data; local only)
    - `data/raw/<provider>/` (raw exports, mbox files, ancillary outputs)
    - `data/raw/<provider>/backups/` (backups when overwriting normalized files)
  - `utils/` (shared helpers and constants)
  - `utils/schema.py` (canonical schema + helpers)
  - `utils/base_parser.py` (BaseParser lifecycle for provider parsers)
  - `utils/geocodio.py` (Geocodio client + cache helper)
  - `ingest.py` (loads normalized CSVs into DuckDB)
  - `app.py` (Streamlit dashboard)
  - `cli.py` (single entrypoint for extract/normalize/parse/fees/ingest)
  - `normalize --platform all` resets `errors.csv` by default (use `--no-reset-errors`)
  - `geocode --all` enriches normalized addresses via Geocodio (optional)
  - `README.md` (usage + conventions)

## Phase 1: Foundation
- Define a unified schema for normalized orders:
  - `order_id`, `platform`, `provider`, `order_datetime`, `order_type`, `payment_type`
  - `subtotal`, `tax`, `tax_withheld`, `tip`, `delivery_fee`, `total`
  - `commission_fee`, `processing_fee`, `adjustments`, `marketing_fee`, `misc_fee`
  - `payout`, `expected_payout`
  - `customer_name`, `phone`, `email`, `address`, `address_formatted`, `lat`, `lng`
  - `restaurant_name`, `items`, `item_count`, `notes`, `errors`
- Add a constants module for:
  - provider names, platform names, currency fields
  - canonical date parsing formats
- Add parser interface guideline:
  - input: provider mbox/csv
  - output: normalized CSV in `data/normalized/`

## Phase 2: Parsers
- Organize parsers by platform folder:
  - `parsers/eatstreet/extract_eatstreet_orders_raw.py`
  - `parsers/eatstreet/extract_eatstreet_billings_raw.py`
  - `parsers/eatstreet/normalize_eatstreet_from_raw.py`
  - `parsers/beyondmenu/parse_beyondmenu_orders.py`
  - `parsers/foodja/parse_foodja_orders.py`
  - `parsers/ezcater/parse_ezcater_orders.py`
  - `parsers/cater2me/extract_cater2me_orders_raw.py`
  - `parsers/cater2me/extract_cater2me_billings_raw.py`
  - `parsers/cater2me/normalize_cater2me_from_raw.py`
  - `parsers/menustar/extract_menustar_orders_raw.py`
  - `parsers/menustar/extract_menustar_billings_raw.py`
  - `parsers/menustar/normalize_menustar_from_raw.py`
  - `parsers/deliverycom/parse_deliverycom_orders.py`
  - `parsers/deliverycom/extract_deliverycom_billings_raw.py`
  - `parsers/foodee/extract_foodee_orders_raw.py`
  - `parsers/foodee/extract_foodee_billings_raw.py`
  - `parsers/foodee/normalize_foodee_from_raw.py`
  - `parsers/foodrunners/extract_foodrunners_orders_raw.py`
  - `parsers/foodrunners/extract_foodrunners_billings_raw.py`
  - `parsers/foodrunners/normalize_foodrunners_from_raw.py`
  - `parsers/officecaterer/extract_officecaterer_orders_raw.py`
  - `parsers/officecaterer/normalize_officecaterer_from_raw.py`
  - `parsers/_legacy/` (archived scripts; not used)
- Update parsers to:
  - emit normalized columns
  - enforce ISO 8601 `order_datetime`
  - dedupe by `order_id`
  - report conflicts
  - write backups and missing-fee reports to `data/raw/<provider>/`
  - use `BaseParser` for shared flow (load → parse → pre/post → validate → dedupe → write)
  - compute `expected_payout` from normalized money fields and validate against `payout` when present
  - for EatStreet, parse orders + billings mbox together to populate fees
  - for BeyondMenu, drop rows where `Status != active`
  - for EatStreet, treat raw CSVs as source of truth and append-only by `order_id`
  - validation: each row must have exactly one real value in `tax` or `tax_withheld`; flag violations in `notes`
  - log validation issues to `data/errors/errors.csv` (deduped by order_id/platform/provider/error_code)

## CLI Flows (Current)
- Extract only (mbox/PDF → raw CSV):
  - `cli.py extract --platform eatstreet`
  - `cli.py extract --platform cater2me`
  - `cli.py extract --platform menustar`
  - `cli.py extract --platform deliverycom`
  - `cli.py extract --platform foodee`
  - `cli.py extract --platform foodrunners`
  - `cli.py extract --platform officecaterer`
- Normalize only (raw CSV → normalized CSV):
  - `cli.py normalize --platform all`
  - `cli.py normalize --platform eatstreet`
  - `cli.py normalize --platform cater2me`
  - `cli.py normalize --platform menustar`
  - CSV-based providers are normalized directly (BeyondMenu/Foodja/ezCater)
  - `--no-reset-errors` to keep existing `errors.csv` (default resets)
- Parse (extract + normalize):
  - `cli.py parse --platform <platform|all>`
  - `cli.py parse --platform deliverycom`
- Geocode (optional, after normalize):
  - `cli.py geocode --platform <platform|all>`

## Phase 3: Ingestion
- Build `ingest.py`:
  - scan `data/normalized/` (no repo-wide search)
  - load CSVs into DuckDB tables
  - create canonical views:
    - `orders_all` (union across providers)
    - `orders_daily`, `orders_monthly`

## Phase 4: Dashboard
- Build `app.py` (Streamlit):
  - filters: provider, platform, restaurant, date range
  - aggregation grain: day, month, year
  - metrics: order count, subtotal, tax, tip, delivery_fee, total
  - charts: time series + breakdown table

## Phase 5: Expansion
- Add remaining providers (15–20) with parser templates.
- Add validation checks (missing dates, zero totals, duplicate IDs).
- Optional: export summaries to CSV for accounting.
