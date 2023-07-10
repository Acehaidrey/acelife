import glob
import os
import shutil
import stat
import time
from datetime import datetime

import pandas as pd
import paramiko
import retrying

from provider_reports.providers.base_provider import OrdersProvider
from provider_reports.utils.constants import Store, RAW_REPORTS_PATH, Provider, ReportType, Extensions
from provider_reports.utils.validation_utils import ValidationUtils


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


def download_files(sftp, remote_path='', local_path='', start_date=None, end_date=None):
    file_list = sftp.listdir(remote_path)
    for item in file_list:
        item_path = remote_path + '/' + item if remote_path else item
        local_item_path = os.path.join(local_path, item) if local_path else item
        try:
            attributes = sftp.stat(item_path)
            if stat.S_ISDIR(attributes.st_mode):
                # If it's a directory and the date is within the specified range, create the corresponding local directory
                # and recursively download its contents
                date_str = item.split('/')[-1]
                if is_valid_date(date_str, start_date, end_date):
                    local_directory = os.path.join(local_path, item)
                    os.makedirs(local_directory, exist_ok=True)
                    download_files(sftp, item_path, local_directory, start_date, end_date)
            else:
                # It's a file, download it
                local_file_path = os.path.join(local_path, item)
                if os.path.exists(local_file_path):
                    os.remove(local_file_path)  # Remove existing file before downloading
                sftp.get(item_path, local_file_path)
                print(f'Downloaded: {item_path}')
        except IOError:
            # Error occurred while getting file attributes, skip the item
            pass



class ToastOrders(OrdersProvider):
    """
    Toast order provider.

    This class implements the OrdersProvider interface for the Toast provider.
    This refers Toast data exports: https://central.toasttab.com/s/article/Automated-Nightly-Data-Export-1492723819691
    Data exports retention is only past 30 days.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.
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

    # @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        """
        Format is top level dirs (generally just one), then within them each will have folders of format YYYYMMDD.
        Those folders will be the sales day for each day.
        :return:
        """
        top_level_dirs = self.sftp_session.listdir()
        for top_lvl_dir in top_level_dirs:
            download_files(self.sftp_session, top_lvl_dir, os.path.join(RAW_REPORTS_PATH, 'toast'))



        # print(f"Downloaded file(s): {self.downloaded_files}")
        # list_files(self.sftp_session)

    def preprocess_reports(self):
        """
        Preprocess the retrieved orders from the Toast provider.
        """
        pass

    def postprocess_reports(self):
        """
        Postprocess the retrieved orders from the Toast provider. Only expect one file.
        """
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        for downloaded_file in self.downloaded_files:
            processed_file_initial = self.create_processed_filename(ReportType.INVOICES, Extensions.CSV)
            downloaded_file_short_name = downloaded_file.lower().split('/')[-1]
            processed_file = processed_file_initial.strip('.' + Extensions.CSV) + f'_{downloaded_file_short_name}'
            shutil.copy(downloaded_file, processed_file)
            self.processed_files.append(processed_file)
            print(f'Saved {self.store_name} invoices to: {processed_file}')

        print(f"Processed file(s): {self.processed_files}")

    def validate_reports(self):
        """
        Perform report validation specific to the Toast provider.
        """
        ValidationUtils.validate_processed_files_count(self.processed_files, self.number_of_invoice_rows)
        ValidationUtils.validate_downloaded_files_count(self.downloaded_files, self.number_of_invoice_rows)
        ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.CSV)
        ValidationUtils.validate_downloaded_files_extension(self.downloaded_files, Extensions.CSV)
        print("Report validation successful")

    def upload_reports(self):
        """
        Send the reports to the forwarded xtraChef email
        """
        pass

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
    start_date = datetime(2023, 5, 1)
    end_date = datetime(2023, 5, 30)
    store_name = Store.AROMA

    orders = ToastOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    # orders.postprocess_reports()
    # orders.validate_reports()
    # orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
