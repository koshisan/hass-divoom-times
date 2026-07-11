from __future__ import annotations

from dataclasses import dataclass

DOMAIN = "divoom_times"

# Config entry keys
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

DEFAULT_SCAN_INTERVAL = 15

# Verified device commands (Times Gate + Times Frame).
CMD_SET_BRIGHTNESS = "Channel/SetBrightness"
CMD_ON_OFF_SCREEN = "Channel/OnOffScreen"
CMD_SET_INDEX = "Channel/SetIndex"
CMD_GET_ALL_CONF = "Channel/GetAllConf"
CMD_SEND_HTTP_TEXT = "Draw/SendHttpText"
CMD_TIMEZONE = "Sys/TimeZone"
CMD_LOG_AND_LAT = "Sys/LogAndLat"
CMD_GET_DEVICE_TIME = "Device/GetDeviceTime"

# Channel indices per Divoom docs.
CHANNEL_LABELS: dict[int, str] = {
    0: "Faces",
    1: "Cloud",
    2: "Visualizer",
    3: "Custom",
}
CHANNEL_LABEL_TO_INDEX: dict[str, int] = {v: k for k, v in CHANNEL_LABELS.items()}

HW_TIMES_GATE_V1 = 400
HW_TIMES_GATE_V2 = 402
HW_TIMES_FRAME = 510

HARDWARE_NAMES: dict[int, str] = {
    HW_TIMES_GATE_V1: "Times Gate",
    HW_TIMES_GATE_V2: "Times Gate",
    HW_TIMES_FRAME: "Times Frame",
}


@dataclass(slots=True, frozen=True)
class HttpProfile:
    port: int
    path: str
    method: str  # "GET" or "POST"


HTTP_PROFILES: dict[int, HttpProfile] = {
    HW_TIMES_GATE_V1: HttpProfile(port=80,   path="/post",       method="POST"),
    HW_TIMES_GATE_V2: HttpProfile(port=9000, path="/divoom_api", method="POST"),
    HW_TIMES_FRAME:   HttpProfile(port=9000, path="/divoom_api", method="GET"),
}

# Which hardware supports which write commands. Empty means we don't
# expose the platform for that device. Verified against real hardware
# 2026-07-10: Times Gate accepts all of these; Times Frame accepts
# brightness / on-off but ignores channel/text.
SUPPORTS_CHANNEL_SELECT: frozenset[int] = frozenset({HW_TIMES_GATE_V1, HW_TIMES_GATE_V2})
SUPPORTS_SEND_TEXT: frozenset[int] = frozenset({HW_TIMES_GATE_V1, HW_TIMES_GATE_V2})

SERVICE_SEND_TEXT = "send_text"
