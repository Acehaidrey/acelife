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
from provider_reports.schema.schema import TransactionRecord
from provider_reports.utils.constants import Store, RAW_REPORTS_PATH, Provider, \
    ReportType, Extensions, DATA_PATH_RAW, PaymentType
from provider_reports.utils.utils import get_chrome_options, \
    standardize_order_report_setup
from provider_reports.utils.validation_utils import ValidationUtils


class EZCaterOrders(OrdersProvider):
    """
    EZCater orders provider.

    This class implements the OrdersProvider interface for the EZCater provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.

    Future work:
        Consider extracting customer business info from here.
    """

    PROVIDER = Provider.EZCATER
    LOGIN_URL = "https://www.ezcater.com/sign_in"
    ORDER_FILENAME_PATTERN = "*.xlsx"

    def __init__(self, credential_file_path, start_date, end_date, store_name):
        """
        Initialize the EZCaterOrders provider.

        Args:
            credential_file_path (str): The path to the credential file.
            start_date (datetime.datetime): The start date for retrieving orders.
            end_date (datetime.datetime): The end date for retrieving orders.
            store_name (Store): The name of the store associated with the provider.
        """
        super().__init__(credential_file_path, start_date, end_date, store_name)

        self.start_date = self.start_date_dt.strftime('%Y-%m-%d')
        self.end_date = self.end_date_dt.strftime('%Y-%m-%d')
        self.download_report_name_prefix = 'completed_orders_' + str(int(time.time()))
        self.driver = None
        self.wait = None

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def login(self):
        """
        Perform the login process for the EZCater provider.
        """
        self.driver = webdriver.Chrome(options=get_chrome_options())
        self.wait = WebDriverWait(self.driver, 30)

        self.driver.get(EZCaterOrders.LOGIN_URL)
        username_input = self.wait.until(EC.presence_of_element_located((By.ID, "email")))
        username_input.clear()
        username_input.send_keys(self.username)
        password_input = self.wait.until(EC.presence_of_element_located((By.ID, "password")))
        password_input.clear()
        password_input.send_keys(self.password)
        self.driver.find_element(By.XPATH, "//button[contains(.,\'Sign In\')]").click()

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        """
        Retrieve orders from the EZCater provider.
        """
        start_time = time.time()
        reports_input = self.wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Reports")))
        reports_input.click()
        new_reports_input = self.wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Create New Report")))
        new_reports_input.click()
        # add all stores by default and post process for what needed
        all_stores_input = self.wait.until(EC.presence_of_element_located(
            (By.XPATH, "//button[contains(.,'Add all stores')]")))
        all_stores_input.click()

        start_date_input = self.wait.until(EC.presence_of_element_located((By.ID, "ez_manage_report_start_date")))
        start_date_input.clear()
        start_date_input.send_keys(self.start_date)
        end_date_input = self.wait.until(EC.presence_of_element_located((By.ID, "ez_manage_report_end_date")))
        end_date_input.clear()
        end_date_input.send_keys(self.end_date)

        report_name_input = self.wait.until(EC.presence_of_element_located((By.ID, "ez_manage_report_name")))
        report_name_input.send_keys(self.download_report_name_prefix)

        new_reports_input = self.wait.until(EC.presence_of_element_located((By.NAME, "commit")))
        new_reports_input.click()

        # wait for processing to complete
        self.wait.until(EC.invisibility_of_element_located((By.LINK_TEXT, "processing...")))

        # Wait for the table to be loaded & get row elements
        table = self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "data-table")))
        rows = table.find_elements(By.TAG_NAME, "tr")

        # Find the div elements with data-role="report-name" & find the one matching this report name
        print('Searching for report: ' + self.download_report_name_prefix)
        for row in rows:
            try:
                report_div = row.find_element(By.CSS_SELECTOR, "div[data-role='report-name']")
            except Exception:
                continue

            # Check if the report name matches the given report_name
            if self.download_report_name_prefix in report_div.text:
                report_div.get_attribute("innerHTML")
                # Find the download button within the row & wait until its clickable
                download_button = self.wait.until(EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "i.icon.icon-download[data-role='report-download-link']")))
                download_button.click()
                # There's only one matching report, break out of the loop
                break

        # Wait for the file to be downloaded
        file_pattern = os.path.join(RAW_REPORTS_PATH, self.download_report_name_prefix + self.ORDER_FILENAME_PATTERN)
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
        Preprocess the retrieved orders from the EZCater provider.
        """
        pass

    def postprocess_reports(self):
        """
        Postprocess the retrieved orders from the EZCater provider. Only expect one file.
        The output file has both stores info in there, we generate two separate csvs.
        """
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        for downloaded_file in self.downloaded_files:
            df = pd.read_excel(downloaded_file)
            df = df.iloc[:-1]
            df['Payment Type'] = PaymentType.CREDIT

            for store in [Store.AROMA.value, Store.AMECI.value]:
                match_df = df[df['Store Name'].str.contains(store, case=False)]
                full_match_fp = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV, store=store)
                match_df.to_csv(full_match_fp, index=False)
                print(f'Saved {store} orders to: {full_match_fp}')
                self.processed_files.append(full_match_fp)

    def standardize_orders_report(self):
        """
        Standardize report to conform to expected table format.
        """
        rename_map = {
            'Order Number': TransactionRecord.TRANSACTION_ID,
            'Event Date': TransactionRecord.ORDER_DATE,
            'Food Total': TransactionRecord.SUBTOTAL,
            'Promotion': TransactionRecord.MARKETING_FEE,
            'Delivery Fee': TransactionRecord.DELIVERY_CHARGE,
            'Commission': TransactionRecord.COMMISSION_FEE,
            'Sales Tax': TransactionRecord.TAX,
            'Sales Tax Remitted by ezCater': TransactionRecord.TAX_WITHHELD,
            'Tip': TransactionRecord.TIP,
            'Payment Transaction Fee': TransactionRecord.MERCHANT_PROCESSING_FEE,
            'Adjustments': TransactionRecord.ADJUSTMENT_FEE,
            'Discounts': 'discounts',
            'Misc Fees': 'misc_fees',
            'Preferred Partner Program': 'preferred_partner',
            'ezRewards': 'ezrewards',
            'Caterer Total Due': TransactionRecord.PAYOUT,
            'Payment Type': TransactionRecord.PAYMENT_TYPE,
        }
        # Get transaction file
        orders_file = [f for f in self.processed_files if ReportType.ORDERS in f and self.store_name.lower() in f][0]
        df = standardize_order_report_setup(orders_file, rename_map, self.PROVIDER, self.store)

        # add in discounts, preferred partner program, and ezrewards into the marketing
        df[TransactionRecord.MARKETING_FEE] = df[TransactionRecord.MARKETING_FEE] + df['preferred_partner'] + df['ezrewards'] + df['discounts']
        # If adjustment_fee is positive, add it to tip and set adjustment_fee to 0 (call in adjustment)
        # If adjustment_fee is negative, leave it as it is
        df.loc[df[TransactionRecord.ADJUSTMENT_FEE] > 0, TransactionRecord.TIP] += df[TransactionRecord.ADJUSTMENT_FEE]
        df.loc[df[TransactionRecord.ADJUSTMENT_FEE] > 0, TransactionRecord.ADJUSTMENT_FEE] = 0
        # add in misc fees to adjustments
        df[TransactionRecord.ADJUSTMENT_FEE] = df[TransactionRecord.ADJUSTMENT_FEE] + df['misc_fees']
        # calculate before/after fees costs
        TransactionRecord.calculate_total_before_fees(df)
        TransactionRecord.calculate_total_after_fees(df)
        df = df.reindex(columns=TransactionRecord.get_column_names())
        # Write the transformed data to a new CSV file (csv and parquet)
        raw_data_filename = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV, parent_path=DATA_PATH_RAW)
        df.to_csv(raw_data_filename, index=False)
        self.data_files.append(raw_data_filename)
        print(f'Saved {self.store_name} data orders to: {raw_data_filename}. Based off of processed file: {orders_file}.')

    def validate_reports(self):
        """
        Perform report validation specific to the EZCater provider.
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
        ValidationUtils.validate_data_files_count(self.data_files, 1)
        store_processed_file = [f for f in self.processed_files if self.store_name.lower() in f]
        ValidationUtils.validate_all_data_file_checks(self.data_files[0], store_processed_file[0])
        print("Report validation successful")

    def upload_reports(self):
        """
        Upload the processed report to a remote location specific to the EZCater provider.
        """
        # TODO: Implement report uploading logic for EZCater
        self.write_parquet_data()

    def quit(self):
        """
        Quit the EZCater provider session.
        """
        self.driver.quit()


def main():
    """
    Main entry point for the script.
    """
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    credential_file_path = '../credentials/ezcater_credentials.json'
    start_date = datetime.datetime(2023, 1, 1)
    end_date = datetime.datetime(2023, 1, 31)
    store_name = Store.AMECI

    orders = EZCaterOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    orders.postprocess_reports()
    # orders.processed_files = [
    #     '/Users/ahaidrey/Desktop/acelife/provider_reports/reports_processed/ezcater_aroma_orders_01_01_2023_01_31_2023.csv',
    #     '/Users/ahaidrey/Desktop/acelife/provider_reports/reports_processed/ezcater_ameci_orders_01_01_2023_01_31_2023.csv'
    # ]
    orders.standardize_orders_report()
    orders.validate_reports()
    orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
