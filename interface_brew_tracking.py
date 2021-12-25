# -*- coding: utf-8 -*-
"""
Created on Sat Nov 16 10:40:05 2019

@author: Stefan Kasperzack

Runs Flask server on localhost:5000 or on executing machine's IP address or on
public IP address. Flask server allows the user to track the brewing process
via the browser. The user can add and delete batches; change batches' phases;
register, dispatch, and delete orders; predict sales numbers; and plan the
production. Further, the status of the brewing process can be saved and loaded.
"""
from datetime import datetime
from datetime import timedelta
import glob
from calendar import monthrange
import pickle
import logging
import os
from typing import List
from typing import Dict
from typing import Tuple
from PIL import Image
from flask import Flask
from flask import request
import pandas as pd
from data_structure_brew_tracking import Batch
from data_structure_brew_tracking import Inventory
from data_structure_brew_tracking import Tanks
from sales_forecast_brewing import load_csv_clean_to_dataframe
from sales_forecast_brewing import convert_to_time_series
from sales_forecast_brewing import average_data
from sales_forecast_brewing import sum_data
from sales_forecast_brewing import define_and_fit_model
from sales_forecast_brewing import plot_sales_forecast

# Creates instance of class Flask; name is used to find resources on filesystem
app = Flask(__name__)
# Adds variables/objects to Flask's app.config dict. to avoid use of global and
# to configure the program.
app.config["batches"] = {}
app.config["customer_orders"] = {}
app.config["monthly_sales_forecasts"] = {}
app.config["table_monthly_growth"] = ""
app.config["table_weekly_growth"] = ""
# Filename of the pickle file with which the program state is saved and loaded.
app.config["save_file_name"] = "savefile_program_state.pickle"
# Initialises tanks to model brewing process; handle on tanks object.
app.config["tanks"] = Tanks()
# Initialises inventory to model brewing process; handle on inventory object.
app.config["inventory"] = Inventory()
# Handle on logger.
app.config["logger"] = None
# Filename of log file.
app.config["log_file_name"] = "brew_tracking.log"
# If True, Flask server is only accessible from the machine that runs it
# through typing http://127.0.0.1:5000 in the browser and hitting enter.
# If set to False, Flask server is accessible from every machine in the same
# network via the IP address of the machine that runs it and the port number
# e.g., http://100.68.241.2:5000 - also, if False and if the router/firewall is
# configured correctly (doesn't block), the Flask server is accessible via the
# public IP address remotely via the Internet, e.g., http://31.220.200.5:5000
app.config["localhost"] = True
# Autoregressive Integrated Moving Average (ARIMA) model for sales prediction.
# Sets hyperparameters (hp) for seasonal ARIMA model; as the hp are set, it is
# assumed that the past repeats itself in the future, thus the model
# overfits the past data. To get a realistic prediction and to model the annual
# seasonal effects, the hp must be calculated using data that include more than
# one year of sales. To adjust the hp for two and more years of data, see
# https://people.duke.edu/~rnau/411arim.htm
# And https://people.duke.edu/~rnau/411sdif.htm for more info on seas. ARIMA.
# order = (number autoregression paramters, differences, moving average param).
app.config["order"] = [0, 0, 0]
# seasonal_order = same hp as before but for seasonal component, and with
# number of periods in season: e.g., 12 for 12 months or 52 for 52 weeks.
app.config["number_past_periods"] = 12
app.config["seasonal_order"] = [0, 1, 0, app.config["number_past_periods"]]

def start_logging() -> logging.RootLogger:
    """Configures and starts logging

    Args:
        No arguments

    Returns:
        logger (logging.RootLogger): Represents handle on logger object
    """
    # Defines the format of the logged messages.
    log_format = "%(levelname)s | %(asctime)s | %(message)s"
    # Configures logging, logs all messages >= 20 (INFO).
    logging.basicConfig(filename=app.config["log_file_name"],
                        format=log_format,
                        level=logging.INFO)
    # Handle on the logger.
    logger = logging.getLogger()
    return logger

def update_batch_table(batches: Dict[str, Batch]) -> str:
    """Creates HTML table containing all the batches' information

    Args:
        batches (dict): A dictionary representing all batches

    Returns:
        batch_table (str): A string representing HTML table of batches' info
    """
    batch_table = ""
    # Iter. over each batch object and inserts batches' values into HTML table.
    for batch in batches.values():
        batch_table = (batch_table
                       + "<tr>"
                       + "<td>{}</td>".format(batch.id)
                       + "<td>{}</td>".format(batch.beer_type)
                       + "<td>{}</td>".format(batch.volume)
                       + "<td>{}</td>".format(batch.phase_current)
                       + "<td>{}</td>".format(batch.phase_current_tank)
                       + "<td>{}</td>".format(batch.get_start_end_dt()["end"])
                       + "<td>{}</td>".format(batch.phase_last_completed)
                       + "<td>{}</td>".format(batch.num_bottles_to_inv)
                       + "</tr>")
    return batch_table

def update_inventory_table(inventory: Inventory) -> str:
    """Creates HTML table containing all inventory values

    Args:
        inventory (Inventory): Instance of class Inventory repres. entire inv.

    Returns:
        inventory_table (str): A string represe. HTML table of inventory values
    """
    inventory_table = ""
    # Gets names of inventory items.
    inventory_items = inventory.get_inv_items_names()
    # Iter. over each inventory item and inserts inv. values into HTML table.
    for inventory_item in inventory_items:
        # Uses inv._item to get value of inv. instance var with same name.
        inventory_item_quant = inventory.get_inv_items_quantity(inventory_item)
        # Gets inventory item's quantity (number of bottles).
        inventory_quantity = inventory_item_quant["num"]
        inventory_table = (inventory_table
                           + "<tr>"
                           + "<td>{}</td>".format(inventory_item)
                           + "<td>{}</td>".format(str(inventory_quantity))
                           + "</tr>")
    return inventory_table

