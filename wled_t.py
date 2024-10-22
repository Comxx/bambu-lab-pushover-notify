#!/usr/bin/python3
import logging
from datetime import datetime
import json
import asyncio
import aiohttp
from aiohttp import ClientError

async def wled_request(ip_address, payload, max_retries=10, retry_delay=60):
    url = f"http://{ip_address}/json"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=5) as response:
                if response.status == 200:
                    return True
                else:
                    logging.warning(f"Failed request. Status: {response.status}")
    except asyncio.TimeoutError:
        logging.warning(f"Timeout occurred. Attempt {attempt + 1} of {max_retries}")
    except ClientError as e:
        logging.error(f"Network error occurred: {str(e)}. Attempt {attempt + 1} of {max_retries}")
    except Exception as e:
        logging.error(f"Unexpected error occurred: {str(e)}. Attempt {attempt + 1} of {max_retries}")
        
    if attempt < max_retries - 1:
        await asyncio.sleep(retry_delay)
    
    
    return False

async def set_power(ip_address, state):
    payload = {"on": state}
    success = await wled_request(ip_address, payload)
    if success:
        logging.info(f"Power state set successfully to {state}.")
    else:
        logging.error("Failed to set power state.")
    return success

async def set_brightness(ip_address, brightness):
    payload = {"bri": brightness}
    success = await wled_request(ip_address, payload)
    if success:
        logging.info(f"Brightness set successfully to {brightness}.")
    else:
        logging.error("Failed to set brightness.")
    return success

async def set_color(ip_address, color):
    payload = {"seg": [{"col": [[color[0], color[1], color[2]]]}]}
    success = await wled_request(ip_address, payload)
    if success:
        logging.info(f"Color set successfully to {color}.")
    else:
        logging.error("Failed to set color.")
    return success

async def set_effect(ip_address, effect):
    payload = {"seg": [{"fx": effect}]}
    success = await wled_request(ip_address, payload)
    if success:
        logging.info(f"Effect set successfully to {effect}.")
    else:
        logging.error("Failed to set effect.")
    return success