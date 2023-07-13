import argparse
import calendar
import os
import shutil
import sys
import time
import traceback
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler

import chromedriver_autoinstaller

# Add this project in the system path to resolve the imports
sys.path.extend([os.path.abspath('..')])

from provider_reports.utils.constants import Provider, RAW_REPORTS_PATH, \
    CREDENTIALS_PATH, Store, PROCESSED_REPORTS_PATH, Stage, DATA_PATH, \
    DATA_PATH_RAW, DATA_PATH_OPTIMIZED
from provider_reports.utils.utils import get_store_names_from_credentials_file
from providers.brygid import BrygidOrders
from providers.eatstreet import EatstreetOrders
from providers.ezcater import EZCaterOrders
from providers.futurefoods import FutureFoodsOrders
from providers.menufy import MenufyOrders
from providers.office_express import FoodjaOrders
from providers.restaurant_depot import RestaurantDepotReceipts
from providers.slice import SliceOrders


def get_logger(log_file):
    """
    Get a logger instance with rotating file handler for log rotation.
    :param log_file: The log file name.
    :return: Logger instance.
    """
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024 * 10, backupCount=5)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


# Map provider names to provider classes and credential files
provider_map = {
    Provider.BRYGID: (BrygidOrders, 'brygid_credentials.json'),
    Provider.EATSTREET: (EatstreetOrders, 'eatstreet_credentials.json'),
    Provider.EZCATER: (EZCaterOrders, 'ezcater_credentials.json'),
    Provider.FUTURE_FOODS: (FutureFoodsOrders, 'future_foods_credentials.json'),
    Provider.MENUFY: (MenufyOrders, 'menufy_credentials.json'),
    Provider.OFFICE_EXPRESS: (FoodjaOrders, 'office_express_credentials.json'),
    Provider.RESTAURANT_DEPOT: (RestaurantDepotReceipts, 'restaurant_depot_credentials.json'),
    Provider.SLICE: (SliceOrders, 'slice_credentials.json'),
}


def run_orders_providers(start_date, end_date, provider_names=None, filtered_stores=None, log_file=None):
    if provider_names is None:
        provider_names = [provider.value for provider in provider_map.keys()]

    logger = get_logger(log_file) if log_file else logging.getLogger()

    for passed_provider_name in provider_names:
        provider_name = Provider[passed_provider_name.upper()]

        if provider_name in provider_map:
            provider_class, provider_credential_filename = provider_map[provider_name]
            credential_file_path = os.path.join(CREDENTIALS_PATH, provider_credential_filename)

            if os.path.isfile(credential_file_path):
                stores = get_store_names_from_credentials_file(credential_file_path, filtered_stores)

                for store in stores:
                    orders_provider = provider_class(credential_file_path, start_date, end_date, store_name=store)
                    start_time = time.time()

                    stages = [
                        (Stage.LOGIN, orders_provider.login),
                        (Stage.PREPROCESSING, orders_provider.preprocess_reports),
                        (Stage.RETRIEVAL, orders_provider.get_reports),
                        (Stage.POSTPROCESSING, orders_provider.postprocess_reports),
                        (Stage.STANDARDIZE, orders_provider.standardize_transaction_report),
                        (Stage.VALIDATION, orders_provider.validate_reports),
                        (Stage.UPLOAD, orders_provider.upload_reports),
                        (Stage.CLOSE, orders_provider.quit)
                    ]

                    for stage, action in stages:
                        try:
                            action()
                            logger.info(f"{provider_name}: {store} Reports {stage} completed")
                        except Exception as e:
                            logger.error(f"{provider_name}: {store} failed on stage: {stage} with error: {str(e)}")
                            logger.error(traceback.format_exc())

                    end_time = time.time()
                    logger.info(f'{provider_name}: {store} Took {round(end_time - start_time, 2)} seconds to run.')
            else:
                logger.error(f"Credential file not found for {provider_name}: {credential_file_path}")
        else:
            logger.error(f"Invalid provider name: {provider_name}")


