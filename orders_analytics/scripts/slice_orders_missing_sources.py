#!/usr/bin/env python3
import os
from typing import Dict, Iterable, Tuple

import pandas as pd

from orders_analytics.utils.constants import raw_path
from orders_analytics.utils.providers import normalize_provider

MIN_ORDER_DATETIME = pd.Timestamp("2020-01-01")
MAX_ORDER_DATETIME_EXCLUSIVE = pd.Timestamp("2026-01-01")


def _read_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def _normalize_provider_series(series: pd.Series) -> pd.Series:
    return series.astype(str).map(lambda value: normalize_provider(value) or str(value).strip().upper())


def _build_source_frame(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["order_id", "provider", "order_datetime", "source_file", source_name])
    out = df.copy()
    out["order_id"] = out.get("order_id", "").astype(str).str.strip()
    out["provider"] = _normalize_provider_series(out.get("provider", ""))
    out["order_type"] = out.get("order_type", "").astype(str).str.strip().str.lower()
    out = out[(out["order_id"] != "") & (out["provider"] != "")]
    out = out[out["order_type"] != "phone_call"]
    out["order_datetime"] = out.get("order_datetime", "").astype(str).str.strip()
    parsed_dt = pd.to_datetime(out["order_datetime"], errors="coerce")
    out = out[parsed_dt.isna() | ((parsed_dt >= MIN_ORDER_DATETIME) & (parsed_dt < MAX_ORDER_DATETIME_EXCLUSIVE))]
    out["source_file"] = out.get("source_file", "").astype(str).str.strip()
    out[source_name] = True
    out = out.sort_values(["order_datetime", "source_file"], kind="stable")
    out = out.drop_duplicates(subset=["order_id", "provider"], keep="first")
    return out[["order_id", "provider", "order_datetime", "source_file", source_name]]


def _inactive_statement_keys(df: pd.DataFrame) -> set[Tuple[str, str]]:
    if df.empty:
        return set()
    work = df.copy()
    work["order_id"] = work.get("order_id", "").astype(str).str.strip()
    work["provider"] = _normalize_provider_series(work.get("provider", ""))
    status = work.get("status", "active").astype(str).str.strip().str.lower()
    inactive = status.ne("").fillna(False) & status.ne("active")
    return set(zip(work.loc[inactive, "order_id"], work.loc[inactive, "provider"]))


def _manual_cancelled_keys(path: str) -> set[Tuple[str, str]]:
    if not os.path.exists(path):
        return set()
    df = pd.read_csv(path, dtype=str).fillna("")
    if "order_id" not in df.columns or "provider" not in df.columns:
        return set()
    df["order_id"] = df["order_id"].astype(str).str.strip()
    df["provider"] = _normalize_provider_series(df["provider"])
    df = df[(df["order_id"] != "") & (df["provider"] != "")]
    return set(zip(df["order_id"], df["provider"]))


def run(output_path: str | None = None) -> str:
    excel_df = _read_csv(raw_path("slice", "orders_raw_from_excel.csv"))
    history_df = _read_csv(raw_path("slice", "orders_raw_from_history.csv"))
    statements_df = _read_csv(raw_path("slice", "orders_raw_from_statements.csv"))
    manual_cancelled_path = raw_path("slice", "cancelled_orders_manual.csv")

    inactive_statement_keys = _inactive_statement_keys(statements_df)
    manual_cancelled_keys = _manual_cancelled_keys(manual_cancelled_path)

    excel = _build_source_frame(excel_df, "in_excel")
    history = _build_source_frame(history_df, "in_history")
    statements = _build_source_frame(statements_df, "in_statements")

    merged = excel.merge(history, on=["order_id", "provider"], how="outer", suffixes=("_excel", "_history"))
    merged = merged.merge(statements, on=["order_id", "provider"], how="outer")

    for col in [
        "order_datetime_excel",
        "source_file_excel",
        "order_datetime_history",
        "source_file_history",
        "order_datetime",
        "source_file",
    ]:
        if col not in merged.columns:
            merged[col] = ""

    merged["order_datetime"] = (
        merged["order_datetime_excel"]
        .where(merged["order_datetime_excel"] != "", merged["order_datetime_history"])
        .where(lambda s: s != "", merged["order_datetime"])
    )
    merged["source_file"] = (
        merged["source_file_excel"]
        .where(merged["source_file_excel"] != "", merged["source_file_history"])
        .where(lambda s: s != "", merged["source_file"])
    )

    for col in ["in_excel", "in_history", "in_statements"]:
        if col not in merged.columns:
            merged[col] = False
        merged[col] = merged[col].fillna(False).astype(bool)

    excluded_keys = inactive_statement_keys | manual_cancelled_keys
    if excluded_keys:
        merged = merged[~merged.apply(lambda row: (row["order_id"], row["provider"]) in excluded_keys, axis=1)]

    merged["missing_sources"] = merged.apply(
        lambda row: ",".join(
            source for source, flag in [
                ("excel", row["in_excel"]),
                ("history", row["in_history"]),
                ("statements", row["in_statements"]),
            ] if not flag
        ),
        axis=1,
    )
    merged = merged[merged["missing_sources"] != ""].copy()

    output_cols = [
        "order_id",
        "provider",
        "order_datetime",
        "in_excel",
        "in_history",
        "in_statements",
        "missing_sources",
        "source_file",
    ]
    merged = merged[output_cols].sort_values(["provider", "order_datetime", "order_id"], kind="stable")
    output_path = output_path or raw_path("slice", "orders_missing_sources.csv")
    merged.to_csv(output_path, index=False)
    return output_path


if __name__ == "__main__":
    path = run()
    print(path)
