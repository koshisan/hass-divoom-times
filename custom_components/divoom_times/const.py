from __future__ import annotations

from dataclasses import dataclass

DOMAIN = "divoom_times"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_USER_ID = "user_id"
CONF_TOKEN = "token"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_TYPE = "device_type"
CONF_HOST = "host"
CONF_MAC = "mac"
CONF_TRANSPORT = "transport"
CONF_LOCAL_TOKEN = "local_token"

TRANSPORT_LOCAL = "local"
TRANSPORT_CLOUD = "cloud"

DEFAULT_SCAN_INTERVAL_LOCAL = 30
DEFAULT_SCAN_INTERVAL_CLOUD = 60

CMD_SET_BRIGHTNESS = "Channel/SetBrightness"
CMD_ON_OFF_SCREEN = "Channel/OnOffScreen"
CMD_GET_INDEX = "Channel/GetIndex"
CMD_SET_INDEX = "Channel/SetIndex"
CMD_GET_ALL_CONF = "Channel/GetAllConf"

# Divoom "DeviceType" == Hardware code from ReturnSameLANDevice.
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
    needs_local_token: bool


# Local-transport profiles per hardware code, per the Divoom docs.
LOCAL_PROFILES: dict[int, LocalProfile] = {
    HW_TIMES_GATE_V1: LocalProfile(port=80, path="/post", method="POST", needs_local_token=True),
    HW_TIMES_GATE_V2: LocalProfile(port=9000, path="/divoom_api", method="POST", needs_local_token=True),
    HW_TIMES_FRAME:   LocalProfile(port=9000, path="/divoom_api", method="GET",  needs_local_token=False),
}
