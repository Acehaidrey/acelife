#!/usr/bin/env python3
import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

from orders_analytics.utils.constants import raw_path


def run(input_path: str, out_path: str) -> int:
    df = pd.read_csv(input_path, dtype=str).fillna("")
    df = df.replace("NULL", "")
    df.columns = [c.strip() for c in df.columns]
    df["source_file"] = Path(input_path).name
    df["added_at"] = dt.datetime.now().isoformat()
    df.to_csv(out_path, index=False)
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract DoorDash error charges/adjustments to raw CSV.")
    parser.add_argument("--input", required=True, help="Path to DoorDash error charges CSV.")
    parser.add_argument("--out", default=raw_path("doordash", "errors_raw.csv"))
    args = parser.parse_args()

    Path(Path(args.out).parent).mkdir(parents=True, exist_ok=True)
    rows = run(args.input, args.out)
    print(f"Wrote {rows} rows -> {args.out}")


if __name__ == "__main__":
    main()
