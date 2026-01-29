# Orders Analytics Plan

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
  - `ingest.py` (loads normalized CSVs into DuckDB)
  - `app.py` (Streamlit dashboard)
  - `cli.py` (single entrypoint for parse/fees/ingest)
  - `README.md` (usage + conventions)

## Phase 1: Foundation
- Define a unified schema for normalized orders:
  - `order_id`, `platform`, `provider`, `order_datetime`, `order_type`
  - `customer_name`, `phone`, `email`, `address`, `payment_type`
  - `subtotal`, `tax`, `tip`, `delivery_fee`, `total`
  - `item_count`, `processing_fee`, `commission_fee`, `items`, `restaurant_name`
  - `tax_withheld`, `adjustments`, `marketing_fee`, `misc_fee`, `notes`
- Add a constants module for:
  - provider names, platform names, currency fields
  - canonical date parsing formats
- Add parser interface guideline:
  - input: provider mbox/csv
  - output: normalized CSV in `data/normalized/`

## Phase 2: Parsers
- Organize parsers by platform folder:
  - `parsers/eatstreet/parse_eatstreet_orders.py`
  - `parsers/eatstreet/update_eatstreet_fees.py`
  - `parsers/eatstreet/extract_eatstreet_orders_raw.py`
  - `parsers/eatstreet/extract_eatstreet_billings_raw.py`
  - `parsers/eatstreet/normalize_eatstreet_from_raw.py`
  - `parsers/beyondmenu/parse_beyondmenu_orders.py`
  - `parsers/beyondmenu/parse_beyondmenu_billings.py` (kept but likely unused)
  - `parsers/foodja/parse_foodja_orders.py`
  - `parsers/ezcater/parse_ezcater_orders.py`
- Update parsers to:
  - emit normalized columns
  - enforce ISO 8601 `order_datetime`
  - dedupe by `order_id`
  - report conflicts
  - write backups and missing-fee reports to `data/raw/<provider>/`
  - use `BaseParser` for shared flow (load → parse → pre/post → validate → dedupe → write)
  - for EatStreet, parse orders + billings mbox together to populate fees
  - for BeyondMenu, drop rows where `Status != active`
  - for EatStreet, treat raw CSVs as source of truth and append-only by `order_id`
  - validation: each row must have exactly one real value in `tax` or `tax_withheld`; flag violations in `notes`
  - log validation issues to `data/errors/errors.csv` (deduped by order_id/platform/provider/error_code)

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
