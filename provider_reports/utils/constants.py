import enum
import os

# file path constants
CURRENT_FILE = os.path.abspath(__file__)
DOWNLOADS_DIR = os.path.join(os.path.expanduser('~'), 'Downloads')
RAW_REPORTS_PATH = os.path.abspath(os.path.join(os.path.dirname(CURRENT_FILE), '../reports'))
PROCESSED_REPORTS_PATH = os.path.abspath(os.path.join(os.path.dirname(CURRENT_FILE), '../reports_processed'))
DATA_PATH = os.path.abspath(os.path.join(os.path.dirname(CURRENT_FILE), '../data'))
DATA_PATH_RAW = os.path.abspath(os.path.join(os.path.dirname(CURRENT_FILE), '../data/raw'))
DATA_PATH_OPTIMIZED = os.path.abspath(os.path.join(os.path.dirname(CURRENT_FILE), '../data/optimized'))
CREDENTIALS_PATH = os.path.abspath(os.path.join(os.path.dirname(CURRENT_FILE), '../credentials'))

# email name constants
SENDER_EMAIL = 'acehaidrey@gmail.com'
AMECI_FWD_EMAIL = '9320.Amec@xcinvoice.com'
AROMA_FWD_EMAIL = '7907.Arom@xcinvoice.com'

TAX_RATE = 0.0775


class Store(enum.Enum):
    """
    Constants for store names.

    This class provides constants for different store names.
    """
    AMECI = 'ameci'
    AROMA = 'aroma'


class PaymentType:
    """
    Constants for store names.

    This class provides constants for different payment types.
    """
    CREDIT = 'credit'
    CASH = 'cash'


class ReportType:
    """
    Constants for store names.

    This class provides constants for different report types.
    """
    ORDERS = 'orders'
    CUSTOMERS = 'customers'
    INVOICES = 'invoices'
    ADJUSTMENTS = 'adjustments'


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
    PDF = 'pdf'
    PARQUET = 'parquet'


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
    ORDER_INN = 'order_inn'


class Stage(enum.Enum):
    """
    Constants for stage names.

    This class provides constants for different stage names.
    """
    START = 'start'
    CREDENTIALS = 'credentials'
    LOGIN = 'login'
    PREPROCESSING = 'preprocessing'
    RETRIEVAL = 'retrieval'
    POSTPROCESSING = 'postprocessing'
    STANDARDIZE = 'standardize'
    VALIDATION = 'validation'
    UPLOAD = 'upload'
    CLOSE = 'close'
    COMPLETE = 'complete'
