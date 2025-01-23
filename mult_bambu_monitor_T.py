#!/usr/bin/python
import asyncio
import logging
from math import e
import ssl
import tzlocal
import signal
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from chump import Application
import json
import aiohttp
import time
import wled_t
from quart import Quart, request, render_template, jsonify, send_file, send_from_directory
import socketio
from bambu_cloud_t import BambuCloud, CloudflareError, CodeRequiredError, TfaCodeRequiredError, CodeExpiredError, CodeIncorrectError
import traceback
from constants import CURRENT_STAGE_IDS
from aiomqtt import Client as MQTTClient, TLSParameters, MqttError
from hypercorn.asyncio import serve
from hypercorn.config import Config as HyperConfig
from collections import defaultdict
from quart_cors import cors
from typing import Dict, Any, Optional

DASH = '\n-------------------------------------------\n'

# Global state
first_run = False
percent_notify = False
message_sent = False
last_fetch_time = None
cached_data = None
my_finish_datetime = ""
previous_gcode_states = {}
printer_states = {}
current_stage = 'unknown'
printer_status = {}
cached_device_error_data = None
printer_tasks = {}
auth_states = {}  # Track authentication states for printers
token_refresh_tasks = {}  # Track token refresh tasks per printer
settings_file = 'settings.json'
Mqttpassword = ''
Mqttuser = ''
class TokenManager:
    def __init__(self, device_id: str, broker_config: dict):
        self.device_id = device_id
        self.broker_config = broker_config
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
        self.refresh_expires_at = None

    async def initialize_tokens(self, bambu_cloud: BambuCloud):
        """Initialize tokens from successful login"""
        self.access_token = bambu_cloud.auth_token
        self.refresh_token = bambu_cloud.refresh_token  # You'll need to add this property to BambuCloud
        self.expires_at = datetime.now() + timedelta(seconds=7776000)  # Default 90 days
        self.refresh_expires_at = self.expires_at

    async def refresh_tokens(self):
        """Refresh tokens before they expire"""
        if not self.refresh_token:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.bambulab.com/v1/user-service/user/refreshtoken"
                data = {"refreshToken": self.refresh_token}
                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.access_token = result["accessToken"]
                        self.refresh_token = result["refreshToken"]
                        self.expires_at = datetime.now() + timedelta(seconds=result["expiresIn"])
                        self.refresh_expires_at = datetime.now() + timedelta(seconds=result["refreshExpiresIn"])
                        return True
                    else:
                        logging.error(f"Token refresh failed for {self.device_id}: {await response.text()}")
                        return False
        except Exception as e:
            logging.error(f"Error refreshing tokens for {self.device_id}: {e}")
            return False

async def token_refresh_loop(token_manager: TokenManager):
    """Background task to refresh tokens before expiration"""
    while True:
        try:
            # Refresh when less than 1 day remaining
            if token_manager.expires_at:
                time_until_expiry = token_manager.expires_at - datetime.now()
                if time_until_expiry < timedelta(days=1):
                    if await token_manager.refresh_tokens():
                        logging.info(f"Successfully refreshed tokens for {token_manager.device_id}")
                    else:
                        logging.error(f"Failed to refresh tokens for {token_manager.device_id}")
            
            # Sleep for 6 hours before checking again
            await asyncio.sleep(21600)
        except Exception as e:
            logging.error(f"Error in token refresh loop for {token_manager.device_id}: {e}")
            await asyncio.sleep(300)  # Sleep for 5 minutes on error

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
    
# Initialize Quart app and SocketIO
app = Quart(__name__)
sio = socketio.AsyncServer(async_mode='asgi')
asgi_app = socketio.ASGIApp(sio, app)

def get_current_stage_name(stage_id):
    if stage_id is None:
        return CURRENT_STAGE_IDS.get(int(stage_id), "unknown")
    return "unknown"
# Load initial printer settings from a file
try:
    with open('settings.json', 'r') as f:
        brokers = json.load(f)
except FileNotFoundError:
    brokers = []

