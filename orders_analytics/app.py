#!/usr/bin/env python3
import os
import sys
from datetime import datetime

import duckdb
import pandas as pd
import streamlit as st
import pydeck as pdk

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from orders_analytics.utils.constants import DEFAULT_DB_PATH, NORMALIZED_DIR


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
    tab_summary, tab_overrides, tab_orders, tab_delivery, tab_ameci = st.tabs(
        ["Summary", "Overrides", "Orders", "Delivery Map", "Ameci Royalty"]
    )

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
            "net_payout",
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
                "misc_fee",
                "commission_fee",
                "processing_fee",
                "adjustments",
                "marketing_fee",
                "total",
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
        def positive_only(series):
            return series.where(series > 0, 0)

        monthly["net_payout"] = (
            monthly["credit_subtotal"]
            + monthly["tax"]
            + monthly["tip"]
            + monthly["delivery_fee"]
            + monthly["adjustments"]
            - positive_only(monthly["commission_fee"])
            - positive_only(monthly["processing_fee"])
            - positive_only(monthly["marketing_fee"])
            - positive_only(monthly["misc_fee"])
        )
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
            "net_payout",
        ]
        yearly = (
            monthly.groupby(["platform", "provider", "year"], dropna=False)[
                [col for col in yearly_numeric_cols if col in monthly.columns]
            ]
            .sum()
            .reset_index()
            .sort_values(["year"], ascending=[False])
        )
        def render_monthly_rollup() -> None:
            st.subheader("Monthly Rollup")
            monthly_column_config = {
                col: st.column_config.NumberColumn(format="dollar")
                for col in money_cols
                if col in monthly.columns
            }
            st.dataframe(monthly, column_config=monthly_column_config, width="stretch")

        render_monthly_rollup()
        st.subheader("Yearly Rollup")
        yearly_column_config = {
            col: st.column_config.NumberColumn(format="dollar")
            for col in money_cols
            if col in yearly.columns
        }
        st.dataframe(yearly, column_config=yearly_column_config, width="stretch")

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

    with tab_orders:
        st.subheader("Filtered Orders")
        filtered_column_config = {
            col: st.column_config.NumberColumn(format="dollar")
            for col in money_cols
            if col in filtered.columns
        }
        st.dataframe(filtered, column_config=filtered_column_config, width="stretch", height=600)

    with tab_delivery:
        if "lat" in filtered.columns and "lng" in filtered.columns:
            geo = filtered.copy()
            from orders_analytics.utils.order_types import OrderTypes

            geo = geo[geo["order_type"] == OrderTypes.DELIVERY]
            geo["lat"] = pd.to_numeric(geo["lat"], errors="coerce")
            geo["lng"] = pd.to_numeric(geo["lng"], errors="coerce")
            geo = geo.dropna(subset=["lat", "lng"])
            if not geo.empty:
                geo["address_display"] = geo["address_formatted"].where(
                    geo["address_formatted"].astype(str).str.strip() != "", geo["address"]
                )
                unique_geo = geo.drop_duplicates(subset=["platform", "provider", "order_id"])
                st.subheader("Delivery Heatmap")
                heat_layer = pdk.Layer(
                    "HeatmapLayer",
                    data=unique_geo,
                    get_position="[lng, lat]",
                    radiusPixels=40,
                    intensity=1.0,
                    threshold=0.2,
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
                        layers=[heat_layer],
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
                "net_payout",
                "royalty",
            ]
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
