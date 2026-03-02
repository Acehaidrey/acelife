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
    SLICE = "slice"
    CHOWNOW = "chownow"
    BRYGID = "brygid"
    ORDERINN = "orderinn"
    UBEREATS = "ubereats"
    GRUBHUB = "grubhub"
    MEALHI5 = "mealhi5"
    DOORDASH = "doordash"
    MAYAEATS = "mayaeats"
    NEXTBITE = "nextbite"

    # list of inactive platforms that no longer partner with
    INACTIVE = {
        CATER2ME,
        DELIVERYCOM,
        FOODA,
        FOODEE,
        BRYGID,
        ORDERINN,
        MEALHI5,
        MAYAEATS,
        NEXTBITE,
    }

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
            cls.SLICE,
            cls.CHOWNOW,
            cls.BRYGID,
            cls.ORDERINN,
            cls.UBEREATS,
            cls.GRUBHUB,
            cls.MEALHI5,
            cls.DOORDASH,
            cls.MAYAEATS,
            cls.NEXTBITE,
        ]

    @classmethod
    def active_platforms(cls) -> list[str]:
        return [p for p in cls.all_platforms() if p not in cls.INACTIVE]

    @classmethod
    def inactive_platforms(cls) -> list[str]:
        return sorted(cls.INACTIVE)

    @classmethod
    def csv_platforms(cls) -> list[str]:
        return [
            cls.BEYONDMENU,
            cls.FOODJA,
            cls.FOODA,
            cls.EZCATER,
            cls.MENUFY,
            cls.SLICE,
            cls.UBEREATS,
            cls.GRUBHUB,
            cls.MEALHI5,
            cls.DOORDASH,
        ]

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
            cls.CHOWNOW,
            cls.BRYGID,
            cls.MEALHI5,
            cls.MAYAEATS,
            cls.NEXTBITE,
        ]
