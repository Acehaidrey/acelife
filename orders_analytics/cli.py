#!/usr/bin/env python3
import argparse
import os
import sys
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.constants import takeout_path


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
            "orders_mbox", takeout_path("Mail", "Orders-Eatstreet.mbox")
        )
        billings = billings_mbox or extras.pop(
            "billings_mbox", takeout_path("Mail", "Billings-Eatstreet.mbox")
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
    elif platform == "fooda":
        from orders_analytics.parsers.fooda.parse_fooda_orders import FoodaOrdersParser

        runner = FoodaOrdersParser(input_path=input_path, out_path=out_path, **extras)
    elif platform == "ezcater":
        from orders_analytics.parsers.ezcater.parse_ezcater_orders import EzCaterOrdersParser

        runner = EzCaterOrdersParser(input_path=input_path, out_path=out_path, **extras)
    elif platform == "deliverycom":
        from orders_analytics.parsers.deliverycom.parse_deliverycom_orders import (
            DeliveryComOrdersParser,
        )

        runner = DeliveryComOrdersParser(input_path=input_path, out_path=out_path, **extras)
    elif platform == "cater2me":
        from orders_analytics.parsers.cater2me import (
            extract_cater2me_billings_raw,
            extract_cater2me_orders_raw,
            normalize_cater2me_from_raw,
        )
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_mbox = input_path or extras.pop(
            "orders_mbox", takeout_path("Mail", "Orders-Cater2Me.mbox")
        )
        billings = billings_mbox or extras.pop(
            "billings_mbox", takeout_path("Mail", "Billings-Cater2Me.mbox")
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
            "orders_mbox", takeout_path("Mail", "Orders-Menustar.mbox")
        )
        billings = billings_mbox or extras.pop(
            "billings_mbox", takeout_path("Mail", "Billings-Menustar.mbox")
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
    elif platform == "deliverycom":
        from orders_analytics.parsers.deliverycom import (
            extract_deliverycom_billings_raw,
            extract_deliverycom_orders_raw,
            normalize_deliverycom_from_raw,
        )
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_mbox = input_path or extras.pop(
            "orders_mbox", takeout_path("Mail", "Orders-DeliveryCom.mbox")
        )
        billings = billings_mbox or extras.pop(
            "billings_mbox", takeout_path("Mail", "Billings-DeliveryCom.mbox")
        )
        orders_raw = extras.pop("orders_raw", raw_path("deliverycom", "orders_raw.csv"))
        billings_raw = extras.pop("billings_raw", raw_path("deliverycom", "billings_raw.csv"))
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("deliverycom_orders_normalized.csv")
        )
        extract_deliverycom_orders_raw.run(orders_mbox, orders_raw)
        extract_deliverycom_billings_raw.run(billings, billings_raw)
        normalize_deliverycom_from_raw.run(orders_raw, billings_raw, normalized_out)
        print("[deliverycom] extracted raw orders + billings and normalized.")
        return
    elif platform == "foodee":
        from orders_analytics.parsers.foodee import (
            extract_foodee_billings_raw,
            extract_foodee_orders_raw,
            normalize_foodee_from_raw,
        )
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_mbox = input_path or extras.pop(
            "orders_mbox", takeout_path("Mail", "Orders-Foodee.mbox")
        )
        billings = billings_mbox or extras.pop(
            "billings_mbox", takeout_path("Mail", "Billings-Foodee.mbox")
        )
        orders_raw = extras.pop("orders_raw", raw_path("foodee", "orders_raw.csv"))
        billings_raw = extras.pop("billings_raw", raw_path("foodee", "billings_raw.csv"))
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("foodee_orders_normalized.csv")
        )
        extract_foodee_orders_raw.run(orders_mbox, orders_raw)
        extract_foodee_billings_raw.run(billings, billings_raw)
        normalize_foodee_from_raw.run(orders_raw, billings_raw, normalized_out)
        print("[foodee] extracted raw orders + billings and normalized.")
        return
    elif platform == "foodrunners":
        from orders_analytics.parsers.foodrunners import (
            extract_foodrunners_billings_raw,
            extract_foodrunners_orders_raw,
            normalize_foodrunners_from_raw,
        )
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_mbox = input_path or extras.pop(
            "orders_mbox", takeout_path("Mail", "Orders-FoodRunners.mbox")
        )
        billings = billings_mbox or extras.pop(
            "billings_mbox", takeout_path("Mail", "Billings-FoodRunners.mbox")
        )
        orders_raw = extras.pop("orders_raw", raw_path("foodrunners", "orders_raw.csv"))
        billings_raw = extras.pop("billings_raw", raw_path("foodrunners", "billings_raw.csv"))
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("foodrunners_orders_normalized.csv")
        )
        extract_foodrunners_orders_raw.run(orders_mbox, orders_raw)
        extract_foodrunners_billings_raw.run(billings, billings_raw)
        normalize_foodrunners_from_raw.run(orders_raw, billings_raw, normalized_out)
        print("[foodrunners] extracted raw orders + billings and normalized.")
        return
    elif platform == "officecaterer":
        from orders_analytics.parsers.officecaterer import (
            extract_officecaterer_billings_raw,
            extract_officecaterer_orders_raw,
            normalize_officecaterer_from_raw,
        )
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_mbox = input_path or extras.pop(
            "orders_mbox", takeout_path("Mail", "Orders-OfficeCaterer.mbox")
        )
        billings = billings_mbox or extras.pop(
            "billings_mbox", takeout_path("Mail", "Billings-OfficeCaterer.mbox")
        )
        orders_raw = extras.pop("orders_raw", raw_path("officecaterer", "orders_raw.csv"))
        billings_raw = extras.pop(
            "billings_raw", raw_path("officecaterer", "billings_raw.csv")
        )
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("officecaterer_orders_normalized.csv")
        )
        extract_officecaterer_orders_raw.run(orders_mbox, orders_raw)
        extract_officecaterer_billings_raw.run(billings, billings_raw)
        normalize_officecaterer_from_raw.run(
            orders_raw,
            normalized_out,
            billings_raw_path=billings_raw,
        )
        print("[officecaterer] extracted raw orders + billings and normalized.")
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
    if platform == "deliverycom":
        from orders_analytics.parsers.deliverycom import (
            extract_deliverycom_billings_raw,
            extract_deliverycom_orders_raw,
        )

        extract_deliverycom_orders_raw.run(orders_mbox, orders_raw)
        extract_deliverycom_billings_raw.run(billings_mbox, billings_raw)
        return
    if platform == "foodee":
        from orders_analytics.parsers.foodee import (
            extract_foodee_billings_raw,
            extract_foodee_orders_raw,
        )

        extract_foodee_orders_raw.run(orders_mbox, orders_raw)
        extract_foodee_billings_raw.run(billings_mbox, billings_raw)
        return
    if platform == "foodrunners":
        from orders_analytics.parsers.foodrunners import (
            extract_foodrunners_billings_raw,
            extract_foodrunners_orders_raw,
        )

        extract_foodrunners_orders_raw.run(orders_mbox, orders_raw)
        extract_foodrunners_billings_raw.run(billings_mbox, billings_raw)
        return
    if platform == "officecaterer":
        from orders_analytics.parsers.officecaterer import (
            extract_officecaterer_billings_raw,
            extract_officecaterer_orders_raw,
        )

        extract_officecaterer_orders_raw.run(orders_mbox, orders_raw)
        extract_officecaterer_billings_raw.run(billings_mbox, billings_raw)
        return
    if platform == "menufy":
        from orders_analytics.parsers.menufy import extract_menufy_orders_raw

        orders_root = "Takeout/Menufy/orders"
        emails_csv = "Takeout/Menufy/Customer_Emails_02-05-2026.csv"
        addresses_csv = "Takeout/Menufy/Customer_Delivery_Addresses_02-05-2026.csv"
        extract_menufy_orders_raw.run(orders_root, orders_raw, emails_csv, addresses_csv)
        return
    if platform == "slice":
        from orders_analytics.parsers.slice import extract_slice_orders_raw

        orders_root = "Takeout/Slice"
        extract_slice_orders_raw.run(orders_root, orders_raw)
        return
    raise ValueError(f"Extract not supported for platform: {platform}")


