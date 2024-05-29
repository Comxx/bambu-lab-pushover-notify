#!/usr/bin/python
import logging
import paho.mqtt.client as paho
import ssl
import sys
from settings import *
import tzlocal
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from chump import Application
import json
import requests
import time
import wled
from flask import Flask, request, render_template, jsonify
from flask_socketio import SocketIO, emit
import hashlib

DASH = '\n-------------------------------------------\n'
doorlight = False
doorOpen = ""
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
previous_gcode_states = {}
printer_states = {}
errorstate = ''
current_stage  = 'unknown'
# Initialize Flask app and SocketIO
app = Flask(__name__)
socketio = SocketIO(app)

CURRENT_STAGE_IDS = {
    "default": "unknown",
    0: "printing",
    1: "auto_bed_leveling",
    2: "heatbed_preheating",
    3: "sweeping_xy_mech_mode",
    4: "changing_filament",
    5: "m400_pause",
    6: "paused_filament_runout",
    7: "heating_hotend",
    8: "calibrating_extrusion",
    9: "scanning_bed_surface",
    10: "inspecting_first_layer",
    11: "identifying_build_plate_type",
    12: "calibrating_micro_lidar",  # DUPLICATED?
    13: "homing_toolhead",
    14: "cleaning_nozzle_tip",
    15: "checking_extruder_temperature",
    16: "paused_user",
    17: "paused_front_cover_falling",
    18: "calibrating_micro_lidar",  # DUPLICATED?
    19: "calibrating_extrusion_flow",
    20: "paused_nozzle_temperature_malfunction",
    21: "paused_heat_bed_temperature_malfunction",
    22: "filament_unloading",
    23: "paused_skipped_step",
    24: "filament_loading",
    25: "calibrating_motor_noise",
    26: "paused_ams_lost",
    27: "paused_low_fan_speed_heat_break",
    28: "paused_chamber_temperature_control_error",
    29: "cooling_chamber",
    30: "paused_user_gcode",
    31: "motor_noise_showoff",
    32: "paused_nozzle_filament_covered_detected",
    33: "paused_cutter_error",
    34: "paused_first_layer_error",
    35: "paused_nozzle_clog",
    # X1 returns -1 for idle
    -1: "idle",  # DUPLICATED
    # P1 returns 255 for idle
    255: "idle",  # DUPLICATED
}

def get_current_stage_name(stage_id):
    return CURRENT_STAGE_IDS.get(int(stage_id), "unknown")
# Load initial printer settings from a file
try:
    with open('settings.py', 'r') as f:
        content = f.read().replace('brokers = ', '')
        if content.strip():  # Check if content is not empty
            brokers = json.loads(content)
        else:
            brokers = []
except FileNotFoundError:
    brokers = []
except json.JSONDecodeError:
    print("Error: The content of 'settings.py' is not valid JSON.")
    brokers = []

@app.route('/')
def home():
    printers = [{"printer_id": hash_printer_id(broker["device_id"]), "printer_title": broker["Printer_Title"], "printer_color": broker["color"]}for broker in brokers]
    return render_template('index.html', printers=printers)
@app.route('/save_printer_settings', methods=['POST'])
def save_printer_settings():
    global brokers
    brokers = request.json
    with open('settings.py', 'w') as f:
        f.write('brokers = ' + json.dumps(brokers, indent=4))
    return jsonify({"status": "success"})

def hash_printer_id(printer_id):
    return hashlib.sha256(printer_id.encode()).hexdigest()

def setup_logging():
    local_timezone = tzlocal.get_localzone()
    current_datetime = datetime.now(local_timezone)
    datetime_str = current_datetime.strftime("%Y-%m-%d_%I-%M-%S%p")
    logfile_path = "logs/"
    logfile_name = f"{logfile_path}output_{datetime_str}.log"
    log_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s', datefmt='%m-%d-%Y %I:%M:%S %p')
    
    rotating_handler = RotatingFileHandler(logfile_name, maxBytes=1024*1024, backupCount=5)
    rotating_handler.setFormatter(log_formatter)
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(rotating_handler)   
def on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe("device/"+userdata["device_id"]+"/report", 0)

def on_publish(client, userdata, mid, reason_codes, properties):
    logging.info(f"Message published successfully to {userdata['Printer_Title']}")  

