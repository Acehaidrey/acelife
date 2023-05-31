import json
import os
from abc import ABC, abstractmethod

from provider_reports.utils.constants import PROCESSED_REPORTS_PATH, Provider


class OrdersProvider(ABC):
    """
    Interface for orders providers.

    This class serves as a base interface for different orders providers. It defines common methods that need to be
    implemented by specific provider classes.

    The expected lifecycle interaction with this class is:
                        login()
                        preprocess_reports()
                        get_reports()
                        postprocess_orders()
                        validate_reports()
                        upload_reports()
                        quit()


    Attributes:
        username (str): The username or account ID used for authentication.
        password (str): The password used for authentication.
        start_date (str): The start date for retrieving orders.
        end_date (str): The end date for retrieving orders.
        store_name (Store): The name of the store associated with the provider (optional).
    """

    PROVIDER: Provider = None
    LOGIN_URL = None
    ORDER_FILENAME_PATTERN = None
    CUSTOMER_FILENAME_PATTERN = None

    def __init__(self, credential_file_path, start_date, end_date, store_name=None):
        """
        Initialize the OrdersProvider.

        Args:
            credential_file_path (str): The path to the credential file.
            start_date (datetime.datetime): The start date for retrieving orders.
            end_date (datetime.datetime): The end date for retrieving orders.
            store_name (Store, optional): The name of the store associated with the provider.
        """
        self.start_date_dt = start_date
        self.end_date_dt = end_date
        self.start_date = self.start_date_dt.strftime('%m/%d/%Y')
        self.end_date = self.end_date_dt.strftime('%m/%d/%Y')
        self.store_name = store_name.value.title()
        self.load_credentials(credential_file_path)
        self.downloaded_files = []
        self.processed_files = []

    def load_credentials(self, credential_file_path):
        """
        Load the credentials from the given credential file path.

        Args:
            credential_file_path (str): The path to the credential file.
        """
        with open(credential_file_path, 'r') as f:
            credentials = json.load(f)

        if self.store_name:
            for store in credentials['stores']:
                if store['name'] == self.store_name:
                    self.username = store['username']
                    self.password = store['password']
                    break
        else:
            self.username = credentials['stores'][0]['username']
            self.password = credentials['stores'][0]['password']

    def create_processed_filename(self, report_type, ext, store=None):
        sdate = self.start_date.replace('/', '_')
        edate = self.end_date.replace('/', '_')
        provider_name = self.PROVIDER.value.lower()
        sname = store.lower() if store else self.store_name.lower()
        report_filename = f'{provider_name}_{sname}_{report_type}_{sdate}_{edate}.{ext}'
        return os.path.join(PROCESSED_REPORTS_PATH, report_filename)

    @abstractmethod
    def login(self):
        """
        Perform the login process specific to the provider.
        """
        pass

    @abstractmethod
    def preprocess_reports(self):
        """
        Preprocess the retrieved reports specific to the provider.
        """
        pass

    def get_reports(self):
        """
        Retrieve the reports specific to the provider.
        """
        self.get_orders()
        self.get_customers()

    @abstractmethod
    def get_orders(self):
        """
        Retrieve the orders info specific to the provider.
        This function is expected to append to self.downloaded_files.
        """
        pass

    def get_customers(self):
        """
        Retrieve the customers info specific to the provider.
        This function is expected to append to self.downloaded_files.
        """
        pass

    @abstractmethod
    def postprocess_reports(self):
        """
        Postprocess the retrieved reports specific to the provider.
        This function is expected to append to self.processed_files.
        See create_processed_filename for naming convention.
        """
        pass

    @abstractmethod
    def validate_reports(self):
        """
        Perform report validation specific to the provider.
        """
        pass

    @abstractmethod
    def upload_reports(self):
        """
        Upload the processed reports to a remote location specific to the provider.
        See validation_utils.py for common check cases.
        """
        pass

    @abstractmethod
    def quit(self):
        """
        Perform cleanup and quit the provider-specific session or connection.
        """
        pass