def update_process_tables(batches: Dict[str, Batch]) -> Tuple[str]:
    """Creates HTML tables containing brewing order and process tracking info

    Args:
        batches (dict): A dictionary representing all batches

    Returns:
        (Tuble):
            hot_brew_table (str): A string repre. HTML table of hot brew. phase
            ferm_table (str): A string repres. HTML table of fermentation phase
            cond_table (str): A string repres. HTML table of conditioning phase
            bottling_table (str): A string repres. HTML table of bottling phase
    """
    hot_brew_table = ""
    ferm_table = ""
    cond_table = ""
    bottling_table = ""
    # True if there are no batches in the batches dict; returns empty tables.
    if not batches:
        return "", "", "", ""
    # Iter. over each batch and inserts batches' values into proper HTML table.
    for batch in batches.values():
        # True if batch is not assigned to a tank.
        if batch.phase_current_tank in ["", "not applicable"]:
            max_capacity = ""
        # If batch is assigned to a tank, get tank name and capacity.
        else:
            tank_name = batch.phase_current_tank
            tank_value = batch.tanks.get_tank_value(tank_name)
            max_capacity = tank_value["volume"]
        # True if batch in hot brew.; writes batches' info in hot brew table.
        if batch.phase_current == "hot brewing":
            phase_current_start_dt = batch.get_start_end_dt()["start"]
            phase_current_end_dt = batch.get_start_end_dt()["end"]
            hot_brew_table = (hot_brew_table
                              + "<tr>"
                              + "<td>{}</td>".format(batch.phase_current_tank)
                              + "<td>{}</td>".format(batch.volume)
                              + "<td>{}</td>".format(phase_current_start_dt)
                              + "<td>{}</td>".format(phase_current_end_dt)
                              + "<td>{}</td>".format(batch.id)
                              + "</tr>")
        # True if batch in fermentation; writes batches' info in ferm. table.
        elif batch.phase_current == "ferm":
            phase_current_start_dt = batch.get_start_end_dt()["start"]
            phase_current_end_dt = batch.get_start_end_dt()["end"]
            ferm_table = (ferm_table
                          + "<tr>"
                          + "<td>{}</td>".format(batch.phase_current_tank)
                          + "<td>{}</td>".format(max_capacity)
                          + "<td>{}</td>".format(batch.volume)
                          + "<td>{}</td>".format(phase_current_start_dt)
                          + "<td>{}</td>".format(phase_current_end_dt)
                          + "<td>{}</td>".format(batch.id)
                          + "</tr>")
        # True if batch in conditioning; writes batches' info in cond. table.
        elif batch.phase_current == "cond":
            phase_current_start_dt = batch.get_start_end_dt()["start"]
            phase_current_end_dt = batch.get_start_end_dt()["end"]
            cond_table = (cond_table
                          + "<tr>"
                          + "<td>{}</td>".format(batch.phase_current_tank)
                          + "<td>{}</td>".format(max_capacity)
                          + "<td>{}</td>".format(batch.volume)
                          + "<td>{}</td>".format(phase_current_start_dt)
                          + "<td>{}</td>".format(phase_current_end_dt)
                          + "<td>{}</td>".format(batch.id)
                          + "</tr>")
        # True if batch in bottling; writes batches' info in bottling table.
        elif batch.phase_current == "bottling":
            phase_current_start_dt = batch.get_start_end_dt()["start"]
            phase_current_end_dt = batch.get_start_end_dt()["end"]
            bottling_table = (bottling_table
                              + "<tr>"
                              + "<td>{}</td>".format(batch.phase_current_tank)
                              + "<td>{}</td>".format(batch.volume)
                              + "<td>{}</td>".format(phase_current_start_dt)
                              + "<td>{}</td>".format(phase_current_end_dt)
                              + "<td>{}</td>".format(batch.id)
                              + "</tr>")
    return hot_brew_table, ferm_table, cond_table, bottling_table

def update_order_table(orders: Dict[str, Dict[str, str]]) -> str:
    """Creates HTML table containing registered customer order information

    Args:
        orders (dict): A dictionary representing all customer orders

    Returns:
        order_table (str): A string represent. HTML table of customer orders
    """
    order_table = ""
    # Iterates over each order and inserts order values into HTML table.
    for order in orders.values():
        order_table = (order_table
                       + "<tr>"
                       + "<td>{}</td>".format(order["invoice number"])
                       + "<td>{}</td>".format(order["customer"])
                       + "<td>{}</td>".format(order["date required"])
                       + "<td>{}</td>".format(order["recipe"])
                       + "<td>{}</td>".format(order["gyle number"])
                       + "<td>{}</td>".format(order["quantity ordered"])
                       + "<td>{}</td>".format(order["dispatched"])
                       + "</tr>")
    return order_table

def update_growth_rate_table(growth_rates: pd.Series) -> str:
    """Creates HTML table containing average sales growth rates

    Args:
        growth_rates (pd.Series): Panda Series repres. avg sales growth rates

    Returns:
        growth_table (str): A string repr. HTML table of avg sales growth rates
    """
    growth_table = ""
    # Iterates over each growth rate and inserts values into HTML table.
    for date_time, growth_rate in growth_rates.items():
        # Formats date_time (of corresponding average growth rate).
        date_time = date_time.strftime("%d/%m/%Y")
        growth_table = (growth_table
                        + "<tr>"
                        + "<td>{}</td>".format(date_time)
                        # Converts growth rate in % with one decimal place.
                        + "<td>{0:.1f}%</td>".format(growth_rate * 100)
                        + "</tr>")
    return growth_table

def update_csv_list(all_uploaded_csv: List[str]) -> str:
    """Creates HTML drop-down list containing all uploaded CSV filenames

    Args:
        all_uploaded_csv (list): A list representing all uploaded CSV filenames

    Returns:
        csv_list (str): A string represe. HTML drop-down list of CSV filenames
    """
    csv_list = ""
    # Iter. over each CSV filename and inserts values into HTML drop-down list.
    for csv_file in all_uploaded_csv:
        csv_list = (csv_list
                    + '<option value="{0}">{0}</option>'.format(csv_file))
    return csv_list

def update_three_months_table(three_months: Dict[str, Dict[str, int]]) -> str:
    """Creates HTML table containing 3 months forecast or inventory data

    Args:
        three_months (dict): A dictionary representing 3 months of data

    Returns:
        three_mon_table (str): A string represe. HTML table of 3 months of data
    """
    three_mon_table = ""
    months = three_months
    # Iterates over each beer type and inserts values into HTML table.
    for beer in months:
        three_mon_table = (three_mon_table
                           + "<tr>"
                           + "<td>{}</td>".format(beer)
                           + "<td>{}</td>".format(months[beer]["this_month"])
                           + "<td>{}</td>".format(months[beer]["next_month"])
                           + "<td>{}</td>".format(months[beer]["third_month"])
                           + "</tr>")
    return three_mon_table

