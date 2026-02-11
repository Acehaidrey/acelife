from __future__ import annotations

from typing import Dict, List

import pandas as pd

from orders_analytics.utils.constants import wave_ameci_path, wave_aroma_path


def _load_wave_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str).fillna("")


def load_wave_transactions(provider: str) -> pd.DataFrame:
    provider_lower = (provider or "").strip().lower()
    if provider_lower == "ameci":
        path = wave_ameci_path("accounting.csv")
    elif provider_lower == "aroma":
        path = wave_aroma_path("accounting.csv")
    else:
        raise ValueError("Unknown provider for wave transactions")
    return _load_wave_csv(path)


def filter_transactions(
    df: pd.DataFrame,
    description_contains: List[str] | None = None,
    account_group: str | None = None,
) -> pd.DataFrame:
    filtered = df.copy()
    columns = {c.lower(): c for c in filtered.columns}
    desc_col = columns.get("transaction description")
    acct_col = columns.get("account group")
    if description_contains:
        for term in description_contains:
            if desc_col:
                filtered = filtered[filtered[desc_col].str.contains(term, case=False, na=False)]
    if account_group and acct_col:
        filtered = filtered[filtered[acct_col].str.lower() == account_group.lower()]
    return filtered
