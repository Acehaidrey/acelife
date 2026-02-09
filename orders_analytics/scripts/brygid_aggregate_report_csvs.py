#!/usr/bin/env python3
import argparse
from pathlib import Path
from typing import List

import pandas as pd


def read_report_csv(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, sep="\t", engine="python", on_bad_lines="skip")
    except Exception:
        df = pd.read_csv(path, engine="python", on_bad_lines="skip")
    if len(df.columns) == 1 and "\t" in df.columns[0]:
        df = pd.read_csv(path, sep="\t", engine="python", on_bad_lines="skip")
    return df


def normalize_zip(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "." in text:
        text = text.split(".", 1)[0]
    return text


def delivery_fee_from_zip(zip_code: str) -> float:
    mapping = {
        "92618": 5.0,
        "92610": 4.0,
        "92691": 4.0,
        "92630": 3.0,
    }
    return mapping.get(zip_code, 3.0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate Brygid report CSVs into a unified CSV (preserve source columns)."
    )
    parser.add_argument(
        "--base-dir",
        default="Takeout/reports2022/Ameci",
        help="Base directory containing Brygid report CSVs.",
    )
    parser.add_argument(
        "--out",
        default="orders_analytics/data/raw/brygid/orders_raw_from_csvs.csv",
        help="Output CSV path.",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        raise SystemExit(f"Missing base dir: {base_dir}")

    files: List[Path] = []
    for path in base_dir.rglob("*.csv"):
        name = path.name.lower()
        if "brygid" not in name:
            continue
        if "billing" in name:
            continue
        files.append(path)

    if not files:
        raise SystemExit("No Brygid report CSVs found.")

    frames = []
    all_columns = set()
    now = pd.Timestamp.utcnow().isoformat()
    for path in sorted(files):
        df = read_report_csv(path)
        if "STATUS" in df.columns:
            df = df[df["STATUS"].astype(str).str.strip().str.lower() == "completed"].copy()
        df["source_file"] = str(path)
        df["added_at"] = now
        if "ZIP" in df.columns:
            df["ZIP"] = df["ZIP"].apply(normalize_zip).astype(str)
            is_delivery = df.get("TYPE", "").astype(str).str.strip().str.lower() == "delivery"
            df["delivery_fee"] = ""
            df.loc[is_delivery, "delivery_fee"] = df.loc[is_delivery, "ZIP"].apply(
                delivery_fee_from_zip
            )
            df["import_notes"] = ""
            df.loc[is_delivery, "import_notes"] = df.loc[is_delivery, "ZIP"].apply(
                lambda z: "" if z in {"92618", "92610", "92691", "92630"} else "unseen_zip"
            )
        else:
            df["delivery_fee"] = 3.0
            df["import_notes"] = "unseen_zip"
        frames.append(df)
        all_columns.update(df.columns)

    # Ensure every frame has all columns (preserve raw columns + new columns)
    all_columns = list(all_columns)
    normalized = []
    for df in frames:
        for col in all_columns:
            if col not in df.columns:
                df[col] = ""
        normalized.append(df[all_columns])

    out_df = pd.concat(normalized, ignore_index=True)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)
    print(f"Wrote {len(out_df)} rows -> {out_path}")


if __name__ == "__main__":
    main()
