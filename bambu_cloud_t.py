from __future__ import annotations
from enum import Enum
import base64
import json
import aiohttp
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta

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
        self._refresh_token = None
        self._password = None
        self._tfaKey = None
        self._token_expires_at = None
        self._refresh_expires_at = None
        self.session: Optional[aiohttp.ClientSession] = None
        self._is_refreshing = False

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
        
        # Check if token needs refresh before making request
        if self._should_refresh_token():
            await self.refresh_token()
            
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

    async def _get_authentication_token(self) -> Tuple[str, str, int, int]:
        """Get authentication token and refresh token with expiration times"""
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
        refreshToken = auth_json.get('refreshToken', '')
        expiresIn = auth_json.get('expiresIn', 7776000)  # Default to 90 days
        refreshExpiresIn = auth_json.get('refreshExpiresIn', expiresIn)

        if accessToken:
            return accessToken, refreshToken, expiresIn, refreshExpiresIn

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

    async def refresh_token(self) -> bool:
        """Refresh the access token using the refresh token"""
        if self._is_refreshing or not self._refresh_token:
            return False

        self._is_refreshing = True
        try:
            refresh_url = self._get_url("refresh_token")
            data = {"refreshToken": self._refresh_token}
            
            async with self.session.post(refresh_url, json=data, headers=self._get_headers()) as response:
                if response.status == 200:
                    result = await response.json()
                    self._auth_token = result["accessToken"]
                    self._refresh_token = result["refreshToken"]
                    self._token_expires_at = datetime.now() + timedelta(seconds=result["expiresIn"])
                    self._refresh_expires_at = datetime.now() + timedelta(seconds=result["refreshExpiresIn"])
                    return True
                else:
                    logging.error(f"Token refresh failed: {await response.text()}")
                    return False
        except Exception as e:
            logging.error(f"Error refreshing token: {e}")
            return False
        finally:
            self._is_refreshing = False

    def _should_refresh_token(self) -> bool:
        """Check if token should be refreshed (less than 1 day remaining)"""
        if not self._token_expires_at:
            return False
        
        time_until_expiry = self._token_expires_at - datetime.now()
        return time_until_expiry < timedelta(days=1)

    async def login(self, region: str, email: str, password: str) -> None:
        self._region = region
        self._email = email
        self._password = password

        try:
            auth_token, refresh_token, expires_in, refresh_expires_in = await self._get_authentication_token()
            self._auth_token = auth_token
            self._refresh_token = refresh_token
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            self._refresh_expires_at = datetime.now() + timedelta(seconds=refresh_expires_in)
            self._username = await self._get_username_from_authentication_token()
        except Exception as e:
            logging.error(f"Login failed: {e}")
            raise

    # [Previous methods remain the same: _get_email_verification_code, login_with_verification_code, 
    #  login_with_2fa_code, _get_url, _get_username_from_authentication_token, get_device_list, close]

    @property
    def username(self) -> str:
        return self._username

    @property
    def auth_token(self) -> str:
        return self._auth_token

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    @property
    def token_expires_at(self) -> Optional[datetime]:
        return self._token_expires_at

    @property
    def refresh_expires_at(self) -> Optional[datetime]:
        return self._refresh_expires_at

    @property
    def bambu_connected(self) -> bool:
        return bool(self._auth_token)

    @property
    def cloud_mqtt_host(self) -> str:
        return "cn.mqtt.bambulab.com" if self._region == "China" else "us.mqtt.bambulab.com"

    def _get_url(self, endpoint: str) -> str:
        base_url = "https://api.bambulab.com" if self._region != "China" else "https://api.bambulab.cn"
        endpoints = {
            "login": "/v1/user-service/user/login",
            "refresh_token": "/v1/user-service/user/refreshtoken",
            "tfa": "/v1/user-service/user/tfa/login",
            "email_code": "/v1/user-service/user/send-code",
            "devices": "/v1/iot-service/api/user/bind",
            "projects": "/v1/iot-service/api/user/projects"
        }
        return f"{base_url}{endpoints[endpoint]}"