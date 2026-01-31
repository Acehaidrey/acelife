from __future__ import annotations


class Providers:
    AROMA = "AROMA"
    AMECI = "AMECI"

    @classmethod
    def all_providers(cls) -> list[str]:
        return [cls.AROMA, cls.AMECI]