def run_normalize(
    platform: str,
    input_path: Optional[str],
    out_path: Optional[str],
    orders_raw: Optional[str],
    billings_raw: Optional[str],
    extras: Dict[str, str],
    reset_errors: bool = False,
) -> None:
    if reset_errors:
        extras = dict(extras)
        extras["reset_errors"] = True
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
        normalize_eatstreet_from_raw.run(
            orders_raw_path, billings_raw_path, normalized_out, reset_errors=reset_errors
        )
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
        normalize_cater2me_from_raw.run(
            orders_raw_path, billings_raw_path, normalized_out, reset_errors=reset_errors
        )
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
        normalize_menustar_from_raw.run(
            orders_raw_path, billings_raw_path, normalized_out, reset_errors=reset_errors
        )
        print(f"[menustar] normalized -> {normalized_out}")
        return
    if platform == "deliverycom":
        from orders_analytics.parsers.deliverycom import normalize_deliverycom_from_raw
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_raw_path = orders_raw or extras.pop(
            "orders_raw", raw_path("deliverycom", "orders_raw.csv")
        )
        billings_raw_path = billings_raw or extras.pop(
            "billings_raw", raw_path("deliverycom", "billings_raw.csv")
        )
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("deliverycom_orders_normalized.csv")
        )
        normalize_deliverycom_from_raw.run(
            orders_raw_path, billings_raw_path, normalized_out, reset_errors=reset_errors
        )
        print(f"[deliverycom] normalized -> {normalized_out}")
        return
    if platform == "foodee":
        from orders_analytics.parsers.foodee import normalize_foodee_from_raw
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_raw_path = orders_raw or extras.pop(
            "orders_raw", raw_path("foodee", "orders_raw.csv")
        )
        billings_raw_path = billings_raw or extras.pop(
            "billings_raw", raw_path("foodee", "billings_raw.csv")
        )
        adjustments_raw_path = extras.pop(
            "adjustments_raw", raw_path("foodee", "adjustments_raw.csv")
        )
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("foodee_orders_normalized.csv")
        )
        normalize_foodee_from_raw.run(
            orders_raw_path,
            billings_raw_path,
            adjustments_raw_path,
            normalized_out,
            reset_errors=reset_errors,
        )
        print(f"[foodee] normalized -> {normalized_out}")
        return
    if platform == "foodrunners":
        from orders_analytics.parsers.foodrunners import normalize_foodrunners_from_raw
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_raw_path = orders_raw or extras.pop(
            "orders_raw", raw_path("foodrunners", "orders_raw.csv")
        )
        billings_raw_path = billings_raw or extras.pop(
            "billings_raw", raw_path("foodrunners", "billings_raw.csv")
        )
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("foodrunners_orders_normalized.csv")
        )
        normalize_foodrunners_from_raw.run(
            orders_raw_path, billings_raw_path, normalized_out, reset_errors=reset_errors
        )
        print(f"[foodrunners] normalized -> {normalized_out}")
        return
    if platform == "officecaterer":
        from orders_analytics.parsers.officecaterer import normalize_officecaterer_from_raw
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_raw_path = orders_raw or extras.pop(
            "orders_raw", raw_path("officecaterer", "orders_raw.csv")
        )
        billings_raw_path = billings_raw or extras.pop(
            "billings_raw", raw_path("officecaterer", "billings_raw.csv")
        )
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("officecaterer_orders_normalized.csv")
        )
        normalize_officecaterer_from_raw.run(
            orders_raw_path,
            normalized_out,
            reset_errors=reset_errors,
            billings_raw_path=billings_raw_path,
        )
        print(f"[officecaterer] normalized -> {normalized_out}")
        return
    if platform == "menufy":
        from orders_analytics.parsers.menufy import normalize_menufy_from_raw
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_raw_path = orders_raw or extras.pop(
            "orders_raw", raw_path("menufy", "orders_raw.csv")
        )
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("menufy_orders_normalized.csv")
        )
        normalize_menufy_from_raw.run(
            orders_raw_path, normalized_out, reset_errors=reset_errors
        )
        print(f"[menufy] normalized -> {normalized_out}")
        return
    if platform == "slice":
        from orders_analytics.parsers.slice import normalize_slice_from_raw
        from orders_analytics.utils.constants import normalized_path, raw_path

        orders_raw_path = orders_raw or extras.pop(
            "orders_raw", raw_path("slice", "orders_raw.csv")
        )
        adjustments_raw_path = extras.pop(
            "adjustments_raw", raw_path("slice", "adjustments_raw.csv")
        )
        normalized_out = out_path or extras.pop(
            "normalized_out", normalized_path("slice_orders_normalized.csv")
        )
        normalize_slice_from_raw.run(
            orders_raw_path,
            adjustments_raw_path,
            normalized_out,
            reset_errors=reset_errors,
        )
        print(f"[slice] normalized -> {normalized_out}")
        return
    if platform == "beyondmenu":
        from orders_analytics.parsers.beyondmenu.parse_beyondmenu_orders import (
            BeyondMenuOrdersParser,
        )

        runner = BeyondMenuOrdersParser(input_path=input_path, out_path=out_path, **extras)
    elif platform == "foodja":
        from orders_analytics.parsers.foodja.parse_foodja_orders import FoodjaOrdersParser

        runner = FoodjaOrdersParser(input_path=input_path, out_path=out_path, **extras)
    elif platform == "fooda":
        from orders_analytics.parsers.fooda.parse_fooda_orders import FoodaOrdersParser

        runner = FoodaOrdersParser(input_path=input_path, out_path=out_path, **extras)
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


