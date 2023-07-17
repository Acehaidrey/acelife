import os
import re
import stat
from datetime import datetime

import numpy as np
import pandas as pd
import paramiko
import retrying

from provider_reports.providers.base_provider import OrdersProvider
from provider_reports.schema.schema import TransactionRecord
from provider_reports.utils.constants import Store, RAW_REPORTS_PATH, Provider, \
    ReportType, Extensions, TAX_RATE, DATA_PATH_RAW
from provider_reports.utils.utils import standardize_order_report_setup
from provider_reports.utils.validation_utils import ValidationUtils


class DownloadFileType:
    ORDER_DETAILS = 'OrderDetails.csv'
    PAYMENT_DETAILS = 'PaymentDetails.csv'


def list_files(sftp, remote_path=''):
    file_list = sftp.listdir(remote_path)
    for item in file_list:
        item_path = remote_path + '/' + item if remote_path else item
        try:
            attributes = sftp.stat(item_path)
            if stat.S_ISDIR(attributes.st_mode):
                # If it's a directory, recursively list its contents
                list_files(sftp, item_path)
            else:
                # It's a file, print its path
                print(item_path)
        except IOError:
            # Error occurred while getting file attributes, skip the item
            pass


def is_valid_date(date_str, start_date, end_date):
    date = datetime.strptime(date_str, '%Y%m%d')
    return start_date <= date <= end_date


def download_files(sftp, remote_path='', local_path='', start_date=None, end_date=None, filters=None, files_downloaded=None):
    files_downloaded = files_downloaded or []
    file_list = sftp.listdir(remote_path)
    for item in file_list:
        item_path = remote_path + '/' + item if remote_path else item
        try:
            attributes = sftp.stat(item_path)
            if stat.S_ISDIR(attributes.st_mode):
                # If it's a directory and the date is within the range,
                # create the corresponding local directory
                # and recursively download its contents
                date_str = item.split('/')[-1]
                if is_valid_date(date_str, start_date, end_date):
                    local_directory = os.path.join(local_path, item)
                    os.makedirs(local_directory, exist_ok=True)
                    files_downloaded = download_files(sftp, item_path, local_directory, start_date, end_date, filters, files_downloaded)
                else:
                    print(f'{item_path} not a valid date assigned or not within filtered dates. Skipping.')
            else:
                # It's a file, download it
                local_file_path = os.path.join(local_path, item)
                if filters and item not in filters:
                    print(f'{local_file_path} does not match filters. Skipping.')
                    continue
                if os.path.exists(local_file_path):
                    os.remove(local_file_path)  # Remove existing file before downloading
                sftp.get(item_path, local_file_path)
                files_downloaded.append(local_file_path)
                print(f'Downloaded: {item_path}')
        except IOError:
            # Error occurred while getting file attributes, skip the item
            print(f'Exception getting file: {item_path}')
    return files_downloaded


