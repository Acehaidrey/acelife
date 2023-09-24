import os

import duckdb
import pandas as pd
import streamlit as st
import plotly.express as px


class ProviderDashboard:
    """
    A class to create a Finance Dashboard using Streamlit and DuckDB.

    Attributes:
        data_dir (str): The path to the cleaned open house data in Parquet format.
    """

    def __init__(self, data_dir):
        """
        Initialize the StoreFinanceDashboard with the path to the cleaned data.

        Args:
            data_dir (str): The path to the cleaned finance data in Parquet format.
        """
        self.data_dir = data_dir
        self.df = self.concatenate_dataframes_from_directory()
        self.con = duckdb.connect(database=':memory:', read_only=False)
        self.con.register("orders", self.df)

    def concatenate_dataframes_from_directory(self):
        """
        Given the data_path, combines all files within its structure into
        a single directory.
        :return:
        """

        # Get a list of all files in the directory
        file_list = os.listdir(self.data_dir)

        # Initialize an empty list to store DataFrames
        df_list = []

        # Loop through each file and read it as a DataFrame
        for file_name in file_list:
            file_path = os.path.join(self.data_dir, file_name)

            # Check if the file ending is ".parquet"
            if file_name.lower().endswith('.parquet'):
                df = pd.read_parquet(file_path)
            elif file_name.lower().endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                # Skip files with unsupported extensions
                continue

            df_list.append(df)

        # Concatenate all DataFrames into a single DataFrame
        concatenated_df = pd.concat(df_list, ignore_index=True)

        return concatenated_df

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

        df = self.df

        # Sidebar to select the month and year
        selected_month = st.sidebar.selectbox('Select Month',
                                              df['order_date'].dt.strftime(
                                                  '%B').unique())
        selected_year = st.sidebar.selectbox('Select Year',
                                             df['order_date'].dt.strftime(
                                                 '%Y').unique())

        # Filter the data by the selected month and year
        filtered_df = df[
            (df['order_date'].dt.strftime('%B') == selected_month) &
            (df['order_date'].dt.strftime('%Y') == selected_year)
            ]

        # Display the total aggregated amounts for each store
        st.subheader(
            f'Total Aggregated Amounts for Each Store in {selected_month} {selected_year}')
        store_totals = filtered_df.groupby('store')[
            'total_after_fees'].sum().reset_index()
        st.dataframe(store_totals)

        # Plot the daily totals aggregated per store
        st.subheader(
            f'Daily Totals Aggregated per Store in {selected_month} {selected_year}')
        daily_totals_chart = px.line(filtered_df, x='order_date',
                                     y='total_after_fees', color='store',
                                     title='Daily Totals Aggregated per Store')
        st.plotly_chart(daily_totals_chart)

        # Plot the daily totals for each provider on one plot
        st.subheader(
            f'Daily Totals for Each Provider in {selected_month} {selected_year}')
        daily_totals_by_provider_chart = px.line(filtered_df, x='order_date',
                                                 y='total_after_fees',
                                                 color='provider',
                                                 title='Daily Totals by Provider')
        st.plotly_chart(daily_totals_by_provider_chart)

        # Plot the monthly totals for each provider
        st.subheader(
            f'Monthly Totals for Each Provider in {selected_month} {selected_year}')
        monthly_totals_by_provider_chart = px.bar(filtered_df, x='provider',
                                                  y='total_after_fees',
                                                  title='Monthly Totals by Provider')
        st.plotly_chart(monthly_totals_by_provider_chart)



        # # Week with the most open houses
        # most_open_houses_week = self.get_week_most_open_houses_query()
        # most_open_houses_week_df = self._query(most_open_houses_week)
        # # print(most_open_houses_week_df)
        # st.subheader('Week with the Most Open Houses')
        # st.write(most_open_houses_week_df)
        #
        # # Top-5 zip codes with the most open houses
        # top_5_zip_codes = self.get_top_zip_codes_query()
        # top_5_zip_codes_df = self._query(top_5_zip_codes)
        # # print(top_5_zip_codes_df)
        # st.subheader('Top-5 Zip Codes with the Most Open Houses')
        # st.write(top_5_zip_codes_df)
        #
        # # Daily cumulative total of open houses over time
        # daily_cumulative_total = self.get_daily_cumulative_total_query()
        # daily_cumulative_total_df = self._query(daily_cumulative_total)
        # # print(daily_cumulative_total_df)
        # st.subheader('Daily Cumulative Total of Open Houses Over Time')
        # st.line_chart(daily_cumulative_total_df, y="daily_cumulative_total", x="OpenHouseDate")

    def close(self):
        """
        Close the DuckDB connection.
        """
        self.con.close()


if __name__ == '__main__':
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    here = os.path.abspath(os.path.dirname(__file__))
    parquet_short_path = 'data/optimized/'
    full_path = os.path.abspath(os.path.join(here, parquet_short_path))
    dashboard = ProviderDashboard(full_path)
    dashboard.display_dashboard()
    df = dashboard._query('select * from orders')
    print(df)
    dashboard.close()
