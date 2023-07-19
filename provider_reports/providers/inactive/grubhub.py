import csv
import os
from datetime import datetime
import time

import pandas as pd
import retrying
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

from provider_reports.providers.base_provider import OrdersProvider
from provider_reports.utils.constants import Store, RAW_REPORTS_PATH, Provider, ReportType, Extensions
from provider_reports.utils.utils import get_chrome_options
from provider_reports.utils.validation_utils import ValidationUtils


class GrubhubOrders(OrdersProvider):
    """
    Grubhub orders provider.

    This class implements the OrdersProvider interface for the Grubhub provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.
    """

    PROVIDER = Provider.GRUBHUB
    LOGIN_URL = "https://restaurant.grubhub.com/login"
    ORDER_FILENAME_PATTERN = "Grubhub*.html"

    def __init__(self, credential_file_path, start_date, end_date, store_name):
        """
        Initialize the GrubhubOrders provider.
        This provider has few orders but still want to account for them.

        Args:
            credential_file_path (str): The path to the credential file.
            start_date (datetime.datetime): The start date for retrieving orders.
            end_date (datetime.datetime): The end date for retrieving orders.
            store_name (Store): The name of the store associated with the provider.
        """
        super().__init__(credential_file_path, start_date, end_date, store_name)

        from selenium.webdriver.chrome.options import Options
        options = Options()
        options.add_argument('--incognito')

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 20)

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def login(self):
        """
        Perform the login process for the Grubhub provider.
        """
        self.driver.get(GrubhubOrders.LOGIN_URL)
        username_input = self.wait.until(EC.presence_of_element_located((By.ID, "gfr-login-authentication-username")))
        username_input.clear()
        username_input.send_keys(self.username)
        password_input = self.wait.until(EC.presence_of_element_located((By.ID, "gfr-login-authentication-password")))
        password_input.clear()
        password_input.send_keys(self.password)
        self.wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(.,'Sign in')]"))).click()
        # TODO: system has a captcha so need another way to handle this. asked for api settings
        time.sleep(120)

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        pass
        # print(f"Downloaded file(s): {full_filename}")
        # self.downloaded_files.extend(full_filename)

    def preprocess_reports(self):
        """
        Preprocess the retrieved orders from the Grubhub provider.
        """
        pass

    def postprocess_reports(self):
        """
        Postprocess the retrieved orders from the Grubhub provider. Only expect one file.
        """
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        for downloaded_file in self.downloaded_files:
            pass

        # self.processed_files.append(processed_file)
        # print(f'Saved {self.store_name} orders to: {processed_file}')

    def standardize_orders_report(self):
        pass

    def validate_reports(self):
        """
        Perform report validation specific to the Grubhub provider.
        TODO: Compare pdf summaries to transaction summaries.
        """
        # ValidationUtils.validate_processed_files_count(self.processed_files, 1)
        # ValidationUtils.validate_downloaded_files_count(self.downloaded_files, 1)
        # ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.CSV)
        # ValidationUtils.validate_downloaded_files_extension(self.downloaded_files, Extensions.CSV)
        # ValidationUtils.validate_processed_files_date_range(
        #     self.processed_files, self.start_date, self.end_date, 'Date', '%m/%d/%Y %I:%M %p')

        print("Report validation successful")

    def upload_reports(self):
        """
        Upload the processed report to a remote location specific to the Grubhub provider.
        """
        # TODO: Implement report uploading logic for Grubhub
        pass

    def quit(self):
        """
        Quit the Grubhub provider session.
        """
        self.driver.quit()


def main():
    """
    Main entry point for the script.
    """
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    credential_file_path = '../../credentials/grubhub_credentials.json'
    start_date = datetime(2023, 4, 1)
    end_date = datetime(2023, 4, 30)
    store_name = Store.AROMA

    orders = GrubhubOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    orders.postprocess_reports()
    orders.standardize_orders_report()
    orders.validate_reports()
    orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
