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
CONF_TRANSPORT = "transport"
CONF_BROKER_IP = "broker_ip"

TRANSPORT_MQTT = "mqtt"
TRANSPORT_HTTP = "http"

# Poll interval used only by the HTTP transport (MQTT is push-based)
DEFAULT_SCAN_INTERVAL = 30

# Device commands
CMD_SET_BRIGHTNESS = "Channel/SetBrightness"
CMD_ON_OFF_SCREEN = "Channel/OnOffScreen"
CMD_GET_INDEX = "Channel/GetIndex"
CMD_SET_INDEX = "Channel/SetIndex"
CMD_GET_ALL_CONF = "Channel/GetAllConf"
CMD_HEARTBEAT = "Device/Hearbeat"  # sic — Divoom's typo, verified on the wire
CMD_DISCONNECT_MQTT = "Device/DisconnectMqtt"
CMD_CONNECT_APP = "Device/ConnectApp"

# Divoom "DeviceType" == Hardware code from Device/GetListV2.
HW_TIMES_GATE_V1 = 400
HW_TIMES_GATE_V2 = 402
HW_TIMES_FRAME = 510

HARDWARE_NAMES: dict[int, str] = {
    HW_TIMES_GATE_V1: "Times Gate",
    HW_TIMES_GATE_V2: "Times Gate",
    HW_TIMES_FRAME: "Times Frame",
}

# Times Gate speaks MQTT; Times Frame is HTTP-only.
MQTT_CAPABLE: frozenset[int] = frozenset({HW_TIMES_GATE_V1, HW_TIMES_GATE_V2})


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

# MQTT topics
MQTT_TOPIC_APP = "DivoomApp"
MQTT_TOPIC_DEVICE = "DivoomDevice"
MQTT_TOPIC_LWT = "DivoomAppLwt"

DEFAULT_BROKER_IP = ""  # user must supply in the flow
