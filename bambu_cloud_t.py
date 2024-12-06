from __future__ import annotations
from enum import Enum
import base64
import json
import aiohttp
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
import asyncio

# Maintain cloudscraper support
cloudscraper_available = False
try:
    import cloudscraper
    cloudscraper_available = True
except ImportError:
    cloudscraper_available = False

class ConnectionMechanismEnum(Enum):
    CLOUDSCRAPER = 1
    REQUESTS = 2

CONNECTION_MECHANISM = ConnectionMechanismEnum.CLOUDSCRAPER if cloudscraper_available else ConnectionMechanismEnum.REQUESTS

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
    def __init__(self, region: str, email: str, username: str = '', auth_token: str = ''):
        self._region = region
        self._email = email
        self._username = username
        self._auth_token = auth_token
        self._password = None
        self._tfaKey = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.scraper = cloudscraper.create_scraper() if cloudscraper_available else None

    def _get_headers(self) -> Dict[str, str]:
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

    def _get_headers_with_auth_token(self) -> Dict[str, str]:
        headers = self._get_headers()
        headers['Authorization'] = f"Bearer {self._auth_token}"
        return headers

    async def _ensure_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()

    async def _test_response(self, response, return400: bool = False) -> None:
        if isinstance(response, aiohttp.ClientResponse):
            status = response.status
            text = await response.text()
        else:
            status = response.status_code
            text = response.text

        if status == 403 and 'cloudflare' in text:
            logging.error("BLOCKED BY CLOUDFLARE")
            raise CloudflareError()

        if status == 400 and not return400:
            logging.error(f"Connection failed with error code: {status}")
            raise PermissionError(status, text)

        if status > 400:
            logging.error(f"Connection failed with error code: {status}")
            raise PermissionError(status, text)

    async def _request(self, method: str, url: str, json_data: dict = None, headers: Dict[str, str] = None, return400: bool = False):
        if CONNECTION_MECHANISM == ConnectionMechanismEnum.CLOUDSCRAPER and self.scraper:
            # Run cloudscraper requests in a thread pool
            loop = asyncio.get_running_loop()
            if method.upper() == 'GET':
                response = await loop.run_in_executor(
                    None, 
                    lambda: self.scraper.get(url, headers=headers)
                )
            else:  # POST
                response = await loop.run_in_executor(
                    None, 
                    lambda: self.scraper.post(url, headers=headers, json=json_data)
                )
        else:
            await self._ensure_session()
            if method.upper() == 'GET':
                async with self.session.get(url, headers=headers) as response:
                    await self._test_response(response, return400)
                    return response, await response.json()
            else:  # POST
                async with self.session.post(url, headers=headers, json=json_data) as response:
                    await self._test_response(response, return400)
                    return response, await response.json()

        await self._test_response(response, return400)
        return response, response.json()

    async def _get_authentication_token(self) -> str:
        logging.debug("Getting accessToken from Bambu Cloud")
        data = {
            "account": self._email,
            "password": self._password,
            "apiError": ""
        }

        login_url = self._get_url("login")
        response, auth_json = await self._request('POST', login_url, json_data=data)

        accessToken = auth_json.get('accessToken', '')
        if accessToken:
            return accessToken

        loginType = auth_json.get("loginType")
        if loginType == 'verifyCode':
            logging.debug("Received verifyCode response")
            raise EmailCodeRequiredError()
        elif loginType == 'tfa':
            logging.debug("Received tfa response")
            self._tfaKey = auth_json.get("tfaKey")
            raise TfaCodeRequiredError()
        else:
            logging.error(f"Response not understood: {auth_json}")
            raise ValueError("Invalid login response")

    async def login(self, region: str, email: str, password: str) -> None:
        self._region = region
        self._email = email
        self._password = password

        self._auth_token = await self._get_authentication_token()
        self._username = await self._get_username_from_authentication_token()

    async def login_with_verification_code(self, code: str) -> None:
        data = {
            "account": self._email,
            "code": code
        }

        login_url = self._get_url("login")
        response, json_data = await self._request('POST', login_url, json_data=data, return400=True)

        if isinstance(response, aiohttp.ClientResponse):
            status = response.status
        else:
            status = response.status_code

        if status == 400:
            if json_data.get('code') == 1:
                await self._get_email_verification_code()
                raise EmailCodeExpiredError()
            elif json_data.get('code') == 2:
                raise EmailCodeIncorrectError()

        self._auth_token = json_data['accessToken']
        self._username = await self._get_username_from_authentication_token()

    async def login_with_2fa_code(self, code: str) -> None:
        data = {
            "tfaKey": self._tfaKey,
            "tfaCode": code
        }

        tfa_url = self._get_url("tfa")
        response, _ = await self._request('POST', tfa_url, json_data=data)
        
        if isinstance(response, aiohttp.ClientResponse):
            self._auth_token = response.cookies.get("token")
        else:
            self._auth_token = response.cookies.get("token")
            
        self._username = await self._get_username_from_authentication_token()

    async def _get_email_verification_code(self):
        data = {
            "email": self._email,
            "type": "codeLogin"
        }
        
        email_code_url = self._get_url("email_code")
        await self._request('POST', email_code_url, json_data=data)
        logging.debug("Verification code requested successfully")

    def _get_url(self, endpoint: str) -> str:
        base_url = "https://api.bambulab.com" if self._region != "China" else "https://api.bambulab.cn"
        endpoints = {
            "login": "/v1/user-service/user/login",
            "tfa": "/v1/user-service/user/tfa/login",
            "email_code": "/v1/user-service/user/send-code",
            "devices": "/v1/iot-service/api/user/bind"
        }
        return f"{base_url}{endpoints[endpoint]}"

    async def _get_username_from_authentication_token(self) -> str:
        if not self._auth_token:
            return None

        try:
            tokens = self._auth_token.split(".")
            if len(tokens) == 3:
                b64_string = tokens[1]
                b64_string += "=" * ((4 - len(b64_string) % 4) % 4)
                json_data = json.loads(base64.b64decode(b64_string))
                return json_data.get('username')
        except Exception as e:
            logging.error(f"Error decoding auth token: {e}")

        try:
            devices = await self.get_device_list()
            if devices and len(devices) > 0:
                return f"u_{devices[0].get('user_id')}"
        except Exception as e:
            logging.error(f"Error getting username from devices: {e}")

        return None

    async def get_device_list(self) -> list:
        devices_url = self._get_url("devices")
        _, response_json = await self._request('GET', devices_url, headers=self._get_headers_with_auth_token())
        return response_json.get('devices', [])

    async def close(self) -> None:
        if self.session:
            await self.session.close()
            self.session = None
        if self.scraper:
            self.scraper.close()

    @property
    def username(self) -> str:
        return self._username

    @property
    def auth_token(self) -> str:
        return self._auth_token

    @property
    def bambu_connected(self) -> bool:
        return bool(self._auth_token)

    @property
    def cloud_mqtt_host(self) -> str:
        return "cn.mqtt.bambulab.com" if self._region == "China" else "us.mqtt.bambulab.com"