#!/usr/bin/python3
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

# Global state
first_run = False
percent_notify = False
percent_done = 0
message_sent = False
last_fetch_time = None
cached_data = None
gcode_state_prev = ''
previous_print_error = 0
my_finish_datetime = ""
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

def on_publish(client, userdata, mid, reason_codes, properties):
    logging.info("Message published successfully to Printer")
def on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe("device/"+device_id+"/report", 0)
def on_message(client, userdata, msg):
    global DASH, gcode_state_prev, app, user, my_pushover_app, my_pushover_user, first_run, percent_notify, percent_donetry, previous_print_error, my_finish_datetime
    try:
        if msg.payload is None:
            logging.info("No message received from Printer")
            return
        msgData = msg.payload.decode('utf-8')
        dataDict = json.loads(msgData)
        
        if 'print' in dataDict:

            hms_data = dataDict['print'].get('hms', [{'attr': 0, 'code': 0}])
        
            if hms_data:
                hms_data = hms_data[0]
            else:
                hms_data = {'attr': 0, 'code': 0}
            
            attr = hms_data.get('attr', 0)
            code = hms_data.get('code', 0)
            
            device__HMS_error_code = hms_code(attr, code)
            
            english_errors = fetch_english_errors() or []
            
            error_code_to_hms_cleaned = str(device__HMS_error_code).replace('_', '')
            found_device_error = search_error(error_code_to_hms_cleaned, english_errors)
            
            gcode_state = dataDict['print'].get('gcode_state')
            percent_done = dataDict['print'].get('mc_percent', 0)  # Provide a default in case the key is missing
            print_error = dataDict['print'].get('print_error')

        # Check if the print has been cancelled
            if previous_print_error == 50348044 and print_error == 0:
                    chamberlight_off_data = {
                            "system": {
                            "sequence_id": "2003",
                            "command": "ledctrl",
                            "led_node": "chamber_light",
                            "led_mode": "off",
                            "led_on_time": 500,
                            "led_off_time": 500,
                            "loop_times": 0,
                            "interval_time": 0
                            },
                            "user_id": "123456789"
                            }
                    Chamberlogo_off_data = {
                                "print": {
                                "sequence_id": "2026",
                                "command": "gcode_line",
                                "param": "M960 S5 P0 \n"
                                 },
                                "user_id": "1234567890"
                                }

                    payload = json.dumps(chamberlight_off_data)
                    payloadlogo = json.dumps(Chamberlogo_off_data)
                    client.publish("device/" + device_id + "/request", payload)
                    client.publish("device/" + device_id + "/request", payloadlogo)
                    logging.info("Print cancelled")
                    previous_print_error = print_error
                    return
            else:
                    previous_print_error = print_error
            if gcode_state and gcode_state_prev != gcode_state:
            
                priority = 0
                logging.info(DASH)
                logging.info("gcode_state has changed to " + gcode_state)
                json_formatted_str = json.dumps(dataDict, indent=2)
                logging.info(DASH + json_formatted_str + DASH)
                gcode_state_prev = gcode_state

                my_datetime = ""
                if('gcode_start_time' in dataDict['print']):
                        unix_timestamp = float(dataDict['print']['gcode_start_time'])
                        if(gcode_state == "PREPARE" and unix_timestamp == 0):
                                unix_timestamp = float(time.time())
                        if(unix_timestamp != 0):
                            local_timezone = tzlocal.get_localzone() # get pytz timezone
                            local_time = datetime.fromtimestamp(unix_timestamp, local_timezone)
                            my_datetime = local_time.strftime("%Y-%m-%d %I:%M %p (%Z)")
                        else:
                             my_finish_datetime = ""

                remaining_time = ""
                if('mc_remaining_time' in dataDict['print']):
                        time_left_seconds = int(dataDict['print']['mc_remaining_time']) * 60
                        if(time_left_seconds != 0):
                            aprox_finish_time = time.time() + time_left_seconds
                            unix_timestamp = float(aprox_finish_time)
                            local_timezone = tzlocal.get_localzone() # get pytz timezone
                            local_time = datetime.fromtimestamp(unix_timestamp, local_timezone)
                            my_finish_datetime = local_time.strftime("%Y-%m-%d %I:%M %p (%Z)")
                            remaining_time = str(timedelta(minutes=dataDict['print']['mc_remaining_time']))
                        else:
                            if(gcode_state == "FINISH" and time_left_seconds == 0):
                                my_finish_datetime = "Done!"

                msg_text = "<ul>"
                msg_text += "<li>State: " + gcode_state + " </li>"
                msg_text += f"<li>Percent: {percent_done}% </li>"
                if 'subtask_name' in dataDict['print']:
                    msg_text += "<li>Name: " + dataDict['print']['subtask_name'] + " </li>"
                msg_text += f"<li>Remaining time: {remaining_time} </li>"
                msg_text += "<li>Started: " + my_datetime + "</li>"
                msg_text += "<li>Aprox End: " + my_finish_datetime + "</li>"

                fail_reason = ""
                if( ('fail_reason' in dataDict['print'] and len(dataDict['print']['fail_reason']) > 1) or ( 'print_error' in dataDict['print'] and dataDict['print']['print_error'] != 0 ) or gcode_state == "FAILED" ):
                    if 'print_error' in dataDict['print'] and dataDict['print']['print_error'] is not None:
                        msg_text += f"<li>print_error: {dataDict['print']['print_error']}</li>"
                    if 'mc_print_error_code' in dataDict['print'] and dataDict['print']['mc_print_error_code'] is not None:
                        msg_text += f"<li>mc_print_error_code: {dataDict['print']['mc_print_error_code']}</li>"
                    if device__HMS_error_code is not None:
                        msg_text += f"<li>HMS code: {device__HMS_error_code}</li>"                        
                        msg_text += f"<li>Description: {found_device_error['intro']}</li>"
                    if 'fail_reason' in dataDict['print']:
                        raw_fail_reason = dataDict['print']['fail_reason']
                        if raw_fail_reason and len(raw_fail_reason) > 1 and raw_fail_reason != '50348044':
                            fail_reason = "Print Canceled"
                        else:
                            fail_reason = raw_fail_reason if raw_fail_reason is not None else 'N/A'
                    else:
                        fail_reason = 'N/A'
                    msg_text += f"<li>fail_reason: {fail_reason}</li>"
                    priority = 1
                    msg_text += "</ul>"
                if not first_run:
                    message = po_user.create_message(
                        title=PO_TITLE,
                        message=msg_text,
                        url= f"https://wiki.bambulab.com/en/x1/troubleshooting/hmscode/{device__HMS_error_code}" if device__HMS_error_code else "",
                        html=True,
                        sound=PO_SOUND,
                        priority=priority
                    )
                    message.send()
                    #if priority == 1:
                    #    for x in range(repeat_errors):
                    #        time.sleep(pause_error_secs)
                        #    message.send()    
        else:
            first_run = False
    except KeyError as e:
        logging.error(f"KeyError accessing 'gcode_state': {e}")
    except json.JSONDecodeError as e:
        logging.error("Failed to decode JSON from MQTT message: {e}")
    except Exception as e:
        logging.error(f"Unexpected error in on_message: {e}")
        
def hms_code(attr, code):
    try:
        if not isinstance(attr, int) or attr < 0 or not isinstance(code, int) or code < 0:
            raise ValueError("attr and code must be positive integers")

        if attr > 0 and code > 0:
            formatted_attr = f'{attr // 0x10000:0>4X}_{attr % 0x10000:0>4X}'
            formatted_code = f'{code // 0x10000:0>4X}_{code % 0x10000:0>4X}'
            return f'{formatted_attr}_{formatted_code}'
        return ""
    except Exception as e:
        logging.error(f"Unexpected error in hms_code: {e}")

def fetch_english_errors():
    global last_fetch_time, cached_data
    if last_fetch_time is None or (datetime.now() - last_fetch_time).days >= 1:
        url = "https://e.bambulab.com/query.php?lang=en"
        try:
            response = requests.get(url, timeout=60)  
            response.raise_for_status()  
            data = response.json()
            last_fetch_time = datetime.now()  
            cached_data = data["data"]["device_hms"]["en"]
            return cached_data
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch data: {e}")
            return None
        except json.JSONDecodeError:
            logging.error("Failed to decode JSON from response")
            return None
        except Exception as e:
            logging.error(f"Unexpected error in fetch_english_errors: {e}")
    else:
        return cached_data  
def search_error(error_code, error_list):
    try:
        for error in error_list:
            if error["ecode"] == error_code:
                return error
        return None
    except Exception as e:
        logging.error(f"Unexpected error in earch_error: {e}")              
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
        client.on_publish = on_publish
        client.connect(host, port, 60)
        client.loop_forever()
    except Exception as e:
        logging.error(f"Fatal error in main: {e}")
        print("Fatal error Please read Logs")

if __name__ == "__main__":
    main(sys.argv[1:])     