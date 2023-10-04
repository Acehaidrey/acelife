from datetime import datetime
import os
import time

import pandas as pd
import requests
import retrying
import tabula
from selenium import webdriver
from selenium.common import TimeoutException, NoSuchElementException
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


def fill_unnamed_columns(cols):
    updated_list = [element if 'Unnamed' not in element else '' for element in cols]
    return updated_list


def find_index_of_slice_adjustment(orders_list):
    for i, record in enumerate(orders_list):
        if isinstance(record[0], str) and 'slice adjustments' in record[0].lower():
            return i


def find_index_of_first_order_row(orders_list):
    desired_format = '%b %d, %Y'

    # Iterate through the list and find the index of the first record
    for i, record in enumerate(orders_list):
        if isinstance(record[0], str):
            try:
                datetime.strptime(record[0], desired_format)
                return i
            except ValueError:
                continue


def create_order_header(orders_list):
    # transpose the list to invert rows & columns
    df = pd.DataFrame(orders_list)
    df = df.transpose()
    df = df.fillna('')
    header_cols = []
    rows = df.values.tolist()

    for row in rows:
        converted_data = [str(int(value))
                          if isinstance(value, float) and value.is_integer()
                          else str(value) for value in row]
        joined_row = ' '.join([v for v in converted_data if v])
        header_cols.append(joined_row.strip())
    # return [h for h in header_cols if h]
    return header_cols


