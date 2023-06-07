import datetime
import os
import shutil
import time

import pandas as pd
import requests
import retrying
from selenium import webdriver
from selenium.common import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from provider_reports.providers.base_provider import OrdersProvider
from provider_reports.utils.constants import Store, RAW_REPORTS_PATH, Provider, ReportType, Extensions
from provider_reports.utils.utils import get_chrome_options
from provider_reports.utils.validation_utils import ValidationUtils


class SliceOrders(OrdersProvider):
    """
    Slice orders provider.

    This class implements the OrdersProvider interface for the Slice provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.

    Note, slice max allows one month at a time for a report to be pulled.
    """

    PROVIDER = Provider.SLICE
    LOGIN_URL = "https://owners.slicelife.com/"
    ORDER_FILENAME_PATTERN = "oar-full-*.pdf"

    def __init__(self, credential_file_path, start_date, end_date, store_name):
        """
        Initialize the SliceOrders provider.

        Args:
            credential_file_path (str): The path to the credential file.
            start_date (datetime.datetime): The start date for retrieving orders.
            end_date (datetime.datetime): The end date for retrieving orders.
            store_name (Store): The name of the store associated with the provider.
        """
        super().__init__(credential_file_path, start_date, end_date, store_name)

        self.driver = webdriver.Chrome(options=get_chrome_options())
        self.wait = WebDriverWait(self.driver, 60)

    def get_store_id(self):
        store_ids = {
            Store.AROMA: 15639,
            Store.AMECI: 3057
        }
        return store_ids[self.store]

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def login(self):
        """
        Perform the login process for the Slice provider.
        """
        self.driver.get(SliceOrders.LOGIN_URL)
        username_input = self.wait.until(EC.presence_of_element_located((By.ID, "username")))
        username_input.clear()
        username_input.send_keys(self.username)
        password_input = self.wait.until(EC.presence_of_element_located((By.ID, "password")))
        password_input.clear()
        password_input.send_keys(self.password)
        self.driver.find_element(By.NAME, "action").click()

    # @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        """
        Retrieve orders from the Slice provider.
        """
        start_time = time.time()
        formatted_start_date = self.start_date_dt.strftime("%A, %B {day}, %Y".format(day=self.start_date_dt.day))
        formatted_end_date = self.end_date_dt.strftime("%A, %B {day}, %Y".format(day=self.end_date_dt.day))
        report_date_range = f'{self.start_date} - {self.end_date}'

        report_url = f'{self.LOGIN_URL}shops/{self.get_store_id()}/order-activity-reports'
        self.driver.get(report_url)
        reports_input = self.wait.until(EC.presence_of_element_located((By.ID, "show-basic-tax-report-form")))
        reports_input.click()
        start_date_btn = self.wait.until(EC.presence_of_element_located((By.ID, "report-start-date")))
        start_date_btn.click()
        start_back_button = self.driver.find_element(By.CSS_SELECTOR,
                                 ".DayPickerNavigation_leftButton__horizontalDefault > .DayPickerNavigation_svg__horizontal")

        # if the start_element is not set or not visible then click back
        start_element = None
        while not start_element:
            try:
                ele = self.driver.find_element(By.XPATH, f'//td[contains(@aria-label, "{formatted_start_date}")]')
                if ele.is_displayed():
                    start_element = ele
                    start_element.click()
                    break
            except NoSuchElementException:
                print('start_element not found or not visible')
                start_element = None
            start_back_button.click()
            time.sleep(1)

        end_date_btn = self.wait.until(EC.presence_of_element_located((By.ID, "report-end-date")))
        end_date_btn.click()
        end_back_button = self.driver.find_element(By.CSS_SELECTOR,
                                 ".DayPickerNavigation_leftButton__horizontalDefault > .DayPickerNavigation_svg__horizontal")

        # if the end_element is not set or not visible then click back
        end_element = None
        while not end_element:
            try:
                ele = self.driver.find_element(By.XPATH, f'//td[contains(@aria-label, "{formatted_end_date}")]')
                if ele.is_displayed():
                    end_element = ele
                    end_element.click()
                    break
            except NoSuchElementException:
                print('end_element not found or not visible')
                end_element = None
            end_back_button.click()
            time.sleep(1)

        self.driver.find_element(By.XPATH, "//button[@type=\'submit\']").click()
        # arbitrary sleep as it takes some time to get the reports to be downloaded - says Pending first
        time.sleep(10)

        # Find all the rows in the table
        rows = self.driver.find_elements(By.XPATH, '//tr[contains(@class, "styles_row")]')
        pdf_url = None
        download_link = None

        for row in rows:
            # Find the date range span within the row
            date_range_span = row.find_element(By.XPATH, './/span[contains(@class, "styles_dateRange")]')
            row_date_range = date_range_span.text.strip()
            if report_date_range == row_date_range:
                try:
                    # Find the "Pending" element within the row if it exists
                    pending_element = row.find_element(By.XPATH, './/span[contains(text(), "Pending")]')
                    # Wait until the "Pending" element is no longer visible
                    if pending_element.is_displayed():
                        print('waiting for pending element to be removed')
                        self.wait.until(EC.invisibility_of_element(pending_element))
                except TimeoutException as te:
                    print('timed out waiting for pending to become an svg. refreshing page\n' + str(te))
                    self.driver.refresh()
                    self.wait.until(EC.presence_of_element_located(row))
                except NoSuchElementException:
                    # Handle the case when the "Pending" element is not found
                    print('no pending label found')

                try:
                    # Find the download link within the row
                    download_link = row.find_element(By.TAG_NAME, 'svg')
                    pdf_url = row.find_element(By.TAG_NAME, 'a').get_attribute('href')
                    print(pdf_url)
                except NoSuchElementException as ex:
                    print(ex)
                break

        # if cannot get url from the href of object then click download button to get url
        if not pdf_url and download_link:
            download_link.click()
            time.sleep(5)
            self.driver.switch_to.window(self.driver.window_handles[-1])
            pdf_url = self.driver.current_url

        # Use requests library to download the file
        response = requests.get(pdf_url)

        # Specify the file path to save the downloaded file
        file_path = os.path.join(RAW_REPORTS_PATH, f'slice_{int(start_time)}.pdf')

        # Save the file
        with open(file_path, 'wb') as file:
            file.write(response.content)

        self.downloaded_files.append(file_path)
        print(f"Downloaded file(s): {self.downloaded_files}")

    def preprocess_reports(self):
        """
        Preprocess the retrieved orders from the Slice provider.
        """
        pass

    def postprocess_reports(self):
        """
        Postprocess the retrieved orders from the Slice provider. Only expect one PDF file.
        """
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        for downloaded_file in self.downloaded_files:
            processed_file = self.create_processed_filename(ReportType.ORDERS, Extensions.PDF)
            shutil.copy(downloaded_file, processed_file)
            self.processed_files.append(processed_file)
            print(f'Saved {self.store_name} orders to: {processed_file}')

    def validate_reports(self):
        """
        Perform report validation specific to the Slice provider.
        """
        ValidationUtils.validate_processed_files_count(self.processed_files, 1)
        ValidationUtils.validate_downloaded_files_count(self.downloaded_files, 1)
        ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.PDF)
        ValidationUtils.validate_downloaded_files_extension(self.downloaded_files, Extensions.PDF)
        print("Report validation successful")

    def upload_reports(self):
        """
        Upload the processed report to a remote location specific to the Slice provider.
        """
        # TODO: Implement report uploading logic for Slice
        pass

    def quit(self):
        """
        Quit the Slice provider session.
        """
        self.driver.quit()


def main():
    """
    Main entry point for the script.
    """
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    credential_file_path = '../credentials/slice_credentials.json'
    start_date = datetime.datetime(2023, 1, 1)
    end_date = datetime.datetime(2023, 1, 28)
    store_name = Store.AMECI

    orders = SliceOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    orders.postprocess_reports()
    orders.validate_reports()
    orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
