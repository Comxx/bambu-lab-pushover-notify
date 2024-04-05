#!/usr/bin/python3
from vardata import *
import paho.mqtt.client as paho
import logging
import json
import sys
import ssl
import time
from chump import Application
from dateutil.parser import parse
from datetime import datetime, timedelta
import tzlocal

dash = '\n-------------------------------------------\n'
gcode_state_prev = ''
first_run = False
percent_notify = False
po_app = Application(my_pushover_app)
po_user = po_app.get_user(my_pushover_user)
percent_done = 0


def parse_message(self, message):
	dataDict = json.loads(message)
	return dataDict

def on_connect(client, userdata, flags, reason_code, properties):
	client.subscribe("device/"+device_id+"/report",0)

def on_message(client, userdata, msg):
	global dash, gcode_state_prev, app, user, my_pushover_app, my_pushover_user, first_run, percent_notify, percent_done
	#logging.info("received message with topic"+msg.topic)
	msgData = msg.payload.decode('utf-8')
	dataDict = json.loads(msgData)
	if('print' in dataDict):
		if('gcode_state' in dataDict['print']):
			gcode_state = dataDict['print']['gcode_state']
			if('mc_percent' in dataDict['print']):
				percent_done = dataDict['print']['mc_percent']
			if(gcode_state_prev != gcode_state or (gcode_state_prev != gcode_state and not percent_notify and percent_done >= notify_at_percent)):
				if(notify_at_percent >= percent_done):
					percent_notify = True

				# init
				priority = 0
				logging.info("gcode_state has chnaged to "+gcode_state)
				json_formatted_str = json.dumps(dataDict, indent=2)
				logging.info(dash+json_formatted_str+dash)
				gcode_state_prev = gcode_state

				# Get start time
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
						my_datetime = ""

				# Get finish time (aprox)
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

				# text
				msg_text = "<ul>"
				msg_text = msg_text + "<li>State: "+ gcode_state + " </li>"
				msg_text = msg_text + f"<li>Percent: {percent_done}% </li>"
				if('subtask_name' in dataDict['print']):
					msg_text = msg_text + "<li>Name: "+ dataDict['print']['subtask_name'] + " </li>"
				msg_text = msg_text + f"<li>Remaining time: {remaining_time} Mins </li>"
				msg_text = msg_text + "<li>Started: "+ my_datetime + " </li>"
				msg_text = msg_text + "<li>Aprox End: "+ my_finish_datetime + " </li>"

				# failed
				if( ('fail_reason' in dataDict['print'] and len(dataDict['print']['fail_reason']) > 1) or ( 'print_error' in dataDict['print'] and dataDict['print']['print_error'] != 0 ) or gcode_state == "FAILED" ):
					# Build the error message
					msg_text = msg_text + f"<li>print_error: {dataDict['print']['print_error']}</li>"
					msg_text = msg_text + f"<li>mc_print_error_code: {dataDict['print']['mc_print_error_code']}</li>"
					msg_text = msg_text + f"<li>HMS code: {dataDict['print']['hms']}</li>"

					# Assign fail_reason
					error_code = int(dataDict['print']['mc_print_error_code'])
					fail_reason = "Print Canceled" if ('fail_reason' in dataDict['print'] and len(dataDict['print']['fail_reason']) > 1 and dataDict['print']['fail_reason'] != '50348044') else dataDict['print']['fail_reason']

					# Set priority and potentially customize fail_reason based on error_code (optional)
					priority = 1
					if error_code in (32778, 32771, 32773, 32774, 32769):  # Check for specific error codes (optional)
						fail_reason = {  # Update fail_reason with custom messages (optional)
							32778: "Arrr! Swab the poop deck!",
							32771: "Spaghetti and meatballs!",
							32773: "Didn't pull out!",
							32774: "Build plate mismatch!",
							32769: "Let's take a moment to PAUSE!",
						}.get(error_code, fail_reason)  # Use default if no custom message found

					# Add fail_reason to message
					msg_text = msg_text + f"<li>fail_reason: {fail_reason}</li>"

					# Check if the message indicates a fail reason or print error cancel on the print if so turn off lights
				if ('print_error' in dataDict['print'] and dataDict['print']['print_error'] == '50348044') or ('fail_reason' in dataDict['print'] and dataDict['print']['fail_reason'] == '50348044'):
						# Turn off the lights
								
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
				
				# pushover notify
				if(not first_run):
					msg_text = msg_text + "</ul>"
					message = po_user.create_message(
						title="Panda Printer",
						message=msg_text,
						html=True,
						sound='magic',
						priority=priority
					)
					message.send()
					if(priority == 1):
						for x in range(repeat_errors):
							time.sleep(pause_error_secs)
							message.send()
				else:
					first_run = False

def main(argv):
	global host, port, user, password
	# Logging Set up
	local_timezone = tzlocal.get_localzone()  # Get the local timezone
	current_datetime = datetime.now(local_timezone)  # Get the current datetime in the local timezone
	datetime_str = current_datetime.strftime("%Y-%m-%d_%I-%M-%S%p")  # %I for 12-hour format, %p for AM/PM
	logfile_path = "logs/"
	logfile_name = f"{logfile_path}output_{datetime_str}.log"
	loglevel = logging.INFO
	logging.basicConfig(filename=logfile_name, format='%(asctime)s %(levelname)s: %(message)s', level=loglevel, datefmt='%m-%d-%Y %I:%M:%S %p')
	logging.info("Starting")
    #Mqtt Set up
	client = paho.Client(paho.CallbackAPIVersion.VERSION2)
	client.tls_set(ca_certs=None, certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS, ciphers=None)
	client.tls_insecure_set(True)
	client.username_pw_set(user, password)
	client.on_connect = on_connect
	client.on_message = on_message
	client.connect(host, port, 60)
	client.loop_forever()

if __name__ == "__main__":
	main(sys.argv[1:])
