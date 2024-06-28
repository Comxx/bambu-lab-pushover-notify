#!/usr/bin/python
import threading
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
import signal
class PrinterManager:
    
    def __init__(self):
        self.DASH = '\n-------------------------------------------\n'
        self.doorlight = False
        self.doorOpen = ""
        self.first_run = False
        self.percent_notify = False
        self.message_sent = False
        self.last_fetch_time = None
        self.cached_data = None
        self.last_fetch_error_time = None
        self.cached_device_error_data = None
        self.gcode_state_prev = ''
        self.previous_print_error = 0
        self.my_finish_datetime = None
        self.previous_gcode_states = {}
        self.printer_states = {}
        self.errorstate = ''
        self.current_stage = 'unknown'
        self.auth_details = {}
        self.socket_connections = {}
        self.stg_cur:int = None
        self.gcode_state:str = None
        self.layer_num:int = None
        self.total_layer_num:int = None
        self.subtask_name:str = None
        self.mc_percent:int = None
        self.mc_remaining_time:int = None
        self.project_id:str = None
        self.print_error:int = None
        self.printer_status = {}
        self.brokers = self.load_initial_settings()
        self.setup_logging()

        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app)

        self.setup_routes()
        signal.signal(signal.SIGINT, self.signal_handler)
        
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

    def get_current_stage_name(self, stage_id):
        if stage_id is None:
            return "unknown"
        return self.CURRENT_STAGE_IDS.get(int(stage_id), "unknown")

    # Load initial printer settings from a file
    def load_initial_settings(self):
        try:
            with open('settings.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def setup_routes(self):
        @self.app.route('/')
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
                for broker in self.brokers
            ]
            return render_template('index.html', printers=printers)

        @self.app.route('/delete_printer', methods=['POST'])
        def delete_printer():
            try:
                printer_id = request.json.get('printer_id')
                if not printer_id:
                    return jsonify({'status': 'error', 'message': 'Printer ID not provided'})

                with open('settings.json', 'r') as file:
                    settings = json.load(file)

                settings = [printer for printer in settings if printer['device_id'] != printer_id]

                with open('settings.json', 'w') as file:
                    json.dump(settings, file, indent=4)

                return jsonify({'status': 'success'})
            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)})

        @self.app.route('/save_printer_settings', methods=['POST'])
        def save_printer_settings():
            self.brokers = request.json
            with open('settings.json', 'w') as f:
                f.write(json.dumps(self.brokers, indent=4))
            return jsonify({"status": "success"})

    def setup_logging(self):
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
    def on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe("device/" + userdata["device_id"] + "/report", 0)
        if userdata ['printer_type'] == "A1":
            getInfo = {"info": {"sequence_id": "0", "command": "get_version"}}
            payloadvesion = json.dumps(getInfo)
            if not client.publish("device/" + userdata["device_id"] + "/request", payloadvesion):
                raise Exception("Failed to publish get_version")
            pushAll = { "pushing": { "sequence_id": "1", "command": "pushall" }, "user_id": "1234567890"}
            payloadpushall = json.dumps(pushAll)
            if not client.publish("device/" + userdata["device_id"] + "/request", payloadpushall):
                raise Exception("Failed to publish full sync")

    def on_publish(self, client, userdata, mid, reason_codes, properties):
        logging.info(f"Message published successfully to {userdata['Printer_Title']}")

    def on_message(self, client, userdata, msg):
        try:   
                po_app = Application(userdata['my_pushover_app'])
                po_user = po_app.get_user(userdata['my_pushover_user'])
                server_identifier = (userdata['password'], userdata['device_id'])
                prev_state = self.previous_gcode_states.get(server_identifier, {'state': None})
                if msg.payload is None:
                    logging.info("No message received from Printer")
                    return
                msgData = msg.payload.decode('utf-8')
                dataDict = json.loads(msgData)
                if 'print' in dataDict:
                    device_id = userdata['device_id']
    
                    # Initialize printer state if it doesn't exist
                    if device_id not in self.printer_states:
                        self.printer_states[device_id] = {
                            'stg_cur': self.stg_cur,
                            'gcode_state': self.gcode_state,
                            'layer_num': self.layer_num,
                            'total_layer_num': self.total_layer_num,
                            'subtask_name': self.subtask_name,
                            'project_id': self.project_id,
                            'mc_percent': self.mc_percent,
                            'print_error': self.print_error,
                            'mc_remaining_time': self.mc_remaining_time,
                        }
                    
                    # Update printer state with new data
                    self.stg_cur = dataDict['print'].get("stg_cur", self.printer_states[device_id]['stg_cur'])
                    self.gcode_state = dataDict['print'].get("gcode_state", self.printer_states[device_id]['gcode_state'])
                    self.layer_num = dataDict['print'].get("layer_num", self.printer_states[device_id]['layer_num'])
                    self.total_layer_num = dataDict['print'].get("total_layer_num", self.printer_states[device_id]['total_layer_num'])
                    self.subtask_name = dataDict['print'].get("subtask_name", self.printer_states[device_id]['subtask_name'])
                    self.project_id = dataDict['print'].get("project_id", self.printer_states[device_id]['project_id'])
                    self.mc_percent = dataDict['print'].get("mc_percent", self.printer_states[device_id]['mc_percent'])
                    self.print_error = dataDict['print'].get("print_error", self.printer_states[device_id]['print_error'])
                    self.mc_remaining_time = dataDict['print'].get("mc_remaining_time", self.printer_states[device_id]['mc_remaining_time'])
                    # Update printer state in the dictionary
                    self.printer_states[device_id] = {
                        'stg_cur': self.stg_cur,
                        'gcode_state': self.gcode_state,
                        'layer_num': self.layer_num,
                        'total_layer_num': self.total_layer_num,
                        'subtask_name': self.subtask_name,
                        'project_id': self.project_id,
                        'mc_percent': self.mc_percent,
                        'print_error': self.print_error,
                        'mc_remaining_time': self.mc_remaining_time,
                    }
                    printer_status ={}
                    if device_id not in printer_status:
                        printer_status[device_id] = {
                        'previous_print_error': 0,
                        'doorlight': False,
                        'doorOpen': False,
                        'gcode_state_prev': None,
                        'errorstate': None
                    }
                    printer_state = printer_status[device_id]    
                    hms_data = dataDict['print'].get('hms', [{'attr': 0, 'code': 0}])

                    if hms_data:
                        hms_data = hms_data[0]
                    else:
                        hms_data = {'attr': 0, 'code': 0}

                    attr = hms_data.get('attr', 0)
                    code = hms_data.get('code', 0)

                    device__HMS_error_code = self.hms_code(attr, code)

                    english_errors = self.fetch_english_errors() or []

                    error_code_to_hms_cleaned = str(device__HMS_error_code).replace('_', '')
                    found_hms_error = self.search_error(error_code_to_hms_cleaned, english_errors)
                    hex_error_code = self.decimal_to_hex(self.print_error)
                    device_errors = self.fetch_device_errors() or []
                    found_device_error = self.search_error(hex_error_code, device_errors)
                    if found_hms_error is None:
                        found_hms_error = {'intro': 'Unknown error'}
                    if found_device_error is None:
                        found_device_error = {'intro': 'Unknown error'}    
                    self.current_stage = self.get_current_stage_name(dataDict['print'].get('mc_print_stage'))
                    
                    if "print" in dataDict and "home_flag" in dataDict["print"]:
                        home_flag = dataDict["print"]["home_flag"]
                        door_state = bool((home_flag >> 23) & 1)
                        # Check if the door state has changed
                        if printer_state['doorOpen'] != door_state:
                            printer_state['doorOpen'] = door_state

                            if self.gcode_state == "FINISH" or self.gcode_state == "IDLE" or self.gcode_state == "FAILED": 
                                if printer_state['doorOpen']:
                                    if printer_state['doorlight']:
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
                                            
                    if printer_state['previous_print_error'] == 50348044 and self.print_error == 0:
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
                            printer_state['previous_print_error'] = self.print_error
                            return
                    else:
                        printer_state['previous_print_error'] = self.print_error
                        remaining_time = ""
                    
                    time_left_seconds = int(self.mc_remaining_time) * 60
                    if time_left_seconds != 0:
                        aprox_finish_time = time.time() + time_left_seconds
                        unix_timestamp = float(aprox_finish_time)
                        local_timezone = tzlocal.get_localzone()
                        local_time = datetime.fromtimestamp(unix_timestamp, local_timezone)
                        self.my_finish_datetime = local_time.strftime("%m-%d-%Y %I:%M %p (%Z)")
                        remaining_time = str(timedelta(minutes=self.mc_remaining_time))
                    else:
                        if self.gcode_state == "FINISH" and time_left_seconds == 0:
                            self.my_finish_datetime = "Done!"
                    if self.gcode_state and (self.gcode_state != prev_state['state'] or prev_state['state'] is None):
                        priority = 0
                        printer_state['errorstate'] = ''
                        logging.info(self.DASH)
                        logging.info(userdata["Printer_Title"] + " gcode_state has changed to " + self.gcode_state)
                        json_formatted_str = json.dumps(dataDict, indent=2)
                        logging.info(self.DASH + json_formatted_str + self.DASH)
                        self.previous_gcode_states[server_identifier] = {'state': self.gcode_state}

                        msg_text = "<ul>"
                        msg_text += "<li>State: " + self.gcode_state + " </li>"
                        msg_text += f"<li>Percent: {self.mc_percent}% </li>"
                        msg_text += f"<li>Lines: {self.layer_num}/{self.total_layer_num} </li>"
                        if 'subtask_name' in dataDict['print']:
                            msg_text += "<li>Name: " + self.subtask_name + " </li>"
                        msg_text += f"<li>Remaining time: {remaining_time} </li>"
                        msg_text += "<li>Aprox End: " + self.my_finish_datetime + "</li>"
                        fail_reason = ""
                        if( ( 'print_error' in dataDict['print'] and dataDict['print']['print_error'] != 0 ) or self.gcode_state == "FAILED" ):
                            printer_state['errorstate'] = "ERROR"
                            msg_text += f"<li>print_error: {self.print_error}</li>"
                            msg_text += f"<li>Description: {found_device_error['intro']}</li>"  
                            if device__HMS_error_code is not None:
                                msg_text += f"<li>HMS code: {device__HMS_error_code}</li>"
                                msg_text += f"<li>Description: {found_hms_error['intro']}</li>"
                            priority = 1
                            msg_text += "</ul>"
                        if not self.first_run:
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

                    if self.print_error is not None:
                        error_messages.append(f"print_error: {self.print_error}")
                    if device__HMS_error_code is not None:
                        error_messages.append(f"HMS code: {device__HMS_error_code}")
                        error_messages.append(f"Description: {found_hms_error['intro']}") 
                    self.socketio.emit('printer_update', {
                        'printer_id': userdata["device_id"],
                        'printer': userdata['Printer_Title'],
                        'percent': self.mc_percent,
                        'remaining_time': remaining_time,
                        'approx_end': self.my_finish_datetime,
                        'state': self.gcode_state,
                        'project_name': self.subtask_name,
                        'current_stage': self.current_stage,  
                        'error': printer_state['errorstate'],
                        'error_messages': error_messages if printer_state['errorstate'] == "ERROR" else []
                    })
                    
                else:
                    self.first_run = False
        except KeyError as e:
                logging.error(f"KeyError accessing 'gcode_state': {e}")
        except json.JSONDecodeError as e:
                logging.error("Failed to decode JSON from MQTT message: {e}")
        except Exception as e:
                logging.error(f"Unexpected error in on_message: {e}")
                logging.error(traceback.format_exc())
                
    def hms_code(self,attr, code):
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
    def decimal_to_hex(self, decimal_error_code):
        hex_error_code = hex(decimal_error_code)[2:]
        
        hex_error_code = hex_error_code.zfill(8)
        return hex_error_code
    def search_error(self, error_code, english_errors):
        try:
            for error in english_errors:
                if error["ecode"] == error_code:
                    return error
            return None
        except Exception as e:
            logging.error(f"Unexpected error in earch_error: {e}")  

    def fetch_english_errors(self):
        if self.last_fetch_time is None or (datetime.now() - self.last_fetch_time).days >= 1:
            url = "https://e.bambulab.com/query.php?lang=en"
            try:
                response = requests.get(url, timeout=60)  
                response.raise_for_status()  
                data = response.json()
                self.last_fetch_time = datetime.now()  
                self.cached_data = data["data"]["device_hms"]["en"]
                return self.cached_data
            except requests.exceptions.RequestException as e:
                logging.error(f"Failed to fetch data: {e}")
                return None
            except json.JSONDecodeError:
                logging.error("Failed to decode JSON from response")
                return None
            except Exception as e:
                logging.error(f"Unexpected error in fetch_english_errors: {e}")
        else:
            return self.cached_data  

    def fetch_device_errors(self):
            if self.last_fetch_error_time is None or (datetime.now() - self.last_fetch_error_time).days >= 1:
                url = "https://e.bambulab.com/query.php?lang=en"
                try:
                    response = requests.get(url, timeout=60)
                    response.raise_for_status()  # Raise an exception for bad status codes
                    data = response.json()
                    self.last_fetch_error_time = datetime.now()
                    self.cached_device_error_data = data.get("data", {}).get("device_error", {}).get("en", [])
                    return self.cached_device_error_data
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
                return self.cached_device_error_data
    def mqtt_client_thread(self, broker):
        global auth_details
        logging.debug(f" printer info device_id{broker['device_id']} Printer type {broker['printer_type']}")
        # For A1 printers, handle BambuCloud authentication and update MQTT credentials
        # if broker["printer_type"] == "A1":
        #     logging.debug("Connecting to A1 printer using BambuCloud")
        #     device_id = broker["device_id"]
            
            # Check if authentication details are already available
        #     if device_id in auth_details:
        #         logging.debug("Authentication details found for A1 printer")
        #         Mqttpassword = auth_details[device_id]['auth_token']
        #         Mqttuser = auth_details[device_id]['username']
        #     else:
        #         logging.debug("Authentication details not found for A1 printer sdding it.")
        #         bambu_cloud = BambuCloud(region="US", email=broker["user"], username='', auth_token='')
        #         logging.debug("Connecting to BambuCloud")
        #         bambu_cloud.login(region="US", email=broker["user"], password=broker["password"])
        #         logging.debug(bambu_cloud.auth_token)
                
        #         Store the authentication details
        #         auth_details[device_id] = {
        #             'auth_token': bambu_cloud.auth_token,
        #             'username': bambu_cloud.username
        #         }
                
        #         Mqttpassword = bambu_cloud.auth_token
        #         Mqttuser = bambu_cloud.username
        # else:
        Mqttpassword = broker["password"]
        Mqttuser = broker["user"] 
        client = paho.Client(paho.CallbackAPIVersion.VERSION2)
        client.tls_set(ca_certs=None, certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS, ciphers=None)
        client.tls_insecure_set(True)
        client.username_pw_set(Mqttuser, Mqttpassword)
        client.reconnect_delay_set(min_delay=1, max_delay=5)
        client.user_data_set(broker)  # Pass the broker data to use in callbacks
        client.on_connect = self.on_connect
        client.on_message = self.on_message
        client.on_publish = self.on_publish
        client.connect(broker["host"], broker["port"], 60)
        client.loop_start()  # Use loop_start() to start the client loop asynchronously
        return client   

    def start(self):
        threads = []
        for broker in self.brokers:
            thread = threading.Thread(target=self.mqtt_client_thread, args=(broker,))
            thread.start()
            threads.append(thread)

        flask_thread = threading.Thread(target=lambda: self.socketio.run(self.app, host='0.0.0.0', port=5000))
        flask_thread.start()
        threads.append(flask_thread)

        for thread in threads:
            thread.join()    
    def signal_handler(self, sig, frame):
        logging.info("SIGINT received. Cleaning up...")
        self.cleanup()
        sys.exit(0)

    def cleanup(self):
        # Perform cleanup tasks here
        logging.info("Performing cleanup...")
        for device_id, client in self.mqtt_clients.items():
            client.loop_stop()
            client.disconnect()
            logging.info(f"Disconnected MQTT client for device ID: {device_id}")
        for socket_conn in self.socket_connections.values():
            socket_conn.disconnect()    

        self.socketio.stop()            
if __name__ == "__main__":
    try:
        manager = PrinterManager()
        manager.start()
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(1)

