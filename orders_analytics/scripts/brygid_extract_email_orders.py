#!/usr/bin/env python3
import os
import sys
import shutil

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from orders_analytics.utils.constants import raw_path  # noqa: E402


def main() -> None:
    # Run the email extractor and then copy to orders_raw_from_email.csv
    from orders_analytics.parsers.brygid import extract_brygid_orders_raw  # noqa: E402

    extract_brygid_orders_raw.main()
    src = raw_path("brygid", "orders_raw.csv")
    dst = raw_path("brygid", "orders_raw_from_email.csv")
    if os.path.exists(src):
        shutil.copyfile(src, dst)
        print(f"Wrote {dst}")


if __name__ == "__main__":
    main()
