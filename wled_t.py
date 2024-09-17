#!/usr/bin/python3
import logging
from datetime import datetime
import json
import aiohttp

async def set_power(ip_address, state):
    url = f"http://{ip_address}/json"
    payload = {"on": state}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status == 200:
                logging.debug("Power state set successfully.")
            else:
                logging.error("Failed to set power state.")

async def set_brightness(ip_address, brightness):
    url = f"http://{ip_address}/json"
    payload = {"bri": brightness}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status == 200:
                logging.debug("Brightness set successfully.")
            else:
                logging.error("Failed to set brightness.")

async def set_color(ip_address, color):
    url = f"http://{ip_address}/json"
    payload = {"seg": [{"col": [[color[0], color[1], color[2]]]}]}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status == 200:
                logging.debug("Color set successfully.")
            else:
                logging.error("Failed to set color.")

async def set_effect(ip_address, effect):
    url = f"http://{ip_address}/json"
    payload = {"seg": [{"fx": effect}]}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status == 200:
                logging.debug("Effect set successfully.")
            else:
                logging.error("Failed to set effect.")