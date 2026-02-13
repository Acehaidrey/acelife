#!/usr/bin/env python3
"""Extract provider payout transactions from Wave accounting (Ameci only)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

import pandas as pd

WAVE_AMECI_PATH = Path("Takeout/wave_ameci/accounting.csv")
OUTPUT_ROOT = Path("orders_analytics/data/raw")

PROVIDER_KEYWORDS: Dict[str, List[str]] = {
    "ubereats": ["uber", "ubereats", "postmates"],
    "doordash": ["doordash", "door dash"],
    "grubhub": ["grubhub"],
    "brygid": ["brygid"],
    "beyondmenu": ["beyondmenu", "beyond menu"],
    "menufy": ["menufy"],
    "menustar": ["menustar", "menu star"],
    "slice": ["slice"],
    "ezcater": ["ezcater", "ez cater"],
    "chownow": ["chownow", "chow now"],
    "cater2me": ["cater2me", "cater 2 me"],
    "deliverycom": ["delivery.com", "deliverycom"],
    "eatstreet": ["eatstreet", "eat street"],
    "fooda": ["fooda"],
    "foodee": ["foodee"],
    "foodja": ["foodja"],
    "foodrunners": ["foodrunners", "food runners"],
    "orderinn": ["order inn", "orderinn"],
}


def main() -> None:
    if not WAVE_AMECI_PATH.exists():
        raise SystemExit(f"Missing {WAVE_AMECI_PATH}")

    df = pd.read_csv(WAVE_AMECI_PATH)
    df.columns = [c.strip().lower() for c in df.columns]

    search_cols = [
        c
        for c in df.columns
        if any(key in c for key in ["description", "memo", "vendor", "customer", "account name", "other accounts"])
    ]
    if not search_cols:
        raise SystemExit("No searchable description columns found in accounting.csv")

    search = pd.Series(["" for _ in range(len(df))])
    for c in search_cols:
        search = search + " " + df[c].astype(str)
    search = search.str.lower()

    if "account group" in df.columns:
        income_mask = df["account group"].astype(str).str.lower() == "income"
    else:
        income_mask = pd.Series([True] * len(df))

    for provider, keywords in PROVIDER_KEYWORDS.items():
        pattern = "|".join(re.escape(k) for k in keywords)
        mask = search.str.contains(pattern, regex=True)
        filtered = df[mask & income_mask].copy()
        if filtered.empty:
            continue
        filtered["source_accounting_file"] = str(WAVE_AMECI_PATH)
        out_dir = OUTPUT_ROOT / provider
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "wave_payouts_ameci.csv"
        filtered.to_csv(out_path, index=False)
        print(f"{provider}: wrote {len(filtered)} rows -> {out_path}")


if __name__ == "__main__":
    main()
