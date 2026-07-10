# Divoom Times — Home Assistant integration

Fully local control for Divoom **Times Gate** and **Times Frame** — no ongoing cloud dependency, no MQTT broker required.

## Why this exists

Existing HA Divoom integrations target Bluetooth-Classic hardware (Aurabox, Pixoo, Timebox) or the Pixoo 64 local HTTP API. None handle Times Gate / Times Frame, whose firmware:

- Times Gate (HW 400): `POST http://<ip>:80/post` with a `LocalToken` field.
- Times Gate (HW 402): `POST http://<ip>:9000/divoom_api` with a `LocalToken` field.
- Times Frame (HW 510): `GET http://<ip>:9000/divoom_api` with a JSON body — unusual shape (GET with body) that stumps generic reverse-engineering.

The `LocalToken` isn't shown in a device menu — the app fetches it from the Divoom cloud at `appin.divoom-gz.com/Device/GetListV2` (not `app.divoom-gz.com/Device/GetList`, which is a V1 endpoint that omits the token). This integration does that fetch once at setup, stores the token, and from then on only talks to the device on your LAN.

## Status

- [x] One-shot cloud login → per-device LocalToken via `Device/GetListV2`.
- [x] Local HTTP transport per hardware profile.
- [x] Light entity: on/off + brightness with real read-back (`Channel/GetAllConf`).
- [x] Reauth flow refreshes both the cloud token and the LocalToken.
- [ ] Channel/face select, notify (`Draw/SendHttpText`, `Draw/SendHttpGif`), sensors.
- [ ] MQTT transport (Times Gate also speaks MQTT via `App/SetIp` + local broker — deferred).

## Install

Add as HACS custom repository: `https://github.com/koshisan/hass-divoom-times`, category "Integration". Then in HA: **Settings → Devices & Services → Add Integration → Divoom Times**.

## Configuration flow

1. Enter your Divoom account email + password (used once, then discarded).
2. Pick a device — the LocalToken is already fetched at this point.
3. Done. Repeat for the second device.

## License

MIT.
