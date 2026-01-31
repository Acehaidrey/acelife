from __future__ import annotations


class Platforms:
    EATSTREET = "eatstreet"
    BEYONDMENU = "beyondmenu"
    FOODJA = "foodja"
    EZCATER = "ezcater"
    CATER2ME = "cater2me"
    MENUSTAR = "menustar"

    @classmethod
    def all_platforms(cls) -> list[str]:
        return [
            cls.EATSTREET,
            cls.BEYONDMENU,
            cls.FOODJA,
            cls.EZCATER,
            cls.CATER2ME,
            cls.MENUSTAR,
        ]

    @classmethod
    def csv_platforms(cls) -> list[str]:
        return [cls.BEYONDMENU, cls.FOODJA, cls.EZCATER]

    @classmethod
    def mbox_platforms(cls) -> list[str]:
        return [cls.EATSTREET, cls.CATER2ME, cls.MENUSTAR]
