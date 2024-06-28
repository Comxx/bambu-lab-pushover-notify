#!/usr/bin/python
from ast import If
import logging
import paho.mqtt.client as paho
import ssl
import sys
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
import socket
from bambu_cloud import BambuCloud
import traceback

DASH = '\n-------------------------------------------\n'
doorlight = False
doorOpen = ""
# Global state
first_run = False
percent_notify = False
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
stg_cur:int = None
gcode_state:str = None
layer_num:int = None
total_layer_num:int = None
subtask_name:str = None
percent_done:int = None
mc_remaining_time:int = None
project_id:str = None
print_error:int = 0
mc_print_stage:str = None
printer_status = {}
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
    if stage_id is None:
        return "unknown"
    return CURRENT_STAGE_IDS.get(int(stage_id), "unknown")
# Load initial printer settings from a fil
try:
    with open('settings.json', 'r') as f:
        brokers = json.load(f)
except FileNotFoundError:
    brokers = []

@app.route('/')
def home():
    printers = [
    {
        "printer_id": broker["device_id"],
        "host": broker["host"],
        "port": broker["port"],
        "user": broker["user"],
        "password": broker["password"],
        "printer_title": broker["Printer_Title"],
        "po_sound": broker["PO_SOUND"],
        "my_pushover_user": broker["my_pushover_user"],
        "my_pushover_app": broker["my_pushover_app"],
        "ledlight": broker["ledlight"],
        "wled_ip": broker["wled_ip"],
        "printer_color": broker["color"]
    } 
    for broker in brokers
]
    return render_template('index.html', printers=printers)
@app.route('/delete_printer', methods=['POST'])
def delete_printer():
    try:
        printer_id = request.json.get('printer_id')
        if not printer_id:
            return jsonify({'status': 'error', 'message': 'Printer ID not provided'})

        with open('settings.json', 'r') as file:
            settings = json.load(file)

        # Remove the printer with the specified ID
        settings = [printer for printer in settings if printer['device_id'] != printer_id]

        # Save the updated settings back to the file
        with open('settings.json', 'w') as file:
            json.dump(settings, file, indent=4)

        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})
@app.route('/save_printer_settings', methods=['POST'])
def save_printer_settings():
    global brokers
    brokers = request.json
    with open('settings.json', 'w') as f:
        f.write(json.dumps(brokers, indent=4))
    return jsonify({"status": "success"})
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
    getInfo = {"info": {"sequence_id": "0", "command": "get_version"}}
    payloadvesion = json.dumps(getInfo)
    if not client.publish("device/" + userdata["device_id"] + "/request", payloadvesion):
        raise Exception("Failed to publish get_version")
    pushAll = { "pushing": { "sequence_id": "1", "command": "pushall" }, "user_id": "1234567890"}
    payloadpushall = json.dumps(pushAll)
    if not client.publish("device/" + userdata["device_id"] + "/request", payloadpushall):
        raise Exception("Failed to publish full sync")


def on_publish(client, userdata, mid, reason_codes, properties):
    logging.info(f"Message published successfully to {userdata['Printer_Title']}")  

