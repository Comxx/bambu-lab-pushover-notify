from __future__ import annotations
from enum import (
    Enum,
)

import base64
import json
import aiohttp
import asyncio

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
    CLOUDSCRAPER = 1,
    CURL_CFFI = 2,
    AIOHTTP = 3

if cloudscraper_available:
    CONNECTION_MECHANISM = ConnectionMechanismEnum.CLOUDSCRAPER
else:
    CONNECTION_MECHANISM = ConnectionMechanismEnum.AIOHTTP

from dataclasses import dataclass

from .constants import (
     LOGGER,
     BambuUrl
)
from .utils import get_Url

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
        self._session = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

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

    def _get_headers_with_auth_token(self) -> dict:
        if CONNECTION_MECHANISM == ConnectionMechanismEnum.CURL_CFFI:
            headers = {}
        else:
            headers = self._get_headers()
        headers['Authorization'] = f"Bearer {self._auth_token}"
        return headers

    async def _test_response(self, response, return400=False):
        # Check specifically for cloudflare block
        if response.status == 403 and 'cloudflare' in await response.text():
            LOGGER.error("BLOCKED BY CLOUDFLARE")
            raise CloudflareError()
        elif response.status == 429 and 'cloudflare' in await response.text():
            LOGGER.error("TEMPORARY 429 BLOCK BY CLOUDFLARE")
            raise CloudflareError(response.status, await response.text())
        elif response.status == 400 and not return400:
            LOGGER.error(f"Connection failed with error code: {response.status}")
            LOGGER.debug(f"Response: '{await response.text()}'")
            raise PermissionError(response.status, await response.text())
        elif response.status > 400:
            LOGGER.error(f"Connection failed with error code: {response.status}")
            LOGGER.debug(f"Response: '{await response.text()}'")
            raise PermissionError(response.status, await response.text())

        LOGGER.debug(f"Response: {response.status}")
        async def _get(self, urlenum: BambuUrl):
        url = get_Url(urlenum, self._region)
        headers = self._get_headers_with_auth_token()
        if CONNECTION_MECHANISM == ConnectionMechanismEnum.CURL_CFFI:
            if not curl_available:
                LOGGER.debug(f"Curl library is unavailable.")
                raise CurlUnavailableError()
            response = curl_requests.get(url, headers=headers, timeout=10, impersonate=IMPERSONATE_BROWSER)
        elif CONNECTION_MECHANISM == ConnectionMechanismEnum.CLOUDSCRAPER:
            if len(headers) == 0:
                headers = self._get_headers()
            scraper = cloudscraper.create_scraper()
            response = scraper.get(url, headers=headers, timeout=10)
        elif CONNECTION_MECHANISM == ConnectionMechanismEnum.AIOHTTP:
            if not self._session:
                self._session = aiohttp.ClientSession()
            async with self._session.get(url, headers=headers, timeout=10) as response:
                await self._test_response(response)
                return response
        else:
            raise NotImplementedError()

    async def _post(self, urlenum: BambuUrl, json_data: dict, headers={}, return400=False):
        url = get_Url(urlenum, self._region)
        if CONNECTION_MECHANISM == ConnectionMechanismEnum.CURL_CFFI:
            if not curl_available:
                LOGGER.debug(f"Curl library is unavailable.")
                raise CurlUnavailableError()
            response = curl_requests.post(url, headers=headers, json=json_data, impersonate=IMPERSONATE_BROWSER)
        elif CONNECTION_MECHANISM == ConnectionMechanismEnum.CLOUDSCRAPER:
            if len(headers) == 0:
                headers = self._get_headers()
            scraper = cloudscraper.create_scraper()
            response = scraper.post(url, headers=headers, json=json_data)
        elif CONNECTION_MECHANISM == ConnectionMechanismEnum.AIOHTTP:
            if not self._session:
                self._session = aiohttp.ClientSession()
            async with self._session.post(url, headers=headers, json=json_data, timeout=10) as response:
                await self._test_response(response, return400)
                return response
        else:
            raise NotImplementedError()

    async def _get_authentication_token(self) -> str:
        LOGGER.debug("Getting accessToken from Bambu Cloud")

        data = {
            "account": self._email,
            "password": self._password,
            "apiError": ""
        }

        response = await self._post(BambuUrl.LOGIN, json_data=data)
        auth_json = await response.json()
        
        accessToken = auth_json.get('accessToken', '')
        if accessToken != '':
            return accessToken
        
        loginType = auth_json.get("loginType", None)
        if loginType is None:
            LOGGER.error(f"loginType not present")
            LOGGER.error(f"Response not understood: '{await response.text()}'")
            return ValueError(0)
        elif loginType == 'verifyCode':
            LOGGER.debug(f"Received verifyCode response")
            raise CodeRequiredError()
        elif loginType == 'tfa':
            LOGGER.debug(f"Received tfa response")
            self._tfaKey = auth_json.get("tfaKey")
            raise TfaCodeRequiredError()
        else:
            LOGGER.debug(f"Did not understand json. loginType = '{loginType}'")
            LOGGER.error(f"Response not understood: '{await response.text()}'")
            return ValueError(1)

    async def _get_new_code(self):
        if '@' in self._email:
            await self._get_email_verification_code()
        else:
            await self._get_sms_verification_code()
    
    async def _get_email_verification_code(self):
        data = {
            "email": self._email,
            "type": "codeLogin"
        }

        LOGGER.debug("Requesting email verification code")
        await self._post(BambuUrl.EMAIL_CODE, json_data=data)
        LOGGER.debug("Verification code requested successfully.")

    async def _get_sms_verification_code(self):
        data = {
            "phone": self._email,
            "type": "codeLogin"
        }

        LOGGER.debug("Requesting SMS verification code")
        await self._post(BambuUrl.SMS_CODE, json_data=data)
        LOGGER.debug("Verification code requested successfully.")

    async def _get_authentication_token_with_verification_code(self, code) -> str:
        LOGGER.debug("Attempting to connect with provided verification code.")
        data = {
            "account": self._email,
            "code": code
        }

        response = await self._post(BambuUrl.LOGIN, json_data=data, return400=True)
        status_code = response.status

        if status_code == 200:
            LOGGER.debug("Authentication successful.")
            response_json = await response.json()
            LOGGER.debug(f"Response = '{response_json}'")
            return response_json['accessToken']
        elif status_code == 400:
            response_json = await response.json()
            LOGGER.debug(f"Received response: {response_json}")           
            if response_json['code'] == 1:
                await self._get_new_code()
                raise CodeExpiredError()
            elif response_json['code'] == 2:
                raise CodeIncorrectError()
            else:
                LOGGER.error(f"Response not understood: '{response_json}'")
                raise ValueError(response_json['code'])

    async def _get_authentication_token_with_2fa_code(self, code: str) -> str:
        LOGGER.debug("Attempting to connect with provided 2FA code.")

        data = {
            "tfaKey": self._tfaKey,
            "tfaCode": code
        }

        response = await self._post(BambuUrl.TFA_LOGIN, json_data=data)

        LOGGER.debug(f"Response: {response.status}")
        if response.status == 200:
            LOGGER.debug("Authentication successful.")

        cookies = response.cookies
        token_from_tfa = cookies.get("token")
        return token_from_tfa

    def _get_username_from_authentication_token(self) -> str:
        LOGGER.debug("Trying to get username from authentication token.")
        username = None
        tokens = self._auth_token.split(".")
        if len(tokens) != 3:
            LOGGER.debug("Received authToken is not a JWT.")
            return None

        LOGGER.debug("Authentication token looks to be a JWT")
        try:
            b64_string = self._auth_token.split(".")[1]
            b64_string += "=" * ((4 - len(b64_string) % 4) % 4)
            jsonAuthToken = json.loads(base64.b64decode(b64_string))
            username = jsonAuthToken.get('username', None)
        except:
            LOGGER.debug("Unable to decode authToken to json to retrieve username.")

        if username is None:
            LOGGER.debug(f"Unable to decode authToken to retrieve username. AuthToken = {self._auth_token}")

        return username

    async def test_authentication(self, region: str, email: str, username: str, auth_token: str) -> bool:
        self._region = region
        self._email = email
        self._username = username
        self._auth_token = auth_token
        try:
            await self.get_device_list()
        except:
            return False
        return True

    async def login(self, region: str, email: str, password: str) -> str:
        self._region = region
        self._email = email
        self._password = password

        result = await self._get_authentication_token()
        self._auth_token = result
        self._username = self._get_username_from_authentication_token()
        
    async def login_with_verification_code(self, code: str):
        result = await self._get_authentication_token_with_verification_code(code)
        self._auth_token = result
        self._username = self._get_username_from_authentication_token()

    async def login_with_2fa_code(self, code: str):
        result = await self._get_authentication_token_with_2fa_code(code)
        self._auth_token = result
        self._username = self._get_username_from_authentication_token()

    async def request_new_code(self):
        await self._get_new_code()

    async def get_device_list(self) -> dict:
        LOGGER.debug("Getting device list from Bambu Cloud")
        try:
            response = await self._get(BambuUrl.BIND)
            return (await response.json())['devices']
        except:
            return None

    async def get_slicer_settings(self) -> dict:
        LOGGER.debug("Getting slicer settings from Bambu Cloud")
        try:
            response = await self._get(BambuUrl.SLICER_SETTINGS)
            return await response.json()
        except:
            return None

    async def get_tasklist(self) -> dict:
        LOGGER.debug("Getting full task list from Bambu Cloud")
        try:
            response = await self._get(BambuUrl.TASKS)
            return await response.json()
        except:
            return None

    async def get_projects(self) -> dict:
        LOGGER.debug("Getting projects list from Bambu Cloud")
        try:
            response = await self._get(BambuUrl.PROJECTS)
            return await response.json()
        except:
            return None