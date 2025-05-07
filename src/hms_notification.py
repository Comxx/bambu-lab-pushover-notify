from dataclasses import dataclass
from typing import Dict, Optional, Union

HMS_ERRORS: Dict[str, str] = {}  # Will be filled from fetch_english_errors()
HMS_MODULES: Dict[Union[int, str], str] = {}  # You may already have this loaded somewhere

HMS_SEVERITY_LEVELS: Dict[Union[int, str], str] = {
    "default": "unknown",
    1: "fatal",
    2: "serious",
    3: "common",
    4: "info"
}

def get_HMS_severity(code: int) -> str:
    uint_code = code >> 16
    return HMS_SEVERITY_LEVELS.get(uint_code, HMS_SEVERITY_LEVELS["default"])

def get_HMS_module(attr: int) -> str:
    uint_attr = (attr >> 24) & 0xFF
    return HMS_MODULES.get(uint_attr, HMS_MODULES["default"])

async def get_HMS_error_text(code: str, language: str) -> str:
    if HMS_ERRORS == {}:
        HMS_ERRORS.update(await fetch_english_errors() or {})
    code = code.replace("_", "")
    return HMS_ERRORS.get(code, "unknown")

@dataclass
class HMSNotification:
    attr: int
    code: int
    _user_language: str

    def __init__(self, user_language: str, attr: int, code: int) -> None:
        self._user_language = user_language
        self.attr = attr
        self.code = code

    @property
    def severity(self) -> str:
        return get_HMS_severity(self.code)

    @property
    def module(self) -> str:
        return get_HMS_module(self.attr)

    @property
    def hms_code(self) -> str:
        if self.attr > 0 and self.code > 0:
            return f'{int(self.attr / 0x10000):0>4X}_{self.attr & 0xFFFF:0>4X}_{int(self.code / 0x10000):0>4X}_{self.code & 0xFFFF:0>4X}'
        return ""

    @property
    async def hms_error(self) -> str:
        return await get_HMS_error_text(self.hms_code, self._user_language)

    @property
    def wiki_url(self) -> str:
        if self.attr > 0 and self.code > 0:
            return f"https://wiki.bambulab.com/en/x1/troubleshooting/hmscode/{self.hms_code}"
        return ""
