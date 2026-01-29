from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List

import pandas as pd

ERROR_COLUMNS = [
    "order_id",
    "platform",
    "provider",
    "error_code",
    "message",
    "source",
    "created_at",
    "resolved",
    "resolved_time",
]


def error_key(error: Dict[str, str]) -> str:
    return "|".join(
        [
            str(error.get("order_id", "")).strip(),
            str(error.get("platform", "")).strip(),
            str(error.get("provider", "")).strip(),
            str(error.get("error_code", "")).strip(),
        ]
    )


def write_errors(errors: List[Dict[str, str]], path: str) -> int:
    if not errors:
        return 0
    now = datetime.now().isoformat()
    for error in errors:
        error.setdefault("created_at", now)
        error.setdefault("resolved", "false")
        error.setdefault("resolved_time", "")

    if os.path.exists(path):
        existing_df = pd.read_csv(path, dtype=str).fillna("")
        existing_rows = existing_df.to_dict("records")
    else:
        existing_rows = []

    existing_map = {error_key(row): row for row in existing_rows}
    inserted = 0
    for error in errors:
        key = error_key(error)
        if not key.strip("|"):
            continue
        if key in existing_map:
            # Do not update existing records; if resolved, keep as-is.
            continue
        existing_map[key] = error
        inserted += 1

    os.makedirs(os.path.dirname(path), exist_ok=True)
    df = pd.DataFrame(list(existing_map.values()))
    df = df.reindex(columns=ERROR_COLUMNS, fill_value="")
    df.to_csv(path, index=False)
    return inserted


def reconcile_errors(errors: List[Dict[str, str]], path: str) -> int:
    """
    Upsert current errors and auto-resolve stale ones.
    - New errors are inserted (no duplicates by key).
    - Existing errors not present in the current set are marked resolved=true.
    """
    now = datetime.now().isoformat()
    current_map = {}
    for error in errors:
        error.setdefault("created_at", now)
        error.setdefault("resolved", "false")
        error.setdefault("resolved_time", "")
        key = error_key(error)
        if key.strip("|"):
            current_map[key] = error

    if os.path.exists(path):
        existing_df = pd.read_csv(path, dtype=str).fillna("")
        existing_rows = existing_df.to_dict("records")
    else:
        existing_rows = []

    existing_map = {error_key(row): row for row in existing_rows}
    inserted = 0
    # insert new errors
    for key, error in current_map.items():
        if key not in existing_map:
            existing_map[key] = error
            inserted += 1
        else:
            # If previously resolved but still present, unresolve.
            if existing_map[key].get("resolved") == "true":
                existing_map[key]["resolved"] = "false"
                existing_map[key]["resolved_time"] = ""

    # resolve stale errors
    for key, row in existing_map.items():
        if key not in current_map:
            if row.get("resolved") != "true":
                row["resolved"] = "true"
                row["resolved_time"] = now

    os.makedirs(os.path.dirname(path), exist_ok=True)
    df = pd.DataFrame(list(existing_map.values()))
    df = df.reindex(columns=ERROR_COLUMNS, fill_value="")
    df.to_csv(path, index=False)
    return inserted
