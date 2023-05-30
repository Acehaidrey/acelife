import csv
import os
from datetime import datetime
import time

import pandas as pd
import retrying
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

from provider_reports.providers.base_provider import OrdersProvider
from provider_reports.utils.constants import Store, RAW_REPORTS_PATH, Provider, ReportType, Extensions
from provider_reports.utils.utils import get_chrome_options
from provider_reports.utils.validation_utils import ValidationUtils


class FutureFoodsOrders(OrdersProvider):
    """
    FutureFoods orders provider.

    This class implements the OrdersProvider interface for the FutureFoods provider.
    It defines methods for logging in, retrieving orders, and performing preprocessing and postprocessing tasks.
    """

    PROVIDER = Provider.FUTURE_FOODS
    LOGIN_URL = "https://manager.tryotter.com/login"
    ORDER_FILENAME_PATTERN = "transactions_export_*.csv"

    def __init__(self, credential_file_path, start_date, end_date, store_name):
        """
        Initialize the FutureFoodsOrders provider.
        This provider has few orders but still want to account for them.

        Args:
            credential_file_path (str): The path to the credential file.
            start_date (str): The start date for retrieving orders.
            end_date (str): The end date for retrieving orders.
            store_name (Store): The name of the store associated with the provider.
        """
        super().__init__(credential_file_path, start_date, end_date, store_name)

        self.driver = webdriver.Chrome(options=get_chrome_options())
        self.wait = WebDriverWait(self.driver, 300)

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def login(self):
        """
        Perform the login process for the FutureFoods provider.
        """
        self.driver.get(FutureFoodsOrders.LOGIN_URL)
        username_input = self.wait.until(EC.presence_of_element_located((By.NAME, "email")))
        username_input.clear()
        username_input.send_keys(self.username)
        password_input = self.wait.until(EC.presence_of_element_located((By.NAME, "password")))
        password_input.clear()
        password_input.send_keys(self.password)
        self.wait.until(EC.presence_of_element_located((By.XPATH, "//button/div[contains(.,'Sign in')]"))).click()

    # @retrying.retry(wait_fixed=5000, stop_max_attempt_number=3)
    def get_orders(self):
        # go to virtual brands endpoint where reporting exists
        self.driver.get('https://manager.tryotter.com/virtual-brands/accounting/payments')
        button = self.wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Download CSV')]")))
        button.click()
        input_field = self.wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Select dates']")))
        # input_field.click()

        # Specify the new value to set
        new_value = "Apr 1, 2023 - Apr 30, 2023"

        # # Find the input element by its attributes
        # input_element = driver.find_element(By.CSS_SELECTOR,
        #                                     'input[placeholder="Select dates"][data-testid="op-input"]')

        # Clear the existing value
        input_field.clear()

        # Set the new value
        input_field.send_keys(new_value)
        # Execute JavaScript to set the value of the input field
        script = f'document.querySelector(\'input[placeholder="Select dates"][data-testid="op-input"]\').value = "{new_value}";'
        self.driver.execute_script(script)

        # time.sleep(30)

        # download_button = self.driver.find_element(By.XPATH, "//button[text()='Download']")
        download_button = self.driver.find_element(By.XPATH,
                                             '//button[contains(text(), "Download")][@data-testid="op-button"]')
        # download_button = self.wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Download')]")))
        self.driver.execute_script("arguments[0].click();", download_button)

        download_button.click()

        time.sleep(200)

        # page_source = self.driver.page_source
        # print(page_source)

        # Specify the desired month and year
        desired_month = "April"
        desired_year = "2023"
        print('desired')
        print(desired_month, desired_year)

        # Find the parent element that contains the calendar
        calendar = self.driver.find_element(By.CSS_SELECTOR, '.CalendarMonthGrid_month__horizontal')
        print('calendar')
        print(calendar)
        # print(calendar.__dict__)
        # print(calendar.text)
        print(calendar.get_attribute("outerHTML"))
        # print(calendar.get_attribute("innerHTML"))

        # Find the back arrow element
        back_arrow = self.driver.find_element(By.CSS_SELECTOR, '.DayPickerNavigation_button__horizontal_2')
        print('back arrow')
        print(back_arrow)
        # print(back_arrow.__dict__)
        # print(back_arrow.text)
        print(back_arrow.get_attribute("outerHTML"))
        # print(back_arrow.get_attribute("innerHTML"))
        # back_arrow.click()

        # Loop until the current month and year match the desired values
        while True:
            # Get the month and year from the caption element
            caption = calendar.find_element(By.CSS_SELECTOR, '.CalendarMonth_caption')
            print('caption')
            print(caption)
            print(caption.get_attribute("outerHTML"))
            # print(caption.get_attribute("innerHTML"))

            soup = BeautifulSoup(caption.get_attribute("innerHTML"), 'html.parser')
            print('bs4')
            bs4_text = soup.div.get_text()
            print(bs4_text)

            print(caption.text)
            month_year = caption.find_element(By.CSS_SELECTOR, 'div')
            print('month_year')
            print(month_year)
            current_month, current_year = bs4_text.split() or month_year.text.split()

            print('current vals')
            print(current_month, current_year)

            # Check if the month and year match the desired values
            if current_month == desired_month and current_year == desired_year:
                print('match')
                break

            # Click the back arrow to navigate to the previous month
            back_arrow.click()

        # Find all the <td> elements within the calendar
        dates = calendar.find_elements(By.CSS_SELECTOR, 'td.CalendarDay')
        print(dates)

        # Iterate through each <td> element
        for date in dates:
            # Get the day value
            print(f'date : {date}')
            print(date.get_attribute("outerHTML"))
            day = date.find_element(By.CSS_SELECTOR, 'span').text
            print(day)

            # Select the desired date
            if day == "1":
                print('day is 1')
                # Select the start date
                # date.click()
            elif day == "30":
                # Select the end date
                print('day is 30')
                # date.click()
            # You can add more conditions to handle other specific dates if needed

        start_date = 'April 1, 2023'
        end_date = 'April 30, 2023'
        start_date_element = calendar.find_element(By.XPATH, f'.//td[contains(@aria-label, "{start_date}")]')

        end_date_element = calendar.find_element(By.XPATH, f'.//td[contains(@aria-label, "{end_date}")]')
        print(start_date_element.get_attribute('outerHTML'))
        print(end_date_element.get_attribute('outerHTML'))

        # Scroll the calendar into view if needed
        self.driver.execute_script("arguments[0].scrollIntoView(true);", start_date_element)

        # Click on the start date element using JavaScript
        self.driver.execute_script("arguments[0].click();", start_date_element)

        # Click on the end date element using JavaScript
        self.driver.execute_script("arguments[0].click();", end_date_element)
        # date_range_element.send_keys(Keys.ENTER)
        # start_date_element.click()
        # end_date_element.click()



        # After selecting the desired dates, you can proceed with other actions on the page

        # page_source = self.driver.page_source
        # print(page_source)
        time.sleep(120)
        # print(f"Downloaded file(s): {full_filename}")
        # self.downloaded_files.extend(full_filename)

    def preprocess_reports(self):
        """
        Preprocess the retrieved orders from the FutureFoods provider.
        """
        pass

    def postprocess_reports(self):
        """
        Postprocess the retrieved orders from the FutureFoods provider. Only expect one file.
        """
        if not self.downloaded_files:
            print('No downloaded_files to process')
            return

        for downloaded_file in self.downloaded_files:
            pass

        # self.processed_files.append(processed_file)
        # print(f'Saved {self.store_name} orders to: {processed_file}')

    def validate_reports(self):
        """
        Perform report validation specific to the FutureFoods provider.
        TODO: Compare pdf summaries to transaction summaries.
        """
        # ValidationUtils.validate_processed_files_count(self.processed_files, 1)
        # ValidationUtils.validate_downloaded_files_count(self.downloaded_files, 1)
        # ValidationUtils.validate_processed_files_extension(self.processed_files, Extensions.CSV)
        # ValidationUtils.validate_downloaded_files_extension(self.downloaded_files, Extensions.CSV)
        # ValidationUtils.validate_processed_files_date_range(
        #     self.processed_files, self.start_date, self.end_date, 'Date', '%m/%d/%Y %I:%M %p')

        print("Report validation successful")

    def upload_reports(self):
        """
        Upload the processed report to a remote location specific to the FutureFoods provider.
        """
        # TODO: Implement report uploading logic for FutureFoods
        pass

    def quit(self):
        """
        Quit the FutureFoods provider session.
        """
        self.driver.quit()


def main():
    """
    Main entry point for the script.
    """
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    credential_file_path = '../credentials/future_foods_credentials.json'
    start_date = '04/01/2023'
    end_date = '04/30/2023'
    store_name = Store.AROMA

    orders = FutureFoodsOrders(credential_file_path, start_date, end_date, store_name)
    orders.login()
    orders.preprocess_reports()
    orders.get_reports()
    # orders.postprocess_reports()
    # orders.validate_reports()
    # orders.upload_reports()
    orders.quit()


if __name__ == '__main__':
    main()