@app.route('/')
async def home():
    """Serve the main HTML page"""
    return await render_template('index.html')

# Route for static files
@app.route('/static/<path:filename>')
async def static_files(filename):
    return await send_from_directory('static', filename)

@app.route('/api/printers')
async def get_printers():
    """API endpoint for getting printer data"""
    try:
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
                "printer_color": broker["color"],
                "printer_type": broker.get("printer_type", "unknown"),
                "status": printer_status.get(broker["device_id"], {})
            } 
            for broker in brokers
        ]
        return jsonify({"printers": printers})
    except Exception as e:
        logging.error(f"Error getting printers: {e}")
        return jsonify({"error": "Failed to get printers"}), 500

@app.errorhandler(404)
async def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
async def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

@app.route('/delete_printer', methods=['POST'])
async def delete_printer():
    try:
        data = await request.get_json()
        printer_id = data.get('printer_id')
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
async def save_printer_settings():
    global brokers
    brokers = await request.get_json()
    with open('settings.json', 'w') as f:
        f.write(json.dumps(brokers, indent=4))
    return jsonify({"status": "success"})

@app.route('/reconnect_printer', methods=['POST'])
async def reconnect_printer():
    try:
        data = await request.get_json()
        printer_id = data.get('printer_id')
        if not printer_id:
            return jsonify({'status': 'error', 'message': 'Printer ID not provided'})

        # Find the broker configuration for the given printer_id
        broker_config = next((broker for broker in brokers if broker['device_id'] == printer_id), None)
        if not broker_config:
            return jsonify({'status': 'error', 'message': 'Printer configuration not found'})

        # Initiate reconnection
        await start_or_restart_printer(broker_config)

        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})
