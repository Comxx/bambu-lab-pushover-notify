import logging
import paho.mqtt.client as paho
import ssl
import sys
from vardata import *
import tzlocal
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
import json

DASH = '\n-------------------------------------------\n'

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
    msgData = msg.payload.decode('utf-8')
    dataDict = json.loads(msgData)
    json_formatted_str = json.dumps(dataDict, indent=2)
    logging.info(DASH + json_formatted_str + DASH)
    logging.info(f"Message received from {userdata['Printer_Title']}")
    logging.info("Message received from Printer: "+userdata["device_id"])
    
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
        
        # Keep the main thread alive
        while True:
            pass
        
    except Exception as e:
        logging.error(f"Fatal error in main: {e}")
        print("Fatal error Please read Logs")


if __name__ == "__main__":
    main(sys.argv[1:])    