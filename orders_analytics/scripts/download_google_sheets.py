#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from typing import List

from orders_analytics.utils.google_sheets import GoogleSheetsDownloader


def ensure_ext(path: str, ext: str) -> str:
    if path.lower().endswith(ext):
        return path
    return f"{path}{ext}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Google Sheets tabs by sheet id + gid.")
    parser.add_argument("--sheet-id", required=True, help="Google Sheet ID.")
    parser.add_argument("--gid", required=True, help="Sheet tab gid.")
    parser.add_argument(
        "--format",
        choices=["csv", "xlsx"],
        default="csv",
        help="Download format.",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output file path (directory will be created if missing).",
    )
    args = parser.parse_args()

    downloader = GoogleSheetsDownloader(args.sheet_id)
    out_path = args.out
    if args.format == "csv":
        out_path = ensure_ext(out_path, ".csv")
        downloader.download_csv(args.gid, out_path)
    else:
        out_path = ensure_ext(out_path, ".xlsx")
        downloader.download_xlsx(args.gid, out_path)

    print(f"Downloaded -> {out_path}")


if __name__ == "__main__":
    main()
