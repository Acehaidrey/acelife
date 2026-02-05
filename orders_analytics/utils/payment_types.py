from __future__ import annotations


class PaymentTypes:
    CREDIT = "credit"
    CASH = "cash"

    @classmethod
    def get_all(cls) -> list[str]:
        return [cls.CREDIT, cls.CASH]