def standardize_row_group(row_group, header):
    all_len_match = all(len(row) == len(row_group[0]) for row in row_group)
    if not all_len_match:
        raise Exception(f'All rows do not match len in row group: {row_group}')

    if len(row_group[0]) == len(header):
        return create_order_header(row_group)

    # handle the larger size where row length is different
    # second row is the one that is full of values (examples below)
    # ['Saturday 82369372', nan, nan, 'Credit', 'Delivery', '$40.20 $1.99', nan, '$0.00',
    # '$3.27 $0.00', '$45.46', nan, '-$2.99', '-$1.82']
    # ['Saturday 17719778', nan, nan, 'Phone', '-', '- -', nan, '-', '- -', '-', nan, '-$2.99', '-']
    altered_lists = pd.DataFrame(row_group[1]).fillna('').values.tolist()
    second_row = []
    for lst in altered_lists:
        vals = ' '.join(lst).strip()
        vals_list = [v for v in vals.split(' ') if v]
        second_row.extend(vals_list)
    first_item = ' '.join([row_group[0][0], second_row[0], row_group[2][0]])
    fixed_record = [first_item] + second_row[1:]
    assert len(fixed_record) == len(header), f'Adjusted row mismatch: {fixed_record}, headers {header}'
    return fixed_record


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

        self.driver = None
        self.wait = None

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
        self.driver = webdriver.Chrome(options=get_chrome_options())
        self.wait = WebDriverWait(self.driver, 60)

        self.driver.get(SliceOrders.LOGIN_URL)
        username_input = self.wait.until(EC.presence_of_element_located((By.ID, "username")))
        username_input.clear()
        username_input.send_keys(self.username)
        password_input = self.wait.until(EC.presence_of_element_located((By.ID, "password")))
        password_input.clear()
        password_input.send_keys(self.password)
        self.driver.find_element(By.NAME, "action").click()

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
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
        Postprocess the retrieved orders from the Slice provider.
        Parse the PDF for order information and try to get summary info.
        TODO: write steps to process summary report & add validation steps
        """
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        # Extract tables from the PDF - tables here is just data in pdf
        downloaded_file = self.downloaded_files[0]
        tables = tabula.read_pdf(downloaded_file, pages='all', multiple_tables=True, guess=False)
        print(f'{len(tables)} tables identified in pdf: {downloaded_file}')

        # Iterate through all rows and make some assumptions on breaking points
        # 1. One csv will be the summary info (Dataframes with 3 columns)
        # 2. One csv will be the orders info (Dataframes with 12/13 columns)
        # 3. One csv will be the adjustment info (Dataframes with 13 columns)

        summary_rows = []
        order_rows = []
        orders_index = None  # index that orders begin
        for i, table in enumerate(tables):
            # print(table)  # Example: Print the table data
            header = table.columns.tolist()
            data = table.values.tolist()

            # marks end of parsing last page reached
            if 'FAQ' in header:
                break

            # mark the orders starting
            if ('Orders' in header and all('Unnamed' in column for column in header[1:])) \
                    or (orders_index and i >= orders_index):
                # set value to compare against
                if orders_index is None:
                    orders_index = i
                order_rows.append(fill_unnamed_columns(header))
                for d in data:
                    order_rows.append(d)
            else:
                # if prior to orders then keep the records of overview numbers
                summary_rows.append(header)
                for d in data:
                    summary_rows.append(d)

        ind = find_index_of_first_order_row(order_rows)
        slice_adjustment_ind = find_index_of_slice_adjustment(order_rows)
        # first row is just Orders header so skip
        order_header = create_order_header(order_rows[1:ind])
        true_order_rows = order_rows[ind:slice_adjustment_ind]
        assert len(true_order_rows) % 3 == 0, \
            "The length of orders_list is not divisible by 3. Issue parsing."

        # process all order rows (separate by column count (12 vs 13)
        # first 4 rows are just trying to make headers
        # identify when we see 'Slice Adjustments'
        # the rest of the rows are groups of 3 for data records
        standardized_rows = []
        for i in range(0, len(true_order_rows), 3):
            row_group = true_order_rows[i:i + 3]
            # Process the three rows together
            standardized_row = standardize_row_group(row_group, order_header)
            standardized_rows.append(standardized_row)

        df = pd.DataFrame(standardized_rows, columns=order_header)
        df = df.replace('-', '0')  # replace - to zero

        processed_file = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV)
        df.to_csv(processed_file)
        self.processed_files.append(processed_file)
        print(f'Saved {self.store_name} orders to: {processed_file}')

        # strip out first row that says Slice Adjustments
        slice_adj_rows = order_rows[slice_adjustment_ind + 1:]
        ind = find_index_of_first_order_row(slice_adj_rows)
        true_slice_adj_rows = slice_adj_rows[ind:]
        adj_header = create_order_header(slice_adj_rows[0: ind])

        adj_rows = []
        for i in range(0, len(true_slice_adj_rows), 3):
            row_group = true_slice_adj_rows[i:i + 3]
            # Process the three rows together
            standardized_row = standardize_row_group(row_group, adj_header)
            adj_rows.append([e for e in standardized_row if e])

        df = pd.DataFrame(adj_rows, columns=[c for c in adj_header if c])
        df = df.replace('-', '0')  # replace - to zero
        processed_file = self.create_processed_filename(ReportType.ADJUSTMENTS, Extensions.CSV)
        df.to_csv(processed_file)
        self.processed_files.append(processed_file)
        print(f'Saved {self.store_name} adjustments to: {processed_file}')

    def standardize_orders_report(self):
        """
        Standardize report to conform to expected table format.
        """
        rename_map = {
            'Order ID': TransactionRecord.TRANSACTION_ID,
            'Order Type': TransactionRecord.PAYMENT_TYPE,
            'Date & Time': TransactionRecord.ORDER_DATE,
            'Subtotal': TransactionRecord.SUBTOTAL,
            'Cust. Delivery Fee': TransactionRecord.DELIVERY_CHARGE,
            'Order Adjust.': TransactionRecord.ADJUSTMENT_FEE,
            'Tax': TransactionRecord.TAX_WITHHELD,
            'Tips': TransactionRecord.TIP,
            'Order Total': TransactionRecord.TOTAL_BEFORE_FEES,
            "P'ship Fee": TransactionRecord.COMMISSION_FEE,
            'Proc. Fee': TransactionRecord.MERCHANT_PROCESSING_FEE,
        }
        # Get order file
        orders_file = [f for f in self.processed_files if ReportType.ORDERS in f][0]
        df = pd.read_csv(orders_file)
        # remove voided orders
        df = df[df['Order Total'] != 'VOIDED']
        # convert all $ columns to remove that value
        df = standardize_order_report_setup(None, rename_map, self.PROVIDER, self.store, df)
        # put note for phone orders and add credit type
        df.loc[df[TransactionRecord.PAYMENT_TYPE] == 'phone', TransactionRecord.NOTES] = 'This is a phone order commission record'
        df.loc[df[TransactionRecord.PAYMENT_TYPE] == 'phone', TransactionRecord.PAYMENT_TYPE] = PaymentType.CREDIT
        # after fees record
        TransactionRecord.calculate_total_after_fees(df)
        # payout record
        TransactionRecord.calculate_payout(df)
        # Pay amount (zero when cash since goes to our pos, total when credit)
        df.loc[df[TransactionRecord.PAYMENT_TYPE] == PaymentType.CASH, TransactionRecord.PAYOUT] = 0
        # Write the transformed data to a new CSV file (csv and parquet)
        raw_data_filename = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV, parent_path=DATA_PATH_RAW)
        df.to_csv(raw_data_filename, index=False)
        self.data_files.append(raw_data_filename)
        print(f'Saved {self.store_name} data orders to: {raw_data_filename}. Based off of processed file: {orders_file}.')

    def validate_reports(self):
        """
        Perform report validation specific to the Slice provider.
        """
        order_files = [f for f in self.processed_files if ReportType.ORDERS in f]
        ValidationUtils.validate_processed_files_count(order_files, 1)
        ValidationUtils.validate_downloaded_files_count(self.downloaded_files, 1)
        ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.CSV)
        ValidationUtils.validate_downloaded_files_extension(self.downloaded_files, Extensions.PDF)
        ValidationUtils.validate_data_files_count(self.data_files, 1)
        ValidationUtils.validate_downloaded_files_extension(self.data_files, Extensions.CSV)
        ValidationUtils.validate_data_file_columns_match(self.data_files[0])
        print("Report validation successful")

    def upload_reports(self):
        """
        Upload the processed report to a remote location specific to the Slice provider.
        """
        self.write_parquet_data()

    def quit(self):
        """
        Quit the Slice provider session.
        """
        if self.driver:
            self.driver.quit()


def main():
    """
    Main entry point for the script.
    """
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    credential_file_path = '../credentials/slice_credentials.json'
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 1, 28)
    store_name = Store.AMECI

    orders = SliceOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    # orders.downloaded_files = ['/Users/ahaidrey/Desktop/acelife/provider_reports/reports/slice_1686121049.pdf']
    orders.postprocess_reports()
    orders.standardize_orders_report()
    orders.validate_reports()
    orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
