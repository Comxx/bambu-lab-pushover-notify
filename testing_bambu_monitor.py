"""
Module-level docstring: This script is used for monitoring the Bambu X1C and sending pushover notifications on gcode_state changes.
"""
import logging
import json
import sys
import ssl
import time
from datetime import datetime, timedelta
import paho.mqtt.client as paho
from chump import Application
import tzlocal
import requests
from vardata import *
# Constants
DASH = '\n-------------------------------------------\n'
PO_TITLE = "Testing Bambu Printer"
PO_SOUND = 'classical'
# Add a global variable to store the last known gcode_state
last_gcode_state = ""
# Global state
first_run = False
percent_notify = False
percent_done = 0
message_sent = False
# Initialize Pushover application
po_app = Application(my_pushover_app)
po_user = po_app.get_user(my_pushover_user)

def setup_logging():
    """Sets up logging with a timestamped log file."""
    local_timezone = tzlocal.get_localzone()
    current_datetime = datetime.now(local_timezone)
    datetime_str = current_datetime.strftime("%Y-%m-%d_%I-%M-%S%p")
    logfile_path = "logs/"
    logfile_name = f"{logfile_path}output_{datetime_str}.log"
    logging.basicConfig(filename=logfile_name, format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO, datefmt='%m-%d-%Y %I:%M:%S %p')

def hms_code(attr, code):

    if not isinstance(attr, int) or attr < 0:
        raise ValueError("attr must be a positive integer")
    if not isinstance(code, int) or code < 0:
        raise ValueError("code must be a positive integer")

    if attr > 0 and code > 0:
        formatted_attr = f'{attr // 0x10000:0>4X}_{attr % 0x10000:0>4X}'
        formatted_code = f'{code // 0x10000:0>4X}_{code % 0x10000:0>4X}'
        return f'{formatted_attr}_{formatted_code}'
    return ""

# Add a global variable to store the last fetch timestamp and cached data
last_fetch_time = None
cached_data = None

def fetch_english_errors():
    """Fetches English error codes and descriptions from the Bambu site."""
    global last_fetch_time, cached_data
    if last_fetch_time is None or (datetime.now() - last_fetch_time).days >= 1:
        url = "https://e.bambulab.com/query.php?lang=en"
        try:
            response = requests.get(url, timeout=60)  # Specify a timeout value (e.g., 10 seconds)
            if response.status_code == 200:
             response.raise_for_status()  # Raises an HTTPError for bad responses
             data = response.json()
             last_fetch_time = datetime.now()  # Update last fetch time
             cached_data = data["data"]["device_hms"]["en"]
             return cached_data
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch data: {e}")
            return None
        except json.JSONDecodeError:
            logging.error("Failed to decode JSON from response")
            return None
    else:
        ##logging.info("Using cached English error data")
        return cached_data  # Return cached data if not expired

def search_error(error_code, error_list):
    """Searches for a specific error code in the error list."""
    for error in error_list:
        if error["ecode"] == error_code:
            return error
    return None

def on_connect(client, userdata, flags, reason_code, properties):
    """Handles MQTT connect event."""
    client.subscribe("device/"+device_id+"/report", 0)

def on_message(client, userdata, msg):
    global last_gcode_state, first_run, message_sent
    english_errors = []
    message_sent = False
      # Initialize english_errors as an empty list
    try:
        msgData = msg.payload.decode('utf-8')
        dataDict = json.loads(msgData)

        english_errors = fetch_english_errors()
        if 'print' in dataDict:
            if 'gcode_state' in dataDict['print']:
                gcode_state = dataDict['print']['gcode_state']
               ## logging.info("gcode_state has changed to " + gcode_state)
                
                if gcode_state != last_gcode_state:
                    process_print_data(dataDict, client, english_errors)
                    
                    # Update the last known gcode_state
                    last_gcode_state = gcode_state
    except json.JSONDecodeError:
        logging.error("Failed to decode JSON from MQTT message")
    except Exception as e:
        logging.error(f"Unexpected error in on_message: {e}")

