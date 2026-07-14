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
CMD_GET_ON_OFF_SCREEN = "Channel/GetOnOffScreen"
CMD_SET_INDEX = "Channel/SetIndex"
CMD_GET_ALL_CONF = "Channel/GetAllConf"
CMD_SET_RGB_INFO = "Channel/SetRGBInfo"
CMD_GET_RGB_INFO = "Channel/GetRGBInfo"
CMD_SET_AMBIENT_LIGHT = "Channel/SetAmbientLight"
CMD_GET_AMBIENT_LIGHT = "Channel/GetAmbientLight"
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
# Times Gate exposes an ambient RGB via Channel/SetRGBInfo (5 LEDs on the
# back). Times Frame exposes its side RGB via Channel/SetAmbientLight
# with a different param shape (EqOnOff, SelectEffect).
SUPPORTS_RGB_INFO: frozenset[int] = frozenset({HW_TIMES_GATE_V1, HW_TIMES_GATE_V2})
SUPPORTS_AMBIENT_LIGHT: frozenset[int] = frozenset({HW_TIMES_FRAME})

# Gate LightIndex enum, per the usausa/divoom-tool reverse engineering.
GATE_LIGHT_INDEX_ALL = 0
GATE_LIGHT_INDEX_EDGE = 1        # Surround-Licht
GATE_LIGHT_INDEX_BACKLIGHT = 2   # 5 back LEDs

GATE_LIGHT_ZONES: dict[int, tuple[str, str]] = {
    GATE_LIGHT_INDEX_ALL:       ("all",       "All lights"),
    GATE_LIGHT_INDEX_EDGE:      ("surround",  "Surround"),
    GATE_LIGHT_INDEX_BACKLIGHT: ("backlight", "Backlight"),
}

# Static effect ID inside a LightList entry. Confirmed on Times Gate 2026-07-15:
# `LightList: [{SelectEffect: 5}, {SelectEffect: 5}, {SelectEffect: 5}]`
# with SelectLightIndex=<zone> + ColorCycle=0 gives a solid colour on the
# targeted zone. LightList with 5 entries hard-times-out the device
# (verified crash) — three entries stay stable.
GATE_EFFECT_STATIC = 5
GATE_LIGHTLIST_STATIC = [{"SelectEffect": GATE_EFFECT_STATIC}] * 3

# Times Frame "Lichteffekt" grid — 8 modes ordered as they appear in the
# Divoom app. Only index 7 (Static) has been user-confirmed; the rest are
# labelled from icon shapes and can be corrected on the fly by renaming
# the select option entries.
FRAME_EFFECT_LABELS: dict[int, str] = {
    0: "Audio Bars",
    1: "Meteor",
    2: "Pixel Rain",
    3: "Sparkle",
    4: "Wind",
    5: "Chat",
    6: "Pulse",
    7: "Static",
}
FRAME_EFFECT_LABEL_TO_INDEX: dict[str, int] = {v: k for k, v in FRAME_EFFECT_LABELS.items()}

# Hardware families whose GetAllConf actually returns brightness/state.
# Times Frame answers GetAllConf with an empty ack — for it we have to
# poll GetOnOffScreen and track Brightness optimistically off Set-echoes.
GETALLCONF_HAS_STATE: frozenset[int] = frozenset({HW_TIMES_GATE_V1, HW_TIMES_GATE_V2})

SERVICE_SEND_TEXT = "send_text"
