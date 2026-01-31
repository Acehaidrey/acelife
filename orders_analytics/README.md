# Orders Analytics

Local workspace for normalizing provider exports, ingesting into DuckDB, and
running a Streamlit dashboard.

## How It Works (Pipeline Overview)
```
Provider Inputs (mbox, PDFs, CSVs)
        |
        v
  Extract (optional)
  - mbox/PDF -> raw CSV
        |
        v
  Normalize (BaseParser)
  - map to canonical schema
  - enforce enums + ISO datetimes
  - validations -> errors.csv
        |
        v
  Ingest -> DuckDB
        |
        v
  Streamlit Dashboard
```

## Structure
- `parsers/` provider-specific scripts (input: mbox/csv, output: normalized CSV)
  - `parsers/<platform>/` platform-specific parsers
  - `parsers/_legacy/` archived scripts kept for reference (not used)
- `data/` raw + normalized data (local only, do not commit)
  - `data/raw/<provider>/` raw provider exports organized by provider name
  - `data/raw/<provider>/backups/` backups of normalized outputs when overwriting in place
- `utils/` shared helpers/constants
  - `utils/schema.py` canonical normalized schema + helpers
  - `utils/base_parser.py` BaseParser for provider parsers
- `data/errors/errors.csv` validation errors log (deduped by order_id/platform/provider/error_code)
- `ingest.py` load normalized CSVs into DuckDB
- `app.py` Streamlit dashboard
  - `cli.py` single entrypoint for extract/normalize/parse/fees/ingest

## Canonical Normalized Schema
All order-level parsers should emit these columns in this order:
`order_id, platform, provider, order_datetime, order_type, customer_name, company_name, phone, email, address, payment_type, restaurant_name, items, item_count, subtotal, tax, tax_withheld, tip, delivery_fee, total, processing_fee, commission_fee, adjustments, marketing_fee, misc_fee, errors, notes`

## Parser Conventions
- BeyondMenu parser drops rows where `Status != active` (inactive orders are excluded).
- BaseParser drops rows with null/blank `order_id`, then dedupes by `order_id`.
- EatStreet flow is two-step:
  - Extract raw orders + billings CSVs from mbox (append-only by `order_id`).
  - Normalize from raw CSVs into canonical schema.
- MenuStar flow is two-step:
  - Extract orders from HTML mbox, billings from CSV/XLSX attachments.
  - Allocate MenuStar Fees proportionally across prepaid orders by subtotal.
- Raw EatStreet CSVs include an `added_at` timestamp that only updates when any field changes for an `order_id`.
- Normalized rows must have exactly one real value in `tax` or `tax_withheld`; violations are logged and annotated in `errors` as `tax_tax_withheld_needs_review`.
- Validation issues are written to `data/errors/errors.csv` with `resolved` and `resolved_time` fields; duplicates (same order_id/platform/provider/error_code) are ignored.

## Common CLI Flows
- Extract only (mbox/PDF → raw CSV):
  - `python3 orders_analytics/cli.py extract --platform eatstreet`
  - `python3 orders_analytics/cli.py extract --platform cater2me`
  - `python3 orders_analytics/cli.py extract --platform menustar`
- Normalize only (raw CSV → normalized CSV):
  - `python3 orders_analytics/cli.py normalize --platform all`
  - `python3 orders_analytics/cli.py normalize --platform eatstreet`
  - `python3 orders_analytics/cli.py normalize --platform cater2me`
  - `python3 orders_analytics/cli.py normalize --platform menustar`
  - `--no-reset-errors` to keep existing `errors.csv` (default resets)
- Parse (extract + normalize):
  - `python3 orders_analytics/cli.py parse --platform eatstreet`
  - `python3 orders_analytics/cli.py parse --platform cater2me`
  - `python3 orders_analytics/cli.py parse --platform menustar`
  - `python3 orders_analytics/cli.py parse --platform all`
- CSV-based providers (BeyondMenu/Foodja/ezCater) are normalized directly from CSV inputs:
  - `python3 orders_analytics/cli.py normalize --platform beyondmenu`
  - `python3 orders_analytics/cli.py normalize --platform foodja`
  - `python3 orders_analytics/cli.py normalize --platform ezcater`
- Optional: pass extra parser args: `--extra key=value` (repeatable)
- Optional: update EatStreet normalized fees from billings (writes missing-fee list to raw):
  - `python3 orders_analytics/cli.py fees` (legacy)
- Ingest normalized CSVs into DuckDB:
  - `python3 orders_analytics/cli.py ingest`
- Start the dashboard:
  - `streamlit run orders_analytics/app.py`

## Requirements Notes
- MenuStar billings may arrive as `.xlsx`. Install extras:
  - `pip install -r orders_analytics/requirements.txt` (includes openpyxl)