# Add new routes for authentication handling
@app.route('/verify_email', methods=['POST'])
async def verify_email():
    try:
        data = await request.get_json()
        printer_id = data.get('printer_id')
        code = data.get('code')
        
        if not printer_id or not code:
            return jsonify({'status': 'error', 'message': 'Missing printer_id or code'})
        
        auth_state = auth_states.get(printer_id)
        if not auth_state:
            return jsonify({'status': 'error', 'message': 'No pending authentication for this printer'})
            
        bambu_cloud = auth_state.get('bambu_cloud')
        if not bambu_cloud:
            return jsonify({'status': 'error', 'message': 'Invalid authentication state'})
        
        try:
            await bambu_cloud.login_with_verification_code(code)
            auth_states[printer_id] = {"status": "connected"}
            
            # Get the broker configuration for this printer
            broker = next((b for b in brokers if b["device_id"] == printer_id), None)
            if not broker:
                return jsonify({'status': 'error', 'message': 'Printer configuration not found'})
                
            # Attempt to reconnect the printer
            await start_or_restart_printer(broker)
            
            return jsonify({'status': 'success', 'message': 'Email verification successful'})
            
        except CodeExpiredError:
            # Request a new code automatically
            await bambu_cloud._get_email_verification_code()
            return jsonify({
                'status': 'error', 
                'message': 'Verification code expired. A new code has been sent to your email.'
            })
        except CodeIncorrectError:
            return jsonify({
                'status': 'error', 
                'message': 'Incorrect verification code. Please try again.'
            })
        except Exception as e:
            logging.error(f"Email verification failed: {str(e)}")
            return jsonify({
                'status': 'error', 
                'message': f'Verification failed: {str(e)}'
            })
            
    except Exception as e:
        logging.error(f"Error in verify_email: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/verify_2fa', methods=['POST'])
async def verify_2fa():
    try:
        data = await request.get_json()
        printer_id = data.get('printer_id')
        code = data.get('code')
        
        broker = next((b for b in brokers if b["device_id"] == printer_id), None)
        if not broker:
            return jsonify({'status': 'error', 'message': 'Printer not found'})
        
        bambu_cloud = BambuCloud(region="US", email=broker["user"], username='', auth_token='')
        
        try:
            await bambu_cloud.login_with_2fa_code(code)
            auth_states[printer_id] = {"status": "connected"}
            
            # Attempt to reconnect the printer
            await start_or_restart_printer(broker)
            
            return jsonify({'status': 'success'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

async def on_connect(client):
    try:
        await client.subscribe(f"device/{client.userdata['device_id']}/report")
        getInfo = {"info": {"sequence_id": "0", "command": "get_version"}}
        payloadvesion = json.dumps(getInfo)
        await client.publish(f"device/{client.userdata['device_id']}/request", payloadvesion)
        pushAll = {"pushing": {"sequence_id": "1", "command": "pushall"}, "user_id": "1234567890"}
        payloadpushall = json.dumps(pushAll)
        await client.publish(f"device/{client.userdata['device_id']}/request", payloadpushall)
    except Exception as e:
        logging.error(f"Error in on_connect: {e}")

async def on_message(client, message):
    global DASH, first_run, percent_notify, my_finish_datetime
    global previous_gcode_states, printer_states
    global current_stage, printer_status
    try:    
        userdata = client.userdata
        po_app = Application(userdata['my_pushover_app'])
        po_user = po_app.get_user(userdata['my_pushover_user'])
        server_identifier = (userdata['password'], userdata['device_id'])
        prev_state = previous_gcode_states.get(server_identifier, {'state': None})
        
        if message.payload is None:
            logging.error("No message received from Printer")
            return
        msgData = message.payload.decode('utf-8')
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
                    'subtask_name': 'Unknown',
                    'project_id': 'Unknown',
                    'print_error': 0,
                    'mc_remaining_time': 0,
                    'percent_done': 0,
                    'mc_print_stage': 'unknown'
                }
            
            # Extract data from dataDict
            print_data = dataDict['print']
            printer_status[device_id].update({
                'stg_cur': print_data.get("stg_cur", printer_status[device_id]['stg_cur']),
                'gcode_state': print_data.get("gcode_state", printer_status[device_id]['gcode_state']),
                'layer_num': print_data.get("layer_num", printer_status[device_id]['layer_num']),
                'total_layer_num': print_data.get("total_layer_num", printer_status[device_id]['total_layer_num']),
                'subtask_name': print_data.get("subtask_name", printer_status[device_id]['subtask_name']),
                'project_id': print_data.get("project_id", printer_status[device_id]['project_id']),
                'percent_done': print_data.get("mc_percent", printer_status[device_id]['percent_done']),
                'print_error': print_data.get("print_error", printer_status[device_id]['print_error']),
                'mc_remaining_time': print_data.get("mc_remaining_time", printer_status[device_id]['mc_remaining_time']),
                'mc_print_stage': print_data.get("mc_print_stage", printer_status[device_id]['mc_print_stage'])
            })
            print_data = dataDict['print']
            current_stage = get_current_stage_name(printer_status[device_id]['mc_print_stage'])
            
            # Initialize state for new printer
            if device_id not in printer_states:
                printer_states[device_id] = {
                    'previous_print_error': 0,
                    'doorlight': False,
                    'doorOpen': False,
                    'errorstate': 'None'
                }
            logging.debug(f"Existing printer_states keys: {printer_states.keys()}")
            printer_state = printer_states[device_id]
            logging.debug(f"Existing printer_states: {printer_state}")
            
            # Process HMS data
            hms_data = print_data.get('hms', [{'attr': 0, 'code': 0}])
            hms_data = hms_data[0] if hms_data else {'attr': 0, 'code': 0}
            attr, code = hms_data.get('attr', 0), hms_data.get('code', 0)
            device__HMS_error_code = hms_code(attr, code)

            # Fetch error information
            english_errors = await fetch_english_errors() or []
            error_code_to_hms_cleaned = str(device__HMS_error_code).replace('_', '')
            found_hms_error = await search_error(error_code_to_hms_cleaned, english_errors)
            hex_error_code = decimal_to_hex(printer_status[device_id]['print_error'])
            device_errors = await fetch_device_errors() or []
            log_cached_data()
            found_device_error = await search_error(hex_error_code, device_errors)
            found_hms_error = found_hms_error or {'intro': 'Unknown error'}
            found_device_error = found_device_error or {'intro': 'Unknown error'}

            # Process door state
            if "home_flag" in print_data:
                home_flag = print_data["home_flag"]
                door_state = bool((home_flag >> 23) & 1)
                if printer_state['doorOpen'] != door_state:
                    printer_state['doorOpen'] = door_state
                    gcode_state = printer_status[device_id]['gcode_state']
                    if gcode_state in ["FINISH", "IDLE", "FAILED"]:
                        if door_state and not printer_state['doorlight'] and userdata['ledlight']:
                            await wled_t.set_power(userdata['wled_ip'], True)
                            await wled_t.set_brightness(userdata['wled_ip'], 255)
                            await wled_t.set_color(userdata['wled_ip'], (255, 255, 255))
                            logging.debug("Opened")
                            printer_state['doorlight'] = True
                        elif not door_state and printer_state['doorlight'] and userdata['ledlight']:
                            await wled_t.set_power(userdata['wled_ip'], False)
                            logging.debug("Closed")
                            printer_state['doorlight'] = False

            # Handle print cancellation
            if printer_state['previous_print_error'] == 50348044 and printer_status[device_id]['print_error'] == 0:
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
                await client.publish(f"device/{userdata['device_id']}/request", payload)
                await client.publish(f"device/{userdata['device_id']}/request", payloadlogo)
                message = po_user.create_message(
                    title=f"{userdata['Printer_Title']} Cancelled",
                    message="Print Cancelled",
                    sound=userdata['PO_SOUND'],
                    priority=1
                )
                asyncio.create_task(asyncio.to_thread(message.send))
                logging.debug(f"Print cancelled on {userdata['Printer_Title']}")
                printer_state['previous_print_error'] = printer_status[device_id]['print_error']
                return
            
            printer_state['previous_print_error'] = printer_status[device_id]['print_error']
            
            # Calculate remaining time and finish datetime
            time_left_seconds = int(printer_status[device_id]['mc_remaining_time']) * 60
            if time_left_seconds != 0:
                aprox_finish_time = time.time() + time_left_seconds
                local_timezone = tzlocal.get_localzone()
                local_time = datetime.fromtimestamp(aprox_finish_time, local_timezone)
                my_finish_datetime = local_time.strftime("%m-%d-%Y %I:%M %p (%Z)")
                remaining_time = str(timedelta(minutes=printer_status[device_id]['mc_remaining_time']))
            else:
                if printer_status[device_id]['gcode_state'] == "FINISH" and time_left_seconds == 0:
                    my_finish_datetime = "Done!"
                remaining_time = ""

            # Handle gcode state changes
            if (printer_status[device_id]['gcode_state'] != prev_state['state'] or prev_state['state'] is None):
                priority = 0
                logging.info(DASH)
                logging.info(f"{userdata['Printer_Title']} gcode_state has changed to {printer_status[device_id]['gcode_state']}")
                json_formatted_str = json.dumps(dataDict, indent=2)
                logging.debug(DASH + json_formatted_str + DASH)
                previous_gcode_states[server_identifier] = {'state': printer_status[device_id]['gcode_state']}

                msg_text = "<ul>"
                msg_text += f"<li>State: {printer_status[device_id]['gcode_state']} </li>"
                msg_text += f"<li>Percent: {printer_status[device_id]['percent_done']}% </li>"
                msg_text += f"<li>Lines: {printer_status[device_id]['layer_num']}/{printer_status[device_id]['total_layer_num']} </li>"
                if 'subtask_name' in print_data:
                    msg_text += f"<li>Name: {printer_status[device_id]['subtask_name']} </li>"
                msg_text += f"<li>Remaining time: {remaining_time} </li>"
                msg_text += f"<li>Aprox End: {my_finish_datetime}</li>"
                if printer_status[device_id]['print_error'] != 0 or printer_status[device_id]['gcode_state'] == "FAILED":
                    if printer_status[device_id]['print_error'] is not None:
                        msg_text += f"<li>print_error: {printer_status[device_id]['print_error']}</li>"
                    if device__HMS_error_code == "":
                        msg_text += f"<li>Description: {found_device_error['intro']}</li>"
                    elif device__HMS_error_code != "":
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
                    asyncio.create_task(asyncio.to_thread(message.send))
                    message.url = ""
                    device__HMS_error_code = ""

            # Prepare error messages
            error_messages = []
            if printer_status[device_id]['print_error'] is not None:
                error_messages.append(f"print_error: {printer_status[device_id]['print_error']}")
            if device__HMS_error_code is not None:
                error_messages.append(f"HMS code: {device__HMS_error_code}")
                error_messages.append(f"Description: {found_hms_error['intro']}")

            # Emit printer update
            await sio.emit('printer_update', {
            'printer_id': userdata["device_id"],
            'printer': userdata['Printer_Title'],
            'percent': printer_status[device_id]['percent_done'],
            'lines': printer_status[device_id]['layer_num'],
            'lines_total': printer_status[device_id]['total_layer_num'],
            'remaining_time': remaining_time,
            'approx_end': my_finish_datetime,
            'state': printer_status[device_id]['gcode_state'],
            'project_name': printer_status[device_id]['subtask_name'],
            'current_stage': current_stage,  
            'error': "",
            'error_messages': error_messages
        })
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
        return ""

async def fetch_english_errors():
    global last_fetch_time, cached_data
    if last_fetch_time is None or (datetime.now() - last_fetch_time).days >= 1:
        url = "https://e.bambulab.com/query.php?lang=en"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=120) as response:
                    if response.status == 200:
                        data = await response.json()
                        last_fetch_time = datetime.now()
                        cached_data = data["data"]["device_hms"]["en"]
                        return cached_data
                    else:
                        logging.error(f"Failed to fetch data, status code: {response.status}")
                        return None
        except aiohttp.ClientError as e:
            logging.error(f"Failed to fetch data: {e}")
            return None
        except aiohttp.ContentTypeError:
            logging.error("Failed to decode JSON from response")
            return None
        except Exception as e:
            logging.error(f"Unexpected error in fetch_english_errors: {e}")
            return None
    else:
        return cached_data

async def fetch_device_errors():
    global last_fetch_time, cached_device_error_data
    if last_fetch_time is None or (datetime.now() - last_fetch_time).days >= 1:
        url = "https://e.bambulab.com/query.php?lang=en"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=120) as response:
                    if response.status == 200:
                        data = await response.json()
                        last_fetch_time = datetime.now()
                        
                        # Log the structure of the received data
                        logging.debug(f"Received data structure: {json.dumps(data, indent=2)}")
                        
                        if "data" not in data:
                            logging.error("No 'data' key in the response")
                            return None
                        
                        if "device_error" not in data["data"]:
                            logging.error("No 'device_error' key in data")
                            return None
                        
                        if "en" not in data["data"]["device_error"]:
                            logging.error("No 'en' key in device_error")
                            return None
                        
                        cached_device_error_data = data["data"]["device_error"]["en"]
                        
                        # Log the cached data
                        logging.debug(f"Cached device error data: {json.dumps(cached_device_error_data, indent=2)}")
                        log_cached_data()
                        return cached_device_error_data
                    else:
                        logging.error(f"Failed to fetch data, status code: {response.status}")
                        return None
        except aiohttp.ClientError as e:
            logging.error(f"Failed to fetch data: {e}")
            return None
        except aiohttp.ContentTypeError:
            logging.error("Failed to decode JSON from response")
            return None
        except json.JSONDecodeError as e:
            logging.error(f"JSON decode error: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error in fetch_device_errors: {e}")
            logging.error(traceback.format_exc())
            return None
    else:
        logging.debug("Using cached device error data")
        log_cached_data()
        return cached_device_error_data

# Add this function to check the cached data
def log_cached_data():
    global cached_device_error_data
    logging.debug(f"Current cached device error data: {json.dumps(cached_device_error_data, indent=2)}")

def decimal_to_hex(decimal_error_code):
    hex_error_code = hex(decimal_error_code)[2:]
    return hex_error_code.zfill(8)

async def search_error(error_code, error_list):
    try:
        for error in error_list:
            if error["ecode"] == error_code:
                return error
        return None
    except Exception as e:
        logging.error(f"Unexpected error in search_error: {e}")
        return None
            
async def connect_to_broker(broker):
    global Mqttpassword, Mqttuser
    try:
        #device_id = broker["device_id"]

        # Initialize BambuCloud instance
       # bambu_cloud = BambuCloud(region="US", email=broker["user"], username='', auth_token='')

        if broker["printer_type"] in ["A1", "P1S"]:
            logging.info(f"Using global credentials to log in cloud for {broker['Printer_Title']}")
            logging.info(f"Using global credentials - User: {Mqttuser}, Password: {Mqttpassword}")
            # try:
            #     # Attempt to login using email and password
            #     await bambu_cloud.login(region="US", email=broker["user"], password=broker["password"])
            # except CodeRequiredError:
            #     logging.info(f"Verification code required for {broker['Printer_Title']}.")

            #     # Check if stored code is available and valid
            #     if not is_code_expired(broker['device_id']):
            #         logging.info(f"Using stored code for {broker['Printer_Title']}.")
            #         with open(settings_file, 'r') as f:
            #             settings = json.load(f)
            #         code_data = next(
            #             (item for item in settings if item['device_id'] == broker['device_id']), {}
            #         ).get('email_code_data', {})
            #         code = code_data.get('code')
            #     else:
            #         code = input(f"Verification code sent to {broker['user']}. Enter the code: ").strip()

            #     try:
            #         # Attempt to login with the verification code
            #         await bambu_cloud.login_with_verification_code(code)
            #         logging.info(f"Verification successful for {broker['Printer_Title']}.")

            #         # Store the email code and set expiration
            #         expires_at = datetime.now() + timedelta(minutes=5)  # Assuming a 5-minute code validity
            #         store_email_code(broker['device_id'], code, expires_at)
            #     except CodeExpiredError:
            #         logging.error(f"Verification code expired for {broker['Printer_Title']}. Requesting a new code...")
            #         await bambu_cloud._get_email_verification_code()
            #         code = input(f"New verification code sent to {broker['user']}. Enter the code: ").strip()

            #         await bambu_cloud.login_with_verification_code(code)
            #         logging.info(f"Verification successful with new code for {broker['Printer_Title']}.")

            #         # Store the updated email code and set expiration
            #         expires_at = datetime.now() + timedelta(minutes=5)
            #         store_email_code(broker['device_id'], code, expires_at)
            #     except Exception as e:
            #         logging.error(f"Failed to verify {broker['Printer_Title']} with the provided code: {e}")
            #         raise e
            # except Exception as e:
            #     logging.error(f"Login failed for {broker['Printer_Title']}: {str(e)}")
            #     auth_states[device_id] = {"status": "error", "message": str(e)}
            #     return None

            # Mqttpassword = bambu_cloud.auth_token
            # Mqttuser = bambu_cloud.username
        else:
            Mqttpassword = broker["password"]
            Mqttuser = broker["user"]

        logging.info(f"Connecting to MQTT broker for {broker['Printer_Title']}...")
        client = MQTTClient(
            hostname=broker["host"],
            port=broker["port"],
            username=Mqttuser,
            password=Mqttpassword,
            keepalive=90,
            tls_params=TLSParameters(
                ca_certs=None,
                certfile=None,
                keyfile=None,
                cert_reqs=ssl.CERT_NONE,
                tls_version=ssl.PROTOCOL_TLS,
                ciphers=None
            )
        )
        client.userdata = broker
        logging.info(f"Successfully created MQTT client for {broker['Printer_Title']}")
        return client
    except Exception as e:
        logging.error(f"Error in connect_to_broker for {broker['Printer_Title']}: {e}")
        logging.error(traceback.format_exc())
        return None


