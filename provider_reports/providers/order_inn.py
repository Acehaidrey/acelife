import datetime
import glob
import os
import time

import numpy as np
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
    ReportType, Extensions, TAX_RATE, DATA_PATH_RAW, PaymentType
from provider_reports.utils.utils import get_chrome_options, \
    standardize_order_report_setup
from provider_reports.utils.validation_utils import ValidationUtils


class OrderInnOrders(OrdersProvider):
    """
    Order Inn orders provider.

    This class implements the OrdersProvider interface for the Order Inn provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.

    OrderInn is a hotel partner that provides us additional orders but we collect
    the customer information and charge them directly. They pass on their fees to us.
    They charge the customer a higher price.
    This report is a summary of the transactions that we will treat each week value
    as a single transaction record to help align with the rest of the report.
    """

    PROVIDER = Provider.ORDER_INN
    LOGIN_URL = "https://orderinn.com/extranet/default.aspx"
    ORDER_FILENAME_PATTERN = "RestData*.csv"

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

        # self.driver = webdriver.Chrome(options=get_chrome_options())
        # self.wait = WebDriverWait(self.driver, 10)

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def login(self):
        """
        Perform the login process for the EZCater provider.
        """
        self.driver.get(OrderInnOrders.LOGIN_URL)
        username_input = self.wait.until(EC.presence_of_element_located((By.NAME, "Username")))
        username_input.clear()
        username_input.send_keys(self.username)
        password_input = self.wait.until(EC.presence_of_element_located((By.NAME, "Password")))
        password_input.clear()
        password_input.send_keys(self.password)
        self.driver.find_element(By.XPATH, "//input[@value=\'Submit\']").click()

    def preprocess_reports(self):
        pass

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        start_time = time.time()
        week56_button = self.wait.until(EC.presence_of_element_located((By.ID, "btn56Weeks")))
        week56_button.click()
        export_button = self.wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Export")))
        export_button.click()

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

        df = pd.read_csv(self.downloaded_files[0])
        df['DateWeekEnding'] = pd.to_datetime(df['DateWeekEnding'])

        # Filter rows based on the date range
        filtered_df = df[(df['DateWeekEnding'] >= self.start_date_dt) & (df['DateWeekEnding'] <= self.end_date_dt)]

        processed_file = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV)
        filtered_df.to_csv(processed_file, index=False)
        print(f'Saved {self.store_name} orders to: {processed_file}')
        self.processed_files.append(processed_file)

    def standardize_orders_report(self):
        rename_map = {
            'DateWeekEnding': TransactionRecord.ORDER_DATE,
            'OrderTotal': TransactionRecord.TOTAL_BEFORE_FEES,
            'AmountDue': TransactionRecord.COMMISSION_FEE,
            'Orders': 'order_count',
            'CSHangups': 'hangups'
        }
        df = standardize_order_report_setup(self.processed_files[0], rename_map, self.PROVIDER, self.store)
        # week ending date is always unique
        df[TransactionRecord.TRANSACTION_ID] =  df[TransactionRecord.ORDER_DATE].dt.strftime('%Y_%m_%d_%H_%M_%S')
        df[TransactionRecord.PAYMENT_TYPE] = PaymentType.CREDIT
        df[TransactionRecord.COMMISSION_FEE] = np.where(df[TransactionRecord.COMMISSION_FEE] > 0,
                                               -df[TransactionRecord.COMMISSION_FEE], df[TransactionRecord.COMMISSION_FEE])

        # always set to 0 as will be part of speedline numbers
        df[TransactionRecord.SUBTOTAL] = 0
        df[TransactionRecord.TAX] = 0
        df[TransactionRecord.TIP] = 0
        df[TransactionRecord.DELIVERY_CHARGE] = 0

        TransactionRecord.calculate_total_after_fees(df)
        df[TransactionRecord.PAYOUT] = 0

        df[TransactionRecord.NOTES] = df.apply(lambda row: f'{row["order_count"]} orders. {row["hangups"]} hangups. Payout part of speedline.', axis=1)
        df = df.reindex(columns=TransactionRecord.get_column_names())

        print(df)
        return
        # Write the transformed data to a new CSV file (csv and parquet)
        raw_data_filename = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV, parent_path=DATA_PATH_RAW)
        df.to_csv(raw_data_filename, index=False)
        self.data_files.append(raw_data_filename)
        print(f'Saved {self.store_name} data orders to: {raw_data_filename}. Based off of processed file: {self.processed_files[0]}.')

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
    credential_file_path = '../credentials/order_inn_credentials.json'
    start_date = datetime.datetime(2023, 1, 1)
    end_date = datetime.datetime(2023, 1, 31)
    store_name = Store.AMECI

    orders = OrderInnOrders(credential_file_path, start_date, end_date, store_name)
    # orders.login()
    # orders.preprocess_reports()
    # orders.get_reports()
    orders.downloaded_files = [
        '/Users/ahaidrey/Desktop/acelife/provider_reports/reports/RestData (1).csv',
    ]
    orders.postprocess_reports()
    orders.standardize_orders_report()
    orders.validate_reports()
    orders.upload_reports()
    # orders.quit()


if __name__ == '__main__':
    main()
