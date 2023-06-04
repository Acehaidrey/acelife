import enum
import os

CURRENT_FILE = os.path.abspath(__file__)
DOWNLOADS_DIR = os.path.join(os.path.expanduser('~'), 'Downloads')
RAW_REPORTS_PATH = os.path.abspath(os.path.join(os.path.dirname(CURRENT_FILE), '../reports'))
PROCESSED_REPORTS_PATH = os.path.abspath(os.path.join(os.path.dirname(CURRENT_FILE), '../reports_processed'))
CREDENTIALS_PATH = os.path.abspath(os.path.join(os.path.dirname(CURRENT_FILE), '../credentials'))


class Store(enum.Enum):
    """
    Constants for store names.

    This class provides constants for different store names.
    """
    AMECI = 'ameci'
    AROMA = 'aroma'


class ReportType:
    """
    Constants for store names.

    This class provides constants for different report types.
    """
    ORDERS = 'orders'
    CUSTOMERS = 'customers'
    INVOICES = 'invoices'


class Extensions:
    """
    Extensions for downloaded and processed files.

    This class provides constants for different extension types.
    """
    CSV = 'csv'
    TXT = 'txt'
    ZIP = 'zip'
    HTML = 'html'
    EXCEL = 'xlsx'


class Provider(enum.Enum):
    """
    Constants for provider names.

    This class provides constants for different provider names.
    """
    BRYGID = 'brygid'
    DOORDASH = 'doordash'
    EATSTREET = 'eatstreet'
    EZCATER = 'ezcater'
    FUTURE_FOODS = 'future_foods'
    GRUBHUB = 'grubhub'
    MENUFY = 'menufy'
    OFFICE_EXPRESS = 'office_express'
    SLICE = 'slice'
    TOAST = 'toast'
    UBEREATS = 'ubereats'
    RESTAURANT_DEPOT = 'restaurant_depot'
