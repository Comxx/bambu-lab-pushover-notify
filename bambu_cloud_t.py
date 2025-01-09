from __future__ import annotations
from enum import Enum
import base64
import json
import aiohttp
from dataclasses import dataclass
from constants import LOGGER, BambuUrl
from utils import get_Url

IMPERSONATE_BROWSER = 'chrome'

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
        super().__init__("Two-factor authentication code required")
        self.error_code = 400

@dataclass
class BambuCloud:
    def __init__(self, region: str, email: str, username: str, auth_token: str):
        self._region = region
        self._email = email
        self._username = username
        self._auth_token = auth_token
        self._password = None
        self._tfaKey = None
        self._session = aiohttp.ClientSession()  # Initialize an HTTP session
    
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
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }

    def _get_headers_with_auth_token(self) -> dict:
        headers = self._get_headers()
        headers['Authorization'] = f"Bearer {self._auth_token}"
        return headers

    async def _test_response(self, response):
        if response.status == 403:
            LOGGER.error("BLOCKED BY CLOUDFLARE")
            raise CloudflareError()
        elif response.status >= 400:
            text = await response.text()
            LOGGER.error(f"Connection failed with error code: {response.status}")
            LOGGER.debug(f"Response: '{text}'")
            raise PermissionError(response.status, text)

        LOGGER.debug(f"Response: {response.status}")

    async def _get(self, urlenum: BambuUrl):
        url = get_Url(urlenum, self._region)
        headers = self._get_headers_with_auth_token()
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                await self._test_response(response)
                return await response.json()

    async def _post(self, urlenum: BambuUrl, data: dict):
        url = get_Url(urlenum, self._region)
        headers = self._get_headers_with_auth_token()
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                await self._test_response(response)
                return await response.json()

    async def _get_authentication_token(self) -> str:
        LOGGER.debug("Getting accessToken from Bambu Cloud")
        data = {
            "account": self._email,
            "password": self._password,
            "apiError": ""
        }

        response = await self._post(BambuUrl.LOGIN, data)
        accessToken = response.get('accessToken', '')
        if accessToken:
            return accessToken

        loginType = response.get("loginType")
        if loginType == 'verifyCode':
            LOGGER.debug("Received verifyCode response")
            raise CodeRequiredError()
        elif loginType == 'tfa':
            self._tfaKey = response.get("tfaKey")
            LOGGER.debug("Received tfa response")
            raise TfaCodeRequiredError()
        else:
            raise ValueError("Unknown loginType")

    async def login(self, region: str, email: str, password: str):
        self._region = region
        self._email = email
        self._password = password
        self._auth_token = await self._get_authentication_token()

    async def login_with_verification_code(self, code: str):
        data = {
            "account": self._email,
            "code": code
        }
        response = await self._post(BambuUrl.LOGIN, data)
        self._auth_token = response.get('accessToken', '')

    async def login_with_2fa_code(self, code: str):
        data = {
            "tfaKey": self._tfaKey,
            "tfaCode": code
        }
        response = await self._post(BambuUrl.TFA_LOGIN, data)
        self._auth_token = response.get('accessToken', '')

    async def get_device_list(self) -> dict:
        LOGGER.debug("Getting device list from Bambu Cloud")
        return await self._get(BambuUrl.BIND)

    async def get_slicer_settings(self) -> dict:
        LOGGER.debug("Getting slicer settings from Bambu Cloud")
        return await self._get(BambuUrl.SLICER_SETTINGS)

    async def get_tasklist(self) -> dict:
        LOGGER.debug("Getting full task list from Bambu Cloud")
        return await self._get(BambuUrl.TASKS)

    async def get_projects(self) -> dict:
        LOGGER.debug("Getting projects list from Bambu Cloud")
        return await self._get(BambuUrl.PROJECTS)

    async def get_latest_task_for_printer(self, deviceId: str) -> dict:
        LOGGER.debug(f"Getting latest task for printer {deviceId}")
        tasklist = await self.get_tasklist()
        for task in tasklist.get('hits', []):
            if task.get('deviceId') == deviceId:
                return task
        return {}

    async def download(self, url: str) -> bytes:
        LOGGER.debug(f"Downloading file from {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                await self._test_response(response)
                return await response.read()
    
    async def close(self):
        """Clean up resources."""
        if self._session:
            await self._session.close()
    @property
    def username(self):
        return self._username

    @property
    def auth_token(self):
        return self._auth_token

    @property
    def bambu_connected(self) -> bool:
        return bool(self._auth_token)
