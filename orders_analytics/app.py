#!/usr/bin/env python3
import os
import sys
from datetime import datetime

import duckdb
import pandas as pd
import streamlit as st

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from orders_analytics.utils.constants import DEFAULT_DB_PATH, NORMALIZED_DIR


ORDER_COLUMNS = [
    "order_id",
    "platform",
    "provider",
    "restaurant",
    "order_datetime",
    "order_type",
    "customer_name",
    "phone",
    "address",
    "payment_type",
    "subtotal",
    "tax",
    "tip",
    "delivery_fee",
    "misc_fee",
    "commission_fee",
    "processing_fee",
    "total",
    "items",
    "items_count",
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
            restaurant TEXT,
            order_datetime TIMESTAMP,
            order_type TEXT,
            customer_name TEXT,
            phone TEXT,
            address TEXT,
            payment_type TEXT,
            subtotal DOUBLE,
            tax DOUBLE,
            tip DOUBLE,
            delivery_fee DOUBLE,
            misc_fee DOUBLE,
            commission_fee DOUBLE,
            processing_fee DOUBLE,
            total DOUBLE,
            items TEXT,
            items_count TEXT,
            notes TEXT,
            updated_at TIMESTAMP
        )
        """
    )
    conn.execute("ALTER TABLE order_overrides ADD COLUMN IF NOT EXISTS misc_fee DOUBLE")
    conn.execute("ALTER TABLE order_overrides ADD COLUMN IF NOT EXISTS commission_fee DOUBLE")
    conn.execute("ALTER TABLE order_overrides ADD COLUMN IF NOT EXISTS processing_fee DOUBLE")
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
            subtotal DOUBLE,
            tax DOUBLE,
            tip DOUBLE,
            delivery_fee DOUBLE,
            misc_fee DOUBLE,
            commission_fee DOUBLE,
            merchant_fee DOUBLE,
            total DOUBLE,
            notes TEXT,
            updated_at TIMESTAMP
        )
        """
    )
    conn.execute("ALTER TABLE monthly_overrides ADD COLUMN IF NOT EXISTS misc_fee DOUBLE")
    conn.execute("ALTER TABLE monthly_overrides ADD COLUMN IF NOT EXISTS commission_fee DOUBLE")
    conn.execute("ALTER TABLE monthly_overrides ADD COLUMN IF NOT EXISTS processing_fee DOUBLE")
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
        "tip",
        "delivery_fee",
        "misc_fee",
        "commission_fee",
        "processing_fee",
        "total",
    ]
    for col in numeric_cols:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce")
        override_col = f"{col}_override"
        if override_col in merged.columns:
            merged[override_col] = pd.to_numeric(merged[override_col], errors="coerce")
            merged[col] = merged[override_col].combine_first(merged[col])
    for col in [
        "provider",
        "restaurant",
        "order_datetime",
        "order_type",
        "customer_name",
        "phone",
        "address",
        "payment_type",
        "items",
        "items_count",
        "notes",
    ]:
        override_col = f"{col}_override"
        if override_col in merged.columns:
            merged[col] = merged[override_col].combine_first(merged[col])
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
        grain = st.selectbox("Date Grain", ["day", "month", "year"])

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
    default_start = min_date.date() if not pd.isna(min_date) else max_value
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

    numeric_cols = ["subtotal", "tax", "tip", "delivery_fee", "total", "misc_fee", "commission_fee", "merchant_fee"]
    for col in numeric_cols:
        if col in filtered.columns:
            filtered[col] = pd.to_numeric(filtered[col], errors="coerce")
        else:
            filtered[col] = 0.0
        filtered[col] = filtered[col].fillna(0.0)

    filtered = add_date_grain(filtered, grain)

    summary = (
        filtered.groupby("date_bucket")
        .agg(
            orders=("order_id", "count"),
            subtotal=("subtotal", "sum"),
            tax=("tax", "sum"),
            tip=("tip", "sum"),
            delivery_fee=("delivery_fee", "sum"),
            total=("total", "sum"),
        )
        .reset_index()
        .sort_values("date_bucket")
    )

    st.subheader("Summary")
    st.dataframe(summary, width="stretch")
    st.line_chart(summary.set_index("date_bucket")[["total", "subtotal", "tip"]])

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
            subtotal=("subtotal", "sum"),
            tax=("tax", "sum"),
            tip=("tip", "sum"),
            delivery_fee=("delivery_fee", "sum"),
            total=("total", "sum"),
        )
        .reset_index()
    )
    for col in ["misc_fee", "commission_fee", "processing_fee"]:
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
            "subtotal",
            "tax",
            "tip",
            "delivery_fee",
            "misc_fee",
            "commission_fee",
            "processing_fee",
            "total",
        ]:
            if f"{col}_override" in monthly.columns:
                monthly[col] = monthly[f"{col}_override"].combine_first(monthly[col])
        if "notes_override" in monthly.columns:
            monthly["notes"] = monthly["notes"].combine_first(monthly["notes_override"])
        monthly = monthly.drop(
            columns=[c for c in monthly.columns if c.endswith("_override")]
        )
    st.subheader("Monthly Rollup")
    st.dataframe(monthly, width="stretch")

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
                    order_id, platform, provider, restaurant, order_datetime, order_type,
                    customer_name, phone, address, payment_type, subtotal, tax, tip,
                    delivery_fee, misc_fee, commission_fee, processing_fee, total,
                    items, items_count, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (order_id, platform)
                DO UPDATE SET
                    provider=excluded.provider,
                    restaurant=excluded.restaurant,
                    order_datetime=excluded.order_datetime,
                    order_type=excluded.order_type,
                    customer_name=excluded.customer_name,
                    phone=excluded.phone,
                    address=excluded.address,
                    payment_type=excluded.payment_type,
                    subtotal=excluded.subtotal,
                    tax=excluded.tax,
                    tip=excluded.tip,
                    delivery_fee=excluded.delivery_fee,
                    misc_fee=excluded.misc_fee,
                    commission_fee=excluded.commission_fee,
                    processing_fee=excluded.processing_fee,
                    total=excluded.total,
                    items=excluded.items,
                    items_count=excluded.items_count,
                    notes=excluded.notes,
                    updated_at=excluded.updated_at
                """,
                (
                    row["order_id"],
                    row["platform"],
                    row["provider"],
                    row["restaurant"],
                    row["order_datetime"],
                    row["order_type"],
                    row["customer_name"],
                    row["phone"],
                    row["address"],
                    row["payment_type"],
                    to_float(subtotal),
                    to_float(tax),
                    to_float(tip),
                    to_float(delivery_fee),
                    to_float(misc_fee),
                    to_float(commission_fee),
                    to_float(processing_fee),
                    to_float(total),
                    row.get("items", ""),
                    row.get("items_count", ""),
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
                subtotal = st.text_input("Subtotal", value=str(row.get("subtotal", "")))
                tax = st.text_input("Tax", value=str(row.get("tax", "")))
                tip = st.text_input("Tip", value=str(row.get("tip", "")))
                delivery_fee = st.text_input("Delivery Fee", value=str(row.get("delivery_fee", "")))
                misc_fee = st.text_input("Misc Fee", value=str(row.get("misc_fee", "")))
                commission_fee = st.text_input("Commission Fee", value=str(row.get("commission_fee", "")))
                processing_fee = st.text_input("Processing Fee", value=str(row.get("processing_fee", "")))
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
                        platform, provider, year, month, orders, subtotal, tax, tip,
                        delivery_fee, misc_fee, commission_fee, processing_fee, total, notes, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (platform, provider, year, month)
                    DO UPDATE SET
                        orders=excluded.orders,
                        subtotal=excluded.subtotal,
                        tax=excluded.tax,
                        tip=excluded.tip,
                        delivery_fee=excluded.delivery_fee,
                        misc_fee=excluded.misc_fee,
                        commission_fee=excluded.commission_fee,
                        processing_fee=excluded.processing_fee,
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
                        to_float(subtotal),
                        to_float(tax),
                        to_float(tip),
                        to_float(delivery_fee),
                        to_float(misc_fee),
                        to_float(commission_fee),
                        to_float(processing_fee),
                        to_float(total),
                        notes,
                        datetime.utcnow(),
                    ),
                )
                st.success("Monthly override saved.")

    st.subheader("Filtered Orders")
    st.dataframe(filtered, width="stretch")

    conn.close()


if __name__ == "__main__":
    main()
