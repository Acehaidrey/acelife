from __future__ import annotations


class OrderTypes:
    PICKUP = "pickup"
    DELIVERY = "delivery"
    PHONE_CALL = "phone_call"

    @classmethod
    def get_all(cls) -> list[str]:
        return [cls.PICKUP, cls.DELIVERY, cls.PHONE_CALL]
