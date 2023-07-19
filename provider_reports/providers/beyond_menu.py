import datetime
import time

import numpy as np
import pandas as pd
import retrying
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from provider_reports.providers.base_provider import OrdersProvider
from provider_reports.schema.schema import TransactionRecord
from provider_reports.utils.constants import Store, RAW_REPORTS_PATH, Provider, \
    ReportType, Extensions, TAX_RATE, DATA_PATH_RAW, PaymentType
from provider_reports.utils.utils import get_chrome_options, \
    standardize_order_report_setup
from provider_reports.utils.validation_utils import ValidationUtils


class BeyondMenuOrders(OrdersProvider):
    """
    Beyond Menu orders provider.

    This class implements the OrdersProvider interface for the Beyond Menu provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.

    Beyond Menu only allows to get reports for the last 90 days. Beyond that will fail.
    """

    PROVIDER = Provider.BEYOND_MENU
    LOGIN_URL = "https://www.beyondmenu.com/admin/index.aspx"

    def __init__(self, credential_file_path, start_date, end_date, store_name):
        """
        Initialize the BeyondMenu provider.

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
        Perform the login process for the Beyond Menu provider.
        """
        self.driver.get(BeyondMenuOrders.LOGIN_URL)
        username_input = self.wait.until(EC.presence_of_element_located((By.ID, "txtUserName")))
        username_input.clear()
        username_input.send_keys(self.username)
        password_input = self.wait.until(EC.presence_of_element_located((By.ID, "txtPassword")))
        password_input.clear()
        password_input.send_keys(self.password)
        login_btn = self.wait.until(EC.presence_of_element_located((By.ID, "imgbtnLogin")))
        login_btn.click()

    def preprocess_reports(self):
        """
        If start time is older than 90 days throw exception as cannot run report older than that.
        """
        # Get the current date
        today = datetime.datetime.today()

        # Calculate the date that is 90 days ago from today
        ninety_days_ago = today - datetime.timedelta(days=90)

        # Compare start_time_dt with the date 90 days ago
        if self.start_date_dt < ninety_days_ago:
            raise Exception("start_date_dt is older than 90 days ago")

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        # report endpoint
        report_url = BeyondMenuOrders.LOGIN_URL.replace('index.aspx', f'{self.username}/Report.aspx')
        self.driver.get(report_url)
        time.sleep(5)
        # set the start date report
        start_date_button = self.wait.until(EC.presence_of_element_located((By.ID, "ContentPlaceHolder1_txtBeginDateTime")))
        start_date_button.clear()
        start_date_button.send_keys(self.start_date)
        # set the end date report
        end_date_button = self.wait.until(EC.presence_of_element_located((By.ID, "ContentPlaceHolder1_txtEndDateTime")))
        end_date_button.clear()
        end_date_button.send_keys(self.end_date)
        # press search button
        search_button = self.wait.until(EC.presence_of_element_located((By.ID, "ContentPlaceHolder1_btnSearch")))
        search_button.click()
        # View report button
        view_button = self.wait.until(EC.presence_of_element_located((By.LINK_TEXT, "View Report")))
        view_button.click()
        # switch to the new tab for the report
        self.driver.switch_to.window(self.driver.window_handles[-1])
        # Get the HTML content of the page
        html_content = self.driver.page_source
        # save the file and write it
        downloaded_name = self.create_processed_filename(ReportType.ORDERS, Extensions.HTML, parent_path=RAW_REPORTS_PATH)
        with open(downloaded_name, 'w+', encoding='utf-8') as file:
            file.write(html_content)

        self.downloaded_files.append(downloaded_name)
        print(f"Downloaded file(s): {self.downloaded_files}")

    def postprocess_reports(self):
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        orders_df = None
        totals_df = None
        tables = pd.read_html(self.downloaded_files[0])
        for table in tables:
            data = table.values.tolist()
            header = [str(x) for x in table.columns.tolist()]
            # print(header)
            # print(table)
            if ('Date' in header[0] and 'Tip' in header[-1]):
                orders_df = table
            # treats the data row with summary info - header as data row
            if (data and 'Order Count' in data[0][0] and 'CC Total' in data[0][-1]):
                rows = data[1:] if len(data) > 1 else []
                totals_df = pd.DataFrame(rows, columns=data[0])

        # totals table always exist in report even if all zeros
        if totals_df is None:
            raise Exception(f'Found no summary table. Check html file: {self.downloaded_files[0]}')

        # ensure if totals says there are orders, we have order records
        order_count = totals_df.loc[0, 'Order Count']
        if not (orders_df is not None and not orders_df.empty and int(order_count) > 0):
            raise Exception(f'Summary report says orders exist but no orders table found: {self.downloaded_files[0]}')

        if orders_df is not None:
            # get how many orders are delivery type, and divide summary Delivery fee but this number to get avg per order
            # initialize empty delivery charge column
            orders_df['Delivery Fee'] = 0
            # Filter the DataFrame to get only the records with Type == 'Delivery' & get count
            delivery_records = orders_df[orders_df['Type'] == 'Deliver']
            count_of_delivery = delivery_records.shape[0]
            # Get the value of total delivery fee
            total_del_fee = float(totals_df.loc[0, 'Delivery Fee'].replace('$', ''))
            # get the average and add it to records
            avg_del_fee = round(total_del_fee / max(count_of_delivery, 1), 2)
            orders_df.loc[orders_df['Type'] == 'Deliver', 'Delivery Fee'] = avg_del_fee
        else:
            print('No orders found, creating an empty df to use as placeholder')
            cols = ['Date', 'Order #', 'Time', 'Name', 'Type', 'Status', 'Paid By', 'Amt', 'Tip', 'Delivery Fee']
            orders_df = pd.DataFrame([], columns=cols)

        processed_file = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV)
        orders_df.to_csv(processed_file, index=False)
        print(f'Saved {self.store_name} orders to: {processed_file}')
        self.processed_files.append(processed_file)

    def standardize_orders_report(self):
        # these rates are set from provider (taken from statement)
        FAX_FEE = 0.12 if self.store == Store.AMECI else 0
        PHONE_FEE = 0.08 if self.store == Store.AMECI else 0
        COMMISSION_RATE = 0.03 if self.store == Store.AMECI else 0.05
        ORDER_FEE = 0.99
        EST_MERCHANT_PROCESSING_RATE = 0.043

        rename_map = {
            'Date': TransactionRecord.ORDER_DATE,
            'Order #': TransactionRecord.TRANSACTION_ID,
            'Paid By': TransactionRecord.PAYMENT_TYPE,
            'Amt': TransactionRecord.TOTAL_BEFORE_FEES,
            'Tip': TransactionRecord.TIP,
            'Delivery Fee': TransactionRecord.DELIVERY_CHARGE
        }
        df = standardize_order_report_setup(self.processed_files[0], rename_map, self.PROVIDER, self.store)

        # always charges customer $0.99 for service fee then we pass it on
        df[TransactionRecord.SERVICE_FEE] = -1.0 * ORDER_FEE

        # Calculate Subtotal Amount (work backwards from total)
        df['subtotal_with_tax'] = df[TransactionRecord.TOTAL_BEFORE_FEES] - df[TransactionRecord.TIP] - df[TransactionRecord.DELIVERY_CHARGE] - ORDER_FEE
        df[TransactionRecord.SUBTOTAL] = (df['subtotal_with_tax'] / (1 + TAX_RATE)).round(2)
        df[TransactionRecord.TAX] = (df[TransactionRecord.SUBTOTAL] * TAX_RATE).round(2)

        # Calculate commission and merchant processing
        df[TransactionRecord.COMMISSION_FEE] = -1.0 * (FAX_FEE + PHONE_FEE + COMMISSION_RATE * df[TransactionRecord.SUBTOTAL]).round(2)
        df[TransactionRecord.MERCHANT_PROCESSING_FEE] = -1.0 * (EST_MERCHANT_PROCESSING_RATE * df[TransactionRecord.TOTAL_BEFORE_FEES]).round(2)

        # Mark it as cash if cash otherwise credit
        df[TransactionRecord.PAYMENT_TYPE] = np.where(
            df[TransactionRecord.PAYMENT_TYPE].str.lower() == PaymentType.CASH, PaymentType.CASH, PaymentType.CREDIT)

        # Calculate after fees and payout
        TransactionRecord.calculate_total_after_fees(df)

        # Zero out payouts for cash
        TransactionRecord.calculate_payout(df)
        df.loc[df[TransactionRecord.PAYMENT_TYPE] == PaymentType.CASH, TransactionRecord.PAYOUT] = 0

        df[TransactionRecord.NOTES] = 'Fees calculated by invoice contract. Merchant Services estimated.'
        df = df.reindex(columns=TransactionRecord.get_column_names())

        print(df)
        # Write the transformed data to a new CSV file (csv and parquet)
        raw_data_filename = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV, parent_path=DATA_PATH_RAW)
        df.to_csv(raw_data_filename, index=False)
        self.data_files.append(raw_data_filename)
        print(f'Saved {self.store_name} data orders to: {raw_data_filename}. Based off of processed file: {self.processed_files[0]}.')

    def validate_reports(self):
        ValidationUtils.validate_downloaded_files_count(self.downloaded_files, 1)
        ValidationUtils.validate_processed_files_count(self.processed_files, 1)
        ValidationUtils.validate_downloaded_files_extension(self.downloaded_files, Extensions.HTML)
        ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.CSV)
        ValidationUtils.validate_data_files_count(self.data_files, 1)
        ValidationUtils.validate_data_file_total_after_fees_accurate(self.data_files[0])
        ValidationUtils.validate_data_file_after_fees_payout_match(self.data_files[0])

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
    credential_file_path = '../credentials/beyond_menu_credentials.json'
    start_date = datetime.datetime(2023, 5, 1)
    end_date = datetime.datetime(2023, 5, 31)
    store_name = Store.AMECI

    orders = BeyondMenuOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    # orders.downloaded_files = ['/Users/ahaidrey/Desktop/acelife/provider_reports/reports/beyond_menu_ameci_orders_05_01_2023_05_31_2023.html']
    orders.postprocess_reports()
    orders.standardize_orders_report()
    orders.validate_reports()
    orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