def on_message(client, userdata, msg):
    global DASH, gcode_state_prev, first_run, percent_notify, previous_print_error, my_finish_datetime, doorlight, doorOpen, previous_gcode_states, printer_states, errorstate, current_stage
    try:
        po_app = Application(userdata['my_pushover_app'])
        po_user = po_app.get_user(userdata['my_pushover_user'])
        server_identifier = (userdata['password'], userdata['device_id'])
        prev_state = previous_gcode_states.get(server_identifier, {'state': None})
        if msg.payload is None:
            logging.info("No message received from Printer")
            return
        msgData = msg.payload.decode('utf-8')
        dataDict = json.loads(msgData)

        if 'print' in dataDict:
            device_id = userdata['device_id']
            if not device_id:
                logging.error("Device ID not found in the message")
                return
            # Initialize state for new printer
            if device_id not in printer_states:
                printer_states[device_id] = {
                    'previous_print_error': 0,
                    'doorlight': False,
                    'doorOpen': "",
                    'gcode_state_prev': '',
                    'errorstate': ''
                }

            printer_state = printer_states[device_id]
            
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

            if found_device_error is None:
                found_device_error = {'intro': 'Unknown error'}

            gcode_state = dataDict['print'].get('gcode_state')
            percent_done = dataDict['print'].get('mc_percent', 0) 
            print_error = dataDict['print'].get('print_error')
            current_stage = get_current_stage_name(dataDict['print'].get('mc_print_stage'))
            
        if "print" in dataDict and "home_flag" in dataDict["print"]:
            home_flag = dataDict["print"]["home_flag"]
            door_state = bool((home_flag >> 23) & 1)
            if printer_state['doorOpen'] != door_state:
                printer_state['doorOpen'] = door_state
                if gcode_state == "FINISH" or gcode_state == "IDLE" or gcode_state == "FAILED": 
                    if printer_state['doorOpen']: 
                        if not printer_state['doorlight']:
                            if userdata['ledligth']:
                                wled.set_power(userdata['wled_ip'], True)
                                wled.set_brightness(userdata['wled_ip'], 255)
                                wled.set_color(userdata['wled_ip'], (255, 255, 255))
                                logging.info("Opened")
                                printer_state['doorlight'] = True
                            else:
                                logging.info("Opened No WLED")
                                printer_state['doorlight'] = True 
                    else:
                        if printer_state['doorlight']: 
                            if userdata['ledligth']:
                                wled.set_power(userdata['wled_ip'], False)
                                logging.info("Closed")
                                printer_state['doorlight'] = False
                            else:
                                logging.info("Closed No WLED")
                                printer_state['doorlight'] = False
            if printer_state['previous_print_error'] == 50348044 and print_error == 0:
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
                client.publish("device/" + userdata["device_id"] + "/request", payload)
                client.publish("device/" + userdata["device_id"] + "/request", payloadlogo)
                message = po_user.create_message(
                    title=f"{userdata['Printer_Title']} Cancelled",
                    message="Print Cancelled",
                    sound=userdata['PO_SOUND'],
                    priority=1
                )
                message.send()
                logging.info("Print cancelled on " + userdata['Printer_Title'])
                printer_state['previous_print_error'] = print_error
                return
            else:
                printer_state['previous_print_error'] = print_error

            remaining_time = ""
            if 'mc_remaining_time' in dataDict['print']:
                time_left_seconds = int(dataDict['print']['mc_remaining_time']) * 60
                if time_left_seconds != 0:
                    aprox_finish_time = time.time() + time_left_seconds
                    unix_timestamp = float(aprox_finish_time)
                    local_timezone = tzlocal.get_localzone()
                    local_time = datetime.fromtimestamp(unix_timestamp, local_timezone)
                    my_finish_datetime = local_time.strftime("%m-%d-%Y %I:%M %p (%Z)")
                    remaining_time = str(timedelta(minutes=dataDict['print']['mc_remaining_time']))
                else:
                    if gcode_state == "FINISH" and time_left_seconds == 0:
                        my_finish_datetime = "Done!"

            if gcode_state and (gcode_state != prev_state['state'] or prev_state['state'] is None):
                priority = 0
                printer_states[errorstate] = "NONE"
                logging.info(DASH)
                logging.info(userdata["Printer_Title"] + " gcode_state has changed to " + gcode_state)
                json_formatted_str = json.dumps(dataDict, indent=2)
                logging.info(DASH + json_formatted_str + DASH)
                previous_gcode_states[server_identifier] = {'state': gcode_state}

                msg_text = "<ul>"
                msg_text += "<li>State: " + gcode_state + " </li>"
                msg_text += f"<li>Percent: {percent_done}% </li>"
                if 'subtask_name' in dataDict['print']:
                    msg_text += "<li>Name: " + dataDict['print']['subtask_name'] + " </li>"
                msg_text += f"<li>Remaining time: {remaining_time} </li>"
                msg_text += "<li>Aprox End: " + my_finish_datetime + "</li>"

                fail_reason = ""
                if( ('fail_reason' in dataDict['print'] and len(dataDict['print']['fail_reason']) > 1) or ( 'print_error' in dataDict['print'] and dataDict['print']['print_error'] != 0 ) or gcode_state == "FAILED" ):
                    printer_states[errorstate] = "ERROR"
                    if 'print_error' in dataDict['print'] and dataDict['print']['print_error'] is not None:
                        msg_text += f"<li>print_error: {dataDict['print']['print_error']}</li>"
                    if 'mc_print_error_code' in dataDict['print'] and dataDict['print']['mc_print_error_code'] is not None:
                        msg_text += f"<li>mc_print_error_code: {dataDict['print']['mc_print_error_code']}</li>"
                    if device__HMS_error_code is not None:
                        msg_text += f"<li>HMS code: {device__HMS_error_code}</li>"
                        msg_text += f"<li>Description: {found_device_error['intro']}</li>"
                    if 'fail_reason' in dataDict['print']:
                        fail_reason = dataDict['print']['fail_reason']
                    else:
                        fail_reason = 'N/A'
                    msg_text += f"<li>fail_reason: {fail_reason}</li>"
                    priority = 1
                    msg_text += "</ul>"
                if not first_run:
                    message = po_user.create_message(
                        title=userdata['Printer_Title'],
                        message=msg_text,
                        url=f"https://wiki.bambulab.com/en/x1/troubleshooting/hmscode/{device__HMS_error_code}" if device__HMS_error_code else "",
                        html=True,
                        sound=userdata['PO_SOUND'],
                        priority=priority
                    )
                    message.send()
                    device__HMS_error_code = ""

            error_messages = []

            if 'print_error' in dataDict['print'] and dataDict['print']['print_error'] is not None:
                error_messages.append(f"print_error: {dataDict['print']['print_error']}")
            if 'mc_print_error_code' in dataDict['print'] and dataDict['print']['mc_print_error_code'] is not None:
                error_messages.append(f"mc_print_error_code: {dataDict['print']['mc_print_error_code']}")
            if device__HMS_error_code is not None:
                error_messages.append(f"HMS code: {device__HMS_error_code}")
                error_messages.append(f"Description: {found_device_error['intro']}")
            if 'fail_reason' in dataDict['print']:
                fail_reason = dataDict['print']['fail_reason']
            else:
                fail_reason = 'N/A'
            error_messages.append(f"fail_reason: {fail_reason}")

            socketio.emit('update_time', {
                'printer_id': hash_printer_id (userdata["device_id"]),
                'printer': userdata['Printer_Title'],
                'percent': percent_done,
                'remaining_time': remaining_time,
                'approx_end': my_finish_datetime,
                'state': gcode_state,
                'project_name': dataDict['print']['subtask_name'],
                'current_stage': get_current_stage_name(dataDict['print'].get('mc_print_stage')),  
                'error': printer_states[errorstate],
                'error_messages': error_messages if errorstate == "ERROR" else []
            })
            
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
def connect_to_broker(broker):
    client = paho.Client(paho.CallbackAPIVersion.VERSION2)
    client.tls_set(ca_certs=None, certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS, ciphers=None)
    client.tls_insecure_set(True)
    client.username_pw_set(broker["user"], broker["password"])
    client.user_data_set(broker)  # Pass the broker data to use in callbacks
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_publish = on_publish
    client.connect(broker["host"], broker["port"], 60)
    client.loop_start()  # Use loop_start() to start thart the client loop asynchronously
    return client

def main(argv):
    try:
            setup_logging()
            logging.info("Starting")

            # Connect to each broker
            mqtt_clients = []
            for broker_config in brokers:
                client = connect_to_broker(broker_config)
                mqtt_clients.append(client)
            logging.info("Flask server starting...")
            socketio.run(app, host='0.0.0.0', port=5000)
            logging.info("Flask server started successfully")
            # Keep the main thread alive
            while True:
            # Fetch and process data for each printer
                for client in mqtt_clients:
                    client.loop()
                
                # Add a short delay to avoid high CPU usage
                time.sleep(1)
    except Exception as e:
        logging.error(f"Fatal error in main: {e}")
        print("Fatal error Please read Logs")


if __name__ == "__main__":
    main(sys.argv[1:])    