@app.route("/", methods=["GET", "POST"])
def interface_tracking() -> str:
    """Creates HTML to track brew, add/edit/del batches&orders, & predict sales

    Args:
        No arguments

    Returns:
        (str): A string representing HTML code for start page / user interface
    """
    batches = app.config["batches"]
    orders = app.config["customer_orders"]
    inventory = app.config["inventory"]
    # Creates HTML table containing all batches.
    html_batch_table = update_batch_table(batches)
    # Creates HTML table containing all inventory.
    html_inventory_table = update_inventory_table(inventory)
    # Creates HTML table containing all orders.
    html_order_table = update_order_table(orders)
    # Creates HTML tables containing all process tracking tables.
    hot_brew, ferm, cond, bottling = update_process_tables(batches)
    html_hot_brewing_table = hot_brew
    html_ferm_table = ferm
    html_cond_table = cond
    html_bottling_table = bottling
    # HTML code shows how HTML should be rendered in the browser (style); order
    # and process tracking; and buttons for loading and saving state of
    # program, uploading sales data, inputting new batch, changing production
    # phase, registering and dispatching orders, predicting sales, and planning
    # what to produce next.
    return ("""<style>
                h1, h2, h3 {
                  font-family: arial, sans-serif;
                }
                table {
                  font-family: arial, sans-serif;
                  border-collapse: collapse;
                  width: 100%;
                }
                td, th {
                  border: 1px solid #dddddd;
                  text-align: left;
                  padding: 8px;
                }
                tr:nth-child(even) {
                  background-color: #dddddd;
                }
            </style>
            </H2>
            <form action="/load_program_state" method="POST">
                <input type="hidden">
                <input type="submit" value="Load program state">
            </form>
            <form action="/save_program_state" method="POST">
                <input type="hidden">
                <input type="submit" value="Save program state">
            </form>
            <form action="/upload_sales_data" method="POST">
                <input type="hidden">
                <input type="submit" value="Upload sales data">
            </form>
            <form action="/add_delete_batch" method="POST">
                <input type="hidden">
                <input type="submit" value="Add / delete batch">
            </form>
            <form action="/change_batchs_phase" method="POST">
                <input type="hidden">
                <input type="submit" value="Change batch's phase">
            </form>
            <form action="/register_dispatch_delete_order" method="POST">
                <input type="hidden">
                <input type="submit" 
                value="Register / dispatch / delete order">
            </form>
            <form action="/predict_sales" method="POST">
                <input type="hidden">
                <input type="submit" value="First: predict sales">
            </form>
            <form action="/plan_production" method="POST">
                <input type="hidden">
                <input type="submit" value="Second: plan production">
            </form>
            <h2>Order tracking</h2>
            <h3>Registered customer orders</h3>
            <table>
              <tr>
                <th>Invoice number</th>
                <th>Customer</th>
                <th>Date required</th>
                <th>Recipe</th>
                <th>Gyle number</th>
                <th>Quantity ordered</th>
                <th>Dispatched</th>
              </tr>""" + html_order_table + "</table>"
            + """<h3>Batches</h3>
            <table>
              <tr>
                <th>Batch ID</th>
                <th>Beer type</th>
                <th>Volume (L)</th>
                <th>Current production phase</th>
                <th>Current tank</th>
                <th>Current phase finishes</th>
                <th>Last completed phase</th>
                <th>Bottles put in inventory</th>
              </tr>""" + html_batch_table + "</table>"
            + """<h3>Ready for delivery</h3>
            <table>
              <tr>
                <th>Beer type</th>
                <th>Number of bottles</th>
              </tr>""" + html_inventory_table + "</table>"
            + """<h2>Process tracking</h2>
            <h3>1. Hot brewing</h3>
            <table>
              <tr>
                <th>Equipment name</th>
                <th>Used capacity (L)</th>
                <th>Start time</th>
                <th>End time</th>
                <th>Batch ID</th>
              </tr>""" + html_hot_brewing_table + "</table>"
            + """<h3>2. Fermentation</h3>
            <table>
              <tr>
                <th>Equipment name</th>
                <th>Max capacity (L)</th>
                <th>Used capacity (L)</th>
                <th>Start time</th>
                <th>End time</th>
                <th>Batch ID</th>
              </tr>""" + html_ferm_table + "</table>"
            + """<h3>3. Conditioning and Carbonation</h3>
            <table>
              <tr>
                <th>Equipment name</th>
                <th>Max capacity (L)</th>
                <th>Used capacity (L)</th>
                <th>Start time</th>
                <th>End time</th>
                <th>Batch ID</th>
              </tr>""" + html_cond_table + "</table>"
            + """<h3>4. Bottling and Labelling</h3>
            <table>
              <tr>
                <th>Equipment name</th>
                <th>Used capacity (L)</th>
                <th>Start time</th>
                <th>End time</th>
                <th>Batch ID</th>
              </tr>""" + html_bottling_table + "</table>")

@app.route("/load_program_state", methods=["GET", "POST"])
def load_program_state() -> str:
    """Loads the state of the program from a pickle file

    Args:
        No arguments

    Returns:
        (str): A string representing HTML code for load_program_state page
    """
    # Contains HTML form data submitted using POST.
    response = request.form
    load_input = response.get("load_button")
    # True if user clicks on the load button.
    if load_input is not None:
        try:
            filename = app.config["save_file_name"]
            # rb to read binary file.
            with open(filename, "rb") as file:
                program_state = pickle.load(file)
        except (FileNotFoundError, PermissionError) as error:
            error_message = ("Loading the program state wasn't successful! "
                             + str(error))
            app.config["logger"].error(error_message)
            return error_message
        else:
            # Accesses program_state dictionary and sets loaded states.
            app.config["batches"] = program_state["batches"]
            app.config["customer_orders"] = program_state["orders"]
            app.config["inventory"] = program_state["inventory"]
            app.config["monthly_sales_forecasts"] = program_state["forecasts"]
            # Logs that state was loaded successfully.
            log_message = "Loading the program state was successful!"
            app.config["logger"].info(log_message)
            return """Loading the program state was successful!<br>
                    <form action="/" method="POST">
                       <input type="hidden">
                       <br>
                       <input type="submit" value="Go back to tracking screen">
                    </form>"""
    return """<style>
                h1, h2, h3 {
                  font-family: arial, sans-serif;
                }
            </style>
            <h2>Load program state</h2>
            Are you sure you want to load the program state?<br>
            <form action="/load_program_state" method="POST">
                <input type="hidden" name="load_button" value="load">
                <br>
                <input type="submit" value="Load state">
            </form>
            <form action="/" method="POST">
                <input type="hidden">
                <br>
                <input type="submit" value="Go back to tracking screen">
            </form>"""

@app.route("/save_program_state", methods=["GET", "POST"])
def save_program_state() -> str:
    """Saves the state of the program to a pickle file

    Args:
        No arguments

    Returns:
        (str): A string representing HTML code for save_program_state page
    """
    # Contains HTML form data submitted using POST.
    response = request.form
    save_input = response.get("save_button")
    # True if user clicks on the save button.
    if save_input is not None:
        batches = app.config["batches"]
        orders = app.config["customer_orders"]
        inventory = app.config["inventory"]
        monthly_sales_forecasts = app.config["monthly_sales_forecasts"]
        # Holds states in program_state.
        program_state = {"batches": batches, "orders": orders,
                         "inventory": inventory,
                         "forecasts": monthly_sales_forecasts}
        try:
            filename = app.config["save_file_name"]
            # Writes program_state to pickle file.
            # wb to write binary to file.
            with open(filename, "wb") as savefile:
                pickle.dump(program_state, savefile)
        except PermissionError as error:
            error_message = ("Saving the program state was not successful! "
                             + str(error))
            app.config["logger"].error(error_message)
            return error_message
        else:
            log_message = "Saving the program state was successful!"
            app.config["logger"].info(log_message)
            return """Saving the program state was successful!<br>
                    <form action="/" method="POST">
                       <input type="hidden">
                       <br>
                       <input type="submit" value="Go back to tracking screen">
                    </form>"""
    return """<style>
                h1, h2, h3 {
                  font-family: arial, sans-serif;
                }
            </style>
            <h2>Save program state</h2>
            Are you sure you want to save the program state?<br>
            <form action="/save_program_state" method="POST">
                <input type="hidden" name="save_button" value="save">
                <br>
                <input type="submit" value="Save state">
            </form>
            <form action="/" method="POST">
                <input type="hidden">
                <br>
                <input type="submit" value="Go back to tracking screen">
            </form>"""

