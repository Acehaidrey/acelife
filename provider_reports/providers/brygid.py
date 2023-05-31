import fnmatch
import glob
import os
import time
from datetime import datetime

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


class BrygidOrders(OrdersProvider):
    """
    Brygid orders provider.

    This class implements the OrdersProvider interface for the Brygid provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.
    """

    PROVIDER = Provider.BRYGID
    LOGIN_URL = "https://secure1.brygid.online/packman/proc/signon.jsp"
    ORDER_FILENAME_PATTERN = "*Raw_Order_Data_export*.txt"
    CUSTOMER_INFO_PATTERN = "*Customer_Information_export*.txt"

    def __init__(self, credential_file_path, start_date, end_date, store_name):
        """
        Initialize the BrygidOrders provider.

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
        Perform the login process for the Brygid provider.
        """
        self.driver.get(BrygidOrders.LOGIN_URL)
        username_input = self.wait.until(EC.presence_of_element_located((By.NAME, "loginid")))
        username_input.clear()
        username_input.send_keys(self.username)
        password_input = self.wait.until(EC.presence_of_element_located((By.NAME, "burn_it")))
        password_input.clear()
        password_input.send_keys(self.password)
        login_link = self.wait.until(EC.element_to_be_clickable((By.ID, "loginbtn")))
        login_link.click()

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        """
        Retrieve orders from the Brygid provider.
        """
        start_time = time.time()

        export_btn_locator = (By.LINK_TEXT, "Export Utility")
        d1_locator = (By.NAME, "d1")  # start date picker
        d2_locator = (By.NAME, "d2")  # end date picker
        exptype1_locator = (By.ID, "exptype1")  # export orders
        include_ord_prms_locator = (By.NAME, "includeOrdPrms")
        include_login_info_locator = (By.NAME, "includeLoginInfo")
        include_payment_info_locator = (By.NAME, "includePaymentInfo")
        include_order_tips_locator = (By.NAME, "includeOrderTips")
        include_order_for_date_locator = (By.NAME, "includeOrderForDate")
        include_user_field1_locator = (By.NAME, "includeUserField1")
        include_tax_breakdown_locator = (By.NAME, "includeTaxBreakdown")
        include_ip_user_agent_locator = (By.NAME, "includeIPUserAgent")
        export_button_locator = (By.CSS_SELECTOR, "a:nth-child(2) > .btn")  # export button
        # find export page
        self.wait.until(EC.presence_of_element_located(export_btn_locator)).click()
        # pass in dates for picker
        d1_element = self.wait.until(EC.presence_of_element_located(d1_locator))
        d1_element.clear()
        d1_element.send_keys(self.start_date)
        d2_element = self.wait.until(EC.presence_of_element_located(d2_locator))
        d2_element.clear()
        d2_element.send_keys(self.end_date)
        # check all options for report (more can be added)
        self.wait.until(EC.presence_of_element_located(exptype1_locator)).click()
        self.wait.until(EC.presence_of_element_located(include_ord_prms_locator)).click()
        self.wait.until(EC.presence_of_element_located(include_login_info_locator)).click()
        self.wait.until(EC.presence_of_element_located(include_payment_info_locator)).click()
        self.wait.until(EC.presence_of_element_located(include_order_tips_locator)).click()
        self.wait.until(EC.presence_of_element_located(include_order_for_date_locator)).click()
        self.wait.until(EC.presence_of_element_located(include_user_field1_locator)).click()
        self.wait.until(EC.presence_of_element_located(include_tax_breakdown_locator)).click()
        self.wait.until(EC.presence_of_element_located(include_ip_user_agent_locator)).click()
        # click the export button
        self.wait.until(EC.presence_of_element_located(export_button_locator)).click()
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

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_customers(self):
        start_time = time.time()

        account_home_btn = (By.LINK_TEXT, "Accounts Home")
        export_btn_locator = (By.LINK_TEXT, "Export Utility")
        d1_locator = (By.NAME, "d1")  # start date picker
        d2_locator = (By.NAME, "d2")  # end date picker
        exptype0_locator = (By.ID, "exptype0")  # export customers
        all_records_chk_locator = (By.NAME, "all_records_chk")
        order_amts_chk_locator = (By.NAME, "ord_amounts_chk")
        export_button_locator = (By.CSS_SELECTOR, "a:nth-child(2) > .btn")  # export button

        # find account home
        self.wait.until(EC.presence_of_element_located(account_home_btn)).click()
        # find export page
        self.wait.until(EC.presence_of_element_located(export_btn_locator)).click()
        # pass in dates for picker
        d1_element = self.wait.until(EC.presence_of_element_located(d1_locator))
        d1_element.clear()
        d1_element.send_keys(self.start_date)
        d2_element = self.wait.until(EC.presence_of_element_located(d2_locator))
        d2_element.clear()
        d2_element.send_keys(self.end_date)
        # check all options for report (more can be added)
        self.wait.until(EC.presence_of_element_located(exptype0_locator)).click()
        self.wait.until(EC.presence_of_element_located(all_records_chk_locator)).click()
        self.wait.until(EC.presence_of_element_located(order_amts_chk_locator)).click()
        # click the export button
        self.wait.until(EC.presence_of_element_located(export_button_locator)).click()
        # Wait for the file to be downloaded
        file_pattern = os.path.join(RAW_REPORTS_PATH, self.CUSTOMER_INFO_PATTERN)
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
        Preprocess the retrieved orders from the Brygid provider.
        """
        pass

    def postprocess_reports(self):
        """
        Postprocess the retrieved orders from the Brygid provider.
        The file is a txt file that is internally like a tsv with additional header rows.
        """
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        # filter out unnecessary columns that are useless
        desired_order_columns = ['STORE', 'ORDER_ID', 'DATE', 'FOR_DATE', 'FIRST_NAME',
                                 'LAST_NAME', 'PHONE', 'TYPE', 'STREET', 'SUITE_APT',
                                 'CITY', 'STATE', 'ZIP', 'EMAIL', 'COMPANY', 'TOTAL_BEFORE_TAX',
                                 'DEL_CHARGE', 'TIP_AMOUNT', 'TOTAL_TAX', 'TOTAL_AFTER_TAX',
                                 'TOTAL_DISCOUNT', 'PAY_TYPE', 'PAY_AMOUNT', 'IP_ADR', 'USER_AGENT']

        for downloaded_file in self.downloaded_files:
            report_type = ReportType.CUSTOMERS
            df = pd.read_csv(downloaded_file, delimiter='\t')
            if fnmatch.fnmatch(downloaded_file, self.ORDER_FILENAME_PATTERN):
                df = df[desired_order_columns]
                df = df.sort_values('DATE', ascending=True)
                report_type = ReportType.ORDERS

            full_filename = self.create_processed_filename(report_type, Extensions.CSV)
            df.to_csv(full_filename, index=False)
            print(f'Saved {self.store_name} orders to: {full_filename}')
            self.processed_files.append(full_filename)

    def validate_reports(self):
        """
        Perform report validation specific to the Brygid provider.
        """
        ValidationUtils.validate_processed_files_count(self.processed_files, 2)
        ValidationUtils.validate_downloaded_files_count(self.downloaded_files, 2)
        ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.CSV)
        ValidationUtils.validate_downloaded_files_extension(self.downloaded_files, Extensions.TXT)
        # only check the order report for the dates match
        order_report = [rep for rep in self.processed_files if fnmatch.fnmatch(rep, self.ORDER_FILENAME_PATTERN)]
        ValidationUtils.validate_processed_files_date_range(
            order_report, self.start_date, self.end_date, 'DATE', '%m/%d/%Y %H:%M')

        print("Report validation successful")

    def upload_reports(self):
        """
        Upload the processed report to a remote location specific to the Brygid provider.
        """
        # TODO: Implement report uploading logic for Brygid
        pass

    def quit(self):
        """
        Quit the Brygid provider session.
        """
        self.driver.quit()


def main():
    """
    Main entry point for the script.
    """
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    credential_file_path = '../credentials/brygid_credentials.json'
    start_date = datetime(2023, 3, 1)
    end_date = datetime(2023, 3, 31)
    store_name = Store.AMECI

    orders = BrygidOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    orders.postprocess_reports()
    orders.validate_reports()
    orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
