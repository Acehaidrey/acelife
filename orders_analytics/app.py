#!/usr/bin/env python3
import os
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st
import pydeck as pdk

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from orders_analytics.utils.constants import DEFAULT_DB_PATH, NORMALIZED_DIR, ERRORS_PATH

ORDER_COLUMNS = [
    "order_id",
    "platform",
    "provider",
    "order_datetime",
    "order_type",
    "payment_type",
    "subtotal",
    "tax",
    "tax_withheld",
    "tip",
    "delivery_fee",
    "total",
    "commission_fee",
    "processing_fee",
    "adjustments",
    "marketing_fee",
    "misc_fee",
    "payout",
    "expected_payout",
    "customer_name",
    "company_name",
    "phone",
    "email",
    "address",
    "address_formatted",
    "lat",
    "lng",
    "restaurant_name",
    "items",
    "item_count",
    "errors",
    "notes",
]

def get_connection() -> duckdb.DuckDBPyConnection:
    os.makedirs(os.path.dirname(DEFAULT_DB_PATH), exist_ok=True)
    conn = duckdb.connect(DEFAULT_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS order_overrides (
            order_id TEXT,
            platform TEXT,
            provider TEXT,
            restaurant_name TEXT,
            order_datetime TIMESTAMP,
            order_type TEXT,
            customer_name TEXT,
            company_name TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            payment_type TEXT,
            items TEXT,
            item_count TEXT,
            subtotal DOUBLE,
            tax DOUBLE,
            tax_withheld DOUBLE,
            tip DOUBLE,
            delivery_fee DOUBLE,
            total DOUBLE,
            processing_fee DOUBLE,
            commission_fee DOUBLE,
            adjustments DOUBLE,
            marketing_fee DOUBLE,
            misc_fee DOUBLE,
            notes TEXT,
            errors TEXT,
            updated_at TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS order_overrides_pk ON order_overrides(order_id, platform)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monthly_overrides (
            platform TEXT,
            provider TEXT,
            year INTEGER,
            month INTEGER,
            orders DOUBLE,
            cash_subtotal DOUBLE,
            credit_subtotal DOUBLE,
            subtotal DOUBLE,
            tax DOUBLE,
            tax_withheld DOUBLE,
            tip DOUBLE,
            delivery_fee DOUBLE,
            misc_fee DOUBLE,
            commission_fee DOUBLE,
            processing_fee DOUBLE,
            adjustments DOUBLE,
            marketing_fee DOUBLE,
            total DOUBLE,
            notes TEXT,
            updated_at TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS monthly_overrides_pk ON monthly_overrides(platform, provider, year, month)"
    )
    return conn

def ingest_normalized(conn: duckdb.DuckDBPyConnection) -> int:
    if not os.path.isdir(NORMALIZED_DIR):
        return 0
    files = [
        os.path.join(NORMALIZED_DIR, name)
        for name in os.listdir(NORMALIZED_DIR)
        if name.endswith(".csv")
    ]
    if not files:
        return 0
    frames = []
    for path in files:
        df = pd.read_csv(path)
        if "phone" in df.columns:
            def _normalize_phone(value):
                if pd.isna(value):
                    return ""
                text = str(value).strip()
                if not text or text.lower() == "nan":
                    return ""
                if text.endswith(".0") and text.replace(".", "", 1).isdigit():
                    text = text[:-2]
                return text

            df["phone"] = df["phone"].apply(_normalize_phone)
        df["source_file"] = os.path.basename(path)
        frames.append(df)
    data = pd.concat(frames, ignore_index=True)
    conn.register("orders_df", data)
    conn.execute("CREATE OR REPLACE TABLE orders_raw AS SELECT * FROM orders_df")
    return len(data)

def load_orders(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    tables = conn.execute("SHOW TABLES").fetchall()
    if not any(row[0] == "orders_raw" for row in tables):
        return pd.DataFrame()
    raw = conn.execute("SELECT * FROM orders_raw").df()
    for col in ORDER_COLUMNS:
        if col not in raw.columns:
            raw[col] = ""
    overrides = conn.execute("SELECT * FROM order_overrides").df()
    if overrides.empty:
        raw["order_datetime"] = pd.to_datetime(
            raw["order_datetime"], errors="coerce", utc=True, format="ISO8601"
        )
        raw["order_datetime"] = raw["order_datetime"].dt.tz_convert(None)
        return raw[ORDER_COLUMNS]

    merged = raw.merge(
        overrides,
        on=["order_id", "platform"],
        how="outer",
        suffixes=("", "_override"),
    )
    numeric_cols = [
        "subtotal",
        "tax",
        "tax_withheld",
        "tip",
        "delivery_fee",
        "total",
        "processing_fee",
        "commission_fee",
        "adjustments",
        "marketing_fee",
        "misc_fee",
    ]
    for col in numeric_cols:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce")
        override_col = f"{col}_override"
        if override_col in merged.columns:
            merged[override_col] = pd.to_numeric(merged[override_col], errors="coerce")
            merged[col] = merged[override_col].combine_first(merged[col])
    # Handle order_datetime separately to avoid pandas trying to infer a strict format.
    if "order_datetime" in merged.columns:
        base_dt = pd.to_datetime(merged["order_datetime"], errors="coerce", utc=True, format="ISO8601")
        override_col = "order_datetime_override"
        if override_col in merged.columns:
            override_dt = pd.to_datetime(merged[override_col], errors="coerce", utc=True, format="ISO8601")
            merged["order_datetime"] = override_dt.combine_first(base_dt)
        else:
            merged["order_datetime"] = base_dt

    for col in [
        "provider",
        "order_type",
        "customer_name",
        "company_name",
        "phone",
        "email",
        "address",
        "address_formatted",
        "lat",
        "lng",
        "payment_type",
        "items",
        "item_count",
        "restaurant_name",
        "notes",
        "errors",
    ]:
        override_col = f"{col}_override"
        if override_col in merged.columns:
            merged[col] = merged[override_col].combine_first(merged[col])
    if "item_count" in merged.columns:
        merged["item_count"] = pd.to_numeric(merged["item_count"], errors="coerce")
    merged["order_datetime"] = pd.to_datetime(
        merged["order_datetime"], errors="coerce", utc=True, format="ISO8601"
    )
    merged["order_datetime"] = merged["order_datetime"].dt.tz_convert(None)
    merged = merged[ORDER_COLUMNS]
    return merged

def load_errors() -> pd.DataFrame:
    if not os.path.exists(ERRORS_PATH):
        return pd.DataFrame()
    df = pd.read_csv(ERRORS_PATH)
    if "resolved" not in df.columns:
        df["resolved"] = ""
    if "resolved_time" not in df.columns:
        df["resolved_time"] = ""
    return df

def resolve_error_row(row_id: int) -> None:
    df = load_errors()
    if df.empty or row_id not in df.index:
        return
    df.loc[row_id, "resolved"] = "true"
    df.loc[row_id, "resolved_time"] = datetime.utcnow().isoformat()
    df.to_csv(ERRORS_PATH, index=False)

def load_markdown_file(path: str) -> str:
    file_path = Path(path)
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")

def _format_mtime(path: Path) -> str:
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(sep=" ", timespec="seconds")

def build_sync_status() -> pd.DataFrame:
    from orders_analytics.utils.platforms import Platforms

    raw_root = Path("orders_analytics/data/raw")
    normalized_root = Path("orders_analytics/data/normalized")
    geocode_cache = Path("orders_analytics/data/raw/geocode_cache.csv")

    rows = []
    for platform in Platforms.all_platforms():
        raw_dir = raw_root / platform
        raw_last = ""
        if raw_dir.exists():
            raw_files = [p for p in raw_dir.rglob("*") if p.is_file()]
            if raw_files:
                raw_last = _format_mtime(max(raw_files, key=lambda p: p.stat().st_mtime))
        normalized_path = normalized_root / f"{platform}_orders_normalized.csv"
        normalized_last = _format_mtime(normalized_path)
        status = "ok"
        if not normalized_path.exists():
            status = "missing_normalized"
        elif raw_last and normalized_last and raw_last > normalized_last:
            status = "stale_normalized"
        rows.append({
            "platform": platform,
            "raw_last_modified": raw_last,
            "normalized_last_modified": normalized_last,
            "geocode_cache_modified": _format_mtime(geocode_cache),
            "status": status,
        })
    return pd.DataFrame(rows)

def load_wave_payouts(provider: str) -> pd.DataFrame:
    base_dir = Path(f"orders_analytics/data/raw/{provider}")
    paths = sorted(base_dir.glob("wave_payouts_*.csv"))
    if not paths:
        return pd.DataFrame()
    frames = []
    for path in paths:
        df = pd.read_csv(path)
        df.columns = [c.strip().lower() for c in df.columns]
        # date column
        date_col = None
        for col in df.columns:
            if col in ("transaction date", "date"):
                date_col = col
                break
        if date_col is None:
            continue
        df["transaction_date"] = pd.to_datetime(df[date_col], errors="coerce")
        # amount column
        if "amount (one column)" in df.columns:
            df["amount"] = pd.to_numeric(df["amount (one column)"], errors="coerce")
        else:
            credit = pd.to_numeric(df.get("credit amount (two column approach)"), errors="coerce")
            debit = pd.to_numeric(df.get("debit amount (two column approach)"), errors="coerce")
            df["amount"] = credit.fillna(0) - debit.fillna(0)
        df["wave_account"] = path.stem.replace("wave_payouts_", "")
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)

def build_global_status() -> pd.DataFrame:
    rows = []
    geocode_cache = Path("orders_analytics/data/raw/geocode_cache.csv")
    errors_path = Path(ERRORS_PATH)
    normalized_root = Path("orders_analytics/data/normalized")
    raw_root = Path("orders_analytics/data/raw")

    rows.append({"artifact": "geocode_cache", "last_modified": _format_mtime(geocode_cache)})
    rows.append({"artifact": "errors", "last_modified": _format_mtime(errors_path)})
    if normalized_root.exists():
        norm_files = [p for p in normalized_root.glob("*.csv") if p.is_file()]
        rows.append({"artifact": "normalized_latest", "last_modified": _format_mtime(max(norm_files, key=lambda p: p.stat().st_mtime)) if norm_files else ""})
    else:
        rows.append({"artifact": "normalized_latest", "last_modified": ""})
    if raw_root.exists():
        raw_files = [p for p in raw_root.rglob("*") if p.is_file()]
        rows.append({"artifact": "raw_latest", "last_modified": _format_mtime(max(raw_files, key=lambda p: p.stat().st_mtime)) if raw_files else ""})
    else:
        rows.append({"artifact": "raw_latest", "last_modified": ""})
    return pd.DataFrame(rows)

def add_date_grain(data: pd.DataFrame, grain: str) -> pd.DataFrame:
    if grain == "day":
        data["date_bucket"] = data["order_datetime"].dt.date
    elif grain == "month":
        data["date_bucket"] = data["order_datetime"].dt.to_period("M").dt.to_timestamp()
    else:
        data["date_bucket"] = data["order_datetime"].dt.to_period("Y").dt.to_timestamp()
    return data

def main() -> None:
    st.set_page_config(page_title="Orders Analytics", layout="wide")
    st.title("Orders Analytics")

    conn = get_connection()
    ingest_normalized(conn)

    with st.sidebar:
        st.subheader("Data")
        if st.button("Normalize + refresh (all platforms)"):
            from orders_analytics.cli import run_normalize
            from orders_analytics.utils.constants import ERRORS_PATH

            if os.path.exists(ERRORS_PATH):
                os.remove(ERRORS_PATH)
            from orders_analytics.utils.platforms import Platforms

            for platform in Platforms.all_platforms():
                run_normalize(platform, None, None, None, None, {})
            count = ingest_normalized(conn)
            st.success(f"Normalized + ingested {count} rows.")
        if st.button("Rebuild orders_raw from CSVs"):
            conn.execute("DROP TABLE IF EXISTS orders_raw")
            count = ingest_normalized(conn)
            st.success(f"Rebuilt orders_raw with {count} rows.")
        if st.button("Refresh from normalized CSVs"):
            count = ingest_normalized(conn)
            st.success(f"Ingested {count} rows.")

    data = load_orders(conn)
    if data.empty:
        st.info("No data loaded yet. Click Refresh from normalized CSVs.")
        return

    platform_counts = data["platform"].value_counts(dropna=False).to_dict()
    nat_count = data["order_datetime"].isna().sum()
    st.caption(
        f"Loaded {len(data)} rows. Date range: {data['order_datetime'].min()} → {data['order_datetime'].max()} | "
        f"NaT: {nat_count} | Platforms: {platform_counts}"
    )

    platform_options = sorted(data["platform"].dropna().unique().tolist())
    provider_options = ["ALL"] + sorted(data["provider"].dropna().unique().tolist())

    col1, col2, col3 = st.columns(3)
    with col1:
        platform = st.multiselect("Platform", platform_options, default=platform_options)
    with col2:
        provider = st.selectbox("Provider", provider_options)
    with col3:
        grain = st.selectbox("Date Grain", ["day", "month", "year"], index=1)

    min_date = data["order_datetime"].min()
    max_date = data["order_datetime"].max()
    if pd.isna(min_date) or pd.isna(max_date):
        st.warning("Order dates are missing or invalid.")
        return

    today = datetime.today().date()
    max_picker = today
    if pd.isna(max_date):
        max_value = max_picker
        default_end = max_picker
    else:
        max_value = max_picker
        default_end = max_picker
    default_start = datetime(2020, 1, 1).date()
    if default_end < default_start:
        default_end = default_start

    date_preset = st.selectbox(
        "Date Preset",
        [
            "Custom",
            "Last Month",
            "This Month",
            "Year to Date",
            "Last 12 Months",
            "Last Year",
            "Last 2 Years",
            "All Time",
        ],
        index=0,
    )
    if date_preset != "Custom":
        if date_preset == "All Time":
            default_start = datetime(2020, 1, 1).date()
            default_end = max_picker
        elif date_preset == "This Month":
            default_start = datetime(max_picker.year, max_picker.month, 1).date()
            default_end = max_picker
        elif date_preset == "Last Month":
            first_of_this_month = datetime(max_picker.year, max_picker.month, 1).date()
            last_month_end = first_of_this_month - pd.Timedelta(days=1)
            default_start = datetime(last_month_end.year, last_month_end.month, 1).date()
            default_end = last_month_end
        elif date_preset == "Year to Date":
            default_start = datetime(max_picker.year, 1, 1).date()
            default_end = max_picker
        elif date_preset == "Last 12 Months":
            default_end = max_picker
            default_start = (pd.Timestamp(max_picker) - pd.DateOffset(months=12)).date()
        elif date_preset == "Last Year":
            last_year = max_picker.year - 1
            default_start = datetime(last_year, 1, 1).date()
            default_end = datetime(last_year, 12, 31).date()
        elif date_preset == "Last 2 Years":
            start_year = max_picker.year - 2
            default_start = datetime(start_year, 1, 1).date()
            default_end = datetime(max_picker.year - 1, 12, 31).date()

    start_date, end_date = st.date_input(
        "Date Range",
        value=(default_start, default_end),
        min_value=default_start,
        max_value=max_value,
    )

    filtered = data.copy()
    if platform:
        filtered = filtered[filtered["platform"].isin(platform)]
    if provider != "ALL":
        filtered = filtered[filtered["provider"] == provider]
    filtered = filtered[
        (filtered["order_datetime"] >= pd.to_datetime(start_date))
        & (filtered["order_datetime"] <= pd.to_datetime(end_date) + pd.Timedelta(days=1))
    ]

    st.caption(f"After filters: {len(filtered)} rows")

    numeric_cols = [
        "subtotal",
        "tax",
        "tax_withheld",
        "tip",
        "delivery_fee",
        "total",
        "payout",
        "expected_payout",
        "misc_fee",
        "commission_fee",
        "processing_fee",
        "adjustments",
        "marketing_fee",
    ]
    for col in numeric_cols:
        if col in filtered.columns:
            filtered[col] = pd.to_numeric(filtered[col], errors="coerce")
        else:
            filtered[col] = 0.0
        filtered[col] = filtered[col].fillna(0.0)

    filtered = add_date_grain(filtered, grain)
    tab_summary, tab_recon, tab_overview, tab_notes, tab_status, tab_overrides, tab_errors, tab_orders, tab_customer, tab_delivery, tab_ameci = st.tabs(
        ["Summary", "Payout Reconciliation", "Overview", "Provider Notes", "Status", "Overrides", "Errors", "Orders", "Customer Search", "Delivery Map", "Ameci Royalty"]
    )

    with tab_overview:
        st.subheader("Project Overview")
        readme = load_markdown_file("orders_analytics/README.md")
        if readme:
            st.markdown(readme)
        else:
            st.info("README not found.")

    with tab_notes:
        st.subheader("Provider Notes")
        notes = load_markdown_file("orders_analytics/parsers/PROVIDER_NOTES.md")
        if notes:
            st.markdown(notes)
        else:
            st.info("Provider notes not found.")

    with tab_status:
        st.subheader("Sync Status")
        st.caption("Raw vs normalized timestamps, plus geocode cache freshness.")
        st.dataframe(build_sync_status(), width="stretch")
        st.subheader("Artifacts")
        st.dataframe(build_global_status(), width="stretch")

    with tab_summary:
        summary = (
            filtered.groupby("date_bucket")
            .agg(
                orders=("order_id", "count"),
                subtotal=("subtotal", "sum"),
                tax=("tax", "sum"),
                tax_withheld=("tax_withheld", "sum"),
                tip=("tip", "sum"),
                delivery_fee=("delivery_fee", "sum"),
                total=("total", "sum"),
                expected_payout=("expected_payout", "sum"),
                payout=("payout", "sum"),
            )
            .reset_index()
            .sort_values("date_bucket")
        )

        st.subheader("Summary")
        money_cols = [
            "cash_subtotal",
            "credit_subtotal",
            "subtotal",
            "tax",
            "tax_withheld",
            "tip",
            "delivery_fee",
            "total",
            "misc_fee",
            "commission_fee",
            "processing_fee",
            "adjustments",
            "marketing_fee",
        ]
        summary_column_config = {
            col: st.column_config.NumberColumn(format="dollar") for col in money_cols if col in summary.columns
        }
        st.dataframe(summary, column_config=summary_column_config, width="stretch")
        platform_summary = (
            filtered.groupby(["date_bucket", "platform"], dropna=False)
            .agg(total=("total", "sum"))
            .reset_index()
        )
        platform_pivot = platform_summary.pivot_table(
            index="date_bucket", columns="platform", values="total", fill_value=0.0
        )
        if not platform_pivot.empty:
            st.line_chart(platform_pivot)

        provider_summary = (
            filtered.groupby(["date_bucket", "provider"], dropna=False)
            .agg(total=("total", "sum"))
            .reset_index()
        )
        provider_pivot = provider_summary.pivot_table(
            index="date_bucket", columns="provider", values="total", fill_value=0.0
        )
        if not provider_pivot.empty:
            st.subheader("Total by Provider")
            st.line_chart(provider_pivot)

        monthly = (
            filtered.assign(
                year=filtered["order_datetime"].dt.year,
                month=filtered["order_datetime"].dt.month,
            )
            .groupby(["platform", "provider", "year", "month"])
            .agg(
                orders=("order_id", "count"),
                cash_subtotal=("subtotal", lambda s: s[filtered.loc[s.index, "payment_type"] == "cash"].sum()),
                credit_subtotal=("subtotal", lambda s: s[filtered.loc[s.index, "payment_type"] == "credit"].sum()),
                tax=("tax", "sum"),
                tax_withheld=("tax_withheld", "sum"),
                tip=("tip", "sum"),
                delivery_fee=("delivery_fee", "sum"),
                total=("total", "sum"),
                expected_payout=("expected_payout", "sum"),
                payout=("payout", "sum"),
            )
            .reset_index()
        )
        monthly["subtotal"] = monthly["cash_subtotal"] + monthly["credit_subtotal"]
        for col in ["misc_fee", "commission_fee", "processing_fee", "adjustments", "marketing_fee"]:
            if col in filtered.columns:
                extra = (
                    filtered.assign(
                        year=filtered["order_datetime"].dt.year,
                        month=filtered["order_datetime"].dt.month,
                    )
                    .groupby(["platform", "provider", "year", "month"])[col]
                    .sum()
                    .reset_index()
                )
                monthly = monthly.merge(
                    extra, on=["platform", "provider", "year", "month"], how="left"
                )
                monthly[col] = monthly[col].fillna(0.0)
            else:
                monthly[col] = 0.0
        monthly = monthly.sort_values(["year", "month"], ascending=[False, False])
        for col in ["year", "month"]:
            if col in monthly.columns:
                monthly[col] = pd.to_numeric(monthly[col], errors="coerce").astype("Int64")
        overrides = conn.execute("SELECT * FROM monthly_overrides").df()
        if not overrides.empty:
            if platform:
                overrides = overrides[overrides["platform"].isin(platform)]
            if provider != "ALL":
                overrides = overrides[overrides["provider"] == provider]
            overrides["date_bucket"] = pd.to_datetime(
                dict(year=overrides["year"], month=overrides["month"], day=1),
                errors="coerce",
            )
            overrides = overrides[
                (overrides["date_bucket"] >= pd.to_datetime(start_date))
                & (overrides["date_bucket"] <= pd.to_datetime(end_date))
            ].drop(columns=["date_bucket"])
            monthly = monthly.merge(
                overrides,
                on=["platform", "provider", "year", "month"],
                how="outer",
                suffixes=("", "_override"),
            )
            for col in [
                "orders",
                "cash_subtotal",
                "credit_subtotal",
                "subtotal",
                "tax",
                "tax_withheld",
                "tip",
                "delivery_fee",
                "total",
                "expected_payout",
                "payout",
            ]:
                if col in monthly.columns:
                    monthly[col] = monthly[col].fillna(0.0)
                if f"{col}_override" in monthly.columns:
                    monthly[col] = monthly[f"{col}_override"].combine_first(monthly[col])
            if "notes_override" in monthly.columns:
                if "notes" not in monthly.columns:
                    monthly["notes"] = ""
                monthly["notes"] = monthly["notes"].combine_first(monthly["notes_override"])
            monthly = monthly.drop(
                columns=[c for c in monthly.columns if c.endswith("_override")]
            )
            monthly = monthly.sort_values(["year", "month"], ascending=[False, False])
            for col in ["year", "month"]:
                if col in monthly.columns:
                    monthly[col] = pd.to_numeric(monthly[col], errors="coerce").astype("Int64")

        yearly_numeric_cols = [
            "orders",
            "cash_subtotal",
            "credit_subtotal",
            "subtotal",
            "tax",
            "tax_withheld",
            "tip",
            "delivery_fee",
            "misc_fee",
            "commission_fee",
            "processing_fee",
            "adjustments",
            "marketing_fee",
            "total",
            "expected_payout",
            "payout",
        ]
        yearly = (
            monthly.groupby(["platform", "provider", "year"], dropna=False)[
                [col for col in yearly_numeric_cols if col in monthly.columns]
            ]
            .sum()
            .reset_index()
            .sort_values(["year"], ascending=[False])
        )
        if "year" in yearly.columns:
            yearly["year"] = pd.to_numeric(yearly["year"], errors="coerce").astype("Int64")

        def render_monthly_rollup() -> None:
            st.subheader("Monthly Rollup")
            monthly_column_config = {
                col: st.column_config.NumberColumn(format="dollar")
                for col in money_cols
                if col in monthly.columns
            }
            ordered_monthly = [
                col for col in [
                    "platform",
                    "provider",
                    "year",
                    "month",
                    "orders",
                    "cash_subtotal",
                    "credit_subtotal",
                    "subtotal",
                    "tax",
                    "tax_withheld",
                    "tip",
                    "delivery_fee",
                    "total",
                    "adjustments",
                    "marketing_fee",
                    "misc_fee",
                    "processing_fee",
                    "commission_fee",
                    "expected_payout",
                    "payout",
                    "notes",
                ] if col in monthly.columns
            ] + [col for col in monthly.columns if col not in {
                "platform",
                "provider",
                "year",
                "month",
                "orders",
                "cash_subtotal",
                "credit_subtotal",
                "subtotal",
                "tax",
                "tax_withheld",
                "tip",
                "delivery_fee",
                "total",
                "adjustments",
                "marketing_fee",
                "misc_fee",
                "processing_fee",
                "commission_fee",
                "expected_payout",
                "payout",
                "notes",
            }]
            st.dataframe(monthly[ordered_monthly], column_config=monthly_column_config, width="stretch")

        render_monthly_rollup()
        st.subheader("Yearly Rollup")
        yearly_column_config = {
            col: st.column_config.NumberColumn(format="dollar")
            for col in money_cols
            if col in yearly.columns
        }
        ordered_yearly = [
            col for col in [
                "platform",
                "provider",
                "year",
                "orders",
                "cash_subtotal",
                "credit_subtotal",
                "subtotal",
                "tax",
                "tax_withheld",
                "tip",
                "delivery_fee",
                "total",
                "adjustments",
                "marketing_fee",
                "misc_fee",
                "processing_fee",
                "commission_fee",
                "expected_payout",
                "payout",
            ] if col in yearly.columns
        ] + [col for col in yearly.columns if col not in {
            "platform",
            "provider",
            "year",
            "orders",
            "cash_subtotal",
            "credit_subtotal",
            "subtotal",
            "tax",
            "tax_withheld",
            "tip",
            "delivery_fee",
            "total",
            "adjustments",
            "marketing_fee",
            "misc_fee",
            "processing_fee",
            "commission_fee",
            "expected_payout",
            "payout",
        }]
        st.dataframe(yearly[ordered_yearly], column_config=yearly_column_config, width="stretch")
    with tab_recon:
        st.subheader("Payout Reconciliation")
        base_recon = filtered.copy()
        missing_dates = base_recon["order_datetime"].isna().sum()
        if missing_dates:
            st.caption(f"Rows missing order_datetime: {missing_dates}")
        base_recon = base_recon[base_recon["order_datetime"].notna()]
        if base_recon.empty:
            st.info("No records in current filters.")
        else:
            platform_values = sorted(base_recon["platform"].dropna().astype(str).str.lower().unique().tolist())
            if len(platform_values) != 1:
                st.info("Select a single platform in the filters to view payout reconciliation.")
            else:
                selected_platform = platform_values[0]
                st.caption(f"Platform: {selected_platform}")
                base_recon["order_month"] = base_recon["order_datetime"].dt.to_period("M").dt.to_timestamp()
                base_recon["expected_payout"] = pd.to_numeric(base_recon["expected_payout"], errors="coerce").fillna(0.0)
                base_recon["payout"] = pd.to_numeric(base_recon["payout"], errors="coerce").fillna(0.0)
                expected_monthly = (
                    base_recon.groupby("order_month")
                    .agg(expected_payout_sum=("expected_payout", "sum"), payout_sum=("payout", "sum"), orders=("order_id", "count"))
                    .reset_index()
                )
                wave = load_wave_payouts(selected_platform)
                if wave.empty:
                    st.warning(f"No Wave payout records found for {selected_platform} (wave_payouts_*.csv).")
                    combined = expected_monthly.copy()
                    combined["wave_payout_sum"] = 0.0
                else:
                    wave = wave.dropna(subset=["transaction_date"]).assign(
                        payout_month=lambda d: d["transaction_date"].dt.to_period("M").dt.to_timestamp()
                    )
                    wave_monthly = (
                        wave.groupby("payout_month")
                        .agg(wave_payout_sum=("amount", "sum"))
                        .reset_index()
                    )
                    combined = expected_monthly.merge(
                        wave_monthly,
                        left_on="order_month",
                        right_on="payout_month",
                        how="outer",
                    )
                    if "order_month" in combined.columns and "payout_month" in combined.columns:
                        combined["order_month"] = combined["order_month"].combine_first(combined["payout_month"])
                    combined = combined.drop(columns=[c for c in ["payout_month"] if c in combined.columns])
                combined["expected_payout_sum"] = combined.get("expected_payout_sum", 0.0).fillna(0.0)
                combined["payout_sum"] = combined.get("payout_sum", 0.0).fillna(0.0)
                combined["wave_payout_sum"] = combined.get("wave_payout_sum", 0.0).fillna(0.0)
                combined["delta_wave_vs_expected"] = combined["wave_payout_sum"] - combined["expected_payout_sum"]
                combined = combined.sort_values("order_month")

                recon_column_config = {
                    col: st.column_config.NumberColumn(format="dollar")
                    for col in ["expected_payout_sum", "payout_sum", "wave_payout_sum", "delta_wave_vs_expected"]
                    if col in combined.columns
                }
                st.dataframe(combined, column_config=recon_column_config, width="stretch")

                st.subheader("Wave Payout Transactions")
                if wave.empty:
                    st.info("No payout transactions to show.")
                else:
                    wave_column_config = {
                        col: st.column_config.NumberColumn(format="dollar")
                        for col in ["amount"]
                        if col in wave.columns
                    }
                    st.dataframe(
                        wave.sort_values("transaction_date", ascending=False),
                        column_config=wave_column_config,
                        width="stretch",
                        height=400,
                    )
    with tab_overrides:
        st.subheader("Order Overrides")
        from orders_analytics.utils.order_types import OrderTypes
        from orders_analytics.utils.payment_types import PaymentTypes

        def to_float(value: str):
            try:
                return float(value) if value != "" else None
            except ValueError:
                return None

        def to_datetime(value: str):
            if not value:
                return None
            parsed = pd.to_datetime(value, errors="coerce", utc=True, format="ISO8601")
            if pd.isna(parsed):
                parsed = pd.to_datetime(value, errors="coerce", utc=True)
            if pd.isna(parsed):
                return None
            return parsed.to_pydatetime()

        platform_choices = sorted(data["platform"].dropna().unique().tolist())
        provider_choices = sorted(data["provider"].dropna().unique().tolist())
        with st.expander("Add Order Record"):
            with st.form("add_order_override_form"):
                col_a, col_b = st.columns(2)
                new_order_id = col_a.text_input("Order ID (required)")
                new_platform = col_b.selectbox(
                    "Platform",
                    [""] + platform_choices + ["OTHER"],
                    key="new_order_platform",
                )
                if new_platform == "OTHER":
                    new_platform = st.text_input("Custom Platform", key="new_order_platform_custom")
                new_provider = col_a.selectbox(
                    "Provider",
                    [""] + provider_choices + ["OTHER"],
                    key="new_order_provider",
                )
                if new_provider == "OTHER":
                    new_provider = col_b.text_input("Custom Provider", key="new_order_provider_custom")
                new_order_datetime = col_a.text_input("Order Datetime (ISO)")
                new_order_type = col_b.selectbox(
                    "Order Type",
                    [""] + OrderTypes.get_all(),
                    key="new_order_type",
                )
                new_payment_type = col_a.selectbox(
                    "Payment Type",
                    [""] + PaymentTypes.get_all(),
                    key="new_payment_type",
                )
                new_restaurant = col_b.text_input("Restaurant Name")
                new_customer = col_a.text_input("Customer Name")
                new_address = col_b.text_input("Address")
                new_notes = st.text_area("Notes")
                col_c, col_d = st.columns(2)
                new_subtotal = col_c.text_input("Subtotal")
                new_tax = col_d.text_input("Tax")
                new_tax_withheld = col_c.text_input("Tax Withheld")
                new_tip = col_d.text_input("Tip")
                new_delivery_fee = col_c.text_input("Delivery Fee")
                new_misc_fee = col_d.text_input("Misc Fee")
                new_commission_fee = col_c.text_input("Commission Fee")
                new_processing_fee = col_d.text_input("Processing Fee")
                new_adjustments = col_c.text_input("Adjustments")
                new_marketing_fee = col_d.text_input("Marketing Fee")
                new_total = col_d.text_input("Total")
                add_submitted = st.form_submit_button("Add Record")
            if add_submitted:
                if not new_order_id or not new_platform:
                    st.warning("Order ID and Platform are required.")
                else:
                    conn.execute(
                        """
                        INSERT INTO order_overrides (
                            order_id, platform, provider, restaurant_name, order_datetime, order_type,
                            customer_name, company_name, phone, email, address, payment_type,
                            subtotal, tax, tax_withheld, tip, delivery_fee, misc_fee, commission_fee,
                            processing_fee, adjustments, marketing_fee, total, items, item_count,
                            notes, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (order_id, platform)
                        DO UPDATE SET
                            provider=excluded.provider,
                            restaurant_name=excluded.restaurant_name,
                            order_datetime=excluded.order_datetime,
                            order_type=excluded.order_type,
                            customer_name=excluded.customer_name,
                            company_name=excluded.company_name,
                            phone=excluded.phone,
                            email=excluded.email,
                            address=excluded.address,
                            payment_type=excluded.payment_type,
                            subtotal=excluded.subtotal,
                            tax=excluded.tax,
                            tax_withheld=excluded.tax_withheld,
                            tip=excluded.tip,
                            delivery_fee=excluded.delivery_fee,
                            misc_fee=excluded.misc_fee,
                            commission_fee=excluded.commission_fee,
                            processing_fee=excluded.processing_fee,
                            adjustments=excluded.adjustments,
                            marketing_fee=excluded.marketing_fee,
                            total=excluded.total,
                            items=excluded.items,
                            item_count=excluded.item_count,
                            notes=excluded.notes,
                            updated_at=excluded.updated_at
                        """,
                        (
                            new_order_id,
                            new_platform,
                            new_provider,
                            new_restaurant or "",
                            to_datetime(new_order_datetime),
                            new_order_type or "",
                            new_customer or "",
                            "",
                            "",
                            "",
                            new_address or "",
                            new_payment_type or "",
                            to_float(new_subtotal),
                            to_float(new_tax),
                            to_float(new_tax_withheld),
                            to_float(new_tip),
                            to_float(new_delivery_fee),
                            to_float(new_misc_fee),
                            to_float(new_commission_fee),
                            to_float(new_processing_fee),
                            to_float(new_adjustments),
                            to_float(new_marketing_fee),
                            to_float(new_total),
                            "",
                            "",
                            new_notes or "",
                            datetime.utcnow(),
                        ),
                    )
                    st.success("Order record saved.")
        order_options = (
            filtered[["order_id", "platform"]]
            .dropna()
            .astype(str)
            .agg(" | ".join, axis=1)
        )
        if isinstance(order_options, pd.DataFrame):
            order_options = order_options.iloc[:, 0]
        order_options = order_options.dropna().unique().tolist()
        order_choice = st.selectbox("Select Order", [""] + sorted(order_options))
        if order_choice:
            order_id, platform = [p.strip() for p in order_choice.split("|", 1)]
            row_match = filtered[
                (filtered["order_id"] == order_id) & (filtered["platform"] == platform)
            ]
            if row_match.empty:
                st.warning("Selected order is not in the current filter set.")
                row = None
            else:
                row = row_match.iloc[0]
            if row is not None:
                with st.form("order_override_form"):
                    notes = st.text_area("Notes", value=row.get("notes", "") or "")
                    subtotal = st.text_input("Subtotal", value=str(row.get("subtotal", "")))
                    tax = st.text_input("Tax", value=str(row.get("tax", "")))
                    tip = st.text_input("Tip", value=str(row.get("tip", "")))
                    delivery_fee = st.text_input("Delivery Fee", value=str(row.get("delivery_fee", "")))
                    misc_fee = st.text_input("Misc Fee", value=str(row.get("misc_fee", "")))
                    commission_fee = st.text_input("Commission Fee", value=str(row.get("commission_fee", "")))
                    processing_fee = st.text_input("Processing Fee", value=str(row.get("processing_fee", "")))
                    total = st.text_input("Total", value=str(row.get("total", "")))
                    submitted = st.form_submit_button("Save Overrides")
            else:
                submitted = False
            if submitted and row is not None:
                conn.execute(
                    """
                    INSERT INTO order_overrides (
                        order_id, platform, provider, restaurant_name, order_datetime, order_type,
                        customer_name, company_name, phone, email, address, payment_type,
                        subtotal, tax, tax_withheld, tip, delivery_fee, misc_fee, commission_fee,
                        processing_fee, adjustments, marketing_fee, total, items, item_count,
                        notes, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (order_id, platform)
                    DO UPDATE SET
                        provider=excluded.provider,
                        restaurant_name=excluded.restaurant_name,
                        order_datetime=excluded.order_datetime,
                        order_type=excluded.order_type,
                        customer_name=excluded.customer_name,
                        company_name=excluded.company_name,
                        phone=excluded.phone,
                        email=excluded.email,
                        address=excluded.address,
                        payment_type=excluded.payment_type,
                        subtotal=excluded.subtotal,
                        tax=excluded.tax,
                        tax_withheld=excluded.tax_withheld,
                        tip=excluded.tip,
                        delivery_fee=excluded.delivery_fee,
                        misc_fee=excluded.misc_fee,
                        commission_fee=excluded.commission_fee,
                        processing_fee=excluded.processing_fee,
                        adjustments=excluded.adjustments,
                        marketing_fee=excluded.marketing_fee,
                        total=excluded.total,
                        items=excluded.items,
                        item_count=excluded.item_count,
                        notes=excluded.notes,
                        updated_at=excluded.updated_at
                    """,
                    (
                        row["order_id"],
                        row["platform"],
                        row["provider"],
                        row.get("restaurant_name", ""),
                        row["order_datetime"],
                        row["order_type"],
                        row["customer_name"],
                        row.get("company_name", ""),
                        row["phone"],
                        row.get("email", ""),
                        row["address"],
                        row["payment_type"],
                        to_float(subtotal),
                        to_float(tax),
                        to_float(row.get("tax_withheld", "")),
                        to_float(tip),
                        to_float(delivery_fee),
                        to_float(misc_fee),
                        to_float(commission_fee),
                        to_float(processing_fee),
                        to_float(row.get("adjustments", "")),
                        to_float(row.get("marketing_fee", "")),
                        to_float(total),
                        row.get("items", ""),
                        row.get("item_count", ""),
                        notes,
                        datetime.utcnow(),
                    ),
                )
                st.success("Order override saved.")

        st.subheader("Monthly Notes / Overrides")
        with st.expander("Add Monthly Record"):
            with st.form("add_monthly_override_form"):
                col_a, col_b = st.columns(2)
                new_platform = col_a.selectbox(
                    "Platform",
                    [""] + platform_choices + ["OTHER"],
                    key="new_monthly_platform",
                )
                if new_platform == "OTHER":
                    new_platform = col_b.text_input("Custom Platform", key="new_monthly_platform_custom")
                new_provider = col_a.selectbox(
                    "Provider",
                    [""] + provider_choices + ["OTHER"],
                    key="new_monthly_provider",
                )
                if new_provider == "OTHER":
                    new_provider = col_b.text_input("Custom Provider", key="new_monthly_provider_custom")
                new_year = col_a.number_input("Year", min_value=2000, max_value=2100, step=1, value=2025)
                new_month = col_b.number_input("Month", min_value=1, max_value=12, step=1, value=1)
                notes = st.text_area("Notes", key="new_monthly_notes")
                orders = st.text_input("Orders", key="new_monthly_orders")
                cash_subtotal = st.text_input("Cash Subtotal", key="new_monthly_cash_subtotal")
                credit_subtotal = st.text_input("Credit Subtotal", key="new_monthly_credit_subtotal")
                subtotal = st.text_input("Subtotal", key="new_monthly_subtotal")
                tax = st.text_input("Tax", key="new_monthly_tax")
                tax_withheld = st.text_input("Tax Withheld", key="new_monthly_tax_withheld")
                tip = st.text_input("Tip", key="new_monthly_tip")
                delivery_fee = st.text_input("Delivery Fee", key="new_monthly_delivery_fee")
                misc_fee = st.text_input("Misc Fee", key="new_monthly_misc_fee")
                commission_fee = st.text_input("Commission Fee", key="new_monthly_commission_fee")
                processing_fee = st.text_input("Processing Fee", key="new_monthly_processing_fee")
                adjustments = st.text_input("Adjustments", key="new_monthly_adjustments")
                marketing_fee = st.text_input("Marketing Fee", key="new_monthly_marketing_fee")
                total = st.text_input("Total", key="new_monthly_total")
                add_monthly_submitted = st.form_submit_button("Add Monthly Record")
            if add_monthly_submitted:
                if not new_platform or not new_provider:
                    st.warning("Platform and Provider are required.")
                else:
                    conn.execute(
                        """
                        INSERT INTO monthly_overrides (
                            platform, provider, year, month, orders, cash_subtotal, credit_subtotal,
                            subtotal, tax, tax_withheld, tip, delivery_fee, misc_fee, commission_fee,
                            processing_fee, adjustments, marketing_fee, total, notes, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (platform, provider, year, month)
                        DO UPDATE SET
                            orders=excluded.orders,
                            cash_subtotal=excluded.cash_subtotal,
                            credit_subtotal=excluded.credit_subtotal,
                            subtotal=excluded.subtotal,
                            tax=excluded.tax,
                            tax_withheld=excluded.tax_withheld,
                            tip=excluded.tip,
                            delivery_fee=excluded.delivery_fee,
                            misc_fee=excluded.misc_fee,
                            commission_fee=excluded.commission_fee,
                            processing_fee=excluded.processing_fee,
                            adjustments=excluded.adjustments,
                            marketing_fee=excluded.marketing_fee,
                            total=excluded.total,
                            notes=excluded.notes,
                            updated_at=excluded.updated_at
                        """,
                        (
                            new_platform,
                            new_provider,
                            int(new_year),
                            int(new_month),
                            to_float(orders),
                            to_float(cash_subtotal),
                            to_float(credit_subtotal),
                            to_float(subtotal),
                            to_float(tax),
                            to_float(tax_withheld),
                            to_float(tip),
                            to_float(delivery_fee),
                            to_float(misc_fee),
                            to_float(commission_fee),
                            to_float(processing_fee),
                            to_float(adjustments),
                            to_float(marketing_fee),
                            to_float(total),
                            notes,
                            datetime.utcnow(),
                        ),
                    )
                    st.success("Monthly record saved.")
        if not monthly.empty:
            monthly_choice = st.selectbox(
                "Select Month",
                [""] + [
                    f"{row.platform} | {row.provider} | {int(row.year)}-{int(row.month):02d}"
                    for row in monthly.itertuples()
                ],
            )
            if monthly_choice:
                platform, provider, year_month = [p.strip() for p in monthly_choice.split("|")]
                year = int(year_month.split("-")[0])
                month = int(year_month.split("-")[1])
                row = monthly[
                    (monthly["platform"] == platform)
                    & (monthly["provider"] == provider)
                    & (monthly["year"] == year)
                    & (monthly["month"] == month)
                ].iloc[0]
                with st.form("monthly_override_form"):
                    notes = st.text_area("Notes", value=row.get("notes", "") or "")
                    orders = st.text_input("Orders", value=str(row.get("orders", "")))
                    cash_subtotal = st.text_input("Cash Subtotal", value=str(row.get("cash_subtotal", "")))
                    credit_subtotal = st.text_input("Credit Subtotal", value=str(row.get("credit_subtotal", "")))
                    subtotal = st.text_input("Subtotal", value=str(row.get("subtotal", "")))
                    tax = st.text_input("Tax", value=str(row.get("tax", "")))
                    tax_withheld = st.text_input("Tax Withheld", value=str(row.get("tax_withheld", "")))
                    tip = st.text_input("Tip", value=str(row.get("tip", "")))
                    delivery_fee = st.text_input("Delivery Fee", value=str(row.get("delivery_fee", "")))
                    misc_fee = st.text_input("Misc Fee", value=str(row.get("misc_fee", "")))
                    commission_fee = st.text_input("Commission Fee", value=str(row.get("commission_fee", "")))
                    processing_fee = st.text_input("Processing Fee", value=str(row.get("processing_fee", "")))
                    adjustments = st.text_input("Adjustments", value=str(row.get("adjustments", "")))
                    marketing_fee = st.text_input("Marketing Fee", value=str(row.get("marketing_fee", "")))
                    total = st.text_input("Total", value=str(row.get("total", "")))
                    submitted = st.form_submit_button("Save Monthly Override")
                if submitted:
                    def to_float(value: str):
                        try:
                            return float(value) if value != "" else None
                        except ValueError:
                            return None

                    conn.execute(
                        """
                        INSERT INTO monthly_overrides (
                            platform, provider, year, month, orders, cash_subtotal, credit_subtotal,
                            subtotal, tax, tax_withheld, tip, delivery_fee, misc_fee, commission_fee,
                            processing_fee, adjustments, marketing_fee, total, notes, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (platform, provider, year, month)
                        DO UPDATE SET
                            orders=excluded.orders,
                            cash_subtotal=excluded.cash_subtotal,
                            credit_subtotal=excluded.credit_subtotal,
                            subtotal=excluded.subtotal,
                            tax=excluded.tax,
                            tax_withheld=excluded.tax_withheld,
                            tip=excluded.tip,
                            delivery_fee=excluded.delivery_fee,
                            misc_fee=excluded.misc_fee,
                            commission_fee=excluded.commission_fee,
                            processing_fee=excluded.processing_fee,
                            adjustments=excluded.adjustments,
                            marketing_fee=excluded.marketing_fee,
                            total=excluded.total,
                            notes=excluded.notes,
                            updated_at=excluded.updated_at
                        """,
                        (
                            platform,
                            provider,
                            year,
                            month,
                            to_float(orders),
                            to_float(cash_subtotal),
                            to_float(credit_subtotal),
                            to_float(subtotal),
                            to_float(tax),
                            to_float(tax_withheld),
                            to_float(tip),
                            to_float(delivery_fee),
                            to_float(misc_fee),
                            to_float(commission_fee),
                            to_float(processing_fee),
                            to_float(adjustments),
                            to_float(marketing_fee),
                            to_float(total),
                            notes,
                            datetime.utcnow(),
                        ),
                    )
                st.success("Monthly override saved.")

        render_monthly_rollup()

        st.subheader("Filtered Orders")
        def highlight_errors(row):
            has_error = str(row.get("errors", "") or "").strip() != ""
            color = "background-color: #f8d7da" if has_error else ""
            return [color] * len(row)

        filtered_column_config = {
            col: st.column_config.NumberColumn(format="dollar")
            for col in money_cols
            if col in filtered.columns
        }
        errors_only = filtered[filtered["errors"].astype(str).str.strip() != ""]
        max_style_cells = 260_000
        if errors_only.shape[0] * max(errors_only.shape[1], 1) <= max_style_cells:
            st.dataframe(
                errors_only.style.apply(highlight_errors, axis=1),
                column_config=filtered_column_config,
                width="stretch",
                height=300,
            )
        else:
            st.caption("Errors table is large; showing without highlight.")
            st.dataframe(
                errors_only,
                column_config=filtered_column_config,
                width="stretch",
                height=300,
            )

    with tab_errors:
        st.subheader("Errors")
        errors_df = load_errors()
        for col in ["year", "month"]:
            if col in errors_df.columns:
                errors_df[col] = pd.to_numeric(errors_df[col].replace("", pd.NA), errors="coerce").astype("Int64")
        hide_resolved = st.checkbox("Hide resolved", value=True)
        if hide_resolved and "resolved" in errors_df.columns:
            errors_df = errors_df[errors_df["resolved"].astype(str).str.lower() != "true"]
        st.caption(f"Errors: {len(errors_df)}")

        if errors_df.empty:
            st.info("No errors to display.")
        else:
            max_rows = st.number_input(
                "Max errors to display", min_value=50, max_value=5000, value=500, step=50
            )
            errors_df = errors_df.reset_index().rename(columns={"index": "row_id"})
            st.dataframe(errors_df.head(int(max_rows)), width="stretch")
            for _, row in errors_df.head(int(max_rows)).iterrows():
                with st.expander(f"{row.get('order_id','')} | {row.get('platform','')} | {row.get('provider','')} | {row.get('error_code','')}"):
                    st.write(str(row.get("message", "")))
                    if st.button("Resolve", key=f"resolve_{row['row_id']}"):
                        resolve_error_row(int(row["row_id"]))
                        st.rerun()

    with tab_orders:
        st.subheader("Filtered Orders")
        filtered_column_config = {
            col: st.column_config.NumberColumn(format="dollar")
            for col in money_cols
            if col in filtered.columns
        }
        st.dataframe(filtered, column_config=filtered_column_config, width="stretch", height=600)

    with tab_customer:
        st.subheader("Customer Search")
        st.caption("Searches across all platforms/providers within the current date range.")
        query = st.text_input("Search by customer name, phone, email, or address")
        if query.strip():
            search_base = data.copy()
            search_base = search_base[
                (search_base["order_datetime"] >= pd.to_datetime(start_date))
                & (search_base["order_datetime"] <= pd.to_datetime(end_date) + pd.Timedelta(days=1))
            ]
            search_columns = [
                col
                for col in ["customer_name", "phone", "email", "address", "address_formatted"]
                if col in search_base.columns
            ]
            if not search_columns:
                st.info("No customer fields available to search.")
            else:
                query_text = query.strip()
                mask = pd.Series(False, index=search_base.index)
                for col in search_columns:
                    mask |= search_base[col].astype(str).str.contains(query_text, case=False, na=False)
                results = search_base[mask].copy()
                if "order_datetime" in results.columns:
                    results = results.sort_values("order_datetime", ascending=False)
                st.caption(f"Matches: {len(results)}")
                max_rows = st.number_input(
                    "Max rows to display", min_value=100, max_value=50000, value=5000, step=100
                )
                search_column_config = {
                    col: st.column_config.NumberColumn(format="dollar")
                    for col in money_cols
                    if col in results.columns
                }
                st.dataframe(
                    results.head(int(max_rows)),
                    column_config=search_column_config,
                    width="stretch",
                    height=600,
                )
        else:
            st.info("Enter a search term to see matching orders.")

    with tab_delivery:
        if "lat" in filtered.columns and "lng" in filtered.columns:
            geo = filtered.copy()
            from orders_analytics.utils.order_types import OrderTypes

            geo = geo[geo["order_type"] == OrderTypes.DELIVERY]
            geo["lat"] = pd.to_numeric(geo["lat"], errors="coerce")
            geo["lng"] = pd.to_numeric(geo["lng"], errors="coerce")
            geo = geo.dropna(subset=["lat", "lng"])
            if not geo.empty:
                ref_addresses = [
                    {"label": "AMECI", "address": "25431 Trabuco Road, Lake Forest, CA 92630"},
                    {"label": "AROMA", "address": "20491 Alton Parkway, Lake Forest, CA 92630"},
                ]
                ref_points = []
                cache_path = "orders_analytics/data/raw/geocode_cache.csv"
                if os.path.exists(cache_path):
                    from orders_analytics.utils.geocodio import normalize_key

                    cache_df = pd.read_csv(cache_path, dtype=str).fillna("")
                    cache_map = {
                        str(row.get("key", "")).strip(): row
                        for _, row in cache_df.iterrows()
                        if str(row.get("key", "")).strip()
                    }
                    for ref in ref_addresses:
                        key = normalize_key(ref["address"])
                        cached = cache_map.get(key)
                        if cached is None:
                            continue
                        try:
                            lat = float(cached.get("lat", ""))
                            lng = float(cached.get("lng", ""))
                        except ValueError:
                            continue
                        ref_points.append({"label": ref["label"], "lat": lat, "lng": lng})

                geo["address_display"] = geo["address_formatted"].where(
                    geo["address_formatted"].astype(str).str.strip() != "", geo["address"]
                )
                unique_geo = geo.drop_duplicates(subset=["platform", "provider", "order_id"])
                st.subheader("Delivery Heatmap")
                layers = []
                heat_layer = pdk.Layer(
                    "HeatmapLayer",
                    data=unique_geo,
                    get_position="[lng, lat]",
                    radiusPixels=40,
                    intensity=1.0,
                    threshold=0.2,
                )
                layers.append(heat_layer)
                if ref_points:
                    layers.append(
                        pdk.Layer(
                            "ScatterplotLayer",
                            data=ref_points,
                            get_position="[lng, lat]",
                            get_radius=120,
                            get_fill_color=[0, 0, 0],
                            get_line_color=[0, 0, 0],
                            line_width_min_pixels=1,
                            pickable=True,
                        )
                    )
                    layers.append(
                        pdk.Layer(
                            "TextLayer",
                            data=ref_points,
                            get_position="[lng, lat]",
                            get_text="label",
                            get_color=[0, 0, 0],
                            get_size=16,
                            get_alignment_baseline="'bottom'",
                        )
                    )
                st.pydeck_chart(
                    pdk.Deck(
                        map_style="light",
                        initial_view_state=pdk.ViewState(
                            latitude=unique_geo["lat"].mean(),
                            longitude=unique_geo["lng"].mean(),
                            zoom=10,
                            pitch=0,
                        ),
                        layers=layers,
                        tooltip={"text": "{label}"} if ref_points else None,
                    )
                )

                st.subheader("Delivery Address Counts")
                addr_counts = (
                    unique_geo.groupby(["address_display", "lat", "lng"], dropna=False)
                    .agg(
                        orders=("order_id", "count"),
                        platforms=("platform", lambda s: " | ".join(sorted(set(s.dropna().astype(str))))),
                        providers=("provider", lambda s: " | ".join(sorted(set(s.dropna().astype(str))))),
                        first_ordered=("order_datetime", "min"),
                        last_ordered=("order_datetime", "max"),
                        lifetime_total=("total", "sum"),
                    )
                    .reset_index()
                    .sort_values("orders", ascending=False)
                )
                addr_column_config = {
                    "lifetime_total": st.column_config.NumberColumn(format="dollar"),
                }
                st.dataframe(addr_counts, column_config=addr_column_config, width="stretch")

    with tab_ameci:
        st.subheader("Ameci Royalty (Monthly)")
        st.caption("Royalty providers only: Toast, UberEats, Grubhub, Slice, DoorDash")
        ameci_monthly = monthly[monthly["provider"].astype(str).str.upper() == "AMECI"].copy()
        if ameci_monthly.empty:
            st.info("No AMECI records in current filters.")
        else:
            fee_cols = ["misc_fee", "marketing_fee", "adjustments"]
            for col in fee_cols:
                if col not in ameci_monthly.columns:
                    ameci_monthly[col] = 0.0
            ameci_monthly["calculated_sales_amount"] = (
                ameci_monthly["subtotal"]
                + ameci_monthly["adjustments"]
                + ameci_monthly["misc_fee"]
                + ameci_monthly["marketing_fee"]
            )
            ameci_monthly["royalty"] = ameci_monthly["calculated_sales_amount"] * 0.04

            royalty_platforms = {"toast", "ubereats", "grubhub", "slice", "doordash"}
            ameci_royalty_only = ameci_monthly[ameci_monthly["platform"].astype(str).str.lower().isin(royalty_platforms)].copy()
            if not ameci_royalty_only.empty:
                st.subheader("Royalty Providers Only")
                st.dataframe(ameci_royalty_only, width="stretch")

            total_cols = [
                "orders",
                "cash_subtotal",
                "credit_subtotal",
                "subtotal",
                "tax",
                "tax_withheld",
                "tip",
                "delivery_fee",
                "misc_fee",
                "commission_fee",
                "processing_fee",
                "adjustments",
                "marketing_fee",
                "calculated_sales_amount",
                "total",
                    "royalty",
            ]
            st.subheader("All Providers")
            totals = {col: ameci_monthly[col].sum() for col in total_cols if col in ameci_monthly.columns}
            totals.update({"platform": "", "provider": "Total", "year": "", "month": ""})
            ameci_monthly = ameci_monthly.copy()
            ameci_monthly = pd.concat([ameci_monthly, pd.DataFrame([totals])], ignore_index=True)

            ameci_column_config = {
                col: st.column_config.NumberColumn(format="dollar")
                for col in money_cols + ["calculated_sales_amount", "royalty"]
                if col in ameci_monthly.columns
            }
            st.dataframe(ameci_monthly, column_config=ameci_column_config, width="stretch")

    conn.close()

if __name__ == "__main__":
    main()