@app.route("/upload_sales_data", methods=["GET", "POST"])
def upload_sales_data() -> str:
    """Loads CSV file in folder where module interface_brew_tracking is located

    Args:
        No arguments

    Returns:
        (str): A string representing HTML code for upload_sales_data page
    """
    # Contains CSV file uploaded by the user.
    response = request.files
    # True if response contains a file.
    if bool(response):
        csv_file = response.get("csv_file")
        csv_filename = csv_file.filename
        # Saves CSV file in the folder where this module is located.
        csv_file.save(csv_filename)
        log_message = "CSV file was successfully uploaded."
        app.config["logger"].info(log_message)
        return "Upload was successful!"
    return """<style>
                h1, h2, h3 {
                  font-family: arial, sans-serif;
                }
            </style>
            <h2>Upload sales data in a CSV file</h2>
            <form enctype="multipart/form-data" method="POST">
              <input type="file" name="csv_file" accept=".csv">
              <br><br>
              <input type="submit" value="Upload CSV">
            </form>
            <form action="/" method="POST">
                <input type="hidden">
                <br>
                <input type="submit" value="Go back to tracking screen">
            </form>"""

@app.route("/add_delete_batch", methods=["GET", "POST"])
def add_delete_batch() -> str:
    """Receives user form input via POST to add/delete batch

    Args:
        No arguments

    Returns:
        (str): A string representing HTML code for add_delete_batch page
    """
    batches = app.config["batches"]
    # Contains HTML form data inputted by the user submitted using POST.
    response = request.form
    batch_id_input = response.get("id_input")
    batch_volume_input = response.get("volume_input")
    batch_beer_type_input = response.get("beer_type_input")
    delete_batch_input = response.get("delete_batch_input")
    # True if user submits batch id, volume, and beer_type (part of one form).
    if batch_id_input is not None:
        # Removes blanks (whitespace characters) from batch id.
        batch_id_input = batch_id_input.replace(" ", "")
        # Volume is always a number as str; HTML is set to only allow num input
        batch_volume_input = int(batch_volume_input)
        # Creates and adds Batch to batches dict. if ID isn't in batches dict.
        if batches.get(batch_id_input) is None:
            handle = {"inventory": app.config["inventory"],
                      "tanks": app.config["tanks"]}
            batches[batch_id_input] = Batch(batch_id_input,
                                            batch_beer_type_input,
                                            batch_volume_input,
                                            handle)
            log_message = ("Batch {} with beer type {} and {} L volume "
                           + "was added.").format(batch_id_input,
                                                  batch_beer_type_input,
                                                  batch_volume_input)
            app.config["logger"].info(log_message)
    # Elif user wants to del. a batch and batch id exists, deletes this batch.
    elif delete_batch_input is not None and delete_batch_input in batches:
        del batches[delete_batch_input]
        log_message = "Batch {} was deleted.".format(delete_batch_input)
        app.config["logger"].info(log_message)
    # Creates HTML table containing all batches.
    html_batch_table = update_batch_table(batches)
    return """<style>
                h1, h2, h3 {
                  font-family: arial, sans-serif;
                }
                table {
                  font-family: arial, sans-serif;
                  border-collapse: collapse;
                  width: 100%;
                }
                td, th {
                  border: 1px solid #dddddd;
                  text-align: left;
                  padding: 8px;
                }
                tr:nth-child(even) {
                  background-color: #dddddd;
                }
            </style>
            <h2>Add batch</h2>
            <form action="/add_delete_batch" method="POST">
                Batch ID:<br>
                <input type="text" name="id_input" required="required">
                <br>
                Volume (in litres):<br>
                <input type="number" name="volume_input" min="0"
                required="required">
                <br>
                Beer type:<br>
                <select name="beer_type_input">
                    <option value="dunkers">Dunkers</option>
                    <option value="pilsner">Pilsner</option>
                    <option value="red_helles">Red Helles</option>
                </select>
                <br><br>
                <input type="submit" value="Add batch">
            </form>
            <h2>Delete batch</h2>
            <form action="/add_delete_batch" method="POST">
                Batch ID:<br>
                <input type="text" name="delete_batch_input" 
                required="required">
                <br><br>
                <input type="submit" value="Delete batch">
            </form>
            <form action="/" method="POST">
                <input type="hidden">
                <br>
                <input type="submit" value="Go back to tracking screen">
            </form>
            <h2>Batches</h2>
            <table>
              <tr>
                <th>Batch ID</th>
                <th>Beer type</th>
                <th>Volume (L)</th>
                <th>Current production phase</th>
                <th>Current tank</th>
                <th>Current phase finishes</th>
                <th>Last completed phase</th>
                <th>Bottles put in inventory</th>
              </tr>""" + html_batch_table + "</table>"

