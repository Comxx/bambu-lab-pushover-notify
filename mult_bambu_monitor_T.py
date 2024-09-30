#!/usr/bin/python
import asyncio
import logging
import ssl
import tzlocal
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from chump import Application
import json
import aiohttp
import time
import wled_t
from quart import Quart, request, render_template, jsonify
import socketio
from bambu_cloud_t import BambuCloud
import traceback
from constants import CURRENT_STAGE_IDS
from aiomqtt import Client as MQTTClient, TLSParameters, MqttError
from hypercorn.asyncio import serve
from hypercorn.config import Config
import signal
from collections import defaultdict

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
    return await render_template('index.html', printers=printers)

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
                async with session.get(url, timeout=60) as response:
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
                async with session.get(url, timeout=60) as response:
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
    try:
        Mqttpassword = ''
        Mqttuser = ''
        bambu_cloud = BambuCloud(region="US", email=broker["user"], username='', auth_token='')
        if broker["printer_type"] in ["A1", "P1S"]:
            if not bambu_cloud.auth_token or not bambu_cloud.username:
                logging.info(f"Logging in to Bambu Cloud for {broker['Printer_Title']}...")
                await bambu_cloud.login(region="US", email=broker["user"], password=broker["password"])
            Mqttpassword = bambu_cloud.auth_token
            Mqttuser = bambu_cloud.username
        else:
            Mqttpassword = broker["password"]
            Mqttuser = broker["user"]

        logging.info(f"Connecting to MQTT broker for {broker['Printer_Title']}...")
        client = MQTTClient(
            hostname=broker["host"],
            port=broker["port"],
            username=Mqttuser,
            password=Mqttpassword,
            keepalive=90,  # Adjust as needed
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
        return None

async def start_server():
    config = Config()
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

async def start_or_restart_printer(broker_config):
    device_id = broker_config['device_id']
    
    # Cancel existing task if it exists
    if device_id in printer_tasks:
        printer_tasks[device_id].cancel()
        try:
            await printer_tasks[device_id]
        except asyncio.CancelledError:
            pass
    
    # Create new client and task
    try:
        client = await connect_to_broker(broker_config)
        if client:
            task = asyncio.create_task(printer_loop(client))
            printer_tasks[device_id] = task
            logging.info(f"Started task for printer {device_id}")
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
    
    await asyncio.gather(*printer_tasks.values(), return_exceptions=True)
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    
    logging.info(f"Cancelling {len(tasks)} outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    
    logging.info("Shutdown complete")

async def main():
    try:
        setup_logging()
        logging.info("Starting")
        
        # Log the initial state of the cached data
        log_cached_data()

        loop = asyncio.get_running_loop()

        # Start a task for each printer
        for broker_config in brokers:
            await start_or_restart_printer(broker_config)

        # Start the Quart app with SocketIO
        logging.info("Quart server with SocketIO starting...")
        web_task = asyncio.create_task(start_server())

        # Setup signal handlers
        signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
        for s in signals:
            loop.add_signal_handler(
                s, lambda s=s: asyncio.create_task(shutdown(s, loop))
            )

        try:
            # Wait for the web task to complete (which it never should)
            await web_task
        except asyncio.CancelledError:
            logging.info("Web task has been cancelled")

    except Exception as e:
        logging.error(f"Fatal error in main: {e}")
        print("Fatal error. Please read Logs")
    finally:
        # Ensure all tasks are cancelled
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        
        # Wait for all tasks to complete with a timeout
        await asyncio.wait(tasks, timeout=10)
        
        # Close the event loop
        loop = asyncio.get_event_loop()
        loop.stop()
        loop.close()
        logging.info("Successfully shutdown the application.")

if __name__ == "__main__":
    asyncio.run(main())