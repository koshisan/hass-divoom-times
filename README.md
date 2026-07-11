# Divoom Times — Home Assistant integration

Local HTTP control for Divoom **Times Gate** and **Times Frame**.

## Why this exists

Existing HA Divoom integrations don't handle the Times Gate / Times Frame local API:

- **Times Gate (HW 400)**: `POST http://<ip>:80/post` with a `LocalToken` field.
- **Times Gate (HW 402)**: `POST http://<ip>:9000/divoom_api` with a `LocalToken` field.
- **Times Frame (HW 510)**: `GET http://<ip>:9000/divoom_api` with a JSON body — the GET-with-body shape stumps generic reverse-engineering.

The `LocalToken` is fetched once at setup from `appin.divoom-gz.com/Device/GetListV2` (not `app.divoom-gz.com/Device/GetList` — V1 omits the token). After that, all commands stay on your LAN.

## What's in the box

**Entities per device:**
- `light.<device>` — on/off + brightness (0-100 scaled to 0-255).
- `select.<device>_channel` — channel picker on Times Gate (Faces / Cloud / Visualizer / Custom).

**Service:**
- `divoom_times.send_text` — display a scrolling text on a Times Gate. Colour, speed, LCD index, and text slot are configurable.

State polls `Channel/GetAllConf` every 15 s and gives you `Brightness`, `LightSwitch`, `MirrorFlag`, `TemperatureMode`, `Time24Flag`, `DateFormat`.

## Install

Add as HACS custom repository: `https://github.com/koshisan/hass-divoom-times`, category "Integration". Then in HA: **Settings → Devices & Services → Add Integration → Divoom Times**.

## Configuration flow

1. Enter your Divoom account email + password (used once, then discarded).
2. Pick a device. Done. Repeat for the second one.

## Notes

- MQTT: v0.5–v0.6 shipped an MQTT transport (Times Gate publishes to `DivoomDevice` after `App/SetIp` registration). Rolled back in v0.7 — of the device's Get* commands only `Channel/GetOnOffScreen` echoes back; brightness and everything else still had to come from HTTP. Not worth the broker setup for the small delta.
- `WifiSingal` (sic — Divoom's typo): only exposed over MQTT heartbeats. Not surfaced in this version.

## License

MIT.
