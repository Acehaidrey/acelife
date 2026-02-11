DEFAULT_DB_PATH = "orders_analytics/data/orders.duckdb"
NORMALIZED_DIR = "orders_analytics/data/normalized"
RAW_DIR = "orders_analytics/data/raw"
ERRORS_PATH = "orders_analytics/data/errors/errors.csv"
TAKEOUT_DIR = "Takeout"
WAVE_DIR = "Takeout"
WAVE_AMECI_DIR = "Takeout/wave_ameci"
WAVE_AROMA_DIR = "Takeout/wave_aroma"


def raw_path(*parts: str) -> str:
    return "/".join([RAW_DIR, *parts])


def normalized_path(filename: str) -> str:
    return "/".join([NORMALIZED_DIR, filename])


def takeout_path(*parts: str) -> str:
    return "/".join([TAKEOUT_DIR, *parts])


def wave_ameci_path(*parts: str) -> str:
    return "/".join([WAVE_AMECI_DIR, *parts])


def wave_aroma_path(*parts: str) -> str:
    return "/".join([WAVE_AROMA_DIR, *parts])

DATE_GRAINS = ["day", "month", "year"]

from orders_analytics.utils.platforms import Platforms
from orders_analytics.utils.providers import Providers
from orders_analytics.utils.order_types import OrderTypes
from orders_analytics.utils.payment_types import PaymentTypes

PLATFORMS = Platforms.all_platforms()
PROVIDERS = Providers.all_providers()

ORDER_TYPES = OrderTypes.get_all()
PAYMENT_TYPES = PaymentTypes.get_all()
