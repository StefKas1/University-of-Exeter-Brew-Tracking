# -*- coding: utf-8 -*-
"""
Created on Wed Nov 13 09:35:18 2019

@author: Stefan Kasperzack

Provides methods to predict future beer sales based on past beer sales. Loads
the data from a CSV file and uses the Autoregressive Integrated Moving Average
(ARIMA) model for the sales prediction. The ARIMA is a time series model that
can model seasonal effects.
Important to note: As powerful as the model is, the model needs at least two
years of sales data to identify these seasonal effects and the hyperparameters
of the model need to be adjusted on the basis of the data. For more information
about the ARIMA model see:
https://people.duke.edu/~rnau/411arim.htm
https://people.duke.edu/~rnau/411sdif.htm
https://www.statsmodels.org/dev/examples/ and search for SARIMAX.
"""
from typing import List
from typing import Dict
from typing import Tuple
import logging
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX
import matplotlib.pyplot as pyplot

def load_csv_clean_to_dataframe(file_path: str) -> pd.DataFrame:
    """Loads a CSV file, removes missing values, and puts data into a dataframe

    Args:
        file_path (str): A string representing the file path to the CSV file

    Returns:
        dataframe (pd.DataFrame): A pandas dataframe repres. loaded CSV data
    """
    # Creates empty dataframe.
    dataframe = pd.DataFrame()
    try:
        # Reads the comma-separated values into a dataframe.
        dataframe = pd.read_csv(file_path, sep=",")
        # Counts the number of rows with missing data.
        number_rows_missing_data = dataframe.isnull().values.ravel().sum()
        data_drop_info = ("After loading the CSV file, {} row(s) were removed "
                          + "due to missing "
                          + "values!").format(number_rows_missing_data)
        logging.info(data_drop_info)
        # Removes rows with missing data.
        dataframe = dataframe.dropna()
    except FileNotFoundError:
        error_message = "The file {} does not exist".format(file_path)
        logging.error(error_message)
    return dataframe

def convert_to_time_series(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Converts dataframe (dt) with numbers as index to dt with dates as index

    Args:
        dataframe (pd.DataFrame): A pandas dataframe with numbers as index

    Returns:
        dataframe (pd.DataFrame): A pandas dataframe with dates as index
    """
    # Formats dates in column "Date Required".
    dataframe["Date Required"] = pd.to_datetime(dataframe["Date Required"],
                                                format="%d-%b-%y")
    # Sets column "Date Required" as the new index for the dataframe;
    # inplace = True to modify the dataframe and to not create a new dataframe.
    dataframe.set_index("Date Required", inplace=True)
    return dataframe

def average_data(dataframe: pd.DataFrame, column_to_avg: str,
                 average_by: str) -> pd.Series:
    """Calculates weekly or monthly averages of data in a dataframe

    Args:
        dataframe (pd.DataFrame): Pandas dataframe with data to be averaged
        column_to_avg (str): A string representing the column to average
        average_by (str): Represen. whether monthly or weekly avg is calculated

    Returns:
        averaged_data (pd.Series): A pd.Series representing averaged data
    """
    averaged_data = dataframe[column_to_avg].resample(average_by).mean()
    return averaged_data

def sum_data(dataframe: pd.DataFrame, column_to_sum: str,
             sum_by: str) -> pd.Series:
    """Calculates weekly or monthly sums of data in a dataframe

    Args:
        dataframe (pd.DataFrame): Pandas dataframe with data to be summed
        column_to_sum (str): A string representing the column to sum
        sum_by (str): Representing whether monthly or weekly sum is calculated

    Returns:
        summed_data (pd.Series): A pd.Series representing summed data
    """
    summed_data = dataframe[column_to_sum].resample(sum_by).sum()
    return summed_data

def define_and_fit_model(avgs_dataframe: pd.Series, display_fitting: bool,
                         order: List[int],
                         seas_ord: List[int]) -> object:
    """Defines and fits seasonal ARIMA model (time series model)

    Args:
        avgs_dataframe (pd.Series): A pd.Series representing averages
        display_fitting (bool): Bool where True displays model fitting process
        order (list): A list representing hyperparameters for the ARIMA model
        seas_ord (list): A list representing hpyerparam. for seasonal component

    Returns:
        fitted_model (obj): An object respresenting the fitted ARIMA model.
    """
    # Defines model as seasonal ARIMA (time series with seasonal component).
    model = SARIMAX(avgs_dataframe, order=order, seasonal_order=seas_ord)
    # Fits model; False disables information about model fitting iterations.
    fitted_model = model.fit(disp=display_fitting)
    return fitted_model

def plot_sales_forecast(sales_forecast: object, past: Dict[str, pd.Series],
                        plot_size: Tuple[int], beer_type: str) -> None:
    """Plots actual and predicted number of bottles sold and saves plot

    Args:
        sales_forecast (obj): An object representing the sales forecast
        past (dict): A dict representing acutal/past number of bottles sold
        plot_size (tuple): A tuple representing the plot size
        beer_type (str): A str representing the beer type

    Returns:
        No returns
    """
    # Clears pyplot figure so that not every plot is drawn in the same figure;
    # dunkers is plotted first, indicating that a new figure must be plotted.
    if beer_type == "dunkers":
        pyplot.clf()
    # Sets label and size of figure.
    label = "Actual " + beer_type
    label_forecast = "Forecast " + beer_type
    plot = past.plot(label=label, figsize=plot_size)
    # Gets predicted values from saels_forecast object and plots data.
    sales_forecast.predicted_mean.plot(ax=plot, label=label_forecast)
    # Labels the axes.
    plot.set_xlabel("Date")
    plot.set_ylabel("Quantity ordered")
    # Sets legend.
    pyplot.legend()
    try:
        # Saves plotted figure to folder in which this module is located.
        filename = "monthly_forecast_and_past.png"
        pyplot.savefig(filename)
    except (FileNotFoundError, PermissionError):
        error_message = "File {} could not be accessed/found.".format(filename)
        logging.error(error_message)
