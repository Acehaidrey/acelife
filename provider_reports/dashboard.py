import os

import duckdb
import pandas as pd
import streamlit as st


class ProviderDashboard:
    """
    A class to create an Open House Dashboard using Streamlit and DuckDB.

    Attributes:
        data_path (str): The path to the cleaned open house data in Parquet format.
    """

    def __init__(self, data_path):
        """
        Initialize the OpenHouseDashboard with the path to the cleaned open house data.

        Args:
            data_path (str): The path to the cleaned open house data in Parquet format.
        """
        self.data_path = data_path
        self.df = pd.read_parquet(data_path)
        self.con = duckdb.connect(database=':memory:', read_only=False)
        self.con.register("orders", self.df)

    def _query(self, sql):
        """
        Execute an SQL query and return the result as a pandas DataFrame.

        Args:
            sql (str): The SQL query to execute.

        Returns:
            pandas.DataFrame: The result of the SQL query.
        """
        return self.con.execute(sql).df()

    # @staticmethod
    # def get_week_most_open_houses_query():
    #     most_open_houses_week = '''
    #     SELECT
    #       DATE_PART('week', CAST(OpenHouseDate AS DATE)) AS Week,
    #       MIN(DATE_TRUNC('week', CAST(OpenHouseDate AS DATE))) AS StartOfWeek,
    #       MIN(DATE_TRUNC('week', CAST(OpenHouseDate AS DATE)) + INTERVAL '6 days') AS EndOfWeek,
    #       COUNT(*) AS OpenHouseCount
    #     FROM
    #       openhouses
    #     GROUP BY
    #       Week
    #     ORDER BY
    #       OpenHouseCount DESC
    #     LIMIT 1
    #     '''
    #     return most_open_houses_week
    #
    # @staticmethod
    # def get_top_zip_codes_query(n=5):
    #     top_5_zip_codes = f'''
    #     SELECT
    #       SUBSTRING(Zipcode, 1, 5) AS Zipcode, COUNT(*) AS OpenHouseCount
    #     FROM
    #       openhouses
    #     GROUP BY
    #       1
    #     ORDER BY
    #       OpenHouseCount DESC
    #     LIMIT {n}
    #     '''
    #     return top_5_zip_codes
    #
    # @staticmethod
    # def get_daily_cumulative_total_query():
    #     daily_cumulative_total = '''
    #     SELECT
    #       OpenHouseDate,
    #       SUM(CountPerDay) OVER (ORDER BY OpenHouseDate) AS daily_cumulative_total
    #     FROM (
    #       SELECT
    #         OpenHouseDate,
    #         COUNT(*) AS CountPerDay
    #       FROM
    #         openhouses
    #       GROUP BY
    #         OpenHouseDate
    #     )
    #     '''
    #     return daily_cumulative_total

    def display_dashboard(self):
        """
        Display the Open House Dashboard using Streamlit components.
        """
        st.title('Store Partner Finance Dashboard')

        # Week with the most open houses
        most_open_houses_week = self.get_week_most_open_houses_query()
        most_open_houses_week_df = self._query(most_open_houses_week)
        # print(most_open_houses_week_df)
        st.subheader('Week with the Most Open Houses')
        st.write(most_open_houses_week_df)

        # Top-5 zip codes with the most open houses
        top_5_zip_codes = self.get_top_zip_codes_query()
        top_5_zip_codes_df = self._query(top_5_zip_codes)
        # print(top_5_zip_codes_df)
        st.subheader('Top-5 Zip Codes with the Most Open Houses')
        st.write(top_5_zip_codes_df)

        # Daily cumulative total of open houses over time
        daily_cumulative_total = self.get_daily_cumulative_total_query()
        daily_cumulative_total_df = self._query(daily_cumulative_total)
        # print(daily_cumulative_total_df)
        st.subheader('Daily Cumulative Total of Open Houses Over Time')
        st.line_chart(daily_cumulative_total_df, y="daily_cumulative_total", x="OpenHouseDate")

    def close(self):
        """
        Close the DuckDB connection.
        """
        self.con.close()


if __name__ == '__main__':
    # Example usage - if no parquet_short_path call processor first to setup
    here = os.path.abspath(os.path.dirname(__file__))
    parquet_short_path = 'data/optimized/'
    full_path = os.path.abspath(os.path.join(here, parquet_short_path))
    dashboard = ProviderDashboard(full_path)
    # dashboard.display_dashboard()
    df = dashboard._query('select * from providers')
    print(df)
    dashboard.close()
