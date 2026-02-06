from __future__ import annotations

import csv
import json
import os
import re
import time
from typing import Dict, Iterable, List, Optional

import requests

DEFAULT_CACHE_PATH = "orders_analytics/data/raw/geocode_cache.csv"
DEFAULT_API_URL = "https://api.geocod.io/v1.9/geocode"


class GeocodeStop(Exception):
    pass


def _load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def normalize_key(address: str) -> str:
    text = str(address or "").lower()
    text = re.sub(r"[^a-z0-9\\s]", " ", text)
    text = re.sub(r"\\s+", " ", text).strip()
    return text


def _read_cache(path: str) -> Dict[str, Dict[str, str]]:
    if not os.path.exists(path):
        return {}
    cache: Dict[str, Dict[str, str]] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            key = str(row.get("key", "")).strip()
            if key:
                cache[key] = row
    return cache


def _write_cache(path: str, rows: Dict[str, Dict[str, str]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fieldnames = [
        "key",
        "platform",
        "provider",
        "input_address",
        "formatted_address",
        "lat",
        "lng",
        "usage_count",
        "response_json",
        "error",
        "updated_at",
    ]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows.values():
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_cache(path: str, rows: Dict[str, Dict[str, str]]) -> None:
    _write_cache(path, rows)


def _merge_provider(existing: str, provider: str) -> str:
    existing_list = [p.strip() for p in str(existing or "").split("|") if p.strip()]
    if provider:
        existing_list.append(provider)
    if not existing_list:
        return ""
    unique = []
    seen = set()
    for item in existing_list:
        if item not in seen:
            unique.append(item)
            seen.add(item)
    return " | ".join(unique)


def _merge_platform(existing: str, platform: str) -> str:
    existing_list = [p.strip() for p in str(existing or "").split("|") if p.strip()]
    if platform:
        existing_list.append(platform)
    if not existing_list:
        return ""
    unique = []
    seen = set()
    for item in existing_list:
        if item not in seen:
            unique.append(item)
            seen.add(item)
    return " | ".join(unique)


def _should_stop(resp: requests.Response) -> bool:
    if resp.status_code in (402, 403, 429):
        return True
    return False


def geocode_batch(
    addresses: List[Dict[str, str]],
    api_key: str,
    cache_path: str = DEFAULT_CACHE_PATH,
    sleep_seconds: float = 1.0,
) -> Dict[str, Dict[str, str]]:
    cache = _read_cache(cache_path)
    if not addresses:
        return cache

    payload = [item["input_address"] for item in addresses]
    params = {"api_key": api_key}
    try:
        resp = requests.post(DEFAULT_API_URL, params=params, json=payload, timeout=20)
    except requests.RequestException:
        return cache

    if _should_stop(resp):
        raise GeocodeStop("Geocode quota or rate limit reached.")
    if resp.status_code != 200:
        return cache

    try:
        data = resp.json()
    except ValueError:
        return cache

    results = data.get("results", []) if isinstance(data, dict) else []
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    for item, result in zip(addresses, results):
        key = item["key"]
        formatted = ""
        lat = ""
        lng = ""
        error = ""
        response = result.get("response", {}) if isinstance(result, dict) else {}
        response_json = json.dumps(response, ensure_ascii=False)
        if isinstance(response, dict) and response.get("results"):
            top = response["results"][0]
            formatted = str(top.get("formatted_address") or "").strip()
            location = top.get("location") or {}
            lat = str(location.get("lat") or "").strip()
            lng = str(location.get("lng") or "").strip()
            if not formatted:
                error = "geocode_no_formatted_address"
        else:
            error = "geocode_no_results"
        cache[key] = {
            "key": key,
            "platform": _merge_platform(cache.get(key, {}).get("platform", ""), item.get("platform", "")),
            "provider": _merge_provider(cache.get(key, {}).get("provider", ""), item.get("provider", "")),
            "input_address": item.get("input_address", ""),
            "formatted_address": formatted,
            "lat": lat,
            "lng": lng,
            "response_json": response_json,
            "error": error,
            "updated_at": now,
        }

    _write_cache(cache_path, cache)
    if sleep_seconds:
        time.sleep(sleep_seconds)
    return cache


def geocode_addresses(
    rows: Iterable[Dict[str, str]],
    api_key: Optional[str] = None,
    cache_path: str = DEFAULT_CACHE_PATH,
    batch_size: int = 100,
    cache_only: bool = False,
) -> Dict[str, Dict[str, str]]:
    _load_env()
    key = api_key or os.getenv("GEOCODE_API_KEY", "").strip()
    if not key:
        return _read_cache(cache_path)

    cache = _read_cache(cache_path)
    cache_updated = False
    pending: List[Dict[str, str]] = []
    for row in rows:
        address = str(row.get("address") or "").strip()
        if not address:
            continue
        k = normalize_key(address)
        if k in cache:
            provider = str(row.get("provider") or "")
            merged = _merge_provider(cache.get(k, {}).get("provider", ""), provider)
            if merged != cache.get(k, {}).get("provider", ""):
                cache[k]["provider"] = merged
                cache_updated = True
            platform = str(row.get("platform") or "")
            merged_platform = _merge_platform(cache.get(k, {}).get("platform", ""), platform)
            if merged_platform != cache.get(k, {}).get("platform", ""):
                cache[k]["platform"] = merged_platform
                cache_updated = True
            continue
        pending.append(
            {
                "key": k,
                "input_address": address,
                "platform": str(row.get("platform") or ""),
                "provider": str(row.get("provider") or ""),
            }
        )
        if cache_only:
            continue
        if len(pending) >= batch_size:
            try:
                cache = geocode_batch(pending, key, cache_path=cache_path)
            except GeocodeStop:
                if cache_updated:
                    _write_cache(cache_path, cache)
                return cache
            pending = []

    if cache_only:
        if cache_updated:
            _write_cache(cache_path, cache)
        return cache
    if pending:
        try:
            cache = geocode_batch(pending, key, cache_path=cache_path)
        except GeocodeStop:
            if cache_updated:
                _write_cache(cache_path, cache)
            return cache
    if cache_updated:
        _write_cache(cache_path, cache)
    return cache


def apply_cache_to_rows(
    rows: List[Dict[str, str]],
    cache_path: str = DEFAULT_CACHE_PATH,
) -> List[Dict[str, str]]:
    cache = _read_cache(cache_path)
    for row in rows:
        address = str(row.get("address") or "").strip()
        if not address:
            continue
        key = normalize_key(address)
        cached = cache.get(key)
        if not cached:
            continue
        formatted = str(cached.get("formatted_address") or "").strip()
        if formatted:
            row["address_formatted"] = formatted
            row["lat"] = str(cached.get("lat") or "")
            row["lng"] = str(cached.get("lng") or "")
        else:
            existing = str(row.get("errors") or "").strip()
            flag = "geocode_no_formatted_address"
            if flag not in existing:
                row["errors"] = f"{existing} | {flag}" if existing else flag
    return rows
