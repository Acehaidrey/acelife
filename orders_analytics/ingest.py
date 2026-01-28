#!/usr/bin/env python3
import os

import duckdb
import pandas as pd

from orders_analytics.utils.constants import DEFAULT_DB_PATH, NORMALIZED_DIR, ERRORS_PATH


def ingest_normalized(db_path: str = DEFAULT_DB_PATH) -> int:
    if not os.path.isdir(NORMALIZED_DIR):
        return 0
    files = [
        os.path.join(NORMALIZED_DIR, name)
        for name in os.listdir(NORMALIZED_DIR)
        if name.endswith(".csv")
    ]
    if not files:
        return 0
    frames = []
    for path in files:
        df = pd.read_csv(path)
        df["source_file"] = os.path.basename(path)
        frames.append(df)
    data = pd.concat(frames, ignore_index=True)
    conn = duckdb.connect(db_path)
    conn.register("orders_df", data)
    conn.execute("CREATE OR REPLACE TABLE orders_raw AS SELECT * FROM orders_df")
    if os.path.exists(ERRORS_PATH):
        errors_df = pd.read_csv(ERRORS_PATH)
        conn.register("errors_df", errors_df)
        conn.execute("CREATE OR REPLACE TABLE orders_errors AS SELECT * FROM errors_df")
    conn.close()
    return len(data)


def main() -> None:
    count = ingest_normalized()
    print(f"Ingested {count} rows into DuckDB.")


if __name__ == "__main__":
    main()
