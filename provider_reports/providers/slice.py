import datetime
import glob
import os
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


class SliceOrders(OrdersProvider):
    """
    Slice orders provider.

    This class implements the OrdersProvider interface for the Slice provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.
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
        self.wait = WebDriverWait(self.driver, 30)

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
        # self.driver.find_element(By.CSS_SELECTOR, ".react-select__single-value").click()
        # continue_btn = self.wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(.,\'Continue\')]")))
        # continue_btn.click()

    # @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        """
        Retrieve orders from the Slice provider.
        """
        start_time = time.time()
        formatted_start_date = self.start_date_dt.strftime("%A, %B {day}, %Y".format(day=self.start_date_dt.day))
        formatted_end_date = self.end_date_dt.strftime("%A, %B {day}, %Y".format(day=self.end_date_dt.day))
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
                    break
            except Exception as e:
                print('start_element not found or not visible\n' + str(e))
                start_element = None
            start_back_button.click()

        # select the start_date
        start_element.click()

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
                    break
            except Exception as e:
                print('end_element not found or not visible\n' + str(e))
                end_element = None
            end_back_button.click()

        # select the end_date
        end_element.click()

        self.driver.find_element(By.XPATH, "//button[@type=\'submit\']").click()

        time.sleep(10)

        # print(f"Downloaded file(s): {downloaded_files}")
        # self.downloaded_files.extend(downloaded_files)

    def preprocess_reports(self):
        """
        Preprocess the retrieved orders from the Slice provider.
        """
        pass

    def postprocess_reports(self):
        """
        Postprocess the retrieved orders from the Slice provider. Only expect one file.
        The output file has both stores info in there, we generate two separate csvs.
        """
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        for downloaded_file in self.downloaded_files:
            df = pd.read_excel(downloaded_file)
            df = df.iloc[:-1]
            df['Payment Type'] = 'Credit'

            for store in [Store.AROMA.value, Store.AMECI.value]:
                match_df = df[df['Store Name'].str.contains(store, case=False)]
                full_match_fp = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV, store=store)
                match_df.to_csv(full_match_fp, index=False)
                print(f'Saved {store} orders to: {full_match_fp}')
                self.processed_files.append(full_match_fp)

    def validate_reports(self):
        """
        Perform report validation specific to the Slice provider.
        """
        ValidationUtils.validate_processed_files_count(self.processed_files, 2)
        ValidationUtils.validate_downloaded_files_count(self.downloaded_files, 1)
        ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.CSV)
        ValidationUtils.validate_downloaded_files_extension(self.downloaded_files, Extensions.EXCEL)
        ValidationUtils.validate_processed_files_date_range(
            self.processed_files, self.start_date_dt.strftime('%m/%d/%Y'), self.end_date_dt.strftime('%m/%d/%Y'),
            'Event Date', '%Y-%m-%d %H:%M:%S')

        downloaded_df = pd.read_excel(self.downloaded_files[0])
        processed_record_count = 0
        for processed_file in self.processed_files:
            processed_df = pd.read_csv(processed_file)
            processed_record_count += len(processed_df)

        if not (abs(len(downloaded_df) - processed_record_count) == 1):
            raise AssertionError(f'Number of rows in the downloaded file does not match the processed file '
                                 f'{len(downloaded_df)}, {processed_record_count}')

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
    start_date = datetime.datetime(2023, 4, 1)
    end_date = datetime.datetime(2023, 4, 30)
    store_name = Store.AMECI

    orders = SliceOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    # orders.postprocess_reports()
    # orders.validate_reports()
    # orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
