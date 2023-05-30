import fnmatch
import glob
import os
import time
import zipfile
from datetime import date

import pandas as pd
import retrying
from selenium import webdriver
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from provider_reports.providers.base_provider import OrdersProvider
from provider_reports.utils.constants import Store, RAW_REPORTS_PATH, PROCESSED_REPORTS_PATH, Provider, Extensions
from provider_reports.utils.utils import get_chrome_options
from provider_reports.utils.validation_utils import ValidationUtils


class MenufyOrders(OrdersProvider):
    """
    Menufy orders provider.

    This class implements the OrdersProvider interface for the Menufy provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.
    """

    PROVIDER = Provider.MENUFY
    LOGIN_URL = "https://manage.menufy.com/Account/LogOn"
    ORDER_FILENAME_PATTERN = "*Sales_Report_*.zip"
    CUSTOMER_EMAIL_PATTERN = "*Customer_Emails*"
    CUSTOMER_DELIVERY_PATTERN = "*Customer_Delivery_Addresses*"

    def __init__(self, credential_file_path, start_date, end_date, store_name):
        """
        Initialize the MenufyOrders provider.

        Args:
            credential_file_path (str): The path to the credential file.
            start_date (str): The start date for retrieving orders.
            end_date (str): The end date for retrieving orders.
            store_name (Store): The name of the store associated with the provider.
        """
        super().__init__(credential_file_path, start_date, end_date, store_name)

        self.order_files = None
        self.driver = webdriver.Chrome(options=get_chrome_options())
        self.wait = WebDriverWait(self.driver, 10)

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def login(self):
        """
        Perform the login process for the Menufy provider.
        """
        self.driver.get(MenufyOrders.LOGIN_URL)
        username_input = self.wait.until(EC.presence_of_element_located((By.ID, "UserEmail")))
        username_input.clear()
        username_input.send_keys(self.username)
        password_input = self.wait.until(EC.presence_of_element_located((By.ID, "Password")))
        password_input.clear()
        password_input.send_keys(self.password)
        login_link = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".login-buttons > .btn")))
        login_link.click()

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        """
        Retrieve orders from the Menufy provider.
        """
        start_time = time.time()

        navbar_dropdown = (By.CSS_SELECTOR, "#navbarDropdown > span")
        store_navbar_link = (By.LINK_TEXT, f'{self.store_name} Pizza & Pasta (Lake Forest, CA 92630)')
        reports_heading = (By.ID, "headingReports")
        combined_sales_report_link = (By.LINK_TEXT, "Combined Sales")

        # pick navbar to select restaurant
        self.wait.until(EC.presence_of_element_located(navbar_dropdown)).click()
        self.wait.until(EC.presence_of_element_located(store_navbar_link)).click()
        # go to sales reports side bar selection
        self.wait.until(EC.presence_of_element_located(reports_heading)).click()
        self.wait.until(EC.presence_of_element_located(combined_sales_report_link)).click()
        # pass in the date range and submit report for downloading
        date_range_element = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".date-range")))
        date_range_element.clear()
        date_range_element.send_keys(f"{self.start_date} - {self.end_date}")
        date_range_element.send_keys(Keys.ENTER)
        # wait for the file to be downloaded
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

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_customers(self):
        start_time = time.time()

        navbar_dropdown = (By.CSS_SELECTOR, "#navbarDropdown > span")
        store_navbar_link = (By.LINK_TEXT, f'{self.store_name} Pizza & Pasta (Lake Forest, CA 92630)')
        reports_heading = (By.ID, "headingReports")
        customer_emails_report_link = (By.LINK_TEXT, "Customer Emails")
        delivery_addresses_report_link = (By.LINK_TEXT, "Delivery Addresses")
        export_button = (By.ID, "export")

        # pick navbar to select restaurant
        self.wait.until(EC.presence_of_element_located(navbar_dropdown)).click()
        self.wait.until(EC.presence_of_element_located(store_navbar_link)).click()
        # go to sales reports side bar selection
        self.wait.until(EC.presence_of_element_located(reports_heading)).click()
        self.wait.until(EC.presence_of_element_located(customer_emails_report_link)).click()
        self.wait.until(EC.presence_of_element_located(export_button)).click()
        # Wait for the file to be downloaded
        email_file_pattern = os.path.join(RAW_REPORTS_PATH, self.CUSTOMER_EMAIL_PATTERN)
        self.wait.until(lambda driver: any(
            os.stat(file_path).st_ctime > start_time
            for file_path in glob.glob(email_file_pattern)
        ))
        self.wait.until(EC.presence_of_element_located(delivery_addresses_report_link)).click()
        self.wait.until(EC.presence_of_element_located(export_button)).click()
        # Wait for the file to be downloaded
        delivery_file_pattern = os.path.join(RAW_REPORTS_PATH, self.CUSTOMER_DELIVERY_PATTERN)
        self.wait.until(lambda driver: any(
            os.stat(file_path).st_ctime > start_time
            for file_path in glob.glob(delivery_file_pattern)
        ))
        # Get the downloaded file(s) that match the condition
        downloaded_files = [
            file_path
            for file_path in glob.glob(email_file_pattern)
            if os.stat(file_path).st_ctime > start_time
        ] + [
            file_path
            for file_path in glob.glob(delivery_file_pattern)
            if os.stat(file_path).st_ctime > start_time
        ]
        print(f"Downloaded file(s): {downloaded_files}")
        self.downloaded_files.extend(downloaded_files)

    def preprocess_reports(self):
        """
        Preprocess the retrieved orders from the Menufy provider.
        """
        pass

    def postprocess_reports(self):
        """
        Postprocess the retrieved orders from the Menufy provider.
        The sales report is a zip that can have 1 or 2 files that we will join.
        We will unpack and then merge them into a single csv.
        The customer reports are two separate csvs. We will keep separate and
        simply rename them for the time being, adding them to our processed list.
        """
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        tday = date.today().strftime("%m_%d_%Y")

        self.order_files = []

        for downloaded_file in self.downloaded_files:
            if fnmatch.fnmatch(downloaded_file, self.ORDER_FILENAME_PATTERN):
                full_filename = self.create_processed_filename('orders', Extensions.CSV)
                unpacked_zip_dir = downloaded_file.strip('.' + Extensions.ZIP)
                if not os.path.exists(unpacked_zip_dir):
                    os.mkdir(unpacked_zip_dir)
                # Unpack the ZIP file
                with zipfile.ZipFile(downloaded_file, "r") as zip_ref:
                    zip_ref.extractall(unpacked_zip_dir)

                instore_df = pd.DataFrame()
                prepaid_df = pd.DataFrame()
                for filename in os.listdir(unpacked_zip_dir):
                    old_file_path = os.path.join(unpacked_zip_dir, filename)
                    self.order_files.append(old_file_path)
                    if os.path.isfile(old_file_path):
                        if 'paidonline' in old_file_path.replace(' ', '').lower():
                            prepaid_df = pd.read_csv(old_file_path)
                            prepaid_df = prepaid_df.iloc[:-1]
                            prepaid_df['Payment Type'] = 'Credit'
                        if 'paidin-store' in old_file_path.replace(' ', '').lower():
                            instore_df = pd.read_csv(old_file_path)
                            instore_df = instore_df.iloc[:-1]
                            instore_df['Payment Type'] = 'Cash'
                # search and processed both files. if can merge, merge, else set to whichever not null
                if not instore_df.empty and not prepaid_df.empty:
                    combined_df = pd.merge(instore_df, prepaid_df, how='outer').fillna(0)
                else:
                    combined_df = instore_df if not instore_df.empty else prepaid_df
                if not combined_df.empty:
                    combined_df.to_csv(full_filename, index=False)
                    self.processed_files.append(full_filename)
                    print(f'Saved {self.store_name} orders to: {full_filename}')
            elif fnmatch.fnmatch(downloaded_file, self.CUSTOMER_EMAIL_PATTERN):
                new_filename = f'menufy_{self.store_name.lower()}_customer_emails_{tday}.csv'
                full_filename = os.path.join(PROCESSED_REPORTS_PATH, new_filename)
                df = pd.read_csv(downloaded_file)
                df.to_csv(full_filename, index=False)
                self.processed_files.append(full_filename)
            elif fnmatch.fnmatch(downloaded_file, self.CUSTOMER_DELIVERY_PATTERN):
                new_filename = f'menufy_{self.store_name.lower()}_customer_delivery_addresses_{tday}.csv'
                full_filename = os.path.join(PROCESSED_REPORTS_PATH, new_filename)
                df = pd.read_csv(downloaded_file)
                df.to_csv(full_filename, index=False)
                self.processed_files.append(full_filename)
        print(f'Menufy Processed Reports: {self.processed_files}')

    def validate_reports(self):
        """
        Perform report validation specific to the Menufy provider.
        """
        ValidationUtils.validate_processed_files_count(self.processed_files, 3)
        ValidationUtils.validate_downloaded_files_count(self.downloaded_files, 3)
        ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.CSV)

        customer_files = [rep for rep in self.downloaded_files if 'Customer' in rep]
        ValidationUtils.validate_downloaded_files_extension(customer_files, Extensions.CSV)
        order_files = [rep for rep in self.downloaded_files if rep.endswith(Extensions.ZIP)]
        ValidationUtils.validate_downloaded_files_extension(order_files, Extensions.ZIP)

        ValidationUtils.validate_processed_files_date_range(
            [f for f in self.processed_files if 'orders' in f], self.start_date, self.end_date, 'Date', '%m/%d/%y')

        if len(self.order_files) > 2:
            raise AssertionError(f"Expected up to 2 order file, but found {len(self.order_files)}")
        ValidationUtils.validate_downloaded_files_extension(self.order_files, Extensions.CSV)

        # add check on the combination of the total number of records in each csv matches our combined minus 2
        processed_len = 0
        for processed_file in self.processed_files:
            if 'orders' in processed_file:
                processed_df = pd.read_csv(processed_file)
                processed_len = len(processed_df)
        order_len = 0
        for order_file in self.order_files:
            order_df = pd.read_csv(order_file)
            order_len += len(order_df)

        if abs(order_len - processed_len) == 2:
            raise AssertionError(f'Number of records combined for order files dont match {order_len}, {processed_len}')

        print("Report validation successful")

    def upload_reports(self):
        """
        Upload the processed report to a remote location specific to the Menufy provider.
        """
        # TODO: Implement report uploading logic for Menufy
        pass

    def quit(self):
        """
        Quit the Menufy provider session.
        """
        self.driver.quit()


def main():
    """
    Main entry point for the script.
    """
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    credential_file_path = '../credentials/menufy_credentials.json'
    start_date = '01/01/2023'
    end_date = '01/31/2023'
    store_name = Store.AROMA

    orders = MenufyOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    orders.postprocess_reports()
    orders.validate_reports()
    orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
