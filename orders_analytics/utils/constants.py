DEFAULT_DB_PATH = "orders_analytics/data/orders.duckdb"
NORMALIZED_DIR = "orders_analytics/data/normalized"
RAW_DIR = "orders_analytics/data/raw"
ERRORS_PATH = "orders_analytics/data/errors/errors.csv"
TAKEOUT_DIR = "Takeout"


def raw_path(*parts: str) -> str:
    return "/".join([RAW_DIR, *parts])


def normalized_path(filename: str) -> str:
    return "/".join([NORMALIZED_DIR, filename])


def takeout_path(*parts: str) -> str:
    return "/".join([TAKEOUT_DIR, *parts])

DATE_GRAINS = ["day", "month", "year"]

from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.providers import Providers

PLATFORMS = Platforms.all_platforms()
PROVIDERS = Providers.all_providers()

ORDER_TYPES = ["pickup", "delivery"]
PAYMENT_TYPES = ["credit", "cash"]
