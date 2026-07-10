from __future__ import annotations

DOMAIN = "divoom_times"

CONF_HOST = "host"
CONF_DEVICE_TOKEN = "device_token"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_MAC = "mac"
CONF_HARDWARE = "hardware"
CONF_PORT = "port"

DEFAULT_PORT = 80
DEFAULT_SCAN_INTERVAL = 30

DIVOOM_CLOUD_BASE = "https://app.divoom-gz.com"
CLOUD_ENDPOINT_LAN_DEVICES = "/Device/ReturnSameLANDevice"
CLOUD_ENDPOINT_USER_LOGIN = "/UserLogin"
CLOUD_ENDPOINT_DEVICE_LIST = "/Device/ReturnDeviceList"

DEVICE_ENDPOINT_POST = "/post"

CMD_GET_INDEX = "Channel/GetIndex"
CMD_SET_INDEX = "Channel/SetIndex"
CMD_SET_BRIGHTNESS = "Channel/SetBrightness"
CMD_GET_ALL_CONF = "Channel/GetAllConf"
CMD_GET_DEVICE_TIME = "Device/GetDeviceTime"
CMD_ON_OFF_SCREEN = "Channel/OnOffScreen"

HW_TIMES_GATE = 400
HW_TIMES_FRAME = 510

HARDWARE_NAMES: dict[int, str] = {
    HW_TIMES_GATE: "Times Gate",
    HW_TIMES_FRAME: "Times Frame",
}
