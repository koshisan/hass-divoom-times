from __future__ import annotations

DOMAIN = "divoom_times"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_USER_ID = "user_id"
CONF_TOKEN = "token"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_TYPE = "device_type"
CONF_MAC = "mac"

DEFAULT_SCAN_INTERVAL = 60

CMD_SET_BRIGHTNESS = "Channel/SetBrightness"
CMD_ON_OFF_SCREEN = "Channel/OnOffScreen"
CMD_GET_INDEX = "Channel/GetIndex"
CMD_SET_INDEX = "Channel/SetIndex"

# Divoom "DeviceType" (a.k.a. Hardware code in ReturnSameLANDevice)
HW_TIMES_GATE = 400
HW_TIMES_FRAME = 510

HARDWARE_NAMES: dict[int, str] = {
    HW_TIMES_GATE: "Times Gate",
    HW_TIMES_FRAME: "Times Frame",
}

ATTR_LAST_BRIGHTNESS = "last_brightness"
ATTR_IS_ON = "is_on"