def parse_date(date_str, date_type='start'):
    """
    If the full date is not passed then auto assign to first and last day of each given month.
    :param date_str:
    :param date_type:
    :return:
    """
    try:
        return datetime.strptime(date_str, "%Y/%m/%d")
    except ValueError:
        try:
            dt = datetime.strptime(date_str, "%Y/%m")
            if date_type == 'start':
                dt = dt.replace(day=1)
            else:
                # end_date - get last day of month
                _, last_day = calendar.monthrange(dt.year, dt.month)
                dt = dt.replace(day=last_day)
            logging.info(f'Using {date_type} date of {dt}')
            return dt
        except ValueError:
            raise argparse.ArgumentTypeError("Invalid date format. Expected format: YYYY/MM or YYYY/MM/DD")


def setup(cleanup=False):
    """Setup utilities for the project to begin."""
    chromedriver_autoinstaller.install()

    for folder in [
        CREDENTIALS_PATH, RAW_REPORTS_PATH, PROCESSED_REPORTS_PATH,
        DATA_PATH, DATA_PATH_RAW, DATA_PATH_OPTIMIZED
    ]:
        if not os.path.exists(folder):
            os.makedirs(folder)
            logging.info(f"Created folder: {folder}")

    if cleanup:
        cleanup_reports()

    logging.info("Setup completed successfully.")


def cleanup_reports(folder=RAW_REPORTS_PATH):
    # Delete all files in the reports folder
    if os.path.exists(folder):
        for file_name in os.listdir(folder):
            file_path = os.path.join(folder, file_name)
            if os.path.isfile(file_path):
                os.remove(file_path)
                logging.info(f'Deleted file: {file_path}')
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
                logging.info(f'Deleted directory and all subfiles in {file_path}')
        logging.info(f"All files in '{folder}' folder have been deleted.")
    else:
        logging.info(f"'{folder}' folder does not exist.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run orders providers to get finance reports")
    parser.add_argument("-s", "--start-date", type=lambda d: parse_date(d, 'start'), required=True,
                        help="Start date (YYYY/MM or YYYY/MM/DD)")
    parser.add_argument("-e", "--end-date", type=lambda d: parse_date(d, 'end'), required=True,
                        help="End date (YYYY/MM or YYYY/MM/DD)")
    parser.add_argument("-p", "--providers", nargs="+", choices=[provider.value for provider in Provider],
                        help="Provider names to run (separated by spaces)")
    parser.add_argument('-n', '--stores', nargs="+", choices=[store.value for store in Store], default=None,
                        help='Store names to filter on. All by default.')
    parser.add_argument("-c", "--cleanup", action="store_true", default=False,
                        help="Cleanup reports folder from previous run files")
    parser.add_argument("-l", "--logfile", default=None, help="Path to the log file to use")

    args = parser.parse_args()
    start_date = args.start_date
    end_date = args.end_date
    providers = args.providers
    stores = args.stores
    log_file = args.logfile
    logging.info(f'Running with args: {args}')
    setup(args.cleanup)
    run_orders_providers(start_date, end_date, providers, stores, log_file)


# print(TransactionRecord.generate_yaml_config('brygid')) (X)
# add stage information (X)
# build a schema file here or yaml (we will do transactional) (X)
# add a mapping file per provider (not a single yaml) (X)
# add utility funcitons to do the transformation
    # to read yaml and check against the schema file here (X)
    # to transform to an output data file we want (X)
# write the new file in a central place (X)
# add validation functions for data file (X)
# save the file as parquet file format (X)
# create duckdb table on top of this transactional data (X)


# update all functions to implement the orders standardization
    # brygid, ezcater
# create quick dashboard
# fix toast script
# fix slice script
# get files from GSuite

# improve by unifying all the underlying files
# fix the logging if needed
# fix the error handling when things aren't working out
# do a deduplication step based on transaction info (separate table maybe)
# build quick dashboard for it
