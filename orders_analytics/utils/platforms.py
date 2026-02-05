from __future__ import annotations


class Platforms:
    EATSTREET = "eatstreet"
    BEYONDMENU = "beyondmenu"
    FOODJA = "foodja"
    FOODA = "fooda"
    EZCATER = "ezcater"
    CATER2ME = "cater2me"
    MENUSTAR = "menustar"
    DELIVERYCOM = "deliverycom"
    FOODEE = "foodee"
    FOODRUNNERS = "foodrunners"
    OFFICECATERER = "officecaterer"
    MENUFY = "menufy"

    @classmethod
    def all_platforms(cls) -> list[str]:
        return [
            cls.EATSTREET,
            cls.BEYONDMENU,
            cls.FOODJA,
            cls.FOODA,
            cls.EZCATER,
            cls.CATER2ME,
            cls.MENUSTAR,
            cls.DELIVERYCOM,
            cls.FOODEE,
            cls.FOODRUNNERS,
            cls.OFFICECATERER,
            cls.MENUFY,
        ]

    @classmethod
    def csv_platforms(cls) -> list[str]:
        return [cls.BEYONDMENU, cls.FOODJA, cls.FOODA, cls.EZCATER, cls.MENUFY]

    @classmethod
    def mbox_platforms(cls) -> list[str]:
        return [
            cls.EATSTREET,
            cls.CATER2ME,
            cls.MENUSTAR,
            cls.DELIVERYCOM,
            cls.FOODEE,
            cls.FOODRUNNERS,
            cls.OFFICECATERER,
        ]
