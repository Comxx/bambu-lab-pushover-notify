

# Pushover info
PO_TITLE = "Bambu Printer"
PO_SOUND = 'classical' 
my_pushover_user = "your_pushover_user_key" # pushover user key
my_pushover_app = "the_application_token" # pushover app key
pause_error_secs = 10 # seconds
repeat_errors = 2 # number of times

# Bambu login information
host = '127.0.0.7' # bambu x1c ipv4 address
port = 8883 # default port
user = 'bblp' # default user
password = 'alphanumeric_code' # access code from bambu x1c screen under cog wheel / network tab
device_id = '0SOMETHING' # use mqtt-explorer to obtain or Bambu Studio, see readme.md for details

# Wled login information and ip address
ledligth = True  # Use Wled light False/True
wled_ip = "192.168.1.100" # ip address of wled