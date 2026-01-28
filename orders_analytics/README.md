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
- `ingest.py` load normalized CSVs into DuckDB
- `app.py` Streamlit dashboard

## Canonical Normalized Schema
All order-level parsers should emit these columns in this order:
`order_id, platform, provider, order_datetime, order_type, customer_name, phone, email, address, payment_type, subtotal, tax, tip, delivery_fee, total, item_count, processing_fee, commission_fee, items, restaurant_name, tax_withheld, adjustments, marketing_fee, misc_fee, notes`

## Next Steps
- Run parsers to create normalized CSVs:
  - `python3 orders_analytics/parsers/eatstreet/parse_eatstreet_orders.py`
  - `python3 orders_analytics/parsers/beyondmenu/parse_beyondmenu_orders.py`
- Update EatStreet normalized fees from billings (writes missing-fee list to raw):
  - `python3 orders_analytics/parsers/eatstreet/update_eatstreet_fees.py`
- Start the dashboard:
  - `streamlit run orders_analytics/app.py`
