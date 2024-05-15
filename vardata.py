# Pushover info
my_pushover_user = "your_pushover_user_key" # pushover user key
my_pushover_app = "the_application_token" # pushover app key

# Bambu login information
brokers = [
            {"host": "broker1.example.com", "port": 8883, "user": "bblp", "password": "password1", "device_id": "device1", "Printer_Title": "Bambu Printer", "PO_SOUND": "classical"},
            {"host": "broker2.example.com", "port": 8883, "user": "bblp", "password": "password2", "device_id": "device2", "Printer_Title": "Another Printer", "PO_SOUND": "jazz"}
            # Add more printers as needed
        ]
# host = '127.0.0.7' # bambu x1c ipv4 address
# port = 8883 # default port
# user = 'bblp' # default user
# password = 'alphanumeric_code' # access code from bambu x1c screen under cog wheel / network tab
# device_id = '0SOMETHING' # use mqtt-explorer to obtain or Bambu Studio, see readme.md for details
# PO_SOUND = 'classical' # List is available at https://pushover.net/api#sounds

# Wled login information and ip address
ledligth = True  # Use Wled light Flase/True
wled_ip = "192.168.1.100" # ip address of wled