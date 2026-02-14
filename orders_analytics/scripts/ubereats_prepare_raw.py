#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import hashlib
from pathlib import Path
from typing import List

import pandas as pd

from orders_analytics.utils.constants import raw_path, takeout_path
from orders_analytics.utils.providers import normalize_provider

BACKFILL_PATH = takeout_path("uber_reports2022_missing_from_base.csv")

NULL_LIKE = {"", "0", "0.0", "0.00", "0.000"}




def _add_offers_excl(df: pd.DataFrame) -> pd.DataFrame:
    if "Offers on items (incl. tax)" not in df.columns or "Tax On Offers on items" not in df.columns:
        return df
    offers_incl = pd.to_numeric(df["Offers on items (incl. tax)"].replace({"": None}), errors="coerce")
    offers_tax = pd.to_numeric(df["Tax On Offers on items"].replace({"": None}), errors="coerce")
    offers_excl = offers_incl - offers_tax
    df = df.copy()
    df["Offers on items (excl. tax)"] = offers_excl.round(2).apply(lambda v: "" if pd.isna(v) else f"{v:.2f}")
    return df

def _read_source(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, header=1, encoding="utf-8-sig").fillna("")
    if "Order ID" not in df.columns:
        df = pd.read_csv(path, dtype=str, header=0, encoding="utf-8-sig").fillna("")
    column_map = {
        "Order Date / Refund date": "Order Date",
        "Order Date/Refund Date": "Order Date",
        "Food Sales (excluding tax)": "Sales (excl. tax)",
        "Tax on Food Sales": "Tax on Sales",
        "Food sales (including tax)": "Sales (incl. tax)",
        "Total Sales after Adjustments (including tax)": "Total Sales after Adjustments (incl tax)",
        "Total Sales after Adjustments (incl. tax)": "Total Sales after Adjustments (incl tax)",
        "Total Sales After Adjustments (incl tax)": "Total Sales after Adjustments (incl tax)",
        "Total Sales After Adjustments (incl. tax)": "Total Sales after Adjustments (incl tax)",
        "Adjustments (excluding tax)": "Price adjustments (excl. tax)",
        "Tax on Adjustments": "Tax on Price Adjustments",
        "Promo Spend on food": "Offers on items (incl. tax)",
        "Tax on Promotion on Food": "Tax On Offers on items",
        "Promo Spend on Delivery": "Delivery Offer Redemptions (incl. tax)",
        "Tax on Promo Spend on Delivery": "Tax On Delivery Offer Redemptions",
        "Marketing Service Fee Adjustment": "Marketing Adjustment",
        "Uber Service Fee": "Marketplace Fee",
        "Gratuity": "Tips",
        "Miscellaneous Payments": "Other payments",
        "Misc Payment Description": "Other payments description",
        "Payout": "Total payout ",
        "Dispatch Fee": "Delivery Network Fee",
        "Tax on Dispatch Fee": "Tax on Delivery Network Fee",
        "Marketplace Facilitator Tax Adjustment": "Marketplace Facilitator Tax Adjustment\n",
    }
    df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})
    df = df.loc[:, ~df.columns.duplicated()]
    return df


def _is_null_like(series: pd.Series) -> pd.Series:
    s = series.fillna("").astype(str).str.strip()
    return s.isin(NULL_LIKE)


def _trim_columns(df: pd.DataFrame) -> pd.DataFrame:
    keep_cols: List[str] = []
    for col in df.columns:
        if not _is_null_like(df[col]).all():
            keep_cols.append(col)
    return df[keep_cols]


def _numeric_columns(df: pd.DataFrame, exclude: set[str]) -> List[str]:
    numeric_cols: List[str] = []
    for col in df.columns:
        if col in exclude:
            continue
        series = df[col]
        series_str = series.astype(str)
        nums = pd.to_numeric(series_str.str.replace(",", "", regex=False), errors="coerce")
        if nums.notna().any():
            numeric_cols.append(col)
            df[col] = nums
    return numeric_cols


def _join_distinct(series: pd.Series) -> str:
    vals = sorted({v.strip() for v in series.astype(str) if v.strip()})
    return ", ".join(vals)