def run_geocode(
    input_path: str,
    out_path: Optional[str],
    cache_path: str,
    batch_size: int,
    api_key: Optional[str],
    cache_only: bool,
    counts_out: Optional[str],
) -> None:
    import pandas as pd
    import os

    from orders_analytics.utils.geocodio import geocode_addresses, normalize_key, write_cache
    from orders_analytics.utils.geocodio import _load_env

    _load_env()

    if not cache_only:
        key = api_key or os.getenv("GEOCODE_API_KEY", "").strip()
        if not key:
            raise ValueError("GEOCODE_API_KEY is required unless --cache-only is set.")

    df = pd.read_csv(input_path, dtype=str).fillna("")
    cache = geocode_addresses(
        df.to_dict("records"),
        api_key=api_key,
        cache_path=cache_path,
        batch_size=batch_size,
        cache_only=cache_only,
    )
    usage_counts = {}
    formatted_platforms = {}
    for _, row in df.iterrows():
        address = str(row.get("address") or "").strip()
        if not address:
            continue
        key = normalize_key(address)
        record_key = (
            str(row.get("platform") or ""),
            str(row.get("provider") or ""),
            str(row.get("order_id") or ""),
        )
        usage_counts.setdefault(key, set()).add(record_key)
        formatted = str(row.get("address_formatted") or "").strip()
        lat = str(row.get("lat") or "").strip()
        lng = str(row.get("lng") or "").strip()
        if formatted:
            formatted_key = (formatted, lat, lng)
            formatted_platforms.setdefault(formatted_key, set()).add(str(row.get("platform") or ""))
    for key, records in usage_counts.items():
        if key in cache:
            cache[key]["usage_count"] = str(len(records))
    for (formatted, lat, lng), platforms in formatted_platforms.items():
        for cache_key, row in cache.items():
            if (
                str(row.get("formatted_address") or "").strip() == formatted
                and str(row.get("lat") or "").strip() == lat
                and str(row.get("lng") or "").strip() == lng
            ):
                existing = str(row.get("platform") or "")
                merged = existing
                for platform in platforms:
                    if platform:
                        if not merged:
                            merged = platform
                        elif platform not in [p.strip() for p in merged.split("|") if p.strip()]:
                            merged = f"{merged} | {platform}"
                row["platform"] = merged
    updated = 0
    for idx, row in df.iterrows():
        address = str(row.get("address") or "").strip()
        if not address:
            continue
        key = normalize_key(address)
        cached = cache.get(key)
        if not cached:
            continue
        formatted = str(cached.get("formatted_address") or "").strip()
        if formatted:
            df.at[idx, "address_formatted"] = formatted
            df.at[idx, "lat"] = str(cached.get("lat") or "")
            df.at[idx, "lng"] = str(cached.get("lng") or "")
            updated += 1
        else:
            existing = str(row.get("errors") or "").strip()
            flag = "geocode_no_formatted_address"
            if flag not in existing:
                df.at[idx, "errors"] = f"{existing} | {flag}" if existing else flag

    output = out_path or input_path
    df.to_csv(output, index=False)
    print(f"Geocoded {updated} row(s) -> {output}")
    if usage_counts:
        write_cache(cache_path, cache)
    if counts_out:
        addr = df["address_formatted"].where(df["address_formatted"].str.strip() != "", df["address"])
        counts = (
            df.assign(address_key=addr)
            .groupby(["address_key", "lat", "lng"], dropna=False)
            .size()
            .reset_index(name="count")
        )
        counts = counts[counts["address_key"].astype(str).str.strip() != ""]
        counts = counts.sort_values("count", ascending=False)
        counts.to_csv(counts_out, index=False)
        print(f"Wrote address counts -> {counts_out}")


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
        choices=[*Platforms.mbox_platforms(), "menufy", "slice"],
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
        default=takeout_path("Mail", "Billings-Eatstreet.mbox"),
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

    geocode_cmd = subparsers.add_parser(
        "geocode", help="Geocode normalized addresses into formatted/lat/lng fields."
    )
    geocode_cmd.add_argument(
        "--platform",
        choices=[*Platforms.all_platforms(), "all"],
        default="all",
        help="Platform to geocode.",
    )
    geocode_cmd.add_argument("--input", help="Override normalized CSV path.")
    geocode_cmd.add_argument("--out", help="Override output path (defaults to input).")
    geocode_cmd.add_argument(
        "--cache",
        default="orders_analytics/data/raw/geocode_cache.csv",
        help="Cache CSV path for geocode results.",
    )
    geocode_cmd.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for Geocodio API requests.",
    )
    geocode_cmd.add_argument(
        "--api-key",
        default=None,
        help="Override GEOCODE_API_KEY env var.",
    )
    geocode_cmd.add_argument(
        "--all",
        action="store_true",
        help="Alias for --platform all.",
    )
    geocode_cmd.add_argument(
        "--cache-only",
        action="store_true",
        help="Only use cached geocodes; do not call the API.",
    )
    geocode_cmd.add_argument(
        "--counts-out",
        default=None,
        help="Write address counts CSV to this path.",
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
            orders_mbox = args.orders_mbox or takeout_path("Mail", "Orders-Eatstreet.mbox")
            billings_mbox = args.billings_mbox or takeout_path("Mail", "Billings-Eatstreet.mbox")
            orders_raw = args.orders_raw or raw_path("eatstreet", "orders_raw.csv")
            billings_raw = args.billings_raw or raw_path("eatstreet", "billings_raw.csv")
        elif args.platform == "cater2me":
            orders_mbox = args.orders_mbox or takeout_path("Mail", "Orders-Cater2Me.mbox")
            billings_mbox = args.billings_mbox or takeout_path("Mail", "Billings-Cater2Me.mbox")
            orders_raw = args.orders_raw or raw_path("cater2me", "orders_raw.csv")
            billings_raw = args.billings_raw or raw_path("cater2me", "billings_raw.csv")
        elif args.platform == "menustar":
            orders_mbox = args.orders_mbox or takeout_path("Mail", "Orders-Menustar.mbox")
            billings_mbox = args.billings_mbox or takeout_path("Mail", "Billings-Menustar.mbox")
            orders_raw = args.orders_raw or raw_path("menustar", "orders_raw.csv")
            billings_raw = args.billings_raw or raw_path("menustar", "billings_raw.csv")
        elif args.platform == "foodee":
            orders_mbox = args.orders_mbox or takeout_path("Mail", "Orders-Foodee.mbox")
            billings_mbox = args.billings_mbox or takeout_path("Mail", "Billings-Foodee.mbox")
            orders_raw = args.orders_raw or raw_path("foodee", "orders_raw.csv")
            billings_raw = args.billings_raw or raw_path("foodee", "billings_raw.csv")
        elif args.platform == "foodrunners":
            orders_mbox = args.orders_mbox or takeout_path("Mail", "Orders-FoodRunners.mbox")
            billings_mbox = args.billings_mbox or takeout_path("Mail", "Billings-FoodRunners.mbox")
            orders_raw = args.orders_raw or raw_path("foodrunners", "orders_raw.csv")
            billings_raw = args.billings_raw or raw_path("foodrunners", "billings_raw.csv")
        elif args.platform == "officecaterer":
            orders_mbox = args.orders_mbox or takeout_path("Mail", "Orders-OfficeCaterer.mbox")
            billings_mbox = args.billings_mbox or takeout_path(
                "Mail", "Billings-OfficeCaterer.mbox"
            )
            orders_raw = args.orders_raw or raw_path("officecaterer", "orders_raw.csv")
            billings_raw = args.billings_raw or raw_path("officecaterer", "billings_raw.csv")
        elif args.platform == "menufy":
            orders_mbox = args.orders_mbox or ""
            billings_mbox = args.billings_mbox or ""
            orders_raw = args.orders_raw or raw_path("menufy", "orders_raw.csv")
            billings_raw = args.billings_raw or ""
        elif args.platform == "slice":
            orders_mbox = args.orders_mbox or ""
            billings_mbox = args.billings_mbox or ""
            orders_raw = args.orders_raw or raw_path("slice", "orders_raw.csv")
            billings_raw = args.billings_raw or ""
        else:
            orders_mbox = args.orders_mbox or takeout_path("Mail", "Orders-DeliveryCom.mbox")
            billings_mbox = args.billings_mbox or takeout_path("Mail", "Billings-DeliveryCom.mbox")
            orders_raw = args.orders_raw or raw_path("deliverycom", "orders_raw.csv")
            billings_raw = args.billings_raw or raw_path("deliverycom", "billings_raw.csv")
        run_extract(args.platform, orders_mbox, billings_mbox, orders_raw, billings_raw)
    elif args.command == "normalize":
        from orders_analytics.utils.constants import ERRORS_PATH

        if args.reset_errors and args.platform == "all" and os.path.exists(ERRORS_PATH):
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
                reset_errors=args.reset_errors,
            )
    elif args.command == "geocode":
        platforms: List[str]
        if args.all or args.platform == "all":
            platforms = Platforms.all_platforms()
        else:
            platforms = [args.platform]
        for platform in platforms:
            input_path = args.input or normalized_path(f"{platform}_orders_normalized.csv")
            run_geocode(
                input_path,
                args.out,
                args.cache,
                args.batch_size,
                args.api_key,
                args.cache_only,
                args.counts_out,
            )


if __name__ == "__main__":
    main()
from orders_analytics.utils.platforms import Platforms
