#!/usr/bin/env python3
"""Extract provider payout transactions from Wave accounting files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

import pandas as pd

WAVE_ACCOUNTS = {
    "ameci": Path("Takeout/wave_ameci/accounting.csv"),
    "aroma": Path("Takeout/wave_aroma/accounting.csv"),
}
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
    "officecaterer": ["office caterer", "officecaterer"],
    "nextbite": ["nextbite", "nextbite brands"],
    "mayaeats": ["maya eats", "mayaeats", "unavu"],
}


def load_account(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def main() -> None:
    search_keys = ["description", "memo", "vendor", "customer", "account name", "other accounts"]
    for account_name, account_path in WAVE_ACCOUNTS.items():
        if not account_path.exists():
            continue
        df = load_account(account_path)
        search_cols = [c for c in df.columns if any(key in c for key in search_keys)]
        if not search_cols:
            print(f"No searchable columns found in {account_path}")
            continue

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
            if provider == "officecaterer":
                if "account name" in df.columns:
                    acct_mask = df["account name"].astype(str).str.strip().str.lower() == "office caterer sales"
                    filtered = df[mask & income_mask & acct_mask].copy()
                else:
                    filtered = filtered.iloc[0:0]
            if filtered.empty:
                continue
            filtered["source_accounting_file"] = str(account_path)
            filtered["wave_account"] = account_name
            out_dir = OUTPUT_ROOT / provider
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"wave_payouts_{account_name}.csv"
            filtered.to_csv(out_path, index=False)
            print(f"{provider} ({account_name}): wrote {len(filtered)} rows -> {out_path}")


if __name__ == "__main__":
    main()