def process_print_data(dataDict, client, english_errors):
    """Processes print data from the message."""
    global first_run, message_sent
    msg_text = "<ul>"
    priority = 0  # Default priority
    hms_data = dataDict['print'].get('hms', [{'attr': 0, 'code': 0}])

    if hms_data:  # Check if hms_data is not empty
        hms_data = hms_data[0]  # Get the first element if hms_data is not empty
    else:
        hms_data = {'attr': 0, 'code': 0}  # Default values if hms_data is empty

    # Extract 'attr' and 'code' from hms_data
    attr = hms_data.get('attr', 0)
    code = hms_data.get('code', 0)
    
    # Format the device_error_code using hms_code function
    device__HMS_error_code = hms_code(attr, code)
    
    # Fetch English errors
    english_errors = fetch_english_errors()
    
    if english_errors is None:
        logging.warning("English error data is not available.")
        english_errors = []  # Initialize to an empty list to avoid NoneType error
    
    
    error_code_to_hms_cleaned = str(device__HMS_error_code).replace('_', '')
    found_device_error = search_error(error_code_to_hms_cleaned, english_errors)
    if 'print' in dataDict:
    
        if 'gcode_state' in dataDict['print']:
            gcode_state = dataDict['print']['gcode_state']
            json_formatted_str = json.dumps(dataDict, indent=2)
            logging.info(DASH + json_formatted_str + DASH)
            msg_text += "<li>State: " + gcode_state + " </li>"

        if 'mc_percent' in dataDict['print']:
            percent_done = dataDict['print']['mc_percent']
            msg_text += f"<li>Percent: {percent_done}% </li>"

        if 'subtask_name' in dataDict['print']:
            msg_text += "<li>Name: " + dataDict['print']['subtask_name'] + " </li>"

        # Handle start time
        my_datetime = ""
        if 'gcode_start_time' in dataDict['print']:
            unix_timestamp = float(dataDict['print']['gcode_start_time'])
            if gcode_state == "PREPARE" and unix_timestamp == 0:
                unix_timestamp = float(time.time())
            if unix_timestamp != 0:
                local_timezone = tzlocal.get_localzone()  # get pytz timezone
                local_time = datetime.fromtimestamp(unix_timestamp, local_timezone)
                my_datetime = local_time.strftime("%Y-%m-%d %I:%M %p (%Z)")
            msg_text += "<li>Started: " + my_datetime + " </li>"

        # Handle finish time (approx)
        my_finish_datetime = ""
        remaining_time = ""
        if 'mc_remaining_time' in dataDict['print']:
            time_left_seconds = int(dataDict['print']['mc_remaining_time']) * 60
            if time_left_seconds != 0:
                aprox_finish_time = time.time() + time_left_seconds
                unix_timestamp = float(aprox_finish_time)
                local_timezone = tzlocal.get_localzone()  # get pytz timezone
                local_time = datetime.fromtimestamp(unix_timestamp, local_timezone)
                my_finish_datetime = local_time.strftime("%Y-%m-%d %I:%M %p (%Z)")
                remaining_time = str(timedelta(seconds=time_left_seconds))
            else:
                if gcode_state == "FINISH" and time_left_seconds == 0:
                    my_finish_datetime = "Done!"
            msg_text += "<li>Aprox End: " + my_finish_datetime + " </li>"
            msg_text += f"<li>Remaining time: {remaining_time} </li>"

        # Handling failed state
        if ('fail_reason' in dataDict['print'] and len(dataDict['print']['fail_reason']) > 1) or ('print_error' in dataDict['print'] and dataDict['print']['print_error'] != 0) or gcode_state == "FAILED":
            msg_text += f"<li>print_error: {dataDict['print'].get('print_error', 'N/A')}</li>"
            msg_text += f"<li>mc_print_error_code: {dataDict['print'].get('mc_print_error_code', 'N/A')}</li>"
            msg_text += f"<li>HMS code: {device__HMS_error_code}</li>"
            msg_text += f"<li>Description: {found_device_error['intro']}</li>"
            if device__HMS_error_code:
                msg_text += f"<li>URL: https://wiki.bambulab.com/en/x1/troubleshooting/hmscode/{error_code_to_hms_cleaned}</li>"
            error_code = int(dataDict['print'].get('mc_print_error_code', 0))
            fail_reason = "Print Canceled" if ('fail_reason' in dataDict['print'] and len(dataDict['print']['fail_reason']) > 1 and dataDict['print']['fail_reason'] != '50348044') else dataDict['print'].get('fail_reason', 'N/A')

            # Custom fail_reason based on error_code
            if error_code in (32778, 32771, 32773, 32774, 32769):
                custom_fail_reasons = {
                    32778: "Arrr! Swab the poop deck!",
                    32771: "Spaghetti and meatballs!",
                    32773: "Didn't pull out!",
                    32774: "Build plate mismatch!",
                    32769: "Let's take a moment to PAUSE!",
                }
                fail_reason = custom_fail_reasons.get(error_code, fail_reason)
            msg_text += f"<li>fail_reason: {fail_reason}</li>"
            priority = 1  # Set higher priority for errors


        # Check for specific error codes or fail reasons to turn off the lights
        if ('print_error' in dataDict['print'] and dataDict['print']['print_error'] == '50348044') or ('fail_reason' in dataDict['print'] and dataDict['print']['fail_reason'] == '50348044'):
            # Logic to turn off the lights
            Chamberlight_off = {
                "system": {
                    "sequence_id": "0",
                    "command": "ledctrl",
                    "led_node": "chamber_light",
                    "led_mode": "off",
                    "led_on_time": 500,
                    "led_off_time": 500,
                    "loop_times": 0,
                    "interval_time": 0
                }
            }
            ChamberLogo_off = {
                "print": {
                    "sequence_id": "2026",
                    "command": "M960 S5 P0",
                    "param": "\n"
                },
                "user_id": "1234567890"
            }
            client.publish("device/"+device_id+"/report", json.dumps(Chamberlight_off))
            client.publish("device/"+device_id+"/report", json.dumps(ChamberLogo_off))
            logging.info("Lights OFF")
        # After processing, send the message if needed
        if msg_text != "<ul>":
            msg_text += "</ul>"
    if not message_sent:
        try:
            if not first_run:  
                message = po_user.create_message(
                    title=PO_TITLE,
                    message=msg_text,
                    html=True,
                    sound=PO_SOUND,  # This is where the sound is specified
                    priority=priority
                )
                message.send()
                if priority == 1:
                    for _ in range(repeat_errors):
                        time.sleep(pause_error_secs)
                        message.send()
            else:
                first_run = False
            message_sent = True 
        except ValueError as e:
                logging.error(f"Failed to send Pushover message due to invalid sound: {e}")
                # Optionally, send the message with a default sound if the specified one is invalid
    
                try:
                    if not first_run:    
                        message = po_user.create_message(
                            title=PO_TITLE,
                            message=msg_text,
                            html=True,
                            sound='pushover',  # Using a default sound
                            priority=priority
                        )
                        message.send()
                        if priority == 1:
                            for _ in range(repeat_errors):
                                time.sleep(pause_error_secs)
                                message.send()
                except Exception as e:
                            logging.error(f"Unexpected error when sending Pushover message with default sound: {e}")
                else:
                        first_run = False            
                message_sent = True
def main(argv):
    try:
        setup_logging()
        logging.info("Starting")
        client = paho.Client(paho.CallbackAPIVersion.VERSION2)
        client.tls_set(ca_certs=None, certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS, ciphers=None)
        client.tls_insecure_set(True)
        client.username_pw_set(user, password)
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(host, port, 60)
        client.loop_forever()
    except Exception as e:
        logging.error(f"Fatal error in main: {e}")
        print("Fatal error Please read Logs")

if __name__ == "__main__":
    main(sys.argv[1:])

