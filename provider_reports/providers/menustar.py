import datetime
import os
import base64
import json
import re
import time
import pandas as pd
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from provider_reports.providers.base_provider import OrdersProvider
from provider_reports.utils.constants import Provider, Store
from provider_reports.utils.google_drive_utils import authenticate


class MenustarOrders(OrdersProvider):
    """
    The menustar interface does not contain reporting.
    The provider sends us emails of the breakdown; therefore we use
    the email protocols to download the reports and process them.
    We cache the reports locally so do not need to make another API call.
    """

    PROVIDER = Provider.ORDER_INN
    LOGIN_URL = 'https://themenustar.com/backend/merchant/'
    ORDER_FILENAME_PATTERN = "RestData*.csv"

    def __init__(self, credential_file_path, start_date, end_date, store_name):
        """
        Initialize the MenuStar provider.

        Args:
            credential_file_path (str): The path to the credential file.
            start_date (datetime.datetime): The start date for retrieving orders.
            end_date (datetime.datetime): The end date for retrieving orders.
            store_name (Store): The name of the store associated with the provider.
        """
        super().__init__(credential_file_path, start_date, end_date, store_name)
        # Initialize the Gmail API
        self.service = self.initialize_gmail_api(credential_file_path)
        print(self.service)


    def initialize_gmail_api(self, credential_file_path):
        creds = None
        # The file token.json stores the user's access and refresh tokens
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/gmail.readonly'])
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credential_file_path, ['https://www.googleapis.com/auth/gmail.readonly'])
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        # creds = authenticate()
        return build('gmail', 'v1', credentials=creds)



    def login(self):
        pass

    def preprocess_reports(self):
        pass

    def get_orders(self):
        pass

    def postprocess_reports(self):
        pass

    def standardize_orders_report(self):
        pass

    def validate_reports(self):
        pass

    def upload_reports(self):
        pass

    def quit(self):
        pass


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

    orders = MenustarOrders(credential_file_path, start_date, end_date, store_name)
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


    import os.path

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    # If modifying these scopes, delete the file token.json.
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


    def main():
        """Shows basic usage of the Gmail API.
        Lists the user's Gmail labels.
        """
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        credential_file_path = os.path.abspath(
            '../credentials/google_client_secret.json')
        if os.path.exists(credential_file_path):
            creds = Credentials.from_authorized_user_file(credential_file_path, SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credential_file_path, SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(credential_file_path, 'w') as token:
                token.write(creds.to_json())

        try:
            # Call the Gmail API
            service = build('gmail', 'v1', credentials=creds)
            results = service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])

            if not labels:
                print('No labels found.')
                return
            print('Labels:')
            for label in labels:
                print(label['name'])

        except HttpError as error:
            # TODO(developer) - Handle errors from gmail API.
            print(f'An error occurred: {error}')


    if __name__ == '__main__':
        main()
