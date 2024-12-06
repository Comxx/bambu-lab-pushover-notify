ffrom __future__ import annotations
from enum import Enum
import base64
import json
import aiohttp
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

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
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def _test_response(self, response: aiohttp.ClientResponse, return400: bool = False) -> None:
        if response.status == 403 and 'cloudflare' in await response.text():
            logging.error("BLOCKED BY CLOUDFLARE")
            raise CloudflareError()

        if response.status == 400 and not return400:
            error_text = await response.text()
            logging.error(f"Connection failed with error code: {response.status}")
            logging.error(f"Error response: {error_text}")
            raise PermissionError(response.status, error_text)

        if response.status > 400:
            error_text = await response.text()
            logging.error(f"Connection failed with error code: {response.status}")
            logging.error(f"Error response: {error_text}")
            raise PermissionError(response.status, error_text)

    async def _get(self, url: str) -> aiohttp.ClientResponse:
        await self._ensure_session()
        headers = self._get_headers_with_auth_token()
        try:
            async with self.session.get(url, headers=headers, timeout=30) as response:
                await self._test_response(response)
                return response
        except aiohttp.ClientError as e:
            logging.error(f"Network error during GET request: {e}")
            raise

    async def _post(self, url: str, json_data: dict, headers: Dict[str, str] = None, return400: bool = False) -> aiohttp.ClientResponse:
        await self._ensure_session()
        if headers is None:
            headers = self._get_headers()
        
        try:
            async with self.session.post(url, headers=headers, json=json_data, timeout=30) as response:
                await self._test_response(response, return400)
                return response
        except aiohttp.ClientError as e:
            logging.error(f"Network error during POST request: {e}")
            raise

    async def _get_authentication_token(self) -> str:
        logging.debug("Getting accessToken from Bambu Cloud")
        data = {
            "account": self._email,
            "password": self._password,
            "apiError": ""
        }

        login_url = self._get_url("login")
        response = await self._post(login_url, json_data=data)
        auth_json = await response.json()

        accessToken = auth_json.get('accessToken', '')
        if accessToken:
            return accessToken

        loginType = auth_json.get("loginType")
        if loginType == 'verifyCode':
            logging.debug("Received verifyCode response")
            await self._get_email_verification_code()
            raise EmailCodeRequiredError()
        elif loginType == 'tfa':
            logging.debug("Received tfa response")
            self._tfaKey = auth_json.get("tfaKey")
            raise TfaCodeRequiredError()
        else:
            logging.error(f"Response not understood: {auth_json}")
            raise ValueError("Invalid login response")

    async def _get_email_verification_code(self):
        data = {
            "email": self._email,
            "type": "codeLogin"
        }
        email_code_url = self._get_url("email_code")
        await self._post(email_code_url, json_data=data)
        logging.debug("Verification code requested successfully")

    async def login(self, region: str, email: str, password: str) -> None:
        self._region = region
        self._email = email
        self._password = password

        try:
            self._auth_token = await self._get_authentication_token()
            self._username = await self._get_username_from_authentication_token()
        except Exception as e:
            logging.error(f"Login failed: {e}")
            raise

    async def login_with_verification_code(self, code: str) -> None:
        data = {
            "account": self._email,
            "code": code
        }

        login_url = self._get_url("login")
        response = await self._post(login_url, json_data=data, return400=True)

        if response.status == 400:
            response_json = await response.json()
            if response_json.get('code') == 1:
                await self._get_email_verification_code()
                raise EmailCodeExpiredError()
            elif response_json.get('code') == 2:
                raise EmailCodeIncorrectError()

        response_json = await response.json()
        self._auth_token = response_json['accessToken']
        self._username = await self._get_username_from_authentication_token()

    async def login_with_2fa_code(self, code: str) -> None:
        data = {
            "tfaKey": self._tfaKey,
            "tfaCode": code
        }

        tfa_url = self._get_url("tfa")
        response = await self._post(tfa_url, json_data=data)
        self._auth_token = response.cookies.get("token")
        if not self._auth_token:
            response_json = await response.json()
            self._auth_token = response_json.get('accessToken')
        self._username = await self._get_username_from_authentication_token()

    def _get_url(self, endpoint: str) -> str:
        base_url = "https://api.bambulab.com" if self._region != "China" else "https://api.bambulab.cn"
        endpoints = {
            "login": "/v1/user-service/user/login",
            "tfa": "/v1/user-service/user/tfa/login",
            "email_code": "/v1/user-service/user/send-code",
            "devices": "/v1/iot-service/api/user/bind",
            "projects": "/v1/iot-service/api/user/projects"
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
                username = json_data.get('username')
                if username:
                    return username
        except Exception as e:
            logging.debug(f"Could not decode JWT token: {e}")

        # Fallback to getting username from projects
        try:
            response = await self._get(self._get_url("projects"))
            projects_data = await response.json()
            if projects_data.get('projects'):
                first_project = projects_data['projects'][0]
                user_id = first_project.get('user_id')
                if user_id:
                    return f"u_{user_id}"
        except Exception as e:
            logging.error(f"Error getting username from projects: {e}")

        return None

    async def get_device_list(self) -> list:
        devices_url = self._get_url("devices")
        response = await self._get(devices_url)
        response_json = await response.json()
        return response_json.get('devices', [])

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

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