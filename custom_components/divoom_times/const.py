from __future__ import annotations

from dataclasses import dataclass

DOMAIN = "divoom_times"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_USER_ID = "user_id"
CONF_CLOUD_TOKEN = "cloud_token"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_TYPE = "device_type"
CONF_HOST = "host"
CONF_MAC = "mac"
CONF_LOCAL_TOKEN = "local_token"

DEFAULT_SCAN_INTERVAL = 30

CMD_SET_BRIGHTNESS = "Channel/SetBrightness"
CMD_ON_OFF_SCREEN = "Channel/OnOffScreen"
CMD_GET_INDEX = "Channel/GetIndex"
CMD_SET_INDEX = "Channel/SetIndex"
CMD_GET_ALL_CONF = "Channel/GetAllConf"

# Divoom "DeviceType" == Hardware code.
HW_TIMES_GATE_V1 = 400
HW_TIMES_GATE_V2 = 402
HW_TIMES_FRAME = 510

HARDWARE_NAMES: dict[int, str] = {
    HW_TIMES_GATE_V1: "Times Gate",
    HW_TIMES_GATE_V2: "Times Gate",
    HW_TIMES_FRAME: "Times Frame",
}


@dataclass(slots=True, frozen=True)
class LocalProfile:
    port: int
    path: str
    method: str  # "GET" or "POST"


# Local-transport profile per hardware code.
LOCAL_PROFILES: dict[int, LocalProfile] = {
    HW_TIMES_GATE_V1: LocalProfile(port=80,   path="/post",        method="POST"),
    HW_TIMES_GATE_V2: LocalProfile(port=9000, path="/divoom_api",  method="POST"),
    HW_TIMES_FRAME:   LocalProfile(port=9000, path="/divoom_api",  method="GET"),
}
