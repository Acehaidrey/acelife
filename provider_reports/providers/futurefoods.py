import glob
import os
import re
import shutil
from datetime import datetime
import time

import pandas as pd
import retrying
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from provider_reports.providers.base_provider import OrdersProvider
from provider_reports.utils.constants import Store, RAW_REPORTS_PATH, Provider, ReportType, Extensions
from provider_reports.utils.utils import get_chrome_options
from provider_reports.utils.validation_utils import ValidationUtils


def get_date_from_aria_label(element):
    date_pattern = r"(?:Choose\s)(.*?)(?:\sas)"
    aria_label = element.get_attribute('aria-label')
    if not aria_label:
        return
    match = re.search(date_pattern, aria_label)
    if match:
        date_string = match.group(1)
        dt = datetime.strptime(date_string, "%A, %B %d, %Y")
        return dt


class FutureFoodsOrders(OrdersProvider):
    """
    FutureFoods orders provider.

    This class implements the OrdersProvider interface for the FutureFoods provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.
    """

    PROVIDER = Provider.FUTURE_FOODS
    LOGIN_URL = "https://manager.tryotter.com/login"
    ORDER_FILENAME_PATTERN = "transactions_export_*.csv"

    def __init__(self, credential_file_path, start_date, end_date, store_name):
        """
        Initialize the FutureFoodsOrders provider.
        This provider has few orders but still want to account for them.

        Args:
            credential_file_path (str): The path to the credential file.
            start_date (datetime.datetime): The start date for retrieving orders.
            end_date (datetime.datetime): The end date for retrieving orders.
            store_name (Store): The name of the store associated with the provider.
        """
        super().__init__(credential_file_path, start_date, end_date, store_name)

        self.driver = webdriver.Chrome(options=get_chrome_options())
        self.wait = WebDriverWait(self.driver, 300)

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def login(self):
        """
        Perform the login process for the FutureFoods provider.
        """
        self.driver.get(FutureFoodsOrders.LOGIN_URL)
        username_input = self.wait.until(EC.presence_of_element_located((By.NAME, "email")))
        username_input.clear()
        username_input.send_keys(self.username)
        password_input = self.wait.until(EC.presence_of_element_located((By.NAME, "password")))
        password_input.clear()
        password_input.send_keys(self.password)
        self.wait.until(EC.presence_of_element_located((By.XPATH, "//button/div[contains(.,'Sign in')]"))).click()

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        start_time = time.time()
        formatted_start_date = self.start_date_dt.strftime("%A, %B {day}, %Y".format(day=self.start_date_dt.day))
        formatted_end_date = self.end_date_dt.strftime("%A, %B {day}, %Y".format(day=self.end_date_dt.day))
        # go to virtual brands endpoint where reporting exists
        self.driver.get('https://manager.tryotter.com/virtual-brands/accounting/payments')
        button = self.wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Download CSV')]")))
        button.click()
        input_field = self.wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Select dates']")))
        input_field.click()

        # have the calendar modal opened
        # identify the back and forward button elements
        buttons = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="button"][class*="DayPickerNavigation_button"]')
        back_button, forward_button = None, None
        for btn in buttons:
            if btn:
                aria_label = btn.get_attribute("aria-label") or ''
                if "previous month" in aria_label.lower():
                    back_button = btn.find_element(By.TAG_NAME, 'svg')
                if "next month" in aria_label.lower():
                    forward_button = btn.find_element(By.TAG_NAME, 'svg')

        # get active day elements
        elements = self.driver.find_elements(By.XPATH,
                                        '//td[contains(@class, "CalendarDay") and @role="button" and @aria-disabled="false"]')

        # if the start_element is not set or not visible then click back
        start_element = None
        while not start_element:
            try:
                ele = self.driver.find_element(By.XPATH, f'//td[contains(@aria-label, "{formatted_start_date}")]')
                if ele.is_displayed():
                    start_element = ele
                    break
            except Exception as e:
                print('start_element not found or not visible\n' + str(e))
                start_element = None
            back_button.click()

        # select the start_date
        start_element.click()

        end_element = None
        while not end_element:
            try:
                ele = self.driver.find_element(By.XPATH, f'//td[contains(@aria-label, "{formatted_end_date}")]')
                if ele.is_displayed():
                    end_element = ele
                    break
            except Exception as e:
                print('end_element not found or not visible\n' + str(e))
                end_element = None
            forward_button.click()

        # select the end_date now
        end_element.click()

        # click on input button again to remove the calendar hover over
        input_field.click()

        # click the download button
        download_buttons = self.driver.find_elements(By.XPATH,
                                              '//button[contains(., "Download") and @data-testid="op-button"]')
        download_button = download_buttons[-1]
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
        print(f"Downloaded file(s): {downloaded_files}")
        self.downloaded_files.extend(downloaded_files)

    def preprocess_reports(self):
        """
        Preprocess the retrieved orders from the FutureFoods provider.
        """
        pass

    def postprocess_reports(self):
        """
        Postprocess the retrieved orders from the FutureFoods provider. Only expect one file.
        """
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        for downloaded_file in self.downloaded_files:
            processed_file = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV)
            shutil.copy(downloaded_file, processed_file)
            self.processed_files.append(processed_file)
            print(f'Saved {self.store_name} virtual store orders to: {processed_file}')

    def validate_reports(self):
        """
        Perform report validation specific to the FutureFoods provider.
        """
        ValidationUtils.validate_processed_files_count(self.processed_files, 1)
        ValidationUtils.validate_downloaded_files_count(self.downloaded_files, 1)
        ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.CSV)
        ValidationUtils.validate_downloaded_files_extension(self.downloaded_files, Extensions.CSV)
        ValidationUtils.validate_processed_files_date_range(
            self.processed_files, self.start_date, self.end_date, 'Date', '%Y-%m-%d')

        print("Report validation successful")

    def upload_reports(self):
        """
        Upload the processed report to a remote location specific to the FutureFoods provider.
        """
        # TODO: Implement report uploading logic for FutureFoods
        pass

    def quit(self):
        """
        Quit the FutureFoods provider session.
        """
        self.driver.quit()


def main():
    """
    Main entry point for the script.
    """
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    credential_file_path = '../credentials/future_foods_credentials.json'
    start_date = datetime(2023, 4, 1)
    end_date = datetime(2023, 4, 30)
    store_name = Store.AROMA

    orders = FutureFoodsOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    orders.postprocess_reports()
    orders.validate_reports()
    orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