@app.route("/change_batchs_phase", methods=["GET", "POST"])
def change_batchs_phase() -> str:
    """Receives user form input via POST to change batch's phase

    Args:
        No arguments

    Returns:
        (str): A string representing HTML code for change_batchs_phase page
    """
    batches = app.config["batches"]
    tanks = app.config["tanks"]
    # Contains HTML form data inputted by the user submitted using POST.
    response = request.form
    id_input = response.get("id_input") # Batch ID.
    phase_input = response.get("phase_input")
    tank_input = response.get("tank_input")
    # Checks if the phase of the batch can be changed to what the user entered;
    # True if batch id was entered and batch is not finished.
    if id_input is not None and batches[id_input].phase_current != "finished":
        # Set to False, batch phase will not be changed to user input.
        change_batch = False
        # True if one of these 3 phases is selected and no tank is selected.
        if (phase_input in ["hot brewing", "bottling", "finished"] and
                tank_input == "not applicable"):
            # Set to True, batch phase will be changed to user input.
            change_batch = True
        # El True if one of these 2 phases is selected and a tank is selected.
        elif (phase_input in ["ferm", "cond"] and
              tank_input != "not applicable"):
            used_tanks = []
            # Checks if selected/inputted tank is available.
            # Adds the names of all used tanks to used_tanks' list.
            for batch in batches.values():
                # True if tank is used.
                if batch.phase_current_tank != "":
                    used_tanks.append(batch.phase_current_tank)
            # Gets list of all tank names.
            all_tanks = tanks.get_tank_names()
            # Gives list of all available tanks.
            available_tanks = [tank for tank in all_tanks
                               if tank not in used_tanks]
            # Adds current tank in use by batch to available_tanks,
            # because if a batch in phase 2 is in a tank that has ferm. and
            # cond. capabilities, then the batch can remain in that tank.
            if batches[id_input].phase_current_tank != "":
                available_tanks.append(batches[id_input].phase_current_tank)
            # True if inputted tank is already used for another batch.
            if tank_input not in available_tanks:
                return ("Please select an available tank. "
                        + "The following tanks are available: "
                        + str(available_tanks))
            # Uses tank_inp. to get value of Tanks' instance var with same name
            tank_value = tanks.get_tank_value(tank_input)
            # True if inputted tank has right capability and volume for batch.
            if (phase_input in tank_value["capability"] and
                    tank_value["volume"] >= batches[id_input].volume):
                # Set to True, batch phase will be changed to user input.
                change_batch = True
        # If True, batch phase will be changed to user input.
        if change_batch:
            change_batch = False
            batches[id_input].phase_current = phase_input
            batches[id_input].phase_current_tank = tank_input
            batches[id_input].set_phase_start_end_datetimes()
            info_message = ("Batch {} was changed to "
                            + "phase {}.").format(id_input, phase_input)
            log_message = (info_message)
            app.config["logger"].info(log_message)
        else:
            return "Please select a tank with the right capability/volume!"
    htm_batch_ids = ""
    # Creates HTML drop-down list options containing all batch IDs.
    for batch in batches.values():
        # True if batch is finished; finished batch can't go back to production
        if batch.phase_current == "finished":
            continue
        # If not finished, adds batch ID to HTML drop-down list.
        htm_batch_ids = (htm_batch_ids
                         + '<option value="{0}">{0}</option>'.format(batch.id))
    # Creates HTML table containing all batches.
    html_batch_table = update_batch_table(batches)
    return ("""<style>
                h1, h2, h3 {
                  font-family: arial, sans-serif;
                }
                table {
                  font-family: arial, sans-serif;
                  border-collapse: collapse;
                  width: 100%;
                }
                td, th {
                  border: 1px solid #dddddd;
                  text-align: left;
                  padding: 8px;
                }
                tr:nth-child(even) {
                  background-color: #dddddd;
                }
            </style>
            <h2>Change batch's phase</h2>
            <b> Important, if the phase of a batch is changed, the 
            previous phases will be set as completed!</b>       
            <form action="change_batchs_phase" method="POST">
                <br>
                Batch ID:<br>
                <select name="id_input">"""
            + htm_batch_ids
            + """</select>
                <br>
                Change production phase to:<br>
                <select name="phase_input">
                    <option value="hot brewing">1. Hot brewing</option>
                    <option value="ferm">2. Fermentation</option>
                    <option value="cond">
                    3. Conditioning and Carbonation</option>
                    <option value="bottling">4. Bottling and Labelling</option>
                    <option value="finished">5. Finished</option>
                </select>
                <br>
                Select available tank:<br>
                <select name="tank_input">
                    <option value="not applicable">
                    Not applicable</option>
                    <option value="albert">
                    Albert, 1000 litres (Fermenter/Conditioner)</option>
                    <option value="brigadier">
                    Brigadier, 800 litres (Fermenter/Conditioner)</option>
                    <option value="camilla">
                    Camilla, 1000 litres (Fermenter/Conditioner)</option>
                    <option value="dylon">
                    Dylon, 800 litres (Fermenter/Conditioner)</option>
                    <option value="emily">
                    Emily, 1000 litres (Fermenter/Conditioner)</option>
                    <option value="florence">
                    Florence, 800 litres (Fermenter/Conditioner)</option>
                    <option value="gertrude">
                    Gertrude, 680 litres (Conditioner)</option>
                    <option value="harry">
                    Harry, 680 litres (Conditioner)</option>
                    <option value="r2d2">R2D2, 800 litres (Fermenter)</option>
                </select>
                <br> <br>
                <input type="submit" value="Change batch's phase">
            </form>
            <form action="/" method="POST">
                <input type="hidden">
                <br>
                <input type="submit" value="Go back to tracking screen">
            </form>
            <h2>Batches</h2>
            <table>
              <tr>
                <th>Batch ID</th>
                <th>Beer type</th>
                <th>Volume (L)</th>
                <th>Current production phase</th>
                <th>Current tank</th>
                <th>Current phase finishes</th>
                <th>Last completed phase</th>
                <th>Bottles put in inventory</th>
              </tr>""" + html_batch_table + "</table>")

@app.route("/register_dispatch_delete_order", methods=["GET", "POST"])
def register_dispatch_delete_order() -> str:
    """Receives user form input via POST to register, dispatch or delete order

    Args:
        No arguments

    Returns:
        (str): String repres. HTML code for register_dispatch_delete_order page
    """
    orders = app.config["customer_orders"]
    inventory = app.config["inventory"]
    # Contains HTML form data inputted by the user submitted using POST.
    response = request.form
    invoice_num_input = response.get("invoice_number_input")
    customer_input = response.get("customer_input")
    date_required_input = response.get("date_required_input")
    recipe_input = response.get("recipe_input")
    gyle_number_input = response.get("gyle_number_input")
    quantity_input = response.get("quantity_ordered_input")
    dispatch_order_num = response.get("dispatch_order")
    delete_order = response.get("delete_order")
    # True if user enters all order info (order info are part of 1 HTML form).
    if invoice_num_input is not None:
        # Removes blanks (whitespace characters) from invoice number.
        invoice_num_input = invoice_num_input.replace(" ", "")
        # Converts string date_required_input to datetime object.
        date_required = datetime.strptime(date_required_input, "%Y-%m-%d")
        # Formats date_required.
        date_required = date_required.strftime("%d/%m/%Y")
        # Adds order to orders dict. if invoice number is not in orders dict.
        if orders.get(invoice_num_input) is None:
            orders[invoice_num_input] = {"invoice number": invoice_num_input,
                                         "customer": customer_input,
                                         "date required": date_required,
                                         "recipe": recipe_input,
                                         "gyle number": gyle_number_input,
                                         "quantity ordered": quantity_input,
                                         "dispatched": ""}
            info_message = ("Order {} was added. Customer: {}; date required: "
                            + "{}; recipe: {}; gyle number: {};  quantity "
                            + "ordered: {}.").format(invoice_num_input,
                                                     customer_input,
                                                     date_required,
                                                     recipe_input,
                                                     gyle_number_input,
                                                     quantity_input)
            app.config["logger"].info(info_message)
    # Else True if user enters order number, clicks dispatch, and order exists.
    elif dispatch_order_num is not None and dispatch_order_num in orders:
        # True if order has already been dispatched.
        if orders[dispatch_order_num]["dispatched"] == "dispatched":
            return "Order has already been dispatched."
        # Gets beer type of order.
        beer_type = orders[dispatch_order_num]["recipe"]
        # Gets number of bottles in inventory for this beer type.
        inventory_item_quantity = inventory.get_inv_items_quantity(beer_type)
        quantity_ordered = int(orders[dispatch_order_num]["quantity ordered"])
        # True if enough bottles of the right beer type in the inventory.
        if inventory_item_quantity["num"] >= quantity_ordered:
            # Reduces inventory quantity by the number of dispatched bottles.
            inventory_item_quantity["num"] -= quantity_ordered
            orders[dispatch_order_num]["dispatched"] = "dispatched"
            log_message = "Order {} was dispatched.".format(dispatch_order_num)
            app.config["logger"].info(log_message)
        # Else order can't be dispatched and user is informed.
        else:
            return ("Unfortunately, not enough bottles of type {} "
                    + "are in stock!").format(beer_type)
    # Else True if user enters order to be deleted and order exists.
    elif delete_order is not None and delete_order in orders:
        del orders[delete_order]
        log_message = "Order {} was deleted.".format(delete_order)
        app.config["logger"].info(log_message)
    # Creates HTML table containing all orders.
    html_order_table = update_order_table(orders)
    return """<style>
                h1, h2, h3 {
                  font-family: arial, sans-serif;
                }
                table {
                  font-family: arial, sans-serif;
                  border-collapse: collapse;
                  width: 100%;
                }
                td, th {
                  border: 1px solid #dddddd;
                  text-align: left;
                  padding: 8px;
                }
                tr:nth-child(even) {
                  background-color: #dddddd;
                }
            </style>
            <h2>Register customer order</h2>
            <form action="/register_dispatch_delete_order" method="POST">
                Invoice number:<br>
                <input type="number" name="invoice_number_input" min="0"
                required="required">
                <br>
                Customer:<br>
                <input type="text" name="customer_input" required="required">
                <br>
                Date required:<br>
                <input type="date" name="date_required_input"
                required="required">
                <br>
                Recipe:<br>
                <select name="recipe_input">
                    <option value="dunkers">Dunkers</option>
                    <option value="pilsner">Pilsner</option>
                    <option value="red_helles">Red Helles</option>
                </select>                
                <br>
                Gyle number:<br>
                <input type="number" name="gyle_number_input" min="0"
                required="required">
                <br>
                Quantity ordered:<br>
                <input type="number" name="quantity_ordered_input" min="0"
                required="required">
                <br><br>
                <input type="submit" value="Register order">
            </form>
            <h2>Dispatch customer order</h2>
            <form action="/register_dispatch_delete_order" method="POST">
                Invoice number:<br>
                <input type="number" name="dispatch_order" min="0"
                required="required">
                <br><br>
                <input type="submit" value="Dispatch order">
            </form>
            <h2>Delete customer order</h2>
            <form action="/register_dispatch_delete_order" method="POST">
                Invoice number:<br>
                <input type="number" name="delete_order" min="0"
                required="required">
                <br><br>
                <input type="submit" value="Delete order">
            </form>
            <form action="/" method="POST">
                <input type="hidden">
                <br>
                <input type="submit" value="Go back to tracking screen">
            </form>
            <h2>Registered customer orders</h2>
            <table>
              <tr>
                <th>Invoice number</th>
                <th>Customer</th>
                <th>Date required</th>
                <th>Recipe</th>
                <th>Gyle number</th>
                <th>Quantity ordered</th>
                <th>Dispatched</th>
              </tr>""" + html_order_table + "</table>"

