import os

import numpy as np
import pandas as pd

from provider_reports.schema.schema import TransactionRecord


class ValidationUtils:
    @staticmethod
    def validate_downloaded_files_count(downloaded_files, expected_count):
        """
        Validate the downloaded files.

        Args:
            downloaded_files (list): List of downloaded files.
            expected_count (int): Expected number of files.

        Raises:
            AssertionError: If the number of files is invalid
        """
        if len(downloaded_files) != expected_count:
            raise AssertionError(
                f"Expected {expected_count} downloaded file(s), but found {len(downloaded_files)}")

    @staticmethod
    def validate_processed_files_count(processed_files, expected_count):
        """
        Validate the processed files.

        Args:
            processed_files (list): List of processed files.
            expected_count (int): Expected number of files.

        Raises:
            AssertionError: If the number of files is invalid
        """
        if len(processed_files) != expected_count:
            raise AssertionError(
                f"Expected {expected_count} processed file(s), but found {len(processed_files)}")

    @staticmethod
    def validate_data_files_count(data_files, expected_count):
        """
        Validate the data files.

        Args:
            data_files (list): List of data files.
            expected_count (int): Expected number of files.

        Raises:
            AssertionError: If the number of files is invalid
        """
        if len(data_files) != expected_count:
            raise AssertionError(
                f"Expected {expected_count} processed file(s), but found {len(data_files)}")

    @staticmethod
    def validate_downloaded_files_extension(downloaded_files, extension):
        """
        Validate the extensions of downloaded files.

        Args:
            downloaded_files (list): List of downloaded files.
            extension (str): Acceptable extension.

        Raises:
            AssertionError: If the extensions of files are incorrect.
        """
        for file_path in downloaded_files:
            if not os.path.isfile(file_path) or not file_path.endswith(extension):
                raise AssertionError(f"Downloaded file does not exist or has an invalid extension: {file_path}")

    @staticmethod
    def validate_processed_files_extension(processed_files, extension):
        """
        Validate the extensions of processed files.

        Args:
            processed_files (list): List of processed files.
            extension (str): Acceptable extension.

        Raises:
            AssertionError: If the extensions of files are incorrect.
        """
        # Perform validation on processed file extensions
        for file_path in processed_files:
            if not os.path.isfile(file_path) or not file_path.endswith(extension):
                raise AssertionError(f"Processed file does not exist or has an invalid extension: {file_path}")

    @staticmethod
    def validate_processed_files_date_range(processed_files, start_date, end_date, date_column_name, date_format):
        """
        Validate the date column in processed files is within the specified date range.

        Args:
            processed_files (list): List of processed files.
            start_date (str): Start date of the range.
            end_date (str): End date of the range.
            date_column_name (str): Date column name in csv to check against
            date_format (str): Date format of the column to check against

        Raises:
            AssertionError: If any date in the processed files is outside the specified range.
        """
        for processed_file in processed_files:
            processed_df = pd.read_csv(processed_file)

            start_date = pd.to_datetime(start_date, format='%m/%d/%Y')
            end_date = pd.to_datetime(end_date, format='%m/%d/%Y').replace(hour=23, minute=59, second=59)
            delivery_dates = pd.to_datetime(processed_df[date_column_name], format=date_format)

            if not ((delivery_dates >= start_date) & (delivery_dates <= end_date)).all():
                raise AssertionError("Dates in the processed file are not within the specified range")

    @staticmethod
    def validate_data_file_columns_match(data_file):
        """
        Validate the raw data file columns match all columns.
        Also check formatting of fee columns to all be 0 or negative.

        Args:
            data_file (str): Filename

        Raises:
            AssertionError: If the columns have a mismatch.
        """
        order_columns = TransactionRecord.get_column_names()
        orders_df = pd.read_csv(data_file)
        df_columns = orders_df.columns.tolist()
        if not df_columns == order_columns:
            raise AssertionError(f'Standardized data columns mismatch: {df_columns}, {order_columns}')
        for fee_col in TransactionRecord.get_fee_column_names():
            is_negative_or_zero = (orders_df[fee_col] <= 0).all()
            if not is_negative_or_zero:
                raise AssertionError(f'column {fee_col} has positive values')


    @staticmethod
    def validate_processed_records_data_records_match(data_file, processed_file):
        """
        Validate the raw data file columns match number records of processed file.

        Args:
            data_file (str): Filename
            processed_file (str): Filename

        Raises:
            AssertionError: If the length have a mismatch.
        """
        orders_df = pd.read_csv(data_file)
        processed_df = pd.read_csv(processed_file)
        if not len(orders_df) == len(processed_df):
            raise AssertionError(
                f'Standardized data length differs from processed file '
                f'length: {len(orders_df)}, {len(processed_df)}')

    @staticmethod
    def validate_data_file_total_before_fees_accurate(data_file):
        """
        Validate that the TOTAL_BEFORE_FEES column is the sum of the
        corresponding columns (SUBTOTAL, TIP, TAX, and DELIVERY_CHARGE).

        Args:
            data_file (str): Filename

        Raises:
            AssertionError: If the columns have a mismatch.
        """
        orders_df = pd.read_csv(data_file)
        # Calculate the expected total before fees
        expected_total_before_fees = orders_df[
            [TransactionRecord.SUBTOTAL,
             TransactionRecord.TIP,
             TransactionRecord.TAX,
             TransactionRecord.DELIVERY_CHARGE]
        ].sum(axis=1)
        # Check if the calculated total before fees matches the column value
        # atol=0.05 sets the tolerance to 5 cents (adjust as needed)
        is_total_before_fees_match = np.isclose(
            orders_df[TransactionRecord.TOTAL_BEFORE_FEES],
                                                expected_total_before_fees,
                                                atol=0.05)

        # Verify that all rows have the matching total before fees
        if not is_total_before_fees_match.all():
            raise AssertionError(f'{TransactionRecord.TOTAL_BEFORE_FEES} column mismatch calculation')

    @staticmethod
    def validate_data_file_total_after_fees_accurate(data_file):
        """
        Validate that the TOTAL_AFTER_FEES column is the
        difference between TOTAL_BEFORE_FEES and the corresponding columns
        (SERVICE_FEE, MARKETING_FEE, ADJUSTMENT_FEE,
        MERCHANT_PROCESSING_FEE, and COMMISSION_FEE)

        Args:
            data_file (str): Filename

        Raises:
            AssertionError: If the columns have a mismatch.
        """
        orders_df = pd.read_csv(data_file)
        # Calculate the expected total after fees
        expected_total_after_fees = \
            orders_df[TransactionRecord.TOTAL_BEFORE_FEES] + \
            orders_df[[TransactionRecord.SERVICE_FEE,
             TransactionRecord.MARKETING_FEE,
             TransactionRecord.ADJUSTMENT_FEE,
             TransactionRecord.MERCHANT_PROCESSING_FEE,
             TransactionRecord.COMMISSION_FEE]].sum(axis=1)
        # Check if the calculated total after fees matches the column value
        # atol=0.05 sets the tolerance to 5 cents (adjust as needed)
        is_total_after_fees_match = np.isclose(orders_df[TransactionRecord.TOTAL_AFTER_FEES],
                                               expected_total_after_fees,
                                               atol=0.05)

        # Verify that all rows have the matching total before fees
        if not is_total_after_fees_match.all():
            raise AssertionError(f'{TransactionRecord.TOTAL_AFTER_FEES} column mismatch calculation')

    @staticmethod
    def validate_data_file_after_fees_payout_match(data_file):
        """
        Validate the payout amount matches the after fees amount.
        If not we should be alerting the provider for incorrect payout.
        Note, cash orders for non POS systems will be counted as 0.

        Args:
            data_file (str): Filename

        Raises:
            AssertionError: If the columns have a mismatch.
        """
        orders_df = pd.read_csv(data_file)
        is_cash = orders_df[TransactionRecord.PAYMENT_TYPE].eq('cash')
        payout_expected = np.where(is_cash, 0, orders_df[TransactionRecord.TOTAL_AFTER_FEES])
        payout_match = np.isclose(payout_expected,
                                  orders_df[TransactionRecord.PAYOUT],
                                  atol=0.05)
        if not payout_match.all():
            raise AssertionError(
                f'{TransactionRecord.TOTAL_AFTER_FEES}, {TransactionRecord.PAYOUT} value mismatch calculation')

    @staticmethod
    def validate_all_data_file_checks(data_file, processed_file):
        """Wrapper around all data checks."""
        ValidationUtils.validate_data_file_columns_match(data_file)
        ValidationUtils.validate_processed_records_data_records_match(data_file, processed_file)
        ValidationUtils.validate_data_file_total_before_fees_accurate(data_file)
        ValidationUtils.validate_data_file_total_after_fees_accurate(data_file)
        ValidationUtils.validate_data_file_after_fees_payout_match(data_file)
