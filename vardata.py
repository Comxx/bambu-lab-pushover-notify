# Pushover info
my_pushover_user = "your_pushover_user_key" # pushover user key
my_pushover_app = "the_application_token" # pushover app key

# Bambu login information
# List of Bambu Pinters with their respective settings
# Each dictionary represents a Printer, with the following keys:
# - host: The hostname or IP address of the Bambu Printer
# - port: 8883 # default port number of the Bambu Printer
# - user: "bblp" # default user to use when connecting to the Bambu Printer
# - password: # access code from bambu x1c screen under cog wheel / network tab no the Bambu Printer
# - device_id: # use mqtt-explorer to obtain or Bambu Studio, see readme.md for details
# - Printer_Title: What you want to call you Bambu Printer
# - PO_SOUND: The sound to use when sending Pushover notifications List is available at https://pushover.net/api#sounds
# - my_pushover_user: The Pushover user key to use for sending notifications
# - my_pushover_app: The Pushover app key to use for sending notifications
brokers = [
    #frist Printer
    {"host": "127.0.0.7", 
        "port": 8883, 
        "user": "bblp", 
        "password": "password1", 
        "device_id": "device1", 
        "Printer_Title": "Bambu Printer", 
        "PO_SOUND": "classical", 
        "my_pushover_user": "your_pushover_user_key", 
        "my_pushover_app": "the_application_token",
        "ledligth":   True,
        "wled_ip": "192.168.1.100"
        },
    # Second Printer
    {"host": "127.0.0.8", 
        "port": 8883, 
        "user": "bblp", 
        "password": "password2", 
        "device_id": "device2", 
        "Printer_Title": "Another Printer", 
        "PO_SOUND": "pushover", 
        "my_pushover_user": "your_pushover_user_key2", 
        "my_pushover_app": "the_application_token2",
        "ledligth":   True,
        "wled_ip": "192.168.1.101"
        },
            # Add more printers as needed
        ]
# host = '127.0.0.7' # bambu x1c ipv4 address
# port = 8883 # default port
# user = 'bblp' # default user
# password = 'alphanumeric_code' # access code from bambu x1c screen under cog wheel / network tab
# device_id = '0SOMETHING' # use mqtt-explorer to obtain or Bambu Studio, see readme.md for details
# PO_SOUND = 'classical' # List is available at https://pushover.net/api#sounds

# Wled login information and ip address
ledligth = True  # Use Wled light False/True
wled_ip = "192.168.1.100" # ip address of wled