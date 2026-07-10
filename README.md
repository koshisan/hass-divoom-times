# Divoom Times — Home Assistant integration

Real-time MQTT control for **Times Gate**, local HTTP for **Times Frame**.

## Why this exists

Existing HA Divoom integrations target Bluetooth-Classic hardware (Aurabox, Pixoo, Timebox) or the Pixoo 64 local HTTP API. None handle Times Gate / Times Frame, whose firmware has moved on:

- **Times Gate** speaks **MQTT** natively. Once the Divoom cloud has been told (via `App/SetIp`) where to find your broker, the device connects to it directly and publishes heartbeats to topic `DivoomDevice`. Commands go over topic `DivoomApp`. Auth is the account's `UserId` + cloud `Token`.
- **Times Frame** is HTTP-only. `GET http://<ip>:9000/divoom_api` with a JSON body — an unusual shape (GET with body) that stumps generic reverse-engineering.
- Both devices need a per-device `LocalToken` for HTTP; that token is fetched from `appin.divoom-gz.com/Device/GetListV2` (not `app.divoom-gz.com/Device/GetList` which is the V1 endpoint that omits the token).

## Transports at a glance

| Hardware | Transport | Endpoint | Auth in payload |
|---|---|---|---|
| Times Gate (HW 400) | MQTT (default) | topic `DivoomApp` | `UserId`, cloud `Token`, `DeviceId` |
| Times Gate (HW 400) | HTTP (fallback) | POST :80/post | `LocalToken` |
| Times Gate (HW 402) | HTTP | POST :9000/divoom_api | `LocalToken` |
| Times Frame (HW 510) | HTTP | GET :9000/divoom_api | `LocalToken` (tolerated) |

MQTT is push-based — brightness, `LightSwitch`, and `WifiSingal` (sic — Divoom's typo) arrive from the device on every heartbeat and on every state change made from any other client (app, physical button, another integration). HTTP polls `Channel/GetAllConf` every 30 s.

## Entities

- `light.<device>` — on/off + brightness.
- `binary_sensor.<device>_online` — connectivity based on heartbeat + Last-Will (MQTT devices only).
- `sensor.<device>_wifi_signal` — RSSI in dBm (MQTT devices only).

## Install

Add as HACS custom repository: `https://github.com/koshisan/hass-divoom-times`, category "Integration". Requires the HA **MQTT integration** to be configured pointing at your broker before adding a Times Gate. Then in HA: **Settings → Devices & Services → Add Integration → Divoom Times**.

## Configuration flow

1. Enter your Divoom account email + password (used once, then discarded).
2. Pick a device.
3. For Times Gate: enter the LAN IP of your MQTT broker. I'll register it with Divoom's cloud via `App/SetIp`; the device connects on its next poll.
4. For Times Frame: nothing more, it's an HTTP entry.

Repeat for the second device.

## License

MIT.
