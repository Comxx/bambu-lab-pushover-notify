
import os
import requests
import json

# Replace these with your actual method of securely retrieving stored credentials
BAMBU_EMAIL = "commxx@gmail.com"
BAMBU_PASSWORD = 'Steven25@@##'

url = 'https://api.bambulab.com/v1/user-service/user/login'  # Change to the correct URL if needed

headers = {
    'Content-Type': 'application/json'
}

payload = {
    "account": BAMBU_EMAIL,
    "password": BAMBU_PASSWORD
}

response = requests.post(url, headers=headers, json=payload)

if response.status_code == 200:
    print("Request was successful.")
    print("Response:", response.json())
else:
    print("Failed to send request.")
    print("Status Code:", response.status_code)
    print("Response:", response.text)