@app.route("/predict_sales", methods=["GET", "POST"])
def predict_sales() -> str:
    """Receives user form input via POST & loads uploaded CSV to predict sales

    Args:
        No arguments

    Returns:
        (str): A string representing HTML code for predict_sales page
    """
    # HTML tables and list that are filled depending on the user input.
    html_gr_month_table = app.config["table_monthly_growth"]
    html_gr_week_table = app.config["table_weekly_growth"]
    html_csv_list = ""
    # Empty filename and path to sales forecast graph; also dep. on user input.
    graph_filename = ""
    graph_filepath = "'File has not been created yet!'"
    # Contains HTML form data inputted by the user submitted using POST.
    response = request.form
    num_months_input = response.get("num_months_input")
    csv_filename_input = response.get("csv_filename_input")
    # True if user inputted num of past months for prediction and uploaded CSV.
    if num_months_input is not None and csv_filename_input is not None:
        # Loads data from CSV into dataframe & removes rows with missing values
        file_name = csv_filename_input
        dataframe = load_csv_clean_to_dataframe(file_name)
        try:
            # Replaces index numbers of df with datetimes to get a time series.
            dataframe = convert_to_time_series(dataframe)
        except KeyError as error:
            error_message = ("The following column name is missing "
                             "in the data: " + str(error))
            app.config["logger"].error(error_message)
            return error_message
        # Calculates Quantity ordered averages for every past week.
        column_to_avg = "Quantity ordered"
        average_by = "W" # "W" = week; "MS" = month
        past_avgs_per_week = average_data(dataframe, column_to_avg, average_by)
        # Calculates Quantity ordered averages for every past month.
        average_by = "MS" # "W" = week; "MS" = month
        past_avgs_per_month = average_data(dataframe, column_to_avg,
                                           average_by)
        # Calculates past Quantity ordered average growth rates.
        growth_rates_per_week = past_avgs_per_week.pct_change()
        growth_rates_per_month = past_avgs_per_month.pct_change()
        # Creates HTML table containing past monthly sales growth rates.
        html_gr_month_table = update_growth_rate_table(growth_rates_per_month)
        app.config["table_monthly_growth"] = html_gr_month_table
        # Creates HTML table containing past weekly sales growth rates.
        html_gr_week_table = update_growth_rate_table(growth_rates_per_week)
        app.config["table_weekly_growth"] = html_gr_week_table
        # Filters dataframe for beer types.
        dunkel = dataframe.loc[dataframe["Recipe"] == "Organic Dunkel"]
        pilsner = dataframe.loc[dataframe["Recipe"] == "Organic Pilsner"]
        red_helles = dataframe.loc[dataframe["Recipe"] == "Organic Red Helles"]
        # Monthly basis;
        # calculates dunkel's Quantity ordered sums for each month.
        column_to_sum = "Quantity ordered"
        sum_by = "MS" # "W" = week; "MS" = month
        dunk_order_sum_per_month = sum_data(dunkel, column_to_sum, sum_by)
        # Calculates pilsner's Quantity ordered sums for each month.
        pils_order_sum_per_month = sum_data(pilsner, column_to_sum, sum_by)
        # Calculates red_helles' Quantity ordered sums for each month.
        redh_order_sum_per_month = sum_data(red_helles, column_to_sum, sum_by)
        all_order_sum_month = {"dunkers": dunk_order_sum_per_month,
                               "pilsner": pils_order_sum_per_month,
                               "red_helles": redh_order_sum_per_month}
        # Clears monthly sales forecasts from the dictionary.
        app.config["monthly_sales_forecasts"] = {}
        # Hyperparameters (hp) for seasonal ARIMA model.
        order = app.config["order"]
        # Sets num_months_in. as num of past periods to be considered by model.
        app.config["seasonal_order"][3] = int(num_months_input)
        seasonal_order = app.config["seasonal_order"]
        # Fits ARIMA model and forecasts monthly sales for each beer type.
        try:
            for beer_type in all_order_sum_month:
                model = define_and_fit_model(all_order_sum_month[beer_type],
                                             False, order, seasonal_order)
                # Forecasts 12 months into the future with the fitted model.
                forecast = model.get_forecast(steps=12)
                # Stores monthly sales forecasts in dictionary by beer_type.
                app.config["monthly_sales_forecasts"][beer_type] = forecast
                # Plots actual and predicted num of beers sold and saves plot.
                plot_size = (15, 10)
                plot_sales_forecast(forecast, all_order_sum_month[beer_type],
                                    plot_size, beer_type)
        except ValueError as error:
            error_message = ("Wrong hyperparameters are set, the model "
                             + "can not be fitted: " + str(error))
            app.config["logger"].error(error_message)
            return error_message
        # Gets filepath of this module and thus filepath to graph (png file).
        graph_filepath = os.path.dirname(os.path.abspath(__file__))
        graph_filename = "monthly_forecast_and_past.png"
        try:
            # Opens plotted graph.
            img = Image.open(graph_filename)
            img.show()
        except (FileNotFoundError, PermissionError) as error:
            app.config["logger"].error(error)
    # Finds names of all uploaded CSV files in folder where this module is.
    all_uploaded_csv = []
    for csv_file in glob.glob("*.csv"):
        all_uploaded_csv.append(csv_file)
    # Creates HTML drop-down list containing all uploaded CSV filenames.
    html_csv_list = update_csv_list(all_uploaded_csv)
    return ("""<style>
                h1, h2, h3 {
                  font-family: arial, sans-serif;
                }
                table {
                  font-family: arial, sans-serif;
                  border-collapse: collapse;
                  width: 100%;
                }
                td, th {
                  border: 1px solid #dddddd;
                  text-align: left;
                  padding: 8px;
                }
                tr:nth-child(even) {
                  background-color: #dddddd;
                }
            </style>
            <h2>Predict sales</h2>
            <form action="/predict_sales" method="POST">
                Please select an uploaded CSV file that should be used for the 
                sales forecast (if the list is empty, no CSV file has been 
                uploaded yet; to upload a file, please go back to the 
                tracking screen).<br>
                <select name="csv_filename_input">"""
            + html_csv_list
            + """</select><br><br>
                Please enter how many <b>months</b> of past data should be
                used for the sales forecast:<br>
                (Note: If the number of past periods is higher than the number
                of periods in the past sales data, the nonexistent periods are
                recorded as 0 sales, which, if too many periods are 0,
                makes the prediction zero.
                <br>
                <input type="number" name="num_months_input" min="2"
                required="required">
                <br><br>
                <input type="submit" value="Predict sales">
            </form>
            In case the graph is not displayed, please open the file """
            + graph_filename + " manually using the path: "
            + graph_filepath
            + """<form action="/" method="POST">
                <input type="hidden">
                <br>
                <input type="submit" value="Go back to tracking screen">
            </form>            
            <h3>Average sales growth rates of the past months</h3>
            <table>
              <tr>
                <th>Date</th>
                <th>Monthly average</th>
              </tr>""" + html_gr_month_table + "</table>"
            + """<h3>Average sales growth rates of the past weeks</h3>
            <table>
              <tr>
                <th>Date</th>
                <th>Weekly average</th>
              </tr>""" + html_gr_week_table + "</table>")

