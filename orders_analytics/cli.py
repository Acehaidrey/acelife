#!/usr/bin/env python3
import argparse
import os
import sys
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orders_analytics.utils.platforms import Platforms


def parse_extras(values: Optional[List[str]]) -> Dict[str, str]:
    extras: Dict[str, str] = {}
    if not values:
        return extras
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"Invalid --extra '{raw}'. Use key=value.")
        key, value = raw.split("=", 1)
        extras[key.strip()] = value.strip()
    return extras


def run_parse(
    platform: str,
    input_path: Optional[str],
    out_path: Optional[str],
    billings_mbox: Optional[str],
    extras: Dict[str, str],
) -> None:
    if platform == "eatstreet":
        from orders_analytics.parsers.eatstreet import (
            extract_eatstreet_billings_raw,
            extract_eatstreet_orders_raw,
            normalize_eatstreet_from_raw,
        )
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_mbox = input_path or extras.pop(
            "orders_mbox", "TakeoutESBM/Mail/Orders-Eatstreet.mbox"
        )
        billings = billings_mbox or extras.pop(
            "billings_mbox", "TakeoutESBM/Mail/Billings-Eatstreet.mbox"
        )
        orders_raw = extras.pop("orders_raw", raw_path("eatstreet", "orders_raw.csv"))
        billings_raw = extras.pop("billings_raw", raw_path("eatstreet", "billings_raw.csv"))
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("eatstreet_orders_normalized.csv")
        )

        extract_eatstreet_orders_raw.run(orders_mbox, orders_raw)
        extract_eatstreet_billings_raw.run(billings, billings_raw)
        normalize_eatstreet_from_raw.run(orders_raw, billings_raw, normalized_out)
        print("[eatstreet] extracted raw orders + billings and normalized.")
        return
    elif platform == "beyondmenu":
        from orders_analytics.parsers.beyondmenu.parse_beyondmenu_orders import (
            BeyondMenuOrdersParser,
        )

        runner = BeyondMenuOrdersParser(input_path=input_path, out_path=out_path, **extras)
    elif platform == "foodja":
        from orders_analytics.parsers.foodja.parse_foodja_orders import FoodjaOrdersParser

        runner = FoodjaOrdersParser(input_path=input_path, out_path=out_path, **extras)
    elif platform == "ezcater":
        from orders_analytics.parsers.ezcater.parse_ezcater_orders import EzCaterOrdersParser

        runner = EzCaterOrdersParser(input_path=input_path, out_path=out_path, **extras)
    elif platform == "cater2me":
        from orders_analytics.parsers.cater2me import (
            extract_cater2me_billings_raw,
            extract_cater2me_orders_raw,
            normalize_cater2me_from_raw,
        )
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_mbox = input_path or extras.pop(
            "orders_mbox", "TakeoutESBM/Mail/Orders-Cater2Me.mbox"
        )
        billings = billings_mbox or extras.pop(
            "billings_mbox", "TakeoutESBM/Mail/Billings-Cater2Me.mbox"
        )
        orders_raw = extras.pop("orders_raw", raw_path("cater2me", "orders_raw.csv"))
        billings_raw = extras.pop("billings_raw", raw_path("cater2me", "billings_raw.csv"))
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("cater2me_orders_normalized.csv")
        )
        extract_cater2me_orders_raw.run(orders_mbox, orders_raw)
        extract_cater2me_billings_raw.run(billings, billings_raw)
        normalize_cater2me_from_raw.run(orders_raw, billings_raw, normalized_out)
        print("[cater2me] extracted raw orders + billings and normalized.")
        return
    elif platform == "menustar":
        from orders_analytics.parsers.menustar import (
            extract_menustar_billings_raw,
            extract_menustar_orders_raw,
            normalize_menustar_from_raw,
        )
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_mbox = input_path or extras.pop(
            "orders_mbox", "TakeoutESBM/Mail/Orders-Menustar.mbox"
        )
        billings = billings_mbox or extras.pop(
            "billings_mbox", "TakeoutESBM/Mail/Billings-Menustar.mbox"
        )
        orders_raw = extras.pop("orders_raw", raw_path("menustar", "orders_raw.csv"))
        billings_raw = extras.pop("billings_raw", raw_path("menustar", "billings_raw.csv"))
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("menustar_orders_normalized.csv")
        )
        extract_menustar_orders_raw.run(orders_mbox, orders_raw)
        extract_menustar_billings_raw.run(billings, billings_raw)
        normalize_menustar_from_raw.run(orders_raw, billings_raw, normalized_out)
        print("[menustar] extracted raw orders + billings and normalized.")
        return
    else:
        raise ValueError(f"Unknown platform: {platform}")

    stats = runner.run()
    if not stats.rows_written:
        print(f"No rows parsed for {platform}.")
        return
    out_path = runner.resolve_paths()[1]
    print(f"[{platform}] wrote {stats.rows_written} rows -> {out_path}")
    if stats.duplicates_removed:
        print(f"[{platform}] removed {stats.duplicates_removed} duplicate rows by order_id")
    if stats.conflicts:
        print(f"[{platform}] {len(stats.conflicts)} duplicate conflicts detected")


