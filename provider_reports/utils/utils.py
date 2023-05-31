"""Random utility functions."""
import json

from selenium.webdriver.chrome.options import Options

from provider_reports.utils.constants import RAW_REPORTS_PATH, Store


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
