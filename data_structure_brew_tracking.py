# -*- coding: utf-8 -*-
"""
Created on Sat Nov 16 12:53:24 2019

@author: Stefan Kasperzack

Provides data structure to model brewing process. Provided are three classes:
Batch, Inventory, and Tanks; and supporting methods.
"""
from datetime import datetime
from datetime import timedelta
from typing import Dict
from typing import List
from typing import Union
import logging

class Tanks:
    """Holds information about all tanks

    Attributes:
        albert (dict): A dict representing capability and volume of tank
        brigadier (dict): A dict representing capability and volume of tank
        camilla (dict): A dict representing capability and volume of tank
        dylon (dict): A dict representing capability and volume of tank
        emily (dict): A dict representing capability and volume of tank
        florence (dict): A dict representing capability and volume of tank
        gertrude (dict): A dict representing capability and volume of tank
        harry (dict): A dict representing capability and volume of tank
        r2d2 (dict): A dict representing capability and volume of tank
    """
    def __init__(self) -> None:
        """Initialises all instance variables of Tanks

        Args:
            No arguments

        Returns:
            No returns
        """
        self.albert = {"capability": ["ferm", "cond"], "volume": 1000}
        self.brigadier = {"capability": ["ferm", "cond"], "volume": 800}
        self.camilla = {"capability": ["ferm", "cond"], "volume": 1000}
        self.dylon = {"capability": ["ferm", "cond"], "volume": 800}
        self.emily = {"capability": ["ferm", "cond"], "volume": 1000}
        self.florence = {"capability": ["ferm", "cond"], "volume": 800}
        self.gertrude = {"capability": ["cond"], "volume": 680}
        self.harry = {"capability": ["cond"], "volume": 680}
        self.r2d2 = {"capability": ["ferm"], "volume": 800}

    def get_tank_value(self, tank_name: str) -> Dict[str,
                                                     Union[List[str], int]]:
        """Uses tank_name to get value of tank instance var with same name

        Args:
            tank_name (str): A string representing the tank name

        Returns:
            tank_value (dict): A dict representing tank's capability and volume
        """
        try:
            # Uses tank_name to get value of Tanks' inst. var with same name.
            tank_value = getattr(self, tank_name)
        # If inst. var with name doesn't exist, returns tank with no cap & vol.
        except AttributeError:
            error_msg = "Tank with name {} doesn't exist.".format(tank_name)
            logging.error(error_msg)
            return {"capability": [""], "volume": 0}
        else:
            # Returns value of Tank's instance var with same name as tank name.
            return tank_value

    def get_tank_names(self) -> List[str]:
        """Creates a list of all tank names

        Args:
            No arguments

        Returns:
            tank_names (list): A list representing all tank names
        """
        # Gets all attributes and methods of Tanks via dir(self) as string and
        # filters out all attributes that are not instance variables of Tanks.
        tank_names = [tank_name for tank_name in dir(self)
                      if not callable(getattr(self, tank_name))
                      and not tank_name.startswith("__")]
        return tank_names

class Inventory:
    """Holds info to inv.: beer types, num of bottles; and supporting methods

    Attributes:
        dunkers (dict): A dict representing the number of bottles of dunkers
        pilsner (dict): A dict representing the number of bottles of pilsner
        red_helles (dict): A dict repres. the number of bottles of red_helles
    """
    def __init__(self) -> None:
        """Initialises all instance variables of Inventory

        Args:
            No arguments

        Returns:
            No returns
        """
        # The dictionary was deliberately chosen so that after assigning the
        # instance variable to another variable, the "another" variable still
        # references to the same object (the dictionary).
        self.dunkers = {"num": 0}
        self.pilsner = {"num": 0}
        self.red_helles = {"num": 0}

    def get_inv_items_quantity(self, inv_item_name: str) -> Dict[str, int]:
        """Uses inv_item_name to get value of inv. instance var with same name

        Args:
            inv_item_name (str): A string representing inventory item name

        Returns:
            inv_items_quantity (dict): A dict representing inventory quantity
        """
        try:
            # Uses inv. name to get value of inv. instance var with same name.
            inv_items_quantity = getattr(self, inv_item_name)
        # If instance var with name does not exist, returns inv. quantity of 0
        except AttributeError:
            error_message = "Inv. item {} doesn't exist.".format(inv_item_name)
            logging.error(error_message)
            inv_items_quantity = {"num": 0}
            return inv_items_quantity
        else:
            # Returns value of inv. instance with same name as inv. item name.
            return inv_items_quantity

    def get_inv_items_names(self) -> List[str]:
        """Creates a list of all inventory item names

        Args:
            No arguments

        Returns:
            inv_items_names (list): A list represent. all inventory item names
        """
        # Gets all attributes and methods of Inventory via dir(self) as string
        # & filters out all attributes that are not instance var of Inventory.
        inv_items_names = [inventory_item for inventory_item in dir(self)
                           if not callable(getattr(self, inventory_item))
                           and not inventory_item.startswith("__")]
        return inv_items_names

class Batch:
    """Holds all information to a batch and supporting methods

    Attributes:
        id (str): A string representing the batch ID
        beer_type (str): A string representing the beer type of the batch
        volume (str): A string representing the volume of the batch in litres
        num_bottles_to_inv (str): A string repres. number bottles to inventory
        bottles_put_in_inventory (bool): A bool stating if bottles put in inv.
        phase_current (str): A string representing current phase of the batch
        phase_current_tank (str): A string representing current tank of batch
        phase_last_completed (str): A string representing last completed phase
        time_start_phase1 (str): Init as str - will hold datetime start phase 1
        time_start_phase2 (str): Init as str - will hold datetime start phase 2
        time_start_phase3 (str): Init as str - will hold datetime start phase 3
        time_start_phase4 (str): Init as str - will hold datetime start phase 4
        time_end_phase1 (str): Init as str - will hold datetime end phase 1
        time_end_phase2 (str): Init as str - will hold datetime end phase 2
        time_end_phase3 (str): Init as str - will hold datetime end phase 3
        time_end_phase4 (str): Init as str - will hold datetime end phase 4
        duration_phase1 (int): An int representing duration of phase 1 in hours
        duration_phase2 (int): An int representing duration of phase 2 in hours
        duration_phase3 (int): An int representing duration of phase 3 in hours
        duration_phase4 (int): An int representing duration of phase 4 in hours
        tank (Tanks): An instance of class Tanks representing the tanks
        inventory (Inventory): Instance of class Inventory represe. entire inv.
    """
    def __init__(self, batch_id: str, beer_type: str, volume: str,
                 handle: Dict[str, Union[Inventory, Tanks]]) -> None:
        """Initialises all instance variables of Batch

        Args:
            batch_id (str): A string representing the batch ID
            beer_type (str): A string representing the beer type of the batch
            volume (str): A string representing the volume of the batch in L
            handle (dict): Contains instances of class Tanks and Inventory

        Returns:
            No returns
        """
        # General information about batch.
        self.id = batch_id
        self.beer_type = beer_type
        self.volume = volume # In litres.
        self.num_bottles_to_inv = ""
        self.bottles_put_in_inventory = False
        # Information about batch's production phase.
        self.phase_current = ""
        self.phase_current_tank = ""
        self.phase_last_completed = ""
        # Datetime information about batch's production phase.
        self.time_start_phase1 = ""
        self.time_start_phase2 = ""
        self.time_start_phase3 = ""
        self.time_start_phase4 = ""
        self.time_end_phase1 = ""
        self.time_end_phase2 = ""
        self.time_end_phase3 = ""
        self.time_end_phase4 = ""
        # Time information about batch's production phase's duration (in hours)
        self.duration_phase1 = 5 # Can be done within a few hours.
        self.duration_phase2 = 672 # On average four weeks.
        self.duration_phase3 = 336 # Up to two weeks.
        # One minute per bottle and each bottle contains 0.5 litres.
        self.duration_phase4 = (1 / 60) * self.volume * 2
        # Handle on Tanks object to check tanks' restraints.
        self.tanks = handle["tanks"]
        # Handle on Inventory obj. to put produced bottles into the inventory.
        self.inventory = handle["inventory"]

    # Is called once per production phase to set production start and end times
    def set_phase_start_end_datetimes(self) -> None:
        """Sets start and end datetimes for 4 phases that a batch goes through

        Args:
            No arguments

        Returns:
            No returns
        """
        # True if current phase is hot brewing (phase 1).
        if self.phase_current == "hot brewing":
            # Sets start time equal to current datetime.
            self.time_start_phase1 = datetime.now()
            # Sets end time equal to current datetime + duration of phase 1.
            self.time_end_phase1 = (self.time_start_phase1
                                    + timedelta(hours=self.duration_phase1))
            # The first phase has no last completed phase.
            self.phase_last_completed = ""
        # Else True if current phase is fermentation (phase 2).
        elif self.phase_current == "ferm":
            self.time_start_phase2 = datetime.now()
            self.time_end_phase2 = (self.time_start_phase2
                                    + timedelta(hours=self.duration_phase2))
            self.phase_last_completed = "hot brewing"
        # Else True if current phase is conditioning (phase 3).
        elif self.phase_current == "cond":
            self.time_start_phase3 = datetime.now()
            self.time_end_phase3 = (self.time_start_phase3
                                    + timedelta(hours=self.duration_phase3))
            self.phase_last_completed = "ferm"
        # Else True if current phase is bottling (phase 4).
        elif self.phase_current == "bottling":
            self.time_start_phase4 = datetime.now()
            self.time_end_phase4 = (self.time_start_phase4
                                    + timedelta(hours=self.duration_phase4))
            self.phase_last_completed = "cond"
        # Else True if all phases have finished.
        elif self.phase_current == "finished":
            self.phase_last_completed = "bottling"
            # Puts the produced bottles into the inventory.
            self.put_bottles_in_inventory()

    def put_bottles_in_inventory(self) -> None:
        """Puts the produced bottles into the inventory when batch is finished

        Args:
            No arguments

        Returns:
            No returns
        """
        # True if the bottles of a batch were not yet put into the inventory.
        if not self.bottles_put_in_inventory:
            # Set to True so the bottles cannot be put into the inventory twice
            self.bottles_put_in_inventory = True
            # * 2 to get the number of bottles, 1 litre equals 2 bottles.
            self.num_bottles_to_inv = self.volume * 2
            # Adds bottles to the inventory depending on the beer type.
            if self.beer_type == "dunkers":
                self.inventory.dunkers["num"] += self.num_bottles_to_inv
            elif self.beer_type == "pilsner":
                self.inventory.pilsner["num"] += self.num_bottles_to_inv
            elif self.beer_type == "red_helles":
                self.inventory.red_helles["num"] += self.num_bottles_to_inv

    def get_start_end_dt(self) -> Dict[str, str]:
        """Gets, formats, and returns start and end datetimes of a phase

        Args:
            No arguments

        Returns:
            (dict): A dict representing start and end datetime of phase as str
        """
        if self.phase_current == "hot brewing":
            # Formats time_start_phase1 and time_end_phase1, and returns them.
            return {"start": self.time_start_phase1.strftime("%d/%m/%Y %H:%M"),
                    "end": self.time_end_phase1.strftime("%d/%m/%Y %H:%M")}
        if self.phase_current == "ferm":
            # Formats time_start_phase2 and time_end_phase2, and returns them.
            return {"start": self.time_start_phase2.strftime("%d/%m/%Y %H:%M"),
                    "end": self.time_end_phase2.strftime("%d/%m/%Y %H:%M")}
        if self.phase_current == "cond":
            return {"start": self.time_start_phase3.strftime("%d/%m/%Y %H:%M"),
                    "end": self.time_end_phase3.strftime("%d/%m/%Y %H:%M")}
        if self.phase_current == "bottling":
            return {"start": self.time_start_phase4.strftime("%d/%m/%Y %H:%M"),
                    "end": self.time_end_phase4.strftime("%d/%m/%Y %H:%M")}
        if self.phase_current == "finished":
            return {"start": "finished", "end": "finished"}
        return {"start": "", "end": ""}
