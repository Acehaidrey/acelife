DEFAULT_DB_PATH = "orders_analytics/data/orders.duckdb"
NORMALIZED_DIR = "orders_analytics/data/normalized"
RAW_DIR = "orders_analytics/data/raw"
ERRORS_PATH = "orders_analytics/data/errors/errors.csv"


def raw_path(*parts: str) -> str:
    return "/".join([RAW_DIR, *parts])


def normalized_path(filename: str) -> str:
    return "/".join([NORMALIZED_DIR, filename])

DATE_GRAINS = ["day", "month", "year"]

PLATFORMS = [
    "eatstreet",
    "beyondmenu",
    "foodja",
    "ezcater",
    "cater2me",
]

PROVIDERS = [
    "aroma",
    "ameci",
]

ORDER_TYPES = ["pickup", "delivery"]
PAYMENT_TYPES = ["credit", "cash"]
