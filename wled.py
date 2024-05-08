#!/usr/bin/python3
import logging
import datetime
import sys
from datetime import datetime
import json
import time
import requests
from vardata import *

def set_power(ip_address, state):
    url = f"http://{ip_address}/json"
    payload = {"on": state}
    response = requests.post(url, data=json.dumps(payload))
    if response.status_code == 200:
        logging.info("Power state set successfully.")
    else:
        logging.info("Failed to set power state.")

def set_brightness(ip_address, brightness):
    url = f"http://{ip_address}/json"
    payload = {"bri": brightness}
    response = requests.post(url, data=json.dumps(payload))
    if response.status_code == 200:
        logging.info("Brightness set successfully.")
    else:
        logging.info("Failed to set brightness.")       
def set_color(ip_address, color):
    url = f"http://{ip_address}/json"
    payload = {"seg": [{"col": color}]}
    response = requests.post(url, data=json.dumps(payload))
    if response.status_code == 200:
        logging.info("Color set successfully.")
    else:
        logging.info("Failed to set color.")        

def setup_logging():
    """Configure logging with a timestamped log file."""
    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file_path = f"logs/output_wled_{current_time}.log"
    logging.basicConfig(
        filename=log_file_path,
        format='%(asctime)s %(levelname)s: %(message)s',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def set_effect(ip_address, effect):
    url = f"http://{ip_address}/json"
    payload = {"seg": [{"fx": effect}]}
    response = requests.post(url, data=json.dumps(payload))
    if response.status_code == 200:
        logging.info("Effect set successfully.")
    else:
        logging.info("Failed to set effect.")   

''' old Code from wled.py
#def display_menu():

        global power_endpoint
        print("Menu:")
        print("1. Led On")
        print("2. Led Off")
        print("3. Led Brightness")
        print("4. Led Color")
        print("q. Quit")   

def process_choice(choice):  
        # Process the user's choice
        if choice == '1':
            set_power(wled_ip, True)
            print("Led On")
        elif choice == '2':
            set_power(wled_ip, False)
            print("Led Off")
        elif choice == '3':
            set_brightness(wled_ip, 100)
            print("Led Brightness set to 100")
        elif choice == '4':
            set_color(wled_ip, [255, 0, 0])
            print("Led Color set to Red")
        else:
            print("Invalid choice. Please select 1, 2, 3, 4 or 'q' to quit.")
            # Log invalid choice
            logging.warning("Invalid choice entered by user: %s", choice)
'''
def main(argv):
    try:
        setup_logging()
    except Exception as e:
        logging.error(f"Fatal error in main: {e}")
        print("Fatal error Please read Logs")
        '''
        logging.info("Starting")
        while True:
            display_menu()
            choice = input("Please enter your choice (1/2/3), or 'q' to quit: ")

            logging.info("User selected option: %s", choice)

            if choice.lower() == 'q':
                print("Exiting program.")
                break  # Exit the loop
            # Process the user's choice
            process_choice(choice)
        
    except Exception as e:
        logging.error(f"Fatal error in main: {e}")
        print("Fatal error Please read Logs")
'''
if __name__ == "__main__":
    main(sys.argv[1:])     