@app.route('/auth_status/<printer_id>', methods=['GET'])
async def get_auth_status(printer_id):
    status = auth_states.get(printer_id, {"status": "unknown"})
    return jsonify(status)
async def start_server():
    config = HyperConfig()
    config.bind = ["0.0.0.0:5000"]
    await serve(asgi_app, config)

async def printer_loop(client):
    while True:
        try:
            async with client:
                await on_connect(client)
                async for message in client.messages:
                    await on_message(client, message)
        except MqttError as error:
            if error.rc == 141:  # Keepalive timeout
                logging.error(f"Keepalive timeout for {client.userdata['Printer_Title']}. aiomqtt will attempt to reconnect.")
            else:
                logging.error(f'MQTT Error for {client.userdata["Printer_Title"]}: {error}')
            logging.info(f'aiomqtt will attempt to reconnect automatically for {client.userdata["Printer_Title"]}')
        except Exception as e:
            logging.error(f"Unexpected error in printer_loop for {client.userdata['Printer_Title']}: {e}")
        
        # Add a small delay before the next iteration
        await asyncio.sleep(5)
    
    # This part will only be reached if the while loop is explicitly broken
    device_id = client.userdata['device_id']
    if device_id in printer_tasks:
        del printer_tasks[device_id]


def is_code_expired(printer_id):
    try:
        with open(settings_file, 'r') as f:
            settings = json.load(f)
        code_data = next((item for item in settings if item['device_id'] == printer_id), {}).get('email_code_data')
        if not code_data:
            return True
        return datetime.now() > datetime.fromisoformat(code_data['expires_at'])
    except Exception as e:
        logging.error(f"Error checking code expiration: {e}")
        return True
    
def store_email_code(printer_id, code, expires_at):
    try:
        with open(settings_file, 'r') as f:
            settings = json.load(f)
        for item in settings:
            if item['device_id'] == printer_id:
                item['email_code_data'] = {
                    'code': code,
                    'expires_at': expires_at.isoformat()
                }
                break
        else:
            settings.append({
                'device_id': printer_id,
                'email_code_data': {
                    'code': code,
                    'expires_at': expires_at.isoformat()
                }
            })
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        logging.error(f"Error storing email code: {e}")


async def authenticate_cloud_printers():
    global Mqttpassword, Mqttuser
    for broker in brokers:
        bambu_cloud = BambuCloud(region="US", email=broker["user"], username='', auth_token='')

        if broker["printer_type"] in ["A1", "P1S"]:
        
            try:
                await bambu_cloud.login(region="US", email=broker["user"], password=broker["password"])
                logging.info(f"Login successful for {broker['Printer_Title']}.")
                
            except CodeRequiredError:
                    logging.info(f"Verification code required for {broker['Printer_Title']}.")
                    await handle_verification_code(bambu_cloud, broker)
            except CodeExpiredError:
                    logging.info(f"Verification code expired for {broker['Printer_Title']}. Requesting a new code...")
                    await bambu_cloud._get_new_code()
            except CodeIncorrectError:
                    logging.info(f"Incorrect verification code for {broker['Printer_Title']}.")
                    await handle_verification_code(bambu_cloud, broker)        
            except Exception as e:
                    logging.error(f"Failed to authenticate {broker['Printer_Title']}: {e}")
                    auth_states[broker['device_id']] = {"status": "error", "message": str(e)}
            
            
            

            # Update global credentials
            Mqttpassword = bambu_cloud.auth_token
            Mqttuser = bambu_cloud.username
            logging.info(f"Global credentials set - User: {Mqttuser}, Password: {Mqttpassword}")
        else:
            logging.info(f"Skipping cloud authentication for {broker['Printer_Title']} (local printer).")


async def handle_verification_code(bambu_cloud, broker):
    """
    Handles the email verification process.
    """
    max_retries = 5
    retry_delay = 10  # Seconds to wait between retries
    retries = 0

    while retries < max_retries:
        try:
            # Prompt user to resend the verification code
            resend_choice = input(f"Do you want to resend the verification code for {broker['Printer_Title']}? (yes/no): ").strip().lower()
            if resend_choice in ["yes", "y"]:
                await bambu_cloud._get_new_code()
                logging.info(f"New verification code sent to {broker['user']}.")

            # Prompt the user for the new code
            code = input(f"Enter the verification code sent to {broker['user']}: ").strip()

            # Try to authenticate with the new code
            await bambu_cloud.login_with_verification_code(code)
            logging.info(f"Verification successful for {broker['Printer_Title']}.")
            return  # Exit on successful authentication

        except CodeExpiredError:
            retries += 1
            logging.warning(f"Verification code expired for {broker['Printer_Title']}. Retrying...")
            await asyncio.sleep(retry_delay)

        except CodeIncorrectError:
            retries += 1
            logging.warning(f"Incorrect verification code for {broker['Printer_Title']}. Please try again.")
            await asyncio.sleep(retry_delay)

        except Exception as e:
            logging.error(f"Unexpected error during verification for {broker['Printer_Title']}: {e}")
            raise e

    # If the maximum retries are reached
    logging.error(f"Max retries reached for {broker['Printer_Title']}. Authentication failed.")

