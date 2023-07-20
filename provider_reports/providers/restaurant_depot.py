import glob
import os
import shutil
import time
from datetime import datetime

import pandas as pd
import retrying
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from provider_reports.providers.base_provider import OrdersProvider
from provider_reports.utils.constants import Store, RAW_REPORTS_PATH, Provider, ReportType, Extensions, \
    AMECI_FWD_EMAIL, AROMA_FWD_EMAIL
from provider_reports.utils.utils import get_chrome_options, send_email
from provider_reports.utils.validation_utils import ValidationUtils


class RestaurantDepotReceipts(OrdersProvider):
    """
    RestaurantDepotReceipts receipts provider.

    This class implements the OrdersProvider interface for the Restaurant Depot provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.
    """

    PROVIDER = Provider.RESTAURANT_DEPOT
    LOGIN_URL = "https://member.restaurantdepot.com/customer/account/login/"
    ORDER_FILENAME_PATTERN = "Receipt*.csv"

    def __init__(self, credential_file_path, start_date, end_date, store_name):
        """
        Initialize the RestaurantDepotReceipts provider.
        This provider is to collect receipts for groceries.

        Args:
            credential_file_path (str): The path to the credential file.
            start_date (datetime.datetime): The start date for retrieving orders.
            end_date (datetime.datetime): The end date for retrieving orders.
            store_name (Store): The name of the store associated with the provider.
        """
        super().__init__(credential_file_path, start_date, end_date, store_name)

        self.driver = None
        self.wait = None
        self.number_of_invoice_rows = 0

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def login(self):
        """
        Perform the login process for the RestaurantDepot provider.
        """
        self.driver = webdriver.Chrome(options=get_chrome_options())
        self.wait = WebDriverWait(self.driver, 30)

        self.driver.get(RestaurantDepotReceipts.LOGIN_URL)
        username_input = self.wait.until(EC.presence_of_element_located((By.ID, "email")))
        username_input.clear()
        username_input.send_keys(self.username)
        password_input = self.wait.until(EC.presence_of_element_located((By.ID, "pass")))
        password_input.clear()
        password_input.send_keys(self.password)
        sign_in_button = self.wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(.,'Log in')]")))
        sign_in_button.click()

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        start_time = time.time()
        # go to receipts tab
        self.driver.get('https://member.restaurantdepot.com/receipts')
        # Find all the rows containing product items
        rows = self.driver.find_elements(By.CSS_SELECTOR, ".products-list .products.list.items.product-items > li")
        self.number_of_invoice_rows = len(rows)
        # Iterate over each row
        for row in rows:
            # Find the download button for each row & click it to invoke
            download_button = row.find_element(By.CSS_SELECTOR, ".download-receipt")
            download_button.click()

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
            print(f"Downloaded file(s) for invoice record: {downloaded_files}")
            self.downloaded_files.extend(downloaded_files)
            start_time = time.time()

        print(f"Downloaded file(s): {self.downloaded_files}")

    def preprocess_reports(self):
        """
        Preprocess the retrieved orders from the RestaurantDepot provider.
        """
        pass

    def postprocess_reports(self):
        """
        Postprocess the retrieved orders from the RestaurantDepot provider. Only expect one file.
        """
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        for downloaded_file in self.downloaded_files:
            processed_file_initial = self.create_processed_filename(ReportType.INVOICES, Extensions.CSV)
            downloaded_file_short_name = downloaded_file.lower().split('/')[-1]
            processed_file = processed_file_initial.strip('.' + Extensions.CSV) + f'_{downloaded_file_short_name}'
            shutil.copy(downloaded_file, processed_file)
            self.processed_files.append(processed_file)
            print(f'Saved {self.store_name} invoices to: {processed_file}')

        print(f"Processed file(s): {self.processed_files}")

    def validate_reports(self):
        """
        Perform report validation specific to the RestaurantDepot provider.
        """
        ValidationUtils.validate_processed_files_count(self.processed_files, self.number_of_invoice_rows)
        ValidationUtils.validate_downloaded_files_count(self.downloaded_files, self.number_of_invoice_rows)
        ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.CSV)
        ValidationUtils.validate_downloaded_files_extension(self.downloaded_files, Extensions.CSV)
        print("Report validation successful")

    def standardize_orders_report(self):
        pass

    def upload_reports(self):
        """
        Send the reports to the forwarded xtraChef email
        """
        subject = f'{self.PROVIDER.value.title()} receipts for {self.store_name} for past 30 days'
        body = f'The attachments are automated receipts pulled from {self.PROVIDER.value.title()} site.'
        recipients = [AMECI_FWD_EMAIL] if self.store == Store.AMECI else [AROMA_FWD_EMAIL]
        send_email(subject, body, recipients, attachments=self.processed_files)

    def quit(self):
        """
        Quit the RestaurantDepot provider session.
        """
        self.driver.quit()


def main():
    """
    Main entry point for the script.
    """
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    credential_file_path = '../credentials/restaurant_depot_credentials.json'
    start_date = datetime(2023, 4, 1)
    end_date = datetime(2023, 4, 30)
    store_name = Store.AROMA

    orders = RestaurantDepotReceipts(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    orders.postprocess_reports()
    orders.validate_reports()
    orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
