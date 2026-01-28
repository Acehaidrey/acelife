# Orders Analytics

Local workspace for normalizing provider exports, ingesting into DuckDB, and
running a Streamlit dashboard.

## Structure
- `parsers/` provider-specific scripts (input: mbox/csv, output: normalized CSV)
  - `parsers/<platform>/` platform-specific parsers
- `data/` raw + normalized data (local only, do not commit)
  - `data/raw/<provider>/` raw provider exports organized by provider name
  - `data/raw/<provider>/backups/` backups of normalized outputs when overwriting in place
- `utils/` shared helpers/constants
  - `utils/schema.py` canonical normalized schema + helpers
  - `utils/base_parser.py` BaseParser for provider parsers
- `data/errors/errors.csv` validation errors log (deduped by order_id/platform/provider/error_code)
- `ingest.py` load normalized CSVs into DuckDB
- `app.py` Streamlit dashboard
  - `cli.py` single entrypoint for parse/fees/ingest

## Canonical Normalized Schema
All order-level parsers should emit these columns in this order:
`order_id, platform, provider, order_datetime, order_type, customer_name, phone, email, address, payment_type, restaurant_name, items, item_count, subtotal, tax, tax_withheld, tip, delivery_fee, total, processing_fee, commission_fee, adjustments, marketing_fee, misc_fee, notes`

## Parser Conventions
- BeyondMenu parser drops rows where `Status != active` (inactive orders are excluded).
- BaseParser drops rows with null/blank `order_id`, then dedupes by `order_id`.
- EatStreet flow is two-step:
  - Extract raw orders + billings CSVs from mbox (append-only by `order_id`).
  - Normalize from raw CSVs into canonical schema.
- Raw EatStreet CSVs include an `added_at` timestamp that only updates when any field changes for an `order_id`.
- Normalized rows must have exactly one real value in `tax` or `tax_withheld`; violations are logged and annotated in `notes` as `tax_tax_withheld_needs_review`.
- Validation issues are written to `data/errors/errors.csv` with `resolved` and `resolved_time` fields; duplicates (same order_id/platform/provider/error_code) are ignored.

## Next Steps
- EatStreet (recommended two-step):
  - `python3 orders_analytics/cli.py extract --platform eatstreet`
  - `python3 orders_analytics/cli.py normalize --platform eatstreet`
- Or one-step parse (extract + normalize):
  - `python3 orders_analytics/cli.py parse --platform eatstreet --extra billings_mbox=TakeoutESBM/Mail/Billings-Eatstreet.mbox`
- BeyondMenu parse:
  - `python3 orders_analytics/cli.py parse --platform beyondmenu`
- (Optional) pass extra parser args: `--extra key=value` (repeatable)
- (Optional) Update EatStreet normalized fees from billings (writes missing-fee list to raw):
  - `python3 orders_analytics/cli.py fees`
- Ingest normalized CSVs into DuckDB:
  - `python3 orders_analytics/cli.py ingest`
- Start the dashboard:
  - `streamlit run orders_analytics/app.py`
