from flask import Flask, request, render_template, jsonify
from flask_socketio import SocketIO, emit
import json
import logging

app = Flask(__name__)
socketio = SocketIO(app)

@app.route('/')
def home():
    try:
        with open('settings.json', 'r') as f:
            brokers = json.load(f)
    except FileNotFoundError:
        brokers = []

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
    brokers = request.json
    with open('settings.json', 'w') as f:
        f.write(json.dumps(brokers, indent=4))
    return jsonify({"status": "success"})

def emit_printer_update(data):
    socketio.emit('printer_update', data)

def start_web_server(host='0.0.0.0', port=5000):
    logging.info("Flask server starting...")
    socketio.run(app, host=host, port=port)
    logging.info("Flask server started successfully")

if __name__ == '__main__':
    start_web_server()