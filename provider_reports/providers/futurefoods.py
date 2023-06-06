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
        # self.wait.until(EC.visibility_of_element_located(buttons[0]))
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
        first_active_date_td = elements[0]
        last_active_date_td = elements[-1]
        if not first_active_date_td and last_active_date_td:
            raise Exception('No active day elements found')

        first_date = get_date_from_aria_label(first_active_date_td)
        last_date = get_date_from_aria_label(last_active_date_td)
        print(self.start_date_dt, first_date, first_active_date_td.get_attribute('aria-label'))
        print(self.end_date_dt, last_date, last_active_date_td.get_attribute('aria-label'))
        print(first_active_date_td.is_displayed())
        print(last_active_date_td.is_displayed())

        # debug html
        # Save the HTML source to a local file
        with open(os.path.join(RAW_REPORTS_PATH, 'futurefoods.html'), 'w+', encoding='utf-8') as file:
            file.write(self.driver.page_source)
            print(f"HTML source saved to '{os.path.join(RAW_REPORTS_PATH, 'futurefoods.html')}'")

        # if the first date is greater than start_date then we need to go back
        # if the start_element is not set or not visible then click back
        start_element = None  # first_date > self.start_date_dt
        while not start_element:
            elements = self.driver.find_elements(By.XPATH,
                                                 '//td[contains(@class, "CalendarDay") and @role="button" and @aria-disabled="false"]')
            # first_active_date_td = elements[0]
            # first_date = get_date_from_aria_label(first_active_date_td)
            try:
                ele = self.driver.find_element(By.XPATH, f'//td[contains(@aria-label, "{formatted_start_date}")]')
                print('found ele')
                print(ele.is_displayed())
                print(ele.get_attribute('aria-label'))
                print(ele.get_attribute('outerHTML'))
                if ele.is_displayed():
                    start_element = ele
            except Exception as e:
                print(e)
                print('start_element not found or not visible')
                start_element = None
            back_button.click()

        # select the start_date
        try:
            # start_element = self.driver.find_element(By.XPATH, f'//td[contains(@aria-label, "{formatted_start_date}")]')
            # print(start_element.get_attribute('innerHTML'))
            start_element.click()
            print('found matching element')
        except Exception as e:
            print('could not find start date')
            print(e)

        print('all elements')
        for ele in elements:
            try:
                print(ele.get_attribute('aria-label') + ' ' + str(ele.is_displayed()))
                al = ele.get_attribute('aria-label')
                formatted_start_date = self.start_date_dt.strftime("%A, %B {day}, %Y".format(day=self.start_date_dt.day))
                if formatted_start_date in al:
                    print(f'matching date for: {formatted_start_date} in {al}')
            except Exception:
                print('issue getting ele ' + str(ele))

        end_element = None
        while not end_element:  # last_date < self.end_date_dt
            # elements = self.driver.find_elements(By.XPATH,
            #                                      '//td[contains(@class, "CalendarDay") and @role="button" and @aria-disabled="false"]')
            # last_active_date_td = elements[-1]
            # last_date = get_date_from_aria_label(last_active_date_td)
            try:
                print('end date')
                ele = self.driver.find_element(By.XPATH, f'//td[contains(@aria-label, "{formatted_end_date}")]')
                print('found ele')
                print(ele.is_displayed())
                print(ele.get_attribute('aria-label'))
                print(ele.get_attribute('outerHTML'))
                if ele.is_displayed():
                    end_element = ele
            except Exception as e:
                print(e)
                print('start_element not found or not visible')
                end_element = None
            forward_button.click()

        # select the end_date now
        # end_element = self.driver.find_element(By.XPATH, f'//td[contains(@aria-label, "{formatted_end_date}")]')
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
            print(f'Saved {self.store_name} orders to: {processed_file}')

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
    # orders.postprocess_reports()
    # orders.validate_reports()
    # orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()


# curl -X POST -F 'client_id=M5VQfGY4x9BjyeOg2XqYQ7cp9xSiHZEp' -F 'client_secret=I7yiL6txSOB0vdR0goWb0PY6BTCphFKTJtE7jvWP' -F 'grant_type=client_credentials' -F "scope=business.receipts" "https://login.uber.com/oauth/v2/token"
