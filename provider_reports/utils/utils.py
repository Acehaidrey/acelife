"""Random utility functions."""
import json
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
from selenium.webdriver.chrome.options import Options

from provider_reports.schema.schema import TransactionRecord
from provider_reports.utils.constants import RAW_REPORTS_PATH, Store, CREDENTIALS_PATH, SENDER_EMAIL


def get_chrome_options():
    options = Options()
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--disable-extensions')
    options.add_experimental_option('prefs', {
        'download.default_directory': RAW_REPORTS_PATH,
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
        'safebrowsing.enabled': False
    })
    if os.getenv('GCP_ENV', 'false') == 'true':
        options.add_argument("--headless")  # Run Chrome in headless mode
        options.add_argument("--no-sandbox")  # Disable sandbox mode
    return options


def get_store_names_from_credentials_file(credential_file, filtered_names=None):
    # Load the JSON data from file
    with open(credential_file) as f:
        data = json.load(f)

    # Extract the store names from the JSON data
    store_names = [store['name'] for store in data['stores']]
    if filtered_names:
        # Filter store_names based on filtered_names list
        store_names = [name.lower() for name in store_names if name.lower() in filtered_names]

    return [Store[store_name.upper()] for store_name in store_names]


def get_email_password(credential_file=os.path.join(CREDENTIALS_PATH, 'google_app_credentials.json')):
    # Load the JSON data from file
    with open(credential_file) as f:
        data = json.load(f)

    return data['password']


def send_email(subject, body, recipients, attachments=None):
    # Create a multipart message
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = ','.join(recipients)
    msg['Subject'] = subject

    # Attach the message to the email
    msg.attach(MIMEText(body, 'plain'))

    if attachments:
        # Attach files
        for file_path in attachments:
            with open(file_path, 'rb') as file:
                attachment = MIMEApplication(file.read(), Name=file_path)
                attachment['Content-Disposition'] = f'attachment; filename="{file_path}"'
                msg.attach(attachment)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp_server:
        smtp_server.login(SENDER_EMAIL, get_email_password())
        smtp_server.sendmail(SENDER_EMAIL, recipients, msg.as_string())
        print("Message sent!")


def standardize_order_report_setup(orders_file, rename_map, provider, store):
    """
    Helper function to clean up a processed file to look like a standard
    report. It will get the order report, lowercase all strings,
    rename columns, remove unnecessary columns, add default columns,
    and add in missing columns then reorder them.
    """

    # Read the provider's CSV file using Pandas
    df = pd.read_csv(orders_file)

    if rename_map:
        # Apply column renaming based on the YAML rename map
        for old_name, new_name in rename_map.items():
            if old_name in df.columns:
                df.rename(columns={old_name: new_name}, inplace=True)

        # Filter out columns not defined in the column schema
        df = df[rename_map.values()]

    # add in provider and store
    df[TransactionRecord.PROVIDER] = provider.value
    df[TransactionRecord.STORE] = store.value

    # Validate and enforce the column schema
    for column, dtype in TransactionRecord.COLUMN_TYPE_MAPPING.items():
        if dtype == 'timestamp':
            dtype = 'datetime64[ns]'
        if column not in df.columns:
            if dtype == 'float':
                df[column] = 0.0
            else:
                df[column] = None
        df[column] = df[column].astype(dtype)

    # lowercase all strings
    df = df.applymap(lambda x: x.lower() if isinstance(x, str) else x)

    # Reindex the columns to the desired order
    # (may have extra cols to keep but will need to merge them before valid)
    extra_columns = [col for col in df.columns if
                     col not in TransactionRecord.get_column_names()]
    df = df[TransactionRecord.get_column_names() + extra_columns]
    return df
