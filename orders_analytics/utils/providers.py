from __future__ import annotations

from datetime import datetime


class Providers:
    AROMA = "AROMA"
    AMECI = "AMECI"

    @classmethod
    def all_providers(cls) -> list[str]:
        return [cls.AROMA, cls.AMECI]


def normalize_provider(name: str) -> str:
    text = (name or "").lower()
    if "aroma" in text:
        return Providers.AROMA
    if "ameci" in text:
        return Providers.AMECI
    return ""


def normalize_datetime(value: str) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return ""
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return text