@app.route("/plan_production", methods=["GET", "POST"])
def plan_production() -> str:
    """Plans, advises, and reasons which beer to produce on basis of all states

    Args:
        No arguments

    Returns:
        (str): A string representing HTML code for plan_production page
    """
    monthly_forecasts = app.config["monthly_sales_forecasts"]
    # True if the dictionary monthly_forecasts is empty.
    if not monthly_forecasts:
        return ("No prediction has been made. Please click first on the "
                + "button 'First: predict sales' on the tracking screen.")
    batches = app.config["batches"]
    tanks = app.config["tanks"]
    inventory = app.config["inventory"]
    # Holds actual number of beers in inventory and actual number of beers that
    # will be finished in the next three months on basis of production stage.
    three_month_end_inv = {"dunkers": {"this_month": 0, "next_month": 0,
                                       "third_month": 0},
                           "pilsner": {"this_month": 0, "next_month": 0,
                                       "third_month": 0},
                           "red_helles": {"this_month": 0, "next_month": 0,
                                          "third_month": 0}}
    # Calculates when product. stage will be finished for 3 consecutive months.
    for batch in batches.values():
        # True if batch is already finished, continue with next batch.
        if batch.bottles_put_in_inventory:
            continue
        # Implies batch isn't assigned to phase, values are set in next if-else
        end_phase4 = ""
        end_phase3_4 = ""
        end_phase2_4 = ""
        end_phase1_4 = ""
        # Calculates end time of each batch assuming that each batch goes
        # directly to the next production phase without any delays.
        # True if the batch is in production phase 4 (bottling).
        if batch.time_end_phase4 != "":
            # Phase 4 ends when time_end_phase4 is reached.
            end_phase4 = batch.time_end_phase4
        # Else True if the batch is in production phase 3 (conditioning).
        elif batch.time_end_phase3 != "":
            # If the product is in phase 3, then the product will be finished
            # after the duration of phase 3 + phase 4 ends.
            # One minute per bottle (1/60) and each bottle contains 0.5 litres.
            duration_p4 = (1 / 60) * batch.volume * 2 # In hours.
            end_phase3_4 = batch.time_end_phase3 + timedelta(hours=duration_p4)
        # Else True if the batch is in production phase 2 (fermentation).
        elif batch.time_end_phase2 != "":
            # P2 product will be finished after duration p2 + p3 + p4 ends.
            duration_p3 = 336 #  In hours.
            duration_p4 = (1 / 60) * batch.volume * 2
            end_phase2_4 = (batch.time_end_phase2
                            + timedelta(hours=duration_p3)
                            + timedelta(hours=duration_p4))
        # Else True if the batch is in production phase 1 (hot brewing).
        elif batch.time_end_phase1 != "":
            # P1 product will be finished after durat. p1 + p2 + p3 + p4 ends.
            duration_p2 = 672 # In hours.
            duration_p3 = 336
            duration_p4 = (1 / 60) * batch.volume * 2
            end_phase1_4 = (batch.time_end_phase1
                            + timedelta(hours=duration_p2)
                            + timedelta(hours=duration_p3)
                            + timedelta(hours=duration_p4))
        # Gets current month and is incremented for each iteration of for loop
        # to represent month number of this_month, next_month, and third_month.
        incre_month = datetime.now().month
        months = ["this_month", "next_month", "third_month"]
        # Calculates end of month inv. values for this, next, and third month.
        for index, _ in enumerate(months):
            # * 2 to get the number of bottles, 1 litre equals 2 bottles.
            volume = batch.volume * 2
            # True if phase4 has been reached and end month matches inc month.
            if end_phase4 != "" and end_phase4.month == incre_month:
                three_month_end_inv[batch.beer_type][months[index]] += volume
            # Elif True if p3 has been reached and end month matches inc month.
            elif end_phase3_4 != "" and end_phase3_4.month == incre_month:
                three_month_end_inv[batch.beer_type][months[index]] += volume
            # Elif True if p2 has been reached and end month matches inc month.
            elif end_phase2_4 != "" and end_phase2_4.month == incre_month:
                three_month_end_inv[batch.beer_type][months[index]] += volume
            # Elif True if p1 has been reached and end month matches inc month.
            elif end_phase1_4 != "" and end_phase1_4.month == incre_month:
                three_month_end_inv[batch.beer_type][months[index]] += volume
            incre_month += 1
            # If month number is incremented to 13, it is set to 1 (January).
            if incre_month == 13:
                incre_month = 1
    # Adds actual inventory quantities to calculated end of month quantities.
    for beer_type in three_month_end_inv:
        inventory_item_quantity = inventory.get_inv_items_quantity(beer_type)
        inventory_quantity = inventory_item_quantity["num"]
        # Actual inventory quantities are only added to this_month inventory.
        three_month_end_inv[beer_type]["this_month"] += inventory_quantity
    # Holds three months (end of month) forecasted sales values.
    three_month_forecast = {"dunkers": {"this_month": 0, "next_month": 0,
                                        "third_month": 0},
                            "pilsner": {"this_month": 0, "next_month": 0,
                                        "third_month": 0},
                            "red_helles": {"this_month": 0, "next_month": 0,
                                           "third_month": 0}}
    # Builds date-index to access forecast value for this, next, and 3rd month.
    # 1. Builds date-index for this month.
    # Gets current datetime.
    current_datetime = datetime.now()
    # Gets current month.
    current_month = current_datetime.month
    # Gets current year.
    current_year = current_datetime.year
    # Creates date-index to access forecast value for this month.
    dt1st_month = datetime(current_year, current_month, 1) # 1st day of month.
    # Gets number of days of the current month.
    number_days = monthrange(current_year, current_month)[1]
    # 2. Builds date-index for next month.
    # Gets next datetime.
    next_datetime = current_datetime + timedelta(days=number_days)
    # Gets next month.
    next_month = next_datetime.month
    # Gets year in next month.
    next_months_year = next_datetime.year
    # Creates date-index to access forecast value for next month.
    dt2nd_month = datetime(next_months_year, next_month, 1)
    # Gets number of days of the next month.
    number_days = monthrange(next_months_year, next_month)[1]
    # 3. Builds date-index for 3rd month.
    # Gets 3rd datetime.
    third_datetime = next_datetime + timedelta(days=number_days)
    # Gets 3rd month.
    third_month = third_datetime.month
    # Gets year in 3rd month.
    third_months_year = third_datetime.year
    # Creates date-index to access forecast value for 3rd month.
    dt3rd_month = datetime(third_months_year, third_month, 1)
    # Gets and stores forecast values for three months in three_month_forecast.
    for beer_type in monthly_forecasts:
        forecast_1st = monthly_forecasts[beer_type].predicted_mean[dt1st_month]
        forecast_2nd = monthly_forecasts[beer_type].predicted_mean[dt2nd_month]
        forecast_3rd = monthly_forecasts[beer_type].predicted_mean[dt3rd_month]
        try:
            three_month_forecast[beer_type]["this_month"] = int(forecast_1st)
            three_month_forecast[beer_type]["next_month"] = int(forecast_2nd)
            three_month_forecast[beer_type]["third_month"] = int(forecast_3rd)
        except ValueError as error:
            app.config["logger"].error(error)
    # Holds 3 months differ. between forecast and finished inv. for each beer.
    diff_3months_forecast_actual = {"dunkers": 0, "pilsner": 0,
                                    "red_helles": 0}
    # Calculates for each beer differ. between forecast and finished inventory.
    for beer_type in three_month_end_inv:
        # Holds finished inventory quantity for 3 months per beer type.
        fin_inv_beer_3months = 0
        # Holds forecasted sales quantity for 3 months per beer type.
        forecast_beer_3months = 0
        # 2nd for loop to iterate over dict in dict to calculate difference.
        for month in three_month_end_inv[beer_type]:
            fin_inv_beer_3months += three_month_end_inv[beer_type][month]
            forecast_beer_3months += three_month_forecast[beer_type][month]
        diff_beer_3months = fin_inv_beer_3months - forecast_beer_3months
        diff_3months_forecast_actual[beer_type] = diff_beer_3months
    # Determines which beer should be produced next;
    # beer type with highest negative difference between finished inventory and
    # sales forecast is recommended to be produced if equipment is available.
    # Gets beer type with highest negative difference.
    produce_beer = min(diff_3months_forecast_actual,
                       key=lambda beer: diff_3months_forecast_actual[beer])
    used_tanks = []
    # Adds the names of all used tanks to used_tanks' list.
    for batch in batches.values():
        # True if tank is used.
        if batch.phase_current_tank != "":
            used_tanks.append(batch.phase_current_tank)
    all_tanks = tanks.get_tank_names()
    available_tanks = [tank for tank in all_tanks if tank not in used_tanks]
    capable_tanks = {}
    # Checks if tank with right capability is available.
    for tank_name in available_tanks:
        # Uses tank_name to get value of Tanks' instance var with same name.
        tank_value = tanks.get_tank_value(tank_name)
        # True if tank with right capability is available.
        if "ferm" in tank_value["capability"]:
            # Puts tank's volume into capable_tanks dictionary.
            capable_tanks[tank_name] = tank_value["volume"]
    # Selects tank with highest volume if tank with right capab. is available.
    if capable_tanks:
        use_tank = max(capable_tanks, key=lambda beer: capable_tanks[beer])
        use_tank_volume = capable_tanks[use_tank]
    else:
        use_tank = "'currently no tank with right capability available'"
        use_tank_volume = 0
    # Creates recommendation for the user.
    recommendation = ("Based on the three-month forecast and production phases"
                      + ", available tanks, capabilities and volumes, it is "
                      + "recommended to produce <b>{0}</b> in tank <b>{1}</b> "
                      + "next.").format(produce_beer, use_tank)
    # Creates reasoning for the user.
    # Creates HTML table containing three months end inventory.
    html_3months_end_inv_table = update_three_months_table(three_month_end_inv)
    # Creates HTML table containing three months forecasted sales.
    html_3months_foreca_table = update_three_months_table(three_month_forecast)
    reason = ("Actual number of beers in inventory and actual number of beers "
              + "that will be finished in the next three months are:<br>"
              + """<table>
                  <tr>
                    <th></th>
                    <th>This month</th>
                    <th>Next month</th>
                    <th>Third month</th>
                  </tr>""" + html_3months_end_inv_table + "</table><br>"
              + "Three months forecasted sales (in bottles) are:"
              + """<table>
                  <tr>
                    <th></th>
                    <th>This month</th>
                    <th>Next month</th>
                    <th>Third month</th>
                  </tr>""" + html_3months_foreca_table + "</table><br>"
              + "Beer type with highest difference between forecast and "
              + "finished inventory is recommended to be produced if "
              + "equipment is available. The difference is (in bottles):<br>"
              + """<table>
                      <tr>
                        <th>Dunkers</th>
                        <th>Pilsner</th>
                        <th>Red Helles</th>
                      </tr>
                      <tr>
                        <td>{0}</td>
                        <td>{1}</td>
                        <td>{2}</td>
                      </tr></table><br>
                  """.format(diff_3months_forecast_actual["dunkers"],
                             diff_3months_forecast_actual["pilsner"],
                             diff_3months_forecast_actual["red_helles"])
              + "Available tank(s) with right capability is/are:<b>"
              + str(capable_tanks) + "</b>, where the highest available "
              + "volume is <b>{}</b> litres. ".format(use_tank_volume)
              + ("Thus, it is recommended to produce <b>{0}</b> in tank "
                 + "<b>{1}</b>.").format(produce_beer, use_tank))
    return ("""<style>
                h1, h2, h3 {
                  font-family: arial, sans-serif;
                }
                table {
                  font-family: arial, sans-serif;
                  border-collapse: collapse;
                  width: 100%;
                }
                td, th {
                  border: 1px solid #dddddd;
                  text-align: left;
                  padding: 8px;
                }
                tr:nth-child(even) {
                  background-color: #dddddd;
                }
            </style>
            <h2>Plan production</h2>"""
            + recommendation
            + "<br><br><b>Reasoning:</b></br>"
            + reason
            + """<form action="/" method="POST">
                <input type="hidden">
                <br>
                <input type="submit" value="Go back to tracking screen">
            </form>""")

def main() -> None:
    """Starts Flask server on localhost or on executing PC's IP or on public IP

    Args:
        No arguments

    Returns:
        No returns
    """
    # Configures and starts logging.
    app.config["logger"] = start_logging()
    # Starts and runs Flask server on localhost:5000 if True.
    if app.config["localhost"]:
        app.run()
    # Else starts and runs Flask server that listens on all IPs. Meaning, Flask
    # server can be accessed via executing machine's IP address, e.g.,
    # 100.68.241.2:5000 - so Flask server can be reached from machines in same
    # network or accessed via the public IP (remotely), e.g., 31.220.200.5:5000
    else:
        app.run(host="0.0.0.0")

if __name__ == "__main__":
    main()