class ToastOrders(OrdersProvider):
    """
    Toast order provider.

    This class implements the OrdersProvider interface for the Toast provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.
    This refers Toast data exports: https://central.toasttab.com/s/article/Automated-Nightly-Data-Export-1492723819691
    Data exports retention is only past 30 days from remote client.
    """

    PROVIDER = Provider.TOAST
    LOGIN_URL = 's-9b0f88558b264dfda.server.transfer.us-east-1.amazonaws.com'  # sftp server url
    PRIVATE_KEY_PATH = os.path.expanduser('~/.ssh/id_rsa_toast')
    ORDER_FILENAME_PATTERN = "*.csv"

    def __init__(self, credential_file_path, start_date, end_date, store_name):
        """
        Initialize the ToastOrders provider.
        This provider is to collect POS data for Toast system.

        Args:
            credential_file_path (str): The path to the credential file.
            start_date (datetime.datetime): The start date for retrieving orders.
            end_date (datetime.datetime): The end date for retrieving orders.
            store_name (Store): The name of the store associated with the provider.
        """
        super().__init__(credential_file_path, start_date, end_date, store_name)
        self.ssh_client = None
        self.sftp_session = None

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def login(self):
        """
        Perform the creation of SFTP client for the Toast data export provider.
        """
        # Create an SSH client
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Load the private key
        private_key = paramiko.RSAKey.from_private_key_file(self.PRIVATE_KEY_PATH, password=self.password)

        # Connect to the SFTP server
        ssh_client.connect(hostname=self.LOGIN_URL, username=self.username, pkey=private_key)

        # Create an SFTP session
        self.sftp_session = ssh_client.open_sftp()
        self.ssh_client = ssh_client

    def preprocess_reports(self):
        """
        Preprocess the retrieved orders from the Toast provider.
        """
        pass

    # @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        """
        Format is top level dirs (generally just one), then within them
        each will have folders of format YYYYMMDD.
        Those folders will be the sales day for each day.

        The following report types are available:
            - AccountingReport.xls, AllItemsReport.csv, CashEntries.csv,
            - CheckDetails.csv, HouseAccountExport.csv, KitchenTimings.csv,
            - ItemSelectionDetails.csv, MenuExport.json, MenuExportV2.json,
            - OrderDetails.csv, PaymentDetails.csv, TimeEntries.csv

        We currently only leverage order details and payment details.
        :return:
        """
        # Download All Files From Toast Client
        # list_files(self.sftp_session)
        top_level_dirs = self.sftp_session.listdir()
        for top_lvl_dir in top_level_dirs:
            self.downloaded_files = download_files(
                self.sftp_session,
                remote_path=top_lvl_dir,
                local_path=os.path.join(RAW_REPORTS_PATH, self.PROVIDER.value),
                start_date=self.start_date_dt,
                end_date=self.end_date_dt,
                filters=[
                    DownloadFileType.ORDER_DETAILS,
                    DownloadFileType.PAYMENT_DETAILS
                ]
            )

        print(f"Downloaded file(s): {self.downloaded_files}")

    def get_customers(self):
        payment_details_df = pd.DataFrame()
        for file_path in self.downloaded_files:
            df = pd.read_csv(file_path)
            if file_path.endswith(DownloadFileType.PAYMENT_DETAILS):
                # Read PaymentDetails file and append to payment_details_df
                payment_details_df = pd.concat([payment_details_df, df], ignore_index=True)
        customer_info_df = payment_details_df[['Tab Name', 'Email', 'Phone']]

        def clean_phone_number(phone):
            if pd.notnull(phone):
                # Remove any punctuation characters
                phone = re.sub(r'[^\d]+', '', phone)

                # Check if the phone number starts with "+1" and has 10 digits
                if phone.startswith('1') and len(phone) == 11:
                    phone = phone[1:]  # Strip the "+1" prefix

                return phone

        # Apply the clean_phone_number function to the 'phone_number' column
        # customer_info_df['Phone'] = customer_info_df['Phone'].apply(clean_phone_number)
        customer_info_df.loc[:, 'Phone'] = customer_info_df['Phone'].apply(clean_phone_number)
        customer_info_df = customer_info_df.drop_duplicates()
        print(customer_info_df)
        processed_file_initial = self.create_processed_filename(ReportType.CUSTOMERS, Extensions.CSV)
        customer_info_df.to_csv(processed_file_initial)
        self.processed_files.append(processed_file_initial)
        print(f"Processed customer file(s): {self.processed_files}")

    def postprocess_reports(self):
        """
        Postprocess the retrieved orders from the Toast provider.
        """
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        # Combine All OrderDetails & PaymentDetails files into single dfs
        order_details_df = pd.DataFrame()
        payment_details_df = pd.DataFrame()

        for file_path in self.downloaded_files:
            # Read the file into a dataframe
            df = pd.read_csv(file_path)
            if file_path.endswith(DownloadFileType.ORDER_DETAILS):
                # Read OrderDetails file and append to order_details_df
                order_details_df = pd.concat([order_details_df, df], ignore_index=True)

            if file_path.endswith(DownloadFileType.PAYMENT_DETAILS):
                # Read PaymentDetails file and append to payment_details_df
                payment_details_df = pd.concat([payment_details_df, df], ignore_index=True)

        # Print the resulting dataframes
        print("OrderDetails DataFrame:")
        print(order_details_df)
        print()
        print("PaymentDetails DataFrame:")
        print(payment_details_df)

        # Run some logic to transform both dfs and join them into one
        # Merge the dataframes based on the "Order Id" column
        merged_df = pd.merge(order_details_df, payment_details_df, on="Order Id", how="left", suffixes=('_order', '_payment'))
        filtered_cols = ['Order Id', 'Order #_order', 'Location_order', 'Opened',
                         'Tab Names', 'Dining Options', 'Discount Amount',
                         'Amount_order', 'Tax', 'Tip_order', 'Gratuity_order', 'Total_order',
                         'Voided', 'Paid', 'Source', 'Payment Id', 'Receipt', 'Check Id',
                         'Amount_payment', 'Tip_payment', 'Gratuity_payment', 'Total_payment',
                         'Swiped Card Amount', 'Keyed Card Amount', 'Amount Tendered',
                         'Refunded', 'Refund Date', 'Refund Amount', 'Refund Tip Amount',
                         'Void User', 'Void Approver', 'Void Date', 'Status', 'Type', 'Card Type',
                         'Other Type', 'Email', 'Phone', 'Last 4 Card Digits', 'V/MC/D Fees']
        merged_df = merged_df[filtered_cols]
        print()
        print("Merged DataFrame:")
        print(merged_df)

        processed_file = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV)
        merged_df.to_csv(processed_file)
        self.processed_files.append(processed_file)
        print(f"Processed file(s): {self.processed_files}")

    def standardize_orders_report(self):

        orders_file = [f for f in self.processed_files if ReportType.ORDERS in f][0]
        df = pd.read_csv(orders_file)
        # remove voided orders
        df = df[df['Voided'] == False]
        df = df.drop('Void User', axis=1)
        df = df.drop('Void Approver', axis=1)
        df = df.drop('Void Date', axis=1)
        df = df.drop('Voided', axis=1)
        # remove credit orders where failed running card (DENIED)
        df = df[df['Status'].isin(['CAPTURED', 'AUTHORIZED'])]
        # remove gift card orders as already tracked in total prior
        df = df[df['Type'] != 'Gift Card']
        # add in gratuity into tip
        df['Tip_order'] = df['Tip_order'] + df['Gratuity_order']
        df = df.drop('Gratuity_order', axis=1)
        df['Tip_payment'] = df['Tip_payment'] + df['Gratuity_payment']
        df = df.drop('Gratuity_payment', axis=1)
        # include refund info to be removed from total
        amount_mask = df['Refund Amount'].notnull()
        df.loc[amount_mask, 'Amount_payment'] = np.subtract(df.loc[amount_mask, 'Amount_payment'], df.loc[amount_mask, 'Refund Amount'].abs())
        tip_mask = df['Refund Tip Amount'].notnull()
        df.loc[tip_mask, 'Tip_payment'] = np.subtract(df.loc[tip_mask, 'Tip_payment'], df.loc[tip_mask, 'Refund Tip Amount'].abs())
        df = df.drop('Refunded', axis=1)
        df = df.drop('Refund Date', axis=1)
        df = df.drop('Refund Amount', axis=1)
        df = df.drop('Refund Tip Amount', axis=1)
        # add in column for the taxes for payments (can be spread mult pay)
        df.rename(columns={'Tax': 'Tax_order'}, inplace=True)
        df['Tax_payment'] = (df['Amount_payment'] * TAX_RATE).round(2)
        df['Amount_payment'] = (df['Amount_payment'] / (1 + TAX_RATE)).round(2)
        # add an estimate for delivery charge if the source is delivery
        # add a notes column and add explanation for del charge
        df['Delivery Charge'] = 0  # Initialize column with 0 for all rows
        df['Notes'] = 'Merchant services rates missing. '
        df.loc[df['Dining Options'] == 'Delivery', 'Notes'] += 'Del charge is an estimate'
        # Adjust subtotal of delivery charge

        # Subset DataFrame with dining option as 'delivery'
        delivery_df = df[df['Dining Options'] == 'Delivery']
        # Find the row with the largest amount_subtotal for each order ID
        max_subtotal_rows = delivery_df.groupby('Order Id')['Amount_payment'].idxmax()
        # Add the delivery charge to the 'delivery charge' column for selected rows
        estimated_tip = 3.50
        df.loc[max_subtotal_rows, 'Delivery Charge'] += estimated_tip
        # Subtract the delivery charge from the 'amount_payment' column for selected rows
        df.loc[max_subtotal_rows, 'Amount_payment'] -= estimated_tip

        rename_map = {
            'Payment Id': TransactionRecord.TRANSACTION_ID,
            'Opened': TransactionRecord.ORDER_DATE,
            'Type': TransactionRecord.PAYMENT_TYPE,
            'Amount_payment': TransactionRecord.SUBTOTAL,
            'Tip_payment': TransactionRecord.TIP,
            'Tax_payment': TransactionRecord.TAX,
            'Total_payment': TransactionRecord.TOTAL_BEFORE_FEES,
            'Delivery Charge': TransactionRecord.DELIVERY_CHARGE,
            'V/MC/D Fees': TransactionRecord.MERCHANT_PROCESSING_FEE,
            'Notes': TransactionRecord.NOTES,
        }
        # Get transaction file
        df = standardize_order_report_setup(None, rename_map, self.PROVIDER, self.store, df)

        # Make transaction id column string type
        df[TransactionRecord.TRANSACTION_ID] = df[TransactionRecord.TRANSACTION_ID].astype(str)
        # treat null values as 0 for commission
        df[TransactionRecord.MERCHANT_PROCESSING_FEE] = df[TransactionRecord.MERCHANT_PROCESSING_FEE].fillna(0)
        # Calculate the after fees total
        df[TransactionRecord.TOTAL_AFTER_FEES] = df[TransactionRecord.TOTAL_BEFORE_FEES] - df[TransactionRecord.MERCHANT_PROCESSING_FEE]
        # Calculate payout
        df[TransactionRecord.PAYOUT] = df[TransactionRecord.TOTAL_AFTER_FEES]

        # Write the transformed data to a new CSV file (csv and parquet)
        raw_data_filename = self.create_processed_filename(ReportType.ORDERS, Extensions.CSV, parent_path=DATA_PATH_RAW)
        df.to_csv(raw_data_filename, index=False)
        self.data_files.append(raw_data_filename)
        print(f'Saved {self.store_name} data orders to: {raw_data_filename}. Based off of processed file: {orders_file}.')

    def validate_reports(self):
        """
        Perform report validation specific to the Toast provider.
        """
        ValidationUtils.validate_processed_files_count(self.processed_files, 2)
        # ValidationUtils.validate_downloaded_files_count(self.downloaded_files, 2 * (self.end_date_dt - self.start_date_dt).days)
        ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.CSV)
        ValidationUtils.validate_downloaded_files_extension(self.downloaded_files, Extensions.CSV)
        # data file checking
        ValidationUtils.validate_data_files_count(self.data_files, 1)
        ValidationUtils.validate_data_file_columns_match(self.data_files[0])
        ValidationUtils.validate_data_file_total_before_fees_accurate(self.data_files[0])
        ValidationUtils.validate_data_file_total_after_fees_accurate(self.data_files[0])
        ValidationUtils.validate_data_file_after_fees_payout_match(self.data_files[0])
        print("Report validation successful")

    def upload_reports(self):
        """
        Send the reports to the forwarded xtraChef email
        """
        self.write_parquet_data()

    def quit(self):
        """
        Quit the Toast provider session.
        """
        if self.sftp_session:
            self.sftp_session.close()
        if self.ssh_client:
            self.ssh_client.close()


def main():
    """
    Main entry point for the script.
    """
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    credential_file_path = '../credentials/toast_sftp_credentials.json'
    start_date = datetime(2023, 7, 10)
    end_date = datetime(2023, 7, 10)
    store_name = Store.AROMA

    orders = ToastOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    orders.postprocess_reports()
    # orders.processed_files = ['/Users/ahaidrey/Desktop/acelife/provider_reports/reports_processed/toast_aroma_customers_07_10_2023_07_10_2023.csv', '/Users/ahaidrey/Desktop/acelife/provider_reports/reports_processed/toast_aroma_orders_07_10_2023_07_10_2023.csv']
    orders.standardize_orders_report()
    orders.validate_reports()
    orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