def on_message(client, userdata, msg):
    global DASH, gcode_state_prev, first_run, percent_notify, previous_print_error, my_finish_datetime
    global doorlight, doorOpen, previous_gcode_states, printer_states
    global errorstate, current_stage, printer_status
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
                if device_id not in printer_status:
                        printer_status[device_id] = {
                            'stg_cur': 0,
                            'gcode_state': None,
                            'layer_num': 0,
                            'total_layer_num': 0,
                            'subtask_name': 'Unkown',
                            'project_id': 'Unkown',
                            'print_error': 0,
                            'mc_remaining_time': 0,
                            'percent_done': 0,
                            'mc_print_stage': 'unknown'
                        }
                    
                    # Update printer state with new data
                # stg_cur = dataDict['print'].get("stg_cur", printer_status[device_id]['stg_cur'])
                # gcode_state = dataDict['print'].get("gcode_state", printer_status[device_id]['gcode_state'])
                # layer_num = dataDict['print'].get("layer_num", printer_status[device_id]['layer_num'])
                # total_layer_num = dataDict['print'].get("total_layer_num", printer_status[device_id]['total_layer_num'])
                # subtask_name = dataDict['print'].get("subtask_name", printer_status[device_id]['subtask_name'])
                # project_id = dataDict['print'].get("project_id", printer_status[device_id]['project_id'])
                # percent_done = dataDict['print'].get("mc_percent", printer_status[device_id]['percent_done'])
                # print_error = dataDict['print'].get("print_error", printer_status[device_id]['print_error'])
                # mc_remaining_time = dataDict['print'].get("mc_remaining_time", printer_status[device_id]['mc_remaining_time'])
                # mc_print_stage = dataDict['print'].get("mc_print_stage", printer_status[device_id]['mc_print_stage'])
                
                try:
                    stg_cur = dataDict['print'].get("stg_cur", printer_status[device_id]['stg_cur'])
                except KeyError as e:
                    logging.error(f"KeyError accessing 'stg_cur': {e}")

                try:
                    gcode_state = dataDict['print'].get("gcode_state", printer_status[device_id]['gcode_state'])
                except KeyError as e:
                    logging.error(f"KeyError accessing 'gcode_state': {e}")

                try:
                    layer_num = dataDict['print'].get("layer_num", printer_status[device_id]['layer_num'])
                except KeyError as e:
                    logging.error(f"KeyError accessing 'layer_num': {e}")

                try:
                    total_layer_num = dataDict['print'].get("total_layer_num", printer_status[device_id]['total_layer_num'])
                except KeyError as e:
                    logging.error(f"KeyError accessing 'total_layer_num': {e}")

                try:
                    subtask_name = dataDict['print'].get("subtask_name", printer_status[device_id]['subtask_name'])
                except KeyError as e:
                    logging.error(f"KeyError accessing 'subtask_name': {e}")

                try:
                    project_id = dataDict['print'].get("project_id", printer_status[device_id]['project_id'])
                except KeyError as e:
                    logging.error(f"KeyError accessing 'project_id': {e}")

                try:
                    percent_done = dataDict['print'].get("mc_percent", printer_status[device_id]['percent_done'])
                except KeyError as e:
                    logging.error(f"KeyError accessing 'mc_percent': {e}")

                try:
                    print_error = dataDict['print'].get("print_error", printer_status[device_id]['print_error'])
                except KeyError as e:
                    logging.error(f"KeyError accessing 'print_error': {e}")

                try:
                    mc_remaining_time = dataDict['print'].get("mc_remaining_time", printer_status[device_id]['mc_remaining_time'])
                except KeyError as e:
                    logging.error(f"KeyError accessing 'mc_remaining_time': {e}")

                try:
                    mc_print_stage = dataDict['print'].get("mc_print_stage", printer_status[device_id]['mc_print_stage'])
                except KeyError as e:
                    logging.error(f"KeyError accessing 'mc_print_stage': {e}")
                current_stage = get_current_stage_name(mc_print_stage) 
                # Update printer state in the dictionary
                printer_status[device_id] = {
                    'stg_cur': stg_cur,
                    'gcode_state': gcode_state,
                    'layer_num': layer_num,
                    'total_layer_num': total_layer_num,
                    'subtask_name': subtask_name,
                    'project_id': project_id,
                    'percent_done': percent_done,
                    'print_error': print_error,
                    'mc_remaining_time': mc_remaining_time,
                    'mc_print_stage': mc_print_stage
                }
                
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
                found_hms_error = search_error(error_code_to_hms_cleaned, english_errors)
                hex_error_code = decimal_to_hex(print_error)
                device_errors = fetch_device_errors() or []
                found_device_error = search_error(hex_error_code, device_errors)
                if found_hms_error is None:
                    found_hms_error = {'intro': 'Unknown error'}
                if found_device_error is None:
                    found_device_error = {'intro': 'Unknown error'}         
                
                if "print" in dataDict and "home_flag" in dataDict["print"]:
                        home_flag = dataDict["print"]["home_flag"]
                        door_state = bool((home_flag >> 23) & 1)
                        if printer_state['doorOpen'] != door_state:
                                printer_state['doorOpen'] = door_state
                                if gcode_state == "FINISH" or gcode_state == "IDLE" or gcode_state == "FAILED": 
                                    if printer_state['doorOpen']: 
                                        if not printer_state['doorlight']:
                                            if userdata['ledlight']:
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
                                            if userdata['ledlight']:
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
                time_left_seconds = int(mc_remaining_time) * 60
                if time_left_seconds != 0:
                    aprox_finish_time = time.time() + time_left_seconds
                    unix_timestamp = float(aprox_finish_time)
                    local_timezone = tzlocal.get_localzone()
                    local_time = datetime.fromtimestamp(unix_timestamp, local_timezone)
                    my_finish_datetime = local_time.strftime("%m-%d-%Y %I:%M %p (%Z)")
                    remaining_time = str(timedelta(minutes=mc_remaining_time))
                else:
                    if gcode_state == "FINISH" and time_left_seconds == 0:
                        my_finish_datetime = "Done!"
                if gcode_state and (gcode_state != prev_state['state'] or prev_state['state'] is None):
                    priority = 0
                    printer_state[errorstate] = "NONE"
                    logging.info(DASH)
                    logging.info(userdata["Printer_Title"] + " gcode_state has changed to " + gcode_state)
                    json_formatted_str = json.dumps(dataDict, indent=2)
                    logging.info(DASH + json_formatted_str + DASH)
                    previous_gcode_states[server_identifier] = {'state': gcode_state}

                    msg_text = "<ul>"
                    msg_text += "<li>State: " + gcode_state + " </li>"
                    msg_text += f"<li>Percent: {percent_done}% </li>"
                    msg_text += f"<li>Lines: {layer_num}/{total_layer_num} </li>"
                    if 'subtask_name' in dataDict['print']:
                        msg_text += "<li>Name: " + subtask_name + " </li>"
                    msg_text += f"<li>Remaining time: {remaining_time} </li>"
                    msg_text += "<li>Aprox End: " + my_finish_datetime + "</li>"
                    if( ( 'print_error' in dataDict['print'] and print_error != 0 ) or gcode_state == "FAILED" ):
                        printer_state[errorstate] = "ERROR"
                        if 'print_error' in dataDict['print'] and print_error is not None:
                            msg_text += f"<li>print_error: {print_error}</li>"
                        if device__HMS_error_code is None:   
                            msg_text += f"<li>Description: {found_device_error['intro']}</li>"
                        if device__HMS_error_code is not None:
                            msg_text += f"<li>HMS code: {device__HMS_error_code}</li>"
                            msg_text += f"<li>Description: {found_hms_error['intro']}</li>"
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

                if 'print_error' in dataDict['print'] and print_error is not None:
                    error_messages.append(f"print_error: {dataDict['print']['print_error']}")
                if device__HMS_error_code is not None:
                    error_messages.append(f"HMS code: {device__HMS_error_code}")
                    error_messages.append(f"Description: {found_hms_error['intro']}") 
                error_state = printer_states[errorstate]
                socketio.emit('printer_update', {
                    'printer_id': userdata["device_id"],
                    'printer': userdata['Printer_Title'],
                    'percent': percent_done,
                    'remaining_time': remaining_time,
                    'approx_end': my_finish_datetime,
                    'state': gcode_state,
                    'project_name': subtask_name,
                    'current_stage': get_current_stage_name(mc_print_stage),  
                    'error': error_state,
                    'error_messages': error_messages if error_state == "ERROR" else []
                })
                
            else:
                first_run = False
    except KeyError as e:
            logging.error(f"KeyError accessing in MsgHandler: {e}")
    except json.JSONDecodeError as e:
            logging.error("Failed to decode JSON from MQTT message: {e}")
    except Exception as e:
            logging.error(f"Unexpected error in on_message: {e}")
            logging.error(traceback.format_exc())


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
def fetch_device_errors():
            last_fetch_error_time = None
            if last_fetch_error_time is None or (datetime.now() - last_fetch_error_time).days >= 1:
                url = "https://e.bambulab.com/query.php?lang=en"
                try:
                    response = requests.get(url, timeout=60)
                    response.raise_for_status()  # Raise an exception for bad status codes
                    data = response.json()
                    last_fetch_error_time = datetime.now()
                    cached_device_error_data = data.get("data", {}).get("device_error", {}).get("en", [])
                    return cached_device_error_data
                except requests.exceptions.RequestException as e:
                    logging.error(f"Failed to fetch data: {e}")
                    return None
                except json.JSONDecodeError:
                    logging.error("Failed to decode JSON from response")
                    return None
                except Exception as e:
                    logging.error(f"Unexpected error in fetch_english_errors: {e}")
                    return None
            else:
                return cached_device_error_data    