def run_extract(
    platform: str,
    orders_mbox: str,
    billings_mbox: str,
    orders_raw: str,
    billings_raw: str,
) -> None:
    if platform == "eatstreet":
        from orders_analytics.parsers.eatstreet import (
            extract_eatstreet_billings_raw,
            extract_eatstreet_orders_raw,
        )

        extract_eatstreet_orders_raw.run(orders_mbox, orders_raw)
        extract_eatstreet_billings_raw.run(billings_mbox, billings_raw)
        return
    if platform == "cater2me":
        from orders_analytics.parsers.cater2me import (
            extract_cater2me_billings_raw,
            extract_cater2me_orders_raw,
        )

        extract_cater2me_orders_raw.run(orders_mbox, orders_raw)
        extract_cater2me_billings_raw.run(billings_mbox, billings_raw)
        return
    if platform == "menustar":
        from orders_analytics.parsers.menustar import (
            extract_menustar_billings_raw,
            extract_menustar_orders_raw,
        )

        extract_menustar_orders_raw.run(orders_mbox, orders_raw)
        extract_menustar_billings_raw.run(billings_mbox, billings_raw)
        return
    raise ValueError(f"Extract not supported for platform: {platform}")


def run_normalize(
    platform: str,
    input_path: Optional[str],
    out_path: Optional[str],
    orders_raw: Optional[str],
    billings_raw: Optional[str],
    extras: Dict[str, str],
) -> None:
    if platform == "eatstreet":
        from orders_analytics.parsers.eatstreet import normalize_eatstreet_from_raw
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_raw_path = orders_raw or extras.pop(
            "orders_raw", raw_path("eatstreet", "orders_raw.csv")
        )
        billings_raw_path = billings_raw or extras.pop(
            "billings_raw", raw_path("eatstreet", "billings_raw.csv")
        )
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("eatstreet_orders_normalized.csv")
        )
        normalize_eatstreet_from_raw.run(orders_raw_path, billings_raw_path, normalized_out)
        print(f"[eatstreet] normalized -> {normalized_out}")
        return
    if platform == "cater2me":
        from orders_analytics.parsers.cater2me import normalize_cater2me_from_raw
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_raw_path = orders_raw or extras.pop(
            "orders_raw", raw_path("cater2me", "orders_raw.csv")
        )
        billings_raw_path = billings_raw or extras.pop(
            "billings_raw", raw_path("cater2me", "billings_raw.csv")
        )
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("cater2me_orders_normalized.csv")
        )
        normalize_cater2me_from_raw.run(orders_raw_path, billings_raw_path, normalized_out)
        print(f"[cater2me] normalized -> {normalized_out}")
        return
    if platform == "menustar":
        from orders_analytics.parsers.menustar import normalize_menustar_from_raw
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_raw_path = orders_raw or extras.pop(
            "orders_raw", raw_path("menustar", "orders_raw.csv")
        )
        billings_raw_path = billings_raw or extras.pop(
            "billings_raw", raw_path("menustar", "billings_raw.csv")
        )
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("menustar_orders_normalized.csv")
        )
        normalize_menustar_from_raw.run(orders_raw_path, billings_raw_path, normalized_out)
        print(f"[menustar] normalized -> {normalized_out}")
        return
    if platform == "beyondmenu":
        from orders_analytics.parsers.beyondmenu.parse_beyondmenu_orders import (
            BeyondMenuOrdersParser,
        )

        runner = BeyondMenuOrdersParser(input_path=input_path, out_path=out_path, **extras)
    elif platform == "foodja":
        from orders_analytics.parsers.foodja.parse_foodja_orders import FoodjaOrdersParser

        runner = FoodjaOrdersParser(input_path=input_path, out_path=out_path, **extras)
    elif platform == "ezcater":
        from orders_analytics.parsers.ezcater.parse_ezcater_orders import EzCaterOrdersParser

        runner = EzCaterOrdersParser(input_path=input_path, out_path=out_path, **extras)
    else:
        raise ValueError(f"Unknown platform: {platform}")

    stats = runner.run()
    out_path = runner.resolve_paths()[1]
    print(f"[{platform}] normalized -> {out_path} ({stats.rows_written} rows)")


