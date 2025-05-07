from __future__ import annotations
from enum import (
    Enum,
)

import base64
import json
import requests
from dataclasses import dataclass
from constants import LOGGER, BambuUrl
from utils import get_Url
import cloudscraper
IMPERSONATE_BROWSER='chrome'

class CloudflareError(Exception):
    def __init__(self):
        super().__init__("Blocked by Cloudflare")
        self.error_code = 403

class CodeRequiredError(Exception):
    def __init__(self):
        super().__init__("Email code required")
        self.error_code = 400

class CodeExpiredError(Exception):
    def __init__(self):
        super().__init__("Email code expired")
        self.error_code = 400

class CodeIncorrectError(Exception):
    def __init__(self):
        super().__init__("Email code incorrect")
        self.error_code = 400

class TfaCodeRequiredError(Exception):
    def __init__(self):
        super().__init__("Two factor authentication code required")
        self.error_code = 400

class CurlUnavailableError(Exception):
    def __init__(self):
        super().__init__("curl library unavailable")
        self.error_code = 400

@dataclass
class BambuCloud:
  
    def __init__(self, region: str, email: str, username: str, auth_token: str):
        self._region = region
        self._email = email
        self._username = username
        self._auth_token = auth_token
        self._tfaKey = None

    def _get_headers(self):
        return {
            'User-Agent': 'bambu_network_agent/01.09.05.01',
            'X-BBL-Client-Name': 'OrcaSlicer',
            'X-BBL-Client-Type': 'slicer',
            'X-BBL-Client-Version': '01.09.05.51',
            'X-BBL-Language': 'en-US',
            'X-BBL-OS-Type': 'linux',
            'X-BBL-OS-Version': '6.2.0',
            'X-BBL-Agent-Version': '01.09.05.01',
            'X-BBL-Executable-info': '{}',
            'X-BBL-Agent-OS-Type': 'linux',
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }
        # Orca/Bambu Studio also add this - need to work out what an appropriate ID is to put here:
        # 'X-BBL-Device-ID': BBL_AUTH_UUID,
        # Example: X-BBL-Device-ID: 370f9f43-c6fe-47d7-aec9-5fe5ef7e7673

    def _get_headers_with_auth_token(self) -> dict:
        headers = self._get_headers()
        headers['Authorization'] = f"Bearer {self._auth_token}"
        return headers

    def _test_response(self, response, return400=False):
        # Check specifically for cloudflare block
        if response.status_code == 403 and 'cloudflare' in response.text:
            LOGGER.error("BLOCKED BY CLOUDFLARE")
            raise CloudflareError()
        elif response.status_code == 429 and 'cloudflare' in response.text:
            LOGGER.error("TEMPORARY 429 BLOCK BY CLOUDFLARE")
            raise CloudflareError(response.status_code, response.text)
        elif response.status_code == 400 and not return400:
            LOGGER.error(f"Connection failed with error code: {response.status_code}")
            LOGGER.info(f"Response: '{response.text}'")
            raise PermissionError(response.status_code, response.text)
        elif response.status_code > 400:
            LOGGER.error(f"Connection failed with error code: {response.status_code}")
            LOGGER.info(f"Response: '{response.text}'")
            raise PermissionError(response.status_code, response.text)

        LOGGER.info(f"Response: {response.status_code}")

    def _get(self, urlenum: BambuUrl):
        url = get_Url(urlenum, self._region)
        headers = self._get_headers_with_auth_token()
        
        # Use cloudscraper for the GET request
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, headers=headers, timeout=10)
        
        self._test_response(response)
        
        return response


    
    def _post(self, urlenum: BambuUrl, json: dict, headers=None, return400=False):
        url = get_Url(urlenum, self._region)        
        headers = headers or self._get_headers()
        scraper = cloudscraper.create_scraper()
        response = scraper.post(url, headers=headers, json=json)
        self._test_response(response, return400)

        return response

    def _get_authentication_token(self) -> str:
        LOGGER.info("Getting accessToken from Bambu Cloud")

        # First we need to find out how Bambu wants us to login.
        data = {
            "account": self._email,
            "password": self._password,
            "apiError": ""
        }

        response = self._post(BambuUrl.LOGIN, json=data)

        auth_json = response.json()
        accessToken = auth_json.get('accessToken', '')
        if accessToken != '':
            # We were provided the accessToken directly.
            return accessToken
        
        loginType = auth_json.get("loginType", None)
        if loginType is None:
            LOGGER.error(f"loginType not present")
            LOGGER.error(f"Response not understood: '{response.text}'")
            return ValueError(0) # FIXME
        elif loginType == 'verifyCode':
            LOGGER.info(f"Received verifyCode response")
            raise CodeRequiredError()
        elif loginType == 'tfa':
            # Store the tfaKey for later use
            LOGGER.info(f"Received tfa response")
            self._tfaKey = auth_json.get("tfaKey")
            raise TfaCodeRequiredError()
        else:
            LOGGER.info(f"Did not understand json. loginType = '{loginType}'")
            LOGGER.error(f"Response not understood: '{response.text}'")
            return ValueError(1) # FIXME
        
    async def _get_new_code(self):
        if '@' in self._email:
            self._get_email_verification_code()
        else:
            self._get_sms_verification_code()
    
    def _get_email_verification_code(self):
        # Send the verification code request
        data = {
            "email": self._email,
            "type": "codeLogin"
        }

        LOGGER.info("Requesting email verification code")
        self._post(BambuUrl.EMAIL_CODE, json=data)
        LOGGER.info("Verification code requested successfully.")

    def _get_sms_verification_code(self):
        # Send the verification code request
        data = {
            "phone": self._email,
            "type": "codeLogin"
        }

        LOGGER.info("Requesting SMS verification code")
        self._post(BambuUrl.SMS_CODE, json=data)
        LOGGER.info("Verification code requested successfully.")

    def _get_authentication_token_with_verification_code(self, code) -> dict:
        LOGGER.info("Attempting to connect with provided verification code.")
        data = {
            "account": self._email,
            "code": code
        }

        response = self._post(BambuUrl.LOGIN, json=data, return400=True)
        status_code = response.status_code

        if status_code == 200:
            LOGGER.info("Authentication successful.")
            LOGGER.info(f"Response = '{response.json()}'")
        elif status_code == 400:
            LOGGER.info(f"Received response: {response.json()}")           
            if response.json()['code'] == 1:
                # Code has expired. Request a new one.
                self._get_new_code()
                raise CodeExpiredError()
            elif response.json()['code'] == 2:
                # Code was incorrect. Let the user try again.
                raise CodeIncorrectError()
            else:
                LOGGER.error(f"Response not understood: '{response.json()}'")
                raise ValueError(response.json()['code'])

        return response.json()['accessToken']
    
    def _get_authentication_token_with_2fa_code(self, code: str) -> dict:
        LOGGER.info("Attempting to connect with provided 2FA code.")

        data = {
            "tfaKey": self._tfaKey,
            "tfaCode": code
        }

        response = self._post(BambuUrl.TFA_LOGIN, json=data)

        LOGGER.info(f"Response: {response.status_code}")
        if response.status_code == 200:
            LOGGER.info("Authentication successful.")

        cookies = response.cookies.get_dict()
        token_from_tfa = cookies.get("token")
        #LOGGER.info(f"token_from_tfa: {token_from_tfa}")

        return token_from_tfa
    
    def _get_username_from_authentication_token(self) -> str:
        LOGGER.info("Trying to get username from authentication token.")
        # User name is in 2nd portion of the auth token (delimited with periods)
        username = None
        tokens = self._auth_token.split(".")
        if len(tokens) != 3:
            LOGGER.info("Received authToken is not a JWT.")
            LOGGER.info("Trying to use project API to retrieve username instead")
            response = self.get_projects();
            if response is not None:
                projectsnode = response.get('projects', None)
                if projectsnode is None:
                    LOGGER.info("Failed to find projects node")
                else:
                    if len(projectsnode) == 0:
                        LOGGER.info("No projects node in response")
                    else:
                        project=projectsnode[0]
                        if project.get('user_id', None) is None:
                            LOGGER.info("No user_id entry")
                        else:
                            username = f"u_{project['user_id']}"
                            LOGGER.info(f"Found user_id of {username}")
        else:
            LOGGER.info("Authentication token looks to be a JWT")
            try:
                b64_string = self._auth_token.split(".")[1]
                # String must be multiples of 4 chars in length. For decode pad with = character
                b64_string += "=" * ((4 - len(b64_string) % 4) % 4)
                jsonAuthToken = json.loads(base64.b64decode(b64_string))
                # Gives json payload with "username":"u_<digits>" within it
                username = jsonAuthToken.get('username', None)
            except:
                LOGGER.info("Unable to decode authToken to json to retrieve username.")

        if username is None:
            LOGGER.info(f"Unable to decode authToken to retrieve username. AuthToken = {self._auth_token}")

        return username
    
    # Retrieves json description of devices in the form:
    # {
    #     'message': 'success',
    #     'code': None,
    #     'error': None,
    #     'devices': [
    #         {
    #             'dev_id': 'REDACTED',
    #             'name': 'Bambu P1S',
    #             'online': True,
    #             'print_status': 'SUCCESS',
    #             'dev_model_name': 'C12',
    #             'dev_product_name': 'P1S',
    #             'dev_access_code': 'REDACTED',
    #             'nozzle_diameter': 0.4
    #         },
    #         {
    #             'dev_id': 'REDACTED',
    #             'name': 'Bambu P1P',
    #             'online': True,
    #             'print_status': 'RUNNING',
    #             'dev_model_name': 'C11',
    #             'dev_product_name': 'P1P',
    #             'dev_access_code': 'REDACTED',
    #             'nozzle_diameter': 0.4
    #         },
    #         {
    #             'dev_id': 'REDACTED',
    #             'name': 'Bambu X1C',
    #             'online': True,
    #             'print_status': 'RUNNING',
    #             'dev_model_name': 'BL-P001',
    #             'dev_product_name': 'X1 Carbon',
    #             'dev_access_code': 'REDACTED',
    #             'nozzle_diameter': 0.4
    #         }
    #     ]
    # }
    
    def test_authentication(self, region: str, email: str, username: str, auth_token: str) -> bool:
        self._region = region
        self._email = email
        self._username = username
        self._auth_token = auth_token
        try:
            self.get_device_list()
        except:
            return False
        return True

    async def login(self, region: str, email: str, password: str) -> str:
        self._region = region
        self._email = email
        self._password = password

        result = self._get_authentication_token()
        self._auth_token = result
        self._username = self._get_username_from_authentication_token()
        
    async def login_with_verification_code(self, code: str):
        result = self._get_authentication_token_with_verification_code(code)
        self._auth_token = result
        self._username = self._get_username_from_authentication_token()

    def login_with_2fa_code(self, code: str):
        result = self._get_authentication_token_with_2fa_code(code)
        self._auth_token = result
        self._username = self._get_username_from_authentication_token()

    def request_new_code(self):
        self._get_new_code()

    def get_device_list(self) -> dict:
        LOGGER.info("Getting device list from Bambu Cloud")
        try:
            response = self._get(BambuUrl.BIND)
        except:
            return None
        return response.json()['devices']

    # The slicer settings are of the following form:
    #
    # {
    #     "message": "success",
    #     "code": null,
    #     "error": null,
    #     "print": {
    #         "public": [
    #             {
    #                 "setting_id": "GP004",
    #                 "version": "01.09.00.15",
    #                 "name": "0.20mm Standard @BBL X1C",
    #                 "update_time": "2024-07-04 11:27:08",
    #                 "nickname": null
    #             },
    #             ...
    #         }
    #         "private": []
    #     },
    #     "printer": {
    #         "public": [
    #             {
    #                 "setting_id": "GM001",
    #                 "version": "01.09.00.15",
    #                 "name": "Bambu Lab X1 Carbon 0.4 nozzle",
    #                 "update_time": "2024-07-04 11:25:07",
    #                 "nickname": null
    #             },
    #             ...
    #         ],
    #         "private": []
    #     },
    #     "filament": {
    #         "public": [
    #             {
    #                 "setting_id": "GFSA01",
    #                 "version": "01.09.00.15",
    #                 "name": "Bambu PLA Matte @BBL X1C",
    #                 "update_time": "2024-07-04 11:29:21",
    #                 "nickname": null,
    #                 "filament_id": "GFA01"
    #             },
    #             ...
    #         ],
    #         "private": [
    #             {
    #                 "setting_id": "PFUS46ea5c221cabe5",
    #                 "version": "1.9.0.14",
    #                 "name": "Fillamentum PLA Extrafill @Bambu Lab X1 Carbon 0.4 nozzle",
    #                 "update_time": "2024-07-10 06:48:17",
    #                 "base_id": null,
    #                 "filament_id": "Pc628b24",
    #                 "filament_type": "PLA",
    #                 "filament_is_support": "0",
    #                 "nozzle_temperature": [
    #                     190,
    #                     240
    #                 ],
    #                 "nozzle_hrc": "3",
    #                 "filament_vendor": "Fillamentum"
    #             },
    #             ...
    #         ]
    #     },
    #     "settings": {}
    # }

    def get_slicer_settings(self) -> dict:
        LOGGER.info("Getting slicer settings from Bambu Cloud")
        try:
            response = self._get(BambuUrl.SLICER_SETTINGS)
        except:
            return None
        return response.json()
    
    # The task list is of the following form with a 'hits' array with typical 20 entries.
    #
    # "total": 531,
    # "hits": [
    #     {
    #     "id": 35237965,
    #     "designId": 0,
    #     "designTitle": "",
    #     "instanceId": 0,
    #     "modelId": "REDACTED",
    #     "title": "REDACTED",
    #     "cover": "REDACTED",
    #     "status": 4,
    #     "feedbackStatus": 0,
    #     "startTime": "2023-12-21T19:02:16Z",
    #     "endTime": "2023-12-21T19:02:35Z",
    #     "weight": 34.62,
    #     "length": 1161,
    #     "costTime": 10346,
    #     "profileId": 35276233,
    #     "plateIndex": 1,
    #     "plateName": "",
    #     "deviceId": "REDACTED",
    #     "amsDetailMapping": [
    #         {
    #         "ams": 4,
    #         "sourceColor": "F4D976FF",
    #         "targetColor": "F4D976FF",
    #         "filamentId": "GFL99",
    #         "filamentType": "PLA",
    #         "targetFilamentType": "",
    #         "weight": 34.62
    #         }
    #     ],
    #     "mode": "cloud_file",
    #     "isPublicProfile": false,
    #     "isPrintable": true,
    #     "deviceModel": "P1P",
    #     "deviceName": "Bambu P1P",
    #     "bedType": "textured_plate"
    #     },

    def get_tasklist(self) -> dict:
        LOGGER.info("Getting full task list from Bambu Cloud")
        try:
            response = self._get(BambuUrl.TASKS)
        except:
            return None
        return response.json()

    # Returns a list of projects for the account.
    #
    # {
    # "message": "success",
    # "code": null,
    # "error": null,
    # "projects": [
    #     {
    #     "project_id": "164995388",
    #     "user_id": "1688388450",
    #     "model_id": "US48e2103d939bf8",
    #     "status": "ACTIVE",
    #     "name": "Alcohol_Marker_Storage_for_Copic,_Ohuhu_and_the_like",
    #     "content": "{'printed_plates': [{'plate': 1}]}",
    #     "create_time": "2024-11-17 06:12:33",
    #     "update_time": "2024-11-17 06:12:40"
    #     },
    #     ...
    #
    def get_projects(self) -> dict:
        LOGGER.info("Getting projects list from Bambu Cloud")
        try:
            response = self._get(BambuUrl.PROJECTS)
        except:
            return None
        return response.json()

    def get_latest_task_for_printer(self, deviceId: str) -> dict:
        LOGGER.info(f"Getting latest task for printer from Bambu Cloud")
        try:
            data = self.get_tasklist_for_printer(deviceId)
            if len(data) != 0:
                return data[0]
            LOGGER.info("No tasks found for printer")
            return None
        except:
            return None

    def get_tasklist_for_printer(self, deviceId: str) -> dict:
        LOGGER.info(f"Getting full task list for printer from Bambu Cloud")
        tasks = []
        data = self.get_tasklist()
        for task in data['hits']:
            if task['deviceId'] == deviceId:
                tasks.append(task)
        return tasks

    def get_device_type_from_device_product_name(self, device_product_name: str):
        if device_product_name == "X1 Carbon":
            return "X1C"
        return device_product_name.replace(" ", "")

    def download(self, url: str) -> bytearray:
        LOGGER.info(f"Downloading cover image: {url}")
        try:
            # This is just a standard download from an unauthenticated end point.
            response = requests.get(url)
        except:
            return None
        return response.content

    @property
    def username(self):
        return self._username
    
    @property
    def auth_token(self):
        return self._auth_token
    
    @property
    def bambu_connected(self) -> bool:
        return self._auth_token != "" and self._auth_token != None
    
    @property
    def cloud_mqtt_host(self):
        return "cn.mqtt.bambulab.com" if self._region == "China" else "us.mqtt.bambulab.com"