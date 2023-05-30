"""Random utility functions."""
from selenium.webdriver.chrome.options import Options

from provider_reports.utils.constants import RAW_REPORTS_PATH


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
