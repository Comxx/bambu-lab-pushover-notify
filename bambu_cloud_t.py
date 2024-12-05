from __future__ import annotations
import ssl
import base64
import json
import aiohttp
import certifi
from dataclasses import dataclass
import logging
from enum import Enum

# Try to import optional dependencies
cloudscraper_available = False
try:
    import cloudscraper
    cloudscraper_available = True
except ImportError:
    cloudscraper_available = False

curl_available = False
try:
    from curl_cffi import requests as curl_requests
    curl_available = True
except ImportError:
    curl_available = False

class ConnectionMechanismEnum(Enum):
    CLOUDSCRAPER = 1
    CURL_CFFI = 2
    REQUESTS = 3

if cloudscraper_available:
    CONNECTION_MECHANISM = ConnectionMechanismEnum.CLOUDSCRAPER
else:
    CONNECTION_MECHANISM = ConnectionMechanismEnum.REQUESTS

IMPERSONATE_BROWSER = 'chrome'

# Custom exceptions
class CloudflareError(Exception):
    def __init__(self):
        super().__init__("Blocked by Cloudflare")
        self.error_code = 403

class EmailCodeRequiredError(Exception):
    def __init__(self):
        super().__init__("Email code required")
        self.error_code = 400

class EmailCodeExpiredError(Exception):
    def __init__(self):
        super().__init__("Email code expired")
        self.error_code = 400

class EmailCodeIncorrectError(Exception):
    def __init__(self):
        super().__init__("Email code incorrect")
        self.error_code = 400

class TfaCodeRequiredError(Exception):
    def __init__(self):
        super().__init__("Two factor authentication code required")
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

    async def _get_authentication_token(self) -> str:
        logging.debug("Getting accessToken from Bambu Cloud")
        if self._region == "China":
            url = 'https://api.bambulab.cn/v1/user-service/user/login'
        else:
            url = 'https://api.bambulab.com/v1/user-service/user/login'

        data = {
            "account": self._email,
            "password": self._password,
            "apiError": ""
        }

        # Create an SSL context
        ssl_context = ssl.create_default_context(cafile=certifi.where())

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, ssl=ssl_context) as response:
                if response.status == 403 and 'cloudflare' in await response.text():
                    raise CloudflareError()
                
                if response.status != 200:
                    logging.debug(f"Received error: {response.status}")
                    raise ValueError(response.status)
                
                auth_json = await response.json()
                accessToken = auth_json.get('accessToken', '')
                
                if accessToken:
                    return accessToken
                
                loginType = auth_json.get("loginType")
                if loginType == 'verifyCode':
                    raise EmailCodeRequiredError()
                elif loginType == 'tfa':
                    self._tfaKey = auth_json.get("tfaKey")
                    raise TfaCodeRequiredError()
                else:
                    raise ValueError(f"Unexpected login type: {loginType}")

    async def _get_email_verification_code(self):
        if self._region == "China":
            url = 'https://api.bambulab.cn/v1/user-service/user/send-code'
        else:
            url = 'https://api.bambulab.com/v1/user-service/user/send-code'
        
        data = {
            "email": self._email,
            "type": "codeLogin"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                if response.status != 200:
                    raise ValueError(response.status)

    async def _get_authentication_token_with_verification_code(self, code: str) -> str:
        if self._region == "China":
            url = 'https://api.bambulab.cn/v1/user-service/user/login'
        else:
            url = 'https://api.bambulab.com/v1/user-service/user/login'

        data = {
            "account": self._email,
            "code": code
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                if response.status == 400:
                    resp_json = await response.json()
                    if resp_json.get('code') == 1:
                        await self._get_email_verification_code()
                        raise EmailCodeExpiredError()
                    elif resp_json.get('code') == 2:
                        raise EmailCodeIncorrectError()
                
                if response.status != 200:
                    raise ValueError(response.status)
                
                resp_json = await response.json()
                return resp_json['accessToken']

    async def _get_authentication_token_with_2fa_code(self, code: str) -> str:
        if self._region == "China":
            url = 'https://api.bambulab.cn/v1/user-service/user/tfa/login'
        else:
            url = 'https://api.bambulab.com/v1/user-service/user/tfa/login'

        data = {
            "tfaKey": self._tfaKey,
            "tfaCode": code
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                if response.status != 200:
                    raise ValueError(response.status)
                return response.cookies.get("token")

    def _get_username_from_authentication_token(self) -> str:
        tokens = self._auth_token.split(".")
        if len(tokens) != 3:
            logging.debug("Auth token is not a JWT, trying alternate method")
            return None
        
        try:
            b64_string = tokens[1]
            b64_string += "=" * ((4 - len(b64_string) % 4) % 4)
            jsonAuthToken = json.loads(base64.b64decode(b64_string))
            return jsonAuthToken.get('username')
        except:
            logging.debug("Failed to decode auth token")
            return None

    async def test_authentication(self, region: str, email: str, username: str, auth_token: str) -> bool:
        self._region = region
        self._email = email
        self._username = username
        self._auth_token = auth_token
        try:
            await self.get_device_list()
            return True
        except:
            return False

    async def login(self, region: str, email: str, password: str):
        self._region = region
        self._email = email
        self._password = password

        self._auth_token = await self._get_authentication_token()
        self._username = self._get_username_from_authentication_token()

    async def login_with_verification_code(self, code: str):
        self._auth_token = await self._get_authentication_token_with_verification_code(code)
        self._username = self._get_username_from_authentication_token()

    async def login_with_2fa_code(self, code: str):
        self._auth_token = await self._get_authentication_token_with_2fa_code(code)
        self._username = self._get_username_from_authentication_token()

    async def get_device_list(self) -> dict:
        logging.debug("Getting device list from Bambu Cloud")
        if self._region == "China":
            url = 'https://api.bambulab.cn/v1/iot-service/api/user/bind'
        else:
            url = 'https://api.bambulab.com/v1/iot-service/api/user/bind'
        
        headers = {'Authorization': f'Bearer {self._auth_token}'}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, ssl=certifi.where()) as response:
                if response.status != 200:
                    logging.debug(f"Received error: {response.status}")
                    raise ValueError(response.status)
                json_response = await response.json()
                return json_response['devices']

    def get_device_type_from_device_product_name(self, device_product_name: str):
        if device_product_name == "X1 Carbon":
            return "X1C"
        return device_product_name.replace(" ", "")

    @property
    def username(self):
        return self._username
    
    @property
    def auth_token(self):
        return self._auth_token
    
    @property
    def bambu_connected(self) -> bool:
        return bool(self._auth_token)
    
    @property
    def cloud_mqtt_host(self):
        return "cn.mqtt.bambulab.com" if self._region == "China" else "us.mqtt.bambulab.com"