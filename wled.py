#!/usr/bin/python3
import logging
from datetime import datetime
import json
import requests

def set_power(ip_address, state):
    url = f"http://{ip_address}/json"
    payload = {"on": state}
    response = requests.post(url, data=json.dumps(payload))
    if response.status_code == 200:
        logging.debug("Power state set successfully.")
    else:
        logging.error("Failed to set power state.")

def set_brightness(ip_address, brightness):
    url = f"http://{ip_address}/json"
    payload = {"bri": brightness}
    response = requests.post(url, data=json.dumps(payload))
    if response.status_code == 200:
        logging.debug("Brightness set successfully.")
    else:
        logging.error("Failed to set brightness.")       
def set_color(ip_address, color):
    url = f"http://{ip_address}/json"
    payload = {"seg": [{"col": [[color[0], color[1], color[2]]]}]}
    response = requests.post(url, data=json.dumps(payload))
    if response.status_code == 200:
        logging.drbug("Color set successfully.")
    else:
        logging.error("Failed to set color.")        

def set_effect(ip_address, effect):
    url = f"http://{ip_address}/json"
    payload = {"seg": [{"fx": effect}]}
    response = requests.post(url, data=json.dumps(payload))
    if response.status_code == 200:
        logging.debug("Effect set successfully.")
    else:
        logging.debug("Failed to set effect.")   
