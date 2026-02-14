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


def _parse_postmates_date(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    # remove timezone/parenthetical suffix
    s = s.str.replace(r" GMT.*", "", regex=True)
    dt = pd.to_datetime(s, errors="coerce", format="%a %b %d %Y %H:%M:%S")
    return dt


def _clean_money(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.replace(",", "", regex=False)
    s = s.str.replace("$", "", regex=False).str.strip()
    # convert (4.69) -> -4.69
    neg = s.str.startswith("(") & s.str.endswith(")")
    s = s.str.strip("()")
    nums = pd.to_numeric(s, errors="coerce")
    nums[neg] = -nums[neg]
    return nums


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
            dt = _parse_postmates_date(df["Date"])
            df["Order Date"] = dt.dt.strftime("%Y-%m-%d")
            df["Order Accept Time"] = dt.dt.strftime("%I:%M %p")
        # Map Postmates fields into Uber columns
        mapped = pd.DataFrame({col: ["" for _ in range(len(df))] for col in uber_cols})
        mapped["Store Name"] = df.get("Place Nickname", "")
        base_order_id = df.get("Order", "").astype(str).str.replace(r"\.0$", "", regex=True)
        base_order_id = base_order_id.replace({"nan": "", "None": ""})
        order_date = df.get("Order Date", "").astype(str)
        mapped["Order ID"] = base_order_id + "_" + order_date.str.replace("-", "_", regex=False)
        mapped["Dining Mode"] = df.get("Order Type", "")
        mapped["Order Status"] = df.get("Order State", "")
        mapped["Order Date"] = df.get("Order Date", "")
        mapped["Order Accept Time"] = df.get("Order Accept Time", "")
        mapped["Sales (excl. tax)"] = _clean_money(df.get("Subtotal", ""))
        mapped["Tax on Sales"] = _clean_money(df.get("Tax", ""))
        mapped["Sales (incl. tax)"] = _clean_money(df.get("Total", ""))
        mapped["Total Sales after Adjustments (incl tax)"] = _clean_money(df.get("Total", ""))
        mapped["Order Error Adjustments"] = _clean_money(df.get("Adjustments", ""))
        mapped["Offers on items (incl. tax)"] = _clean_money(df.get("Promotion Cost", ""))
        mapped["Delivery Network Fee"] = _clean_money(df.get("Fees", ""))
        mapped["Delivery Fee"] = _clean_money(df.get("API Delivery Fee", ""))
        mapped["Tips"] = _clean_money(df.get("Tip", ""))
        mapped["Marketplace Fee"] = _clean_money(df.get("Commission", ""))
        mapped["Other payments description"] = df.get("Issues", "")
        mapped["Other payments"] = _clean_money(df.get("Reimbursement", ""))
        mapped["Total payout "] = _clean_money(df.get("Payout", ""))
        mapped["Payout Date"] = ""
        mapped["Order Channel"] = "Postmates"
        mapped["customer_name"] = df.get("Customer Name", "")
        mapped["items"] = df.get("items", "")
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
