import enum
import os

DOWNLOADS_DIR = os.path.join(os.path.expanduser('~'), 'Downloads')
RAW_REPORTS_PATH = os.path.abspath('../reports')
PROCESSED_REPORTS_PATH = os.path.abspath('../reports_processed')


class Store(enum.Enum):
    """
    Constants for store names.

    This class provides constants for different store names.
    """
    AMECI = 'Ameci'
    AROMA = 'Aroma'


class ReportType:
    """
    Constants for store names.

    This class provides constants for different report types.
    """
    ORDERS = 'orders'
    CUSTOMERS = 'customers'


class Extensions:
    """
    Extensions for downloaded and processed files.

    This class provides constants for different extension types.
    """
    CSV = 'csv'
    TXT = 'txt'
    ZIP = 'zip'
    HTML = 'html'


class Provider(enum.Enum):
    """
    Constants for provider names.

    This class provides constants for different provider names.
    """
    BRYGID = 'brygid'
    DOORDASH = 'doordash'
    EATSTREET = 'eatstreet'
    FUTURE_FOODS = 'future_foods'
    GRUBHUB = 'grubhub'
    MENUFY = 'menufy'
    OFFICE_EXPRESS = 'office_express'
    SLICE = 'slice'
    UBEREATS = 'ubereats'
