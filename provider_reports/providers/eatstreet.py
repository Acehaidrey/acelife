import csv
import os
from datetime import datetime

import pandas as pd
import retrying
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from provider_reports.providers.base_provider import OrdersProvider
from provider_reports.schema.schema import TransactionRecord
from provider_reports.utils.constants import Store, RAW_REPORTS_PATH, Provider, \
    ReportType, Extensions, PaymentType, TAX_RATE, DATA_PATH_RAW
from provider_reports.utils.utils import get_chrome_options, \
    standardize_order_report_setup
from provider_reports.utils.validation_utils import ValidationUtils


class EatstreetOrders(OrdersProvider):
    """
    Eatstreet orders provider.

    This class implements the OrdersProvider interface for the Eatstreet provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.

    TODO: Get advertisement and other costs (not per transaction) into a separate csv to use.
    """

    PROVIDER = Provider.EATSTREET
    LOGIN_URL = "https://eatstreet.com/restaurant-dashboard/signin?next=home"
    ORDER_FILENAME_PATTERN = "eatstreet*.html"

    def __init__(self, credential_file_path, start_date, end_date, store_name):
        """
        Initialize the EatstreetOrders provider.
        This provider has few orders but still want to account for them.

        Args:
            credential_file_path (str): The path to the credential file.
            start_date (datetime.datetime): The start date for retrieving orders.
            end_date (datetime.datetime): The end date for retrieving orders.
            store_name (Store): The name of the store associated with the provider.
        """
        super().__init__(credential_file_path, start_date, end_date, store_name)

        cap = DesiredCapabilities.CHROME
        cap["pageLoadStrategy"] = "none"
        self.driver = webdriver.Chrome(options=get_chrome_options(), desired_capabilities=cap)
        self.wait = WebDriverWait(self.driver, 20)

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def login(self):
        """
        Perform the login process for the Eatstreet provider.
        """
        self.driver.get(EatstreetOrders.LOGIN_URL)
        username_input = self.wait.until(EC.presence_of_element_located((By.ID, "identifier")))
        username_input.clear()
        username_input.send_keys(self.username)
        password_input = self.wait.until(EC.presence_of_element_located((By.ID, "password")))
        password_input.clear()
        password_input.send_keys(self.password)
        self.wait.until(EC.presence_of_element_located((By.ID, "signin"))).click()

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        # go to summary tab
        summary_input = self.wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Summary")))
        summary_input.click()
        start_date = self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, f"input[ng-model='startDate']")))
        start_date.click()
        # set the start date in date picker (cannot send keys)
        date_object = datetime.strptime(self.start_date, "%m/%d/%Y")
        year, month, day = date_object.year, date_object.month, date_object.day
        while True:
            # Check the current month and year
            current_month = self.driver.find_element(By.CSS_SELECTOR, ".picker__month").text
            current_year = self.driver.find_element(By.CSS_SELECTOR, ".picker__year").text

            # Break the loop if we find the desired month and year
            if current_month.lower() == date_object.strftime('%B').lower() and current_year == str(year):
                break

            # Click the previous button to go to previous month
            prev_button = self.driver.find_element(By.CSS_SELECTOR, ".picker__nav--prev")
            prev_button.click()
        # set the date when in the right month
        day_element = self.driver.find_element(By.XPATH, f".//div[text()='{day}' and contains(@class, 'picker__day--infocus')]")
        day_element.click()
        # end date set
        end_date_elem = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, f"input[ng-model='endDate']")))
        end_date_elem.click()

        date_object = datetime.strptime(self.end_date, "%m/%d/%Y")
        year, month, day = date_object.year, date_object.month, date_object.day
        end_date_picker = self.driver.find_element(By.CLASS_NAME, 'picker--opened')

        while True:
            # Check the current month and year
            current_month = end_date_picker.find_element(By.CSS_SELECTOR, ".picker__month").text
            current_year = end_date_picker.find_element(By.CSS_SELECTOR, ".picker__year").text
            print(current_month, current_year)

            # Break the loop if we find the desired month and year
            if current_month.lower() == date_object.strftime('%B').lower() and current_year == str(year):
                break

            # Click the previous button
            prev_button = end_date_picker.find_element(By.CSS_SELECTOR, ".picker__nav--prev")
            print(prev_button)
            prev_button.click()

        day_element = end_date_picker.find_element(By.XPATH,
                                                   f".//div[text()='{day}' and contains(@class, 'picker__day--infocus')]")

        # generate the report and display it to new window
        self.driver.execute_script("arguments[0].click();", day_element)
        self.wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Generate Summary"))).click()
        self.wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Print Summary"))).click()
        self.driver.switch_to.window(self.driver.window_handles[-1])

        # Get the HTML content of the page
        html_content = self.driver.page_source
        orders_filename = self.create_processed_filename(ReportType.ORDERS, Extensions.HTML, parent_path=RAW_REPORTS_PATH)
        with open(orders_filename, 'w+', encoding='utf-8') as file:
            file.write(html_content)

        self.downloaded_files.append(orders_filename)
        print(f"Downloaded file(s): {self.downloaded_files}")

    def preprocess_reports(self):
        """
        Preprocess the retrieved orders from the Eatstreet provider.
        """
        pass

    def postprocess_reports(self):
        """
        Postprocess the retrieved orders from the Eatstreet provider. Only expect one file.
        The eatstreet output is an html file with order info as well as general summaries.
        We ignore the general summary info and simply take the transaction order info.
        If no orders exist we just have a zero'd out row to post a file to show we processed.
        """
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        for downloaded_file in self.downloaded_files:
            if downloaded_file.endswith(Extensions.HTML):
                # Read the HTML file
                with open(downloaded_file, 'r') as file:
                    html_data = file.read()
                # Parse the HTML data
                soup = BeautifulSoup(html_data, 'html.parser')
                # Find all tables with class 'summary-table--orders'
                tables = soup.find_all('table', class_='summary-table--orders')
                records = []
                for table in tables:
                    # Get the table headers
                    headers = [header.text.strip() for header in
                               table.select('.summary-table--orders__header span.bold')]
                    assert len(headers) == 7
                    # Get the table rows
                    rows = table.select('.summary-table--orders__row')
                    assert len(rows) == 1
                    # Loop through each row
                    for row in rows:
                        row_data = [data.text.strip() for data in row.select('td span.medium_text')]
                        assert len(row_data) >= 7
                        # expecting one row_data and one headers to combine
                        # ['4/23/2023', '', 'ID', 'Tip', 'Total', 'Proc', 'Comm']
                        # ['5:17 PM', 'Takeout', '', '34505982', '$0.00', '$67.95', '$2.51', '$10.19']
                        date = ('Date', headers[0] + ' ' + row_data[0])
                        order_type = ('OrderType', row_data[1])
                        record = [date, order_type] + list(zip(headers[-5:], row_data[-5:]))
                        records.append(record)

                if not tables:
                    headers = ['Date', 'OrderType', 'ID', 'Tip', 'Total', 'Proc', 'Comm']
                    row_data = [self.start_date + ' 00:00 AM', '', '$0.00', '$0.00', '$0.00', '$0.00', '$0.00']
                    record = list(zip(headers, row_data))
                    records.append(record)

                # Create a CSV file to write the table data
                processed_file = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV)
                with open(processed_file, 'w+', newline='') as csv_file:
                    writer = csv.writer(csv_file)
                    # Write the header row based on the first row of data
                    writer.writerow([header for header, _ in records[0]])
                    # Write each row
                    for row in records:
                        writer.writerow([value for _, value in row])

                self.processed_files.append(processed_file)
                print(f'Saved {self.store_name} orders to: {processed_file}')

    def standardize_orders_report(self):
        """
        The total value includes the tip and del fee.
        The taxes are withheld but do not show up on report so manual calc.
        The delivery fee is not included. We make an estimate as 2.99.
        Payment types are always set to credit (can be inaccurate).
        :return:
        """
        rename_map = {
            'ID': TransactionRecord.TRANSACTION_ID,
            'Date': TransactionRecord.ORDER_DATE,
            'Tip': TransactionRecord.TIP,
            'Total': TransactionRecord.SUBTOTAL,
            'Proc': TransactionRecord.MERCHANT_PROCESSING_FEE,
            'Comm': TransactionRecord.COMMISSION_FEE,
            'OrderType': 'order_type',
        }
        # have to first do cleanup on the processed file to convert types
        orders_file = self.processed_files[0]
        df = pd.read_csv(orders_file)
        df['Tip'] = df['Tip'].str.replace('$', '').astype(float)
        df['Total'] = df['Total'].str.replace('$', '').astype(float)
        df['Proc'] = -(df['Proc'].str.replace('$', '').astype(float))
        df['Comm'] = -(df['Comm'].str.replace('$', '').astype(float))

        df = standardize_order_report_setup(None, rename_map, self.PROVIDER, self.store, df)

        df[TransactionRecord.PAYMENT_TYPE] = PaymentType.CREDIT
        # if order type delivery add 2.99 charge as that is most common (not 100% accurate here)
        # report given to us does not include this information
        df.loc[df['order_type'] == 'delivery', TransactionRecord.DELIVERY_CHARGE] = 2.99
        # subtotal includes tip and del charge so remove them
        df[TransactionRecord.SUBTOTAL] = df[TransactionRecord.SUBTOTAL] - df[TransactionRecord.TIP] - df[TransactionRecord.DELIVERY_CHARGE]
        # multiply subtotal by tax rate to get taxes withheld amount
        df[TransactionRecord.TAX_WITHHELD] = (TAX_RATE * df[TransactionRecord.SUBTOTAL]).round(2)
        # get before and after fees
        TransactionRecord.calculate_total_before_fees(df)
        TransactionRecord.calculate_total_after_fees(df)
        # set payout column (taxes withheld)
        TransactionRecord.calculate_payout(df)
        # remove extra columns
        df = df.reindex(columns=TransactionRecord.get_column_names())

        # Write the transformed data to a new CSV file (csv and parquet)
        raw_data_filename = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV, parent_path=DATA_PATH_RAW)
        df.to_csv(raw_data_filename, index=False)
        self.data_files.append(raw_data_filename)
        print(f'Saved {self.store_name} data orders to: {raw_data_filename}. Based off of processed file: {orders_file}.')

    def validate_reports(self):
        """
        Perform report validation specific to the Eatstreet provider.
        TODO: Add additional checks against the HTML where order info matches their summary.
        TODO: Do additional checks in HTML file to see if any additional charges are added, like advertisements.
        """
        ValidationUtils.validate_processed_files_count(self.processed_files, 1)
        ValidationUtils.validate_downloaded_files_count(self.downloaded_files, 1)
        ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.CSV)
        ValidationUtils.validate_downloaded_files_extension(self.downloaded_files, Extensions.HTML)
        ValidationUtils.validate_processed_files_date_range(
            self.processed_files, self.start_date, self.end_date, 'Date', '%m/%d/%Y %I:%M %p')
        ValidationUtils.validate_data_files_count(self.data_files, 1)
        ValidationUtils.validate_all_data_file_checks(self.data_files[0], self.processed_files[0])
        print("Report validation successful")

    def upload_reports(self):
        """
        Upload the processed report to a remote location specific to the Eatstreet provider.
        """
        self.write_parquet_data()

    def quit(self):
        """
        Quit the Eatstreet provider session.
        """
        self.driver.quit()


def main():
    """
    Main entry point for the script.
    """
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    credential_file_path = '../credentials/eatstreet_credentials.json'
    start_date = datetime(2023, 4, 1)
    end_date = datetime(2023, 4, 30)
    store_name = Store.AROMA

    orders = EatstreetOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    orders.postprocess_reports()
    # orders.processed_files = ['/Users/ahaidrey/Desktop/acelife/provider_reports/reports_processed/eatstreet_aroma_orders_04_01_2023_04_30_2023.csv']
    orders.standardize_orders_report()
    orders.validate_reports()
    orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