def decimal_to_hex(decimal_error_code):
    hex_error_code = hex(decimal_error_code)[2:]

    hex_error_code = hex_error_code.zfill(8)
    return hex_error_code     
def search_error(error_code, error_list):
    try:
        for error in error_list:
            if error["ecode"] == error_code:
                return error
        return None
    except Exception as e:
        logging.error(f"Unexpected error in earch_error: {e}")                  
def on_disconnect(client, userdata, rc):
    if rc != 0:
        logging.warning(f"Unexpected disconnection. Reconnecting... (rc={rc})")
def connect_to_broker(broker):
    # Mqttpassworrd = ''
    # Mqttuser = ''
    # bambu_cloud = BambuCloud(region="US", email=broker["user"], username='', auth_token='')
    # if broker["printer_type"] == "A1":
    #     bambu_cloud.login(region="US", email=broker["user"], password= broker["password"])
    #     Mqttpassworrd = bambu_cloud.auth_token
    #     Mqttuser = bambu_cloud.username
    # else:
    Mqttpassworrd = broker["password"]
    Mqttuser = broker["user"]    
    client = paho.Client(paho.CallbackAPIVersion.VERSION2)
    client.tls_set(ca_certs=None, certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS, ciphers=None)
    client.tls_insecure_set(True)
    client.username_pw_set(Mqttuser, Mqttpassworrd)
    client.user_data_set(broker)  # Pass the broker data to use in callbacks
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_publish = on_publish
    client.on_disconnect = on_disconnect
    client.connect(broker["host"], broker["port"], 60)
    client.loop_start()  # Use loop_start() to start the client loop asynchronously
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
    local_ip = socket.gethostbyname(socket.gethostname())
    port = 5000  # Flask default port
    print(f'Web interface is available at http://{local_ip}:{port}')

if __name__ == "__main__":
    main(sys.argv[1:])     