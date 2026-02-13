#!/usr/bin/env python3
"""Create a review CSV mapping Postmates exports to Uber-style columns."""
from __future__ import annotations

from pathlib import Path
import pandas as pd

REPORTS_ROOT = Path("Takeout/reports2022")
OUTPUT_PATH = Path("Takeout/postmates_missing_as_uber.csv")
UBER_BASE = Path("Takeout/uber-bc08b66d-0603-49ef-8186-07a637505732-united_states.csv")


def iter_postmates_files():
    for root in [REPORTS_ROOT / "Ameci", REPORTS_ROOT / "Aroma"]:
        if not root.exists():
            continue
        for path in root.rglob("*.csv"):
            name = path.name.lower()
            if "postmates" in name:
                yield path


def within_cutoff(path: Path) -> bool:
    # Only include through 2021-04
    parts = path.parts
    year = None
    month = None
    for part in parts:
        if part.isdigit() and len(part) == 4:
            year = int(part)
        if part.isdigit() and len(part) == 2:
            m = int(part)
            if 1 <= m <= 12:
                month = m
    if year is None:
        return False
    if year < 2020:
        return False
    if year > 2021:
        return False
    if year == 2021 and (month is None or month > 4):
        return False
    return True


def main() -> None:
    if not UBER_BASE.exists():
        raise SystemExit(f"Missing base Uber file: {UBER_BASE}")
    uber_cols = pd.read_csv(UBER_BASE, header=1).columns.tolist()

    frames = []
    for path in sorted(iter_postmates_files()):
        if not within_cutoff(path):
            continue
        df = pd.read_csv(path)
        if df.empty:
            continue
        df = df.copy()
        # Parse Date into Order Date and Order Accept Time
        if "Date" in df.columns:
            dt = pd.to_datetime(df["Date"], errors="coerce")
            df["Order Date"] = dt.dt.date.astype(str)
            df["Order Accept Time"] = dt.dt.strftime("%I:%M %p")
        # Map Postmates fields into Uber columns
        mapped = pd.DataFrame({col: ["" for _ in range(len(df))] for col in uber_cols})
        mapped["Store Name"] = df.get("Place Nickname", "")
        mapped["Order ID"] = df.get("Order", "")
        mapped["Dining Mode"] = df.get("Order Type", "")
        mapped["Order Status"] = df.get("Order State", "")
        mapped["Order Date"] = df.get("Order Date", "")
        mapped["Order Accept Time"] = df.get("Order Accept Time", "")
        mapped["Sales (excl. tax)"] = df.get("Subtotal", "")
        mapped["Tax on Sales"] = df.get("Tax", "")
        mapped["Sales (incl. tax)"] = df.get("Total", "")
        mapped["Total Sales after Adjustments (incl tax)"] = df.get("Total", "")
        mapped["Order Error Adjustments"] = df.get("Adjustments", "")
        mapped["Offers on items (incl. tax)"] = df.get("Promotion Cost", "")
        mapped["Delivery Network Fee"] = df.get("Fees", "")
        mapped["Delivery Fee"] = df.get("API Delivery Fee", "")
        mapped["Tips"] = df.get("Tip", "")
        mapped["Marketplace Fee"] = df.get("Commission", "")
        mapped["Other payments description"] = df.get("Issues", "")
        mapped["Other payments"] = df.get("Reimbursement", "")
        mapped["Total payout "] = df.get("Payout", "")
        mapped["Payout Date"] = df.get("Date", "")
        mapped["Order Channel"] = "Postmates"
        mapped["source_file"] = str(path)

        frames.append(mapped)

    if not frames:
        print("No postmates rows found.")
        return

    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(out)} rows -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
