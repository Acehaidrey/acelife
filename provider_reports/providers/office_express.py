import datetime
import glob
import os
import time

import pandas as pd
import retrying
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from provider_reports.providers.base_provider import OrdersProvider
from provider_reports.schema.schema import TransactionRecord
from provider_reports.utils.constants import Store, RAW_REPORTS_PATH, Provider, \
    ReportType, Extensions, TAX_RATE, DATA_PATH_RAW
from provider_reports.utils.utils import get_chrome_options, \
    standardize_order_report_setup
from provider_reports.utils.validation_utils import ValidationUtils


class FoodjaOrders(OrdersProvider):
    """
    Foodja orders provider.

    This class implements the OrdersProvider interface for the Foodja provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.
    """

    PROVIDER = Provider.OFFICE_EXPRESS
    LOGIN_URL = "https://foodja.com/"
    ORDER_FILENAME_PATTERN = "oex-orders*.csv"

    def __init__(self, credential_file_path, start_date, end_date, store_name):
        """
        Initialize the FoodjaOrders/OfficeExpressOrders provider.
        Office Express is historic name where Foodja is new name.

        Args:
            credential_file_path (str): The path to the credential file.
            start_date (datetime.datetime): The start date for retrieving orders.
            end_date (datetime.datetime): The end date for retrieving orders.
            store_name (Store): The name of the store associated with the provider.
        """
        super().__init__(credential_file_path, start_date, end_date, store_name)

        self.driver = webdriver.Chrome(options=get_chrome_options())
        self.wait = WebDriverWait(self.driver, 10)

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def login(self):
        """
        Perform the login process for the Foodja provider.
        """
        self.driver.get(FoodjaOrders.LOGIN_URL)
        login_link = self.wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "LOG IN")))
        login_link.click()
        username_input = self.wait.until(EC.presence_of_element_located((By.ID, "username")))
        username_input.clear()
        username_input.send_keys(self.username)
        self.driver.find_element(By.ID, "btnNext").click()
        password_input = self.wait.until(EC.presence_of_element_located((By.ID, "password")))
        password_input.clear()
        password_input.send_keys(self.password)
        self.driver.find_element(By.CSS_SELECTOR, ".on").click()
        self.driver.find_element(By.ID, "btnLogin").click()

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        """
        Retrieve orders from the Foodja provider.
        """
        start_time = time.time()
        order_input = self.wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Orders")))
        order_input.click()
        self.driver.find_element(By.LINK_TEXT, "Completed Orders").click()
        start_element = self.wait.until(EC.presence_of_element_located((By.XPATH, "//input[@name='startDate']")))
        start_element.clear()
        start_element.send_keys(self.start_date)
        start_element.send_keys(Keys.ENTER)
        end_element = self.wait.until(EC.presence_of_element_located((By.XPATH, "//input[@name='endDate']")))
        end_element.clear()
        end_element.send_keys(self.end_date)
        end_element.send_keys(Keys.ENTER)
        self.driver.find_element(By.CSS_SELECTOR, ".product-green").click()
        self.wait.until(EC.presence_of_element_located((By.LINK_TEXT, "EXPORT TO EXCEL"))).click()

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
        Preprocess the retrieved orders from the Foodja provider.
        """
        pass

    def postprocess_reports(self):
        """
        Postprocess the retrieved orders from the Foodja provider. Only expect one file.
        The output file has both stores info in there, we generate two separate csvs.
        """
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        for downloaded_file in self.downloaded_files:
            df = pd.read_csv(downloaded_file)
            df['Payment Type'] = 'Credit'
            df = df.sort_values('Delivery Date', ascending=True)

            for store in [Store.AROMA.value, Store.AMECI.value]:
                match_df = df[df['Location'].str.contains(store, case=False)]
                full_match_fp = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV, store=store.lower())
                match_df.to_csv(full_match_fp, index=False)
                print(f'Saved {store} orders to: {full_match_fp}')
                self.processed_files.append(full_match_fp)

    def standardize_orders_report(self):
        """
        Standardize report to conform to expected table format.
        Manually calculate taxes withheld and commission as 30% of subtotal.
        """
        rename_map = {
            'Order #': TransactionRecord.TRANSACTION_ID,
            'Delivery Date': TransactionRecord.ORDER_DATE,
            'Payment Type': TransactionRecord.PAYMENT_TYPE,
            'Food Total': TransactionRecord.SUBTOTAL,
            'Check Date': TransactionRecord.NOTES
        }
        # Get transaction file
        orders_file = [f for f in self.processed_files if self.store.value in f][0]
        df = standardize_order_report_setup(orders_file, rename_map, self.PROVIDER, self.store)

        # Calculate taxes withheld manually
        df[TransactionRecord.TAX_WITHHELD] = (df[TransactionRecord.SUBTOTAL] * TAX_RATE).round(2)
        # Calculate commission as 30% of order total
        df[TransactionRecord.COMMISSION_FEE] = -(df[TransactionRecord.SUBTOTAL] * 0.3).round(2)
        # Rewrite the notes column
        df[TransactionRecord.NOTES] = 'check date: ' + df[TransactionRecord.NOTES]
        # calculate before/after fees and payout
        TransactionRecord.calculate_total_before_fees(df)
        TransactionRecord.calculate_total_after_fees(df)
        TransactionRecord.calculate_payout(df)

        # Write the transformed data to a new CSV file (csv and parquet)
        raw_data_filename = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV, parent_path=DATA_PATH_RAW)
        df.to_csv(raw_data_filename, index=False)
        self.data_files.append(raw_data_filename)
        print(f'Saved {self.store_name} data orders to: {raw_data_filename}. Based off of processed file: {orders_file}.')

    def validate_reports(self):
        """
        Perform report validation specific to the Foodja provider.
        """
        ValidationUtils.validate_processed_files_count(self.processed_files, 2)
        ValidationUtils.validate_downloaded_files_count(self.downloaded_files, 1)
        ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.CSV)
        ValidationUtils.validate_downloaded_files_extension(self.downloaded_files, Extensions.CSV)
        ValidationUtils.validate_processed_files_date_range(
            self.processed_files, self.start_date, self.end_date, 'Delivery Date', '%m/%d/%Y')

        downloaded_df = pd.read_csv(self.downloaded_files[0])
        processed_record_count = 0
        for processed_file in self.processed_files:
            processed_df = pd.read_csv(processed_file)
            processed_record_count += len(processed_df)
        if len(downloaded_df) != processed_record_count:
            raise AssertionError("Number of rows in the downloaded file does not match the processed file")

        # data file checking
        ValidationUtils.validate_data_files_count(self.data_files, 1)
        orders_file = [f for f in self.processed_files if self.store.value in f][0]
        ValidationUtils.validate_all_data_file_checks(self.data_files[0], orders_file)

        print("Report validation successful")

    def upload_reports(self):
        """
        Upload the processed report to a remote location specific to the Foodja provider.
        """
        self.write_parquet_data()

    def quit(self):
        """
        Quit the Foodja provider session.
        """
        self.driver.quit()


def main():
    """
    Main entry point for the script.
    """
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    credential_file_path = '../credentials/office_express_credentials.json'
    start_date = datetime.datetime(2023, 3, 1)
    end_date = datetime.datetime(2023, 3, 31)
    store_name = Store.AROMA

    orders = FoodjaOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    orders.postprocess_reports()
    # orders.processed_files = ['/Users/ahaidrey/Desktop/acelife/provider_reports/reports_processed/office_express_aroma_orders_03_01_2023_03_31_2023.csv', '/Users/ahaidrey/Desktop/acelife/provider_reports/reports_processed/office_express_ameci_orders_03_01_2023_03_31_2023.csv']
    orders.standardize_orders_report()
    orders.validate_reports()
    orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
