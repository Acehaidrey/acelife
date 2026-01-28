#!/usr/bin/env python3
"""
Template parser for new providers.

Goal: map provider-specific exports to the canonical schema in
orders_analytics/utils/schema.py, then write a normalized CSV.
"""
import argparse
from typing import Dict, Iterable, List

from orders_analytics.utils.schema import canonicalize_rows, write_normalized_rows


def parse_source_files(inputs: Iterable[str]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    # TODO: load provider-specific files, extract fields into dicts.
    # Each dict can be partial; it will be filled to the canonical schema.
    return rows


def pre_process(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    # TODO: optional cleansing/standardization (dates, providers, etc.)
    return rows


def post_process(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    # TODO: optional QA or enrichment.
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Template parser for a provider.")
    parser.add_argument("--input", nargs="+", required=True, help="Input file(s).")
    parser.add_argument(
        "--out",
        required=True,
        help="Output normalized CSV path.",
    )
    args = parser.parse_args()

    rows = parse_source_files(args.input)
    if not rows:
        print("No rows parsed.")
        return

    rows = pre_process(rows)
    rows = post_process(rows)
    rows = canonicalize_rows(rows)
    write_normalized_rows(rows, args.out)
    print(f"Wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