def run_fees(args) -> None:
    from orders_analytics.parsers.eatstreet import update_eatstreet_fees

    update_eatstreet_fees.run(
        mbox=args.mbox,
        orders=args.orders,
        out=args.out,
        missing_out=args.missing_out,
        backup_dir=args.backup_dir,
    )


def run_ingest(db_path: Optional[str]) -> None:
    from orders_analytics.ingest import ingest_normalized

    count = ingest_normalized(db_path=db_path) if db_path else ingest_normalized()
    print(f"Ingested {count} rows into DuckDB.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Orders analytics CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_cmd = subparsers.add_parser("parse", help="Run a platform parser.")
    parse_cmd.add_argument(
        "--platform",
        choices=[*Platforms.all_platforms(), "all"],
        default="all",
        help="Platform to parse.",
    )
    parse_cmd.add_argument(
        "--input",
        help="Override input path (orders mbox for EatStreet, CSV for BeyondMenu).",
    )
    parse_cmd.add_argument(
        "--billings-mbox",
        help="Override Billings-Eatstreet.mbox path (EatStreet only).",
    )
    parse_cmd.add_argument(
        "--extra",
        action="append",
        default=None,
        help="Additional parser args as key=value (can repeat).",
    )

    from orders_analytics.utils.constants import normalized_path, raw_path

    extract_cmd = subparsers.add_parser(
        "extract", help="Extract raw data from provider inputs."
    )
    extract_cmd.add_argument(
        "--platform",
        choices=Platforms.mbox_platforms(),
        default="eatstreet",
        help="Platform to extract.",
    )
    extract_cmd.add_argument(
        "--orders-mbox",
        default=None,
        help="Path to Orders mbox (platform-specific default if omitted).",
    )
    extract_cmd.add_argument(
        "--billings-mbox",
        default=None,
        help="Path to Billings mbox (platform-specific default if omitted).",
    )
    extract_cmd.add_argument(
        "--orders-raw",
        default=None,
        help="Output orders raw CSV path (platform-specific default if omitted).",
    )
    extract_cmd.add_argument(
        "--billings-raw",
        default=None,
        help="Output billings raw CSV path (platform-specific default if omitted).",
    )

    normalize_cmd = subparsers.add_parser(
        "normalize", help="Normalize raw data into canonical schema."
    )
    normalize_cmd.add_argument(
        "--platform",
        choices=[*Platforms.all_platforms(), "all"],
        default="all",
        help="Platform to normalize.",
    )
    normalize_cmd.add_argument("--input", help="Override input path for CSV-based parsers.")
    normalize_cmd.add_argument("--out", help="Override output path.")
    normalize_cmd.add_argument(
        "--orders-raw",
        default=None,
        help="Input orders raw CSV path (platform-specific default if omitted).",
    )
    normalize_cmd.add_argument(
        "--billings-raw",
        default=None,
        help="Input billings raw CSV path (platform-specific default if omitted).",
    )
    normalize_cmd.add_argument(
        "--extra",
        action="append",
        default=None,
        help="Additional parser args as key=value (can repeat).",
    )
    normalize_cmd.add_argument(
        "--reset-errors",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reset errors.csv before normalizing (default: true).",
    )
    parse_cmd.add_argument("--out", help="Override output path.")

    fees_cmd = subparsers.add_parser("fees", help="Update EatStreet fees from billings.")
    fees_cmd.add_argument(
        "--mbox",
        default="TakeoutESBM/Mail/Billings-Eatstreet.mbox",
        help="Path to Billings-Eatstreet.mbox",
    )
    fees_cmd.add_argument(
        "--orders",
        default="orders_analytics/data/normalized/eatstreet_orders_normalized.csv",
        help="Path to EatStreet orders CSV",
    )
    fees_cmd.add_argument(
        "--out",
        default="orders_analytics/data/normalized/eatstreet_orders_normalized.csv",
        help="Output CSV path",
    )
    fees_cmd.add_argument(
        "--missing-out",
        default="orders_analytics/data/raw/eatstreet/eatstreet_orders_missing_fees.csv",
        help="Output CSV path for order_ids missing proc/comm fees",
    )
    fees_cmd.add_argument(
        "--backup-dir",
        default="orders_analytics/data/raw/eatstreet/backups",
        help="Directory for backups when overwriting the output CSV",
    )

    ingest_cmd = subparsers.add_parser("ingest", help="Load normalized CSVs into DuckDB.")
    ingest_cmd.add_argument(
        "--db-path",
        default=None,
        help="Override DuckDB path (defaults to utils.constants.DEFAULT_DB_PATH).",
    )

    errors_cmd = subparsers.add_parser(
        "errors", help="Rebuild errors.csv by re-running validations."
    )
    errors_cmd.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing errors.csv before rebuilding.",
    )

    args = parser.parse_args()

    if args.command == "parse":
        platforms: List[str]
        if args.platform == "all":
            platforms = Platforms.all_platforms()
        else:
            platforms = [args.platform]
        base_extras = parse_extras(args.extra)
        for platform in platforms:
            run_parse(
                platform,
                args.input,
                args.out,
                args.billings_mbox,
                dict(base_extras),
            )
    elif args.command == "fees":
        run_fees(args)
    elif args.command == "ingest":
        run_ingest(args.db_path)
    elif args.command == "errors":
        from orders_analytics.utils.constants import ERRORS_PATH

        if args.reset and os.path.exists(ERRORS_PATH):
            os.remove(ERRORS_PATH)
            print(f"Deleted {ERRORS_PATH}")
        # Re-run validations by re-normalizing/parsing platforms.
        run_parse("eatstreet", None, None, None, {})
        run_parse("beyondmenu", None, None, None, {})
    elif args.command == "extract":
        from orders_analytics.utils.constants import raw_path

        if args.platform == "eatstreet":
            orders_mbox = args.orders_mbox or "TakeoutESBM/Mail/Orders-Eatstreet.mbox"
            billings_mbox = args.billings_mbox or "TakeoutESBM/Mail/Billings-Eatstreet.mbox"
            orders_raw = args.orders_raw or raw_path("eatstreet", "orders_raw.csv")
            billings_raw = args.billings_raw or raw_path("eatstreet", "billings_raw.csv")
        elif args.platform == "cater2me":
            orders_mbox = args.orders_mbox or "TakeoutESBM/Mail/Orders-Cater2Me.mbox"
            billings_mbox = args.billings_mbox or "TakeoutESBM/Mail/Billings-Cater2Me.mbox"
            orders_raw = args.orders_raw or raw_path("cater2me", "orders_raw.csv")
            billings_raw = args.billings_raw or raw_path("cater2me", "billings_raw.csv")
        else:
            orders_mbox = args.orders_mbox or "TakeoutESBM/Mail/Orders-Menustar.mbox"
            billings_mbox = args.billings_mbox or "TakeoutESBM/Mail/Billings-Menustar.mbox"
            orders_raw = args.orders_raw or raw_path("menustar", "orders_raw.csv")
            billings_raw = args.billings_raw or raw_path("menustar", "billings_raw.csv")
        run_extract(args.platform, orders_mbox, billings_mbox, orders_raw, billings_raw)
    elif args.command == "normalize":
        from orders_analytics.utils.constants import ERRORS_PATH

        if args.reset_errors and os.path.exists(ERRORS_PATH):
            os.remove(ERRORS_PATH)
            print(f"Deleted {ERRORS_PATH}")
        platforms: List[str]
        if args.platform == "all":
            platforms = Platforms.all_platforms()
        else:
            platforms = [args.platform]
        base_extras = parse_extras(args.extra)
        for platform in platforms:
            run_normalize(
                platform,
                args.input,
                args.out,
                args.orders_raw,
                args.billings_raw,
                dict(base_extras),
            )


if __name__ == "__main__":
    main()
from orders_analytics.utils.platforms import Platforms