async def start_or_restart_printer(broker_config):
    device_id = broker_config['device_id']
    
    # Cancel existing task if it exists
    if device_id in printer_tasks:
        printer_tasks[device_id].cancel()
        try:
            await printer_tasks[device_id]
        except asyncio.CancelledError:
            pass
    
    # Clear any existing auth state when restarting
    if device_id in auth_states:
        old_auth_state = auth_states[device_id]
        if old_auth_state.get('bambu_cloud'):
            await old_auth_state['bambu_cloud'].close()
    
    # Create new client and task
    try:
        client = await connect_to_broker(broker_config)
        if client:
            task = asyncio.create_task(printer_loop(client))
            printer_tasks[device_id] = task
            logging.info(f"Started/Restarted task for printer {device_id}")
        else:
            logging.error(f"Failed to connect to broker for printer {device_id}")
    except Exception as e:
        logging.error(f"Error connecting to broker for printer {device_id}: {e}")

async def shutdown(signal, loop):
    """Cleanup tasks tied to the service's shutdown."""
    logging.info(f"Received exit signal {signal.name}...")
    
    logging.info("Closing printer tasks...")
    for task in printer_tasks.values():
        task.cancel()
    
    logging.info("Closing token refresh tasks...")
    for task in token_refresh_tasks.values():
        task.cancel()
    
    await asyncio.gather(*printer_tasks.values(), *token_refresh_tasks.values(), return_exceptions=True)
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    
    logging.info(f"Cancelling {len(tasks)} outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    
    logging.info("Shutdown complete")
    loop.stop()

async def main():
    try:
        setup_logging()
        logging.info("Starting Bambu Monitor")

        # Authenticate cloud printers before any connections
        logging.info("Authenticating cloud printers...")
        await authenticate_cloud_printers()

        # Connect to cloud printers first
        logging.info("Connecting cloud printers...")
        for broker in brokers:
            if broker['printer_type'] in ['A1', 'P1S']:
                await start_or_restart_printer(broker)

        # Connect to local printers (X1)
        logging.info("Connecting local printers...")
        for broker in brokers:
            if broker['printer_type'] == 'X1C':
                await start_or_restart_printer(broker)

        # Start the web server
        logging.info("Starting web server...")
        web_task = asyncio.create_task(start_server())

        # Handle shutdown signals
        signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
        for s in signals:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(
                s, lambda s=s: asyncio.create_task(shutdown(s, loop))
            )

        await web_task
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        raise e



if __name__ == "__main__":
    asyncio.run(main())