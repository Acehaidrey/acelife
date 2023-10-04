import datetime
import glob
import os
import time

import numpy as np
import pandas as pd
import retrying
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from provider_reports.providers.base_provider import OrdersProvider
from provider_reports.schema.schema import TransactionRecord
from provider_reports.utils.constants import Store, RAW_REPORTS_PATH, Provider, \
    ReportType, Extensions, TAX_RATE, DATA_PATH_RAW, PaymentType
from provider_reports.utils.utils import get_chrome_options, \
    standardize_order_report_setup
from provider_reports.utils.validation_utils import ValidationUtils


class DeliveryComOrders(OrdersProvider):
    """
    Delivery.com orders provider.

    This class implements the OrdersProvider interface for the Delivery.com provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.

    Has captcha preventing automation steps. Will use the emails to parse instead.
    """

    PROVIDER = Provider.DELIVERY_COM
    LOGIN_URL = "https://www.delivery.com/storefront/login"
    ORDER_FILENAME_PATTERN = "rc_*.csv"

    def __init__(self, credential_file_path, start_date, end_date, store_name):
        """
        Initialize the Delivery Com provider.

        Args:
            credential_file_path (str): The path to the credential file.
            start_date (datetime.datetime): The start date for retrieving orders.
            end_date (datetime.datetime): The end date for retrieving orders.
            store_name (Store): The name of the store associated with the provider.
        """
        super().__init__(credential_file_path, start_date, end_date, store_name)

        self.driver = None
        self.wait = None

    # @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def login(self):
        """
        Perform the login process for the Order Inn provider.
        """
        self.driver = webdriver.Chrome(options=get_chrome_options())
        self.wait = WebDriverWait(self.driver, 10)

        self.driver.get(DeliveryComOrders.LOGIN_URL)
        username_input = self.wait.until(EC.presence_of_element_located((By.ID, "inputEmail")))
        username_input.clear()
        username_input.send_keys(self.username)
        password_input = self.wait.until(EC.presence_of_element_located((By.ID, "inputPassword")))
        password_input.clear()
        password_input.send_keys(self.password)

        self.driver.find_element(By.CSS_SELECTOR,
                                 ".recaptcha-checkbox-border").click()

        self.driver.find_element(By.XPATH, "//input[@value=\'Log in\']").click()

    def preprocess_reports(self):
        pass

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        start_time = time.time()

        # FILL IN

        # Wait for the file to be downloaded
        file_pattern = os.path.join(RAW_REPORTS_PATH, self.ORDER_FILENAME_PATTERN)
        self.wait.until(lambda driver: any(
            os.stat(file_path).st_ctime > start_time
            for file_path in glob.glob(file_pattern)
        ))
        # Get the downloaded file(s) that match the condition
        downloaded_files = [
            file_path
            for file_path in glob.glob(file_pattern)
            if os.stat(file_path).st_ctime > start_time
        ]
        print(f"Downloaded file(s): {downloaded_files}")
        self.downloaded_files.extend(downloaded_files)

    def postprocess_reports(self):
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

    def standardize_orders_report(self):
        pass

    def validate_reports(self):
        ValidationUtils.validate_downloaded_files_count(self.downloaded_files, 1)
        ValidationUtils.validate_processed_files_count(self.processed_files, 1)
        ValidationUtils.validate_downloaded_files_extension(self.downloaded_files, Extensions.CSV)
        ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.CSV)
        ValidationUtils.validate_data_files_count(self.data_files, 1)
        ValidationUtils.validate_data_file_total_after_fees_accurate(self.data_files[0])

    def upload_reports(self):
        self.write_parquet_data()

    def quit(self):
        self.driver.quit()


def main():
    """
    Main entry point for the script.
    """
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    credential_file_path = '../../credentials/delivery_com_credentials.json'
    start_date = datetime.datetime(2022, 1, 1)
    end_date = datetime.datetime(2023, 1, 31)
    store_name = Store.AROMA

    orders = DeliveryComOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    # orders.preprocess_reports()
    # orders.get_reports()
    # orders.downloaded_files = [
    #     '/Users/ahaidrey/Desktop/acelife/provider_reports/reports/RestData (1).csv',
    # ]
    # orders.postprocess_reports()
    # orders.standardize_orders_report()
    # orders.validate_reports()
    # orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
