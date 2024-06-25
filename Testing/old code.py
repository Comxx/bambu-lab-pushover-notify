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

class PrinterManager:
    CURRENT_STAGE_IDS = {
        "default": "unknown",
        0: "printing",
        # Add remaining stages...
        -1: "idle",
        255: "idle",
    }

    def __init__(self):
        self.doorlight = False
        self.doorOpen = ""
        self.first_run = False
        self.percent_notify = False
        self.percent_done = 0
        self.message_sent = False
        self.last_fetch_time = None
        self.cached_data = None
        self.gcode_state_prev = ''
        self.previous_print_error = 0
        self.my_finish_datetime = ""
        self.previous_gcode_states = {}
        self.printer_states = {}
        self.errorstate = ''
        self.current_stage = 'unknown'
        self.auth_details = {}

        self.brokers = self.load_initial_settings()
        self.setup_logging()

        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app)

        self.setup_routes()

    def load_initial_settings(self):
        try:
            with open('settings.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return []

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

    def get_current_stage_name(self, stage_id):
        if stage_id is None:
            return "unknown"
        return self.CURRENT_STAGE_IDS.get(int(stage_id), "unknown")

    def on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe("device/" + userdata["device_id"] + "/report", 0)
        getInfo = {"info": {"sequence_id": "0", "command": "get_version"}}
        if not client.publish(getInfo):
            raise Exception("Failed to publish get_version")
        pushAll = {"pushing": {"sequence_id": "1", "command": "pushall"}, "user_id": "1234567890"}
        if not client.publish(pushAll):
            raise Exception("Failed to publish full sync")

    def on_publish(self, client, userdata, mid, reason_codes, properties):
        logging.info(f"Message published successfully to {userdata['Printer_Title']}")

    def on_message(self, client, userdata, msg):
        # Implementation of on_message callback
        pass

    def mqtt_client_thread(self, broker):
        Mqttpassword = broker["password"]
        Mqttuser = broker["user"]
        client = paho.Client(paho.CallbackAPIVersion.VERSION2)
        client.tls_set(ca_certs=None, certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS, ciphers=None)
        client.tls_insecure_set(True)
        client.username_pw_set(Mqttuser, Mqttpassword)
        client.reconnect_delay_set(min_delay=1, max_delay=5)
        client.user_data_set(broker)
        client.on_connect = self.on_connect
        client.on_message = self.on_message
        client.on_publish = self.on_publish
        client.connect(broker["host"], broker["port"], 60)
        client.loop_start()
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

if __name__ == "__main__":
    manager = PrinterManager()
    manager.start()
