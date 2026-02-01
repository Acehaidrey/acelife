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
    "customer_name",
    "company_name",
    "phone",
    "email",
    "address",
    "address_formatted",
    "lat",
    "lng",
    "payment_type",
    "restaurant_name",
    "items",
    "item_count",
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
    overrides = conn.execute("SELECT * FROM order_overrides").df()
    if overrides.empty:
        raw["order_datetime"] = pd.to_datetime(
            raw["order_datetime"], errors="coerce", utc=True, format="ISO8601"
        )
        raw["order_datetime"] = raw["order_datetime"].dt.tz_convert(None)
        for col in ORDER_COLUMNS:
            if col not in raw.columns:
                raw[col] = ""
        return raw[ORDER_COLUMNS]

    merged = raw.merge(
        overrides,
        on=["order_id", "platform"],
        how="left",
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

    platform_options = ["ALL"] + sorted(data["platform"].dropna().unique().tolist())
    provider_options = ["ALL"] + sorted(data["provider"].dropna().unique().tolist())

    col1, col2, col3 = st.columns(3)
    with col1:
        platform = st.selectbox("Platform", platform_options)
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

    start_date, end_date = st.date_input(
        "Date Range",
        value=(default_start, default_end),
        min_value=default_start,
        max_value=max_value,
    )

    filtered = data.copy()
    if platform != "ALL":
        filtered = filtered[filtered["platform"] == platform]
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
    tab_summary, tab_overrides, tab_delivery = st.tabs(
        ["Summary", "Overrides", "Delivery Map"]
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
            monthly = monthly.merge(
                overrides,
                on=["platform", "provider", "year", "month"],
                how="left",
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
                if f"{col}_override" in monthly.columns:
                    monthly[col] = monthly[f"{col}_override"].combine_first(monthly[col])
            if "notes_override" in monthly.columns:
                monthly["notes"] = monthly["notes"].combine_first(monthly["notes_override"])
            monthly = monthly.drop(
                columns=[c for c in monthly.columns if c.endswith("_override")]
            )
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
        def render_monthly_rollup() -> None:
            st.subheader("Monthly Rollup")
            monthly_column_config = {
                col: st.column_config.NumberColumn(format="dollar")
                for col in money_cols
                if col in monthly.columns
            }
            st.dataframe(monthly, column_config=monthly_column_config, width="stretch")

        render_monthly_rollup()

    with tab_overrides:
        st.subheader("Order Overrides")
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
                def to_float(value: str):
                    try:
                        return float(value) if value != "" else None
                    except ValueError:
                        return None

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
        filtered_column_config = {
            col: st.column_config.NumberColumn(format="dollar")
            for col in money_cols
            if col in filtered.columns
        }
        st.dataframe(filtered, column_config=filtered_column_config, width="stretch")

    with tab_delivery:
        if "lat" in filtered.columns and "lng" in filtered.columns:
            geo = filtered.copy()
            geo = geo[geo["order_type"] == "delivery"]
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

                st.subheader("Top 25 Delivery Addresses")
                addr_counts = (
                    unique_geo.groupby(["address_display", "lat", "lng"], dropna=False)
                    .size()
                    .reset_index(name="orders")
                    .sort_values("orders", ascending=False)
                    .head(25)
                )
                st.dataframe(addr_counts, width="stretch")

    conn.close()


if __name__ == "__main__":
    main()