def _round_numeric(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        series = df[col]
        series_str = series.astype(str)
        nums = pd.to_numeric(series_str.str.replace(",", "", regex=False), errors="coerce")
        if nums.notna().any():
            df[col] = nums.round(2).apply(lambda v: "" if pd.isna(v) else f"{v:.2f}")
    return df


def _reorder_all_null_columns(df: pd.DataFrame, original_order: List[str]) -> pd.DataFrame:
    cols_in_df = [c for c in original_order if c in df.columns]
    extra_cols = [c for c in df.columns if c not in cols_in_df]

    empty_cols = []
    keep_cols = []
    for col in cols_in_df + extra_cols:
        if _is_null_like(df[col]).all():
            empty_cols.append(col)
        else:
            keep_cols.append(col)
    return df[keep_cols + empty_cols]


def _last_day_date(month_value: str) -> str:
    text = str(month_value or "").strip()
    if not text or text.lower() == "nan":
        return ""
    parts = text.split("-")
    if len(parts) != 2:
        return ""
    year = int(parts[0])
    month = int(parts[1])
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-{last_day:02d}"


def _make_monthly_order_id(provider: str, month: str, desc: str) -> str:
    key = f"{provider}|{month}|{desc}"
    suffix = hashlib.md5(key.encode("utf-8")).hexdigest()[:10]
    return f"UBER_OTHER_{suffix}"


def _build_no_ids_monthly(df: pd.DataFrame, colmap: dict[str, str]) -> pd.DataFrame:
    store_name_col = colmap.get("store name")
    order_date_col = colmap.get("order date")
    other_desc_col = colmap.get("other payments description")
    order_status_col = colmap.get("order status")

    order_dates = pd.to_datetime(df[order_date_col], errors="coerce")
    df = df.copy()
    df["_order_month"] = order_dates.dt.to_period("M").astype(str)

    exclude = {store_name_col, order_date_col, other_desc_col, "_order_month"}
    numeric_cols = _numeric_columns(df, exclude)

    group_cols = [store_name_col, "_order_month", other_desc_col]
    if order_status_col:
        group_cols.append(order_status_col)

    agg_df = (
        df.groupby(group_cols, dropna=False)
        .agg({c: "sum" for c in numeric_cols})
        .reset_index()
    )

    agg_df["Order ID"] = agg_df.apply(
        lambda row: _make_monthly_order_id(
            normalize_provider(str(row.get(store_name_col, ""))) or "UNKNOWN",
            str(row.get("_order_month", "")),
            str(row.get(other_desc_col, "")),
        ),
        axis=1,
    )
    agg_df["Order Date"] = agg_df["_order_month"].apply(_last_day_date)
    agg_df["Order Accept Time"] = "12:00 AM"
    if order_status_col and order_status_col in agg_df.columns:
        agg_df[order_status_col] = "Completed"

    for col in agg_df.columns:
        if col.lower().strip() in {"other payments", "total payout"}:
            nums = pd.to_numeric(agg_df[col], errors="coerce")
            agg_df[col] = nums.round(2).apply(lambda v: "" if pd.isna(v) else f"{v:.2f}")

    return agg_df


def _build_duplicate_workflow(df: pd.DataFrame, workflow_col: str) -> pd.DataFrame:
    numeric_cols = _numeric_columns(df, exclude={workflow_col})
    string_cols = [c for c in df.columns if c not in numeric_cols]

    agg_dict = {col: "sum" for col in numeric_cols}
    for col in string_cols:
        if col == workflow_col:
            agg_dict[col] = "first"
        else:
            agg_dict[col] = _join_distinct

    merged = (
        df.groupby(workflow_col, dropna=False)
        .agg(agg_dict)
        .reset_index(drop=True)
    )
    if "Total Sales after Adjustments (incl tax)" in merged.columns and "Order Error Adjustments (incl. tax)" in merged.columns:
        total_vals = pd.to_numeric(merged["Total Sales after Adjustments (incl tax)"], errors="coerce")
        adj_vals = pd.to_numeric(merged["Order Error Adjustments (incl. tax)"], errors="coerce")
        merged["Total Sales after Adjustments (incl tax)"] = (total_vals.fillna(0) + adj_vals.fillna(0)).round(2)
    counts = df[workflow_col].value_counts(dropna=False).rename("merged_row_count")
    merged = merged.merge(counts, left_on=workflow_col, right_index=True, how="left")
    return merged


def run(source_path: str) -> None:
    df = _read_source(source_path)
    backfill_df = pd.DataFrame()
    if BACKFILL_PATH and Path(BACKFILL_PATH).exists():
        backfill_df = _read_source(BACKFILL_PATH)
        if "Order Date" in backfill_df.columns:
            backfill_df["Order Date"] = pd.to_datetime(backfill_df["Order Date"], errors="coerce")
            feb_mask = (backfill_df["Order Date"] >= "2021-02-01") & (backfill_df["Order Date"] < "2021-03-01")
            if "Order ID" in backfill_df.columns and "Workflow ID" in backfill_df.columns:
                backfill_feb = backfill_df[feb_mask].drop_duplicates(subset=["Order ID", "Workflow ID"])
                backfill_other = backfill_df[~feb_mask]
                backfill_df = pd.concat([backfill_other, backfill_feb], ignore_index=True)

    orig_cols = list(df.columns)
    colmap = {c.lower().strip(): c for c in orig_cols}
    os_raw = Path(raw_path("ubereats"))
    os_raw.mkdir(parents=True, exist_ok=True)

    order_id_col = colmap.get("order id")
    workflow_col = colmap.get("workflow id")

    base_for_missing = df
    if not backfill_df.empty:
        base_for_missing = pd.concat([df, backfill_df], ignore_index=True)
    extra_cols = [c for c in base_for_missing.columns if c not in orig_cols]

    no_ids = base_for_missing[(base_for_missing[order_id_col].str.strip() == "") & (base_for_missing[workflow_col].str.strip() == "")].copy()
    no_ids_out = os_raw / "no_order_ids.csv"
    if not no_ids.empty:
        _trim_columns(no_ids).to_csv(no_ids_out, index=False)
    else:
        no_ids_out.write_text("", encoding="utf-8")

    no_ids_monthly = _build_no_ids_monthly(no_ids, colmap) if not no_ids.empty else pd.DataFrame()
    no_ids_monthly_out = os_raw / "no_order_ids_other_payments_monthly.csv"
    if not no_ids_monthly.empty:
        no_ids_monthly = _add_offers_excl(no_ids_monthly)
        _round_numeric(no_ids_monthly).to_csv(no_ids_monthly_out, index=False)
    else:
        no_ids_monthly_out.write_text("", encoding="utf-8")

    workflow_present_base = base_for_missing[workflow_col].str.strip() != ""
    with_ids = base_for_missing[(workflow_present_base) | (base_for_missing[order_id_col].str.strip() != "")].copy()
    workflow_counts = base_for_missing[workflow_present_base][workflow_col].value_counts(dropna=False)
    dup_workflows = workflow_counts[workflow_counts > 1].index
    dup_df = base_for_missing[workflow_present_base & base_for_missing[workflow_col].isin(dup_workflows)].copy()

    dup_out = os_raw / "duplicate_workflow_records.csv"
    if not dup_df.empty:
        _trim_columns(dup_df).to_csv(dup_out, index=False)
    else:
        dup_out.write_text("", encoding="utf-8")

    merged_dup = _build_duplicate_workflow(dup_df, workflow_col) if not dup_df.empty else pd.DataFrame()
    merged_dup_out = os_raw / "duplicate_workflow_records_merged.csv"
    if not merged_dup.empty:
        _round_numeric(merged_dup).to_csv(merged_dup_out, index=False)
    else:
        merged_dup_out.write_text("", encoding="utf-8")

    workflow_present = with_ids[workflow_col].str.strip() != ""
    regular = with_ids[~(workflow_present & with_ids[workflow_col].isin(dup_workflows))].copy()

    # align columns to original set + merged_row_count
    if not merged_dup.empty:
        merged_dup = merged_dup.reindex(columns=orig_cols + extra_cols + ["merged_row_count"], fill_value="")
    if not no_ids_monthly.empty:
        no_ids_monthly = no_ids_monthly.reindex(columns=orig_cols + extra_cols + ["merged_row_count"], fill_value="")
    regular = regular.reindex(columns=orig_cols + extra_cols + ["merged_row_count"], fill_value="")

    stitched = pd.concat([regular, merged_dup, no_ids_monthly], ignore_index=True, sort=False)
    stitched = _add_offers_excl(stitched)
    # place Offers on items (excl. tax) after Offers on items (incl. tax)
    if "Offers on items (excl. tax)" in stitched.columns and "Offers on items (incl. tax)" in stitched.columns:
        cols = list(stitched.columns)
        cols = [c for c in cols if c != "Offers on items (excl. tax)"]
        idx = cols.index("Offers on items (incl. tax)") + 1
        cols.insert(idx, "Offers on items (excl. tax)")
        stitched = stitched[cols]
    stitched = _reorder_all_null_columns(stitched, orig_cols + extra_cols + ["merged_row_count"])
    stitched_out = os_raw / "ubereats_stitched_raw.csv"
    stitched.to_csv(stitched_out, index=False)

    print(f"no_order_ids_rows={len(no_ids)} -> {no_ids_out}")
    print(f"no_order_ids_monthly_rows={len(no_ids_monthly)} -> {no_ids_monthly_out}")
    print(f"duplicate_workflow_rows={len(dup_df)} -> {dup_out}")
    print(f"duplicate_workflow_merged_rows={len(merged_dup)} -> {merged_dup_out}")
    print(f"stitched_rows={len(stitched)} -> {stitched_out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare Uber Eats raw data for normalization.")
    parser.add_argument(
        "--csv",
        default=takeout_path("uber-bc08b66d-0603-49ef-8186-07a637505732-united_states.csv"),
        help="Path to Uber Eats export CSV.",
    )
    args = parser.parse_args()
    run(args.csv)


if __name__ == "__main__":
    main()
