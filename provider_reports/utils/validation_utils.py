import os

import pandas as pd


class ValidationUtils:
    @staticmethod
    def validate_downloaded_files_count(downloaded_files, expected_count):
        """
        Validate the downloaded files.

        Args:
            downloaded_files (list): List of downloaded files.
            expected_count (int): Expected number of files.

        Raises:
            ValueError: If the number of files is invalid
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
            ValueError: If the number of files is invalid
        """
        if len(processed_files) != expected_count:
            raise AssertionError(
                f"Expected {expected_count} processed file(s), but found {len(processed_files)}")

    @staticmethod
    def validate_downloaded_files_extension(downloaded_files, extension):
        """
        Validate the extensions of downloaded files.

        Args:
            downloaded_files (list): List of downloaded files.
            extension (str): Acceptable extension.

        Raises:
            ValueError: If the extensions of files are incorrect.
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
            ValueError: If the extensions of files are incorrect.
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
