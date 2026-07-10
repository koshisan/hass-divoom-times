# Divoom Times — Home Assistant integration

Local (and cloud-relay) control for newer Divoom devices: **Times Gate** and **Times Frame**.

## Why this exists

Existing HA Divoom integrations target Bluetooth-Classic Aurabox/Pixoo/Timebox or the Pixoo 64 local HTTP API. Neither handles the newer Times Gate / Times Frame firmware, which:

- Times Frame: local API lives at `GET http://<ip>:9000/divoom_api` with a JSON body — an unusual shape (GET + body) that stumps generic reverse-engineering tools.
- Times Gate (HW 400): local API at `POST http://<ip>:80/post` and requires a `LocalToken` field. The token is shown in the device's settings menu.
- Times Gate (HW 402): local API at `POST http://<ip>:9000/divoom_api`, also with `LocalToken`.

This integration knows all three shapes and picks the right one per device based on the hardware code returned by `Device/GetList`.

## Transports

| Hardware | Transport | Endpoint | Auth |
|---|---|---|---|
| Times Frame (510) | local | GET :9000/divoom_api | none |
| Times Gate HW 400 | local | POST :80/post | LocalToken |
| Times Gate HW 402 | local | POST :9000/divoom_api | LocalToken |
| fallback | cloud | POST app.divoom-gz.com/{Command} | account UserId + Token |

The cloud path is used when a local transport can't be reached or the user skips the LocalToken step.

## Status

- [x] Login via Divoom account (`/UserLogin`) — password md5'd before send, only the resulting `UserId` + `Token` are stored.
- [x] Device enumeration via `/Device/GetList`.
- [x] Local transport for Times Frame (no auth).
- [x] Local transport for Times Gate (LocalToken).
- [x] Cloud transport fallback.
- [x] Light entity: on/off + brightness.
- [x] Reauth flow.
- [ ] Channel select, notify/text/GIF, sensors.

## Install

Add as HACS custom repository: `https://github.com/koshisan/hass-divoom-times`, category "Integration". Then in HA: **Settings → Devices & Services → Add Integration → Divoom Times**.

## Configuration flow

1. Enter Divoom account email + password (used once to enumerate devices; only `UserId` + `Token` are stored).
2. Pick a device.
3. If it's a Times Gate, you'll be asked for the `LocalToken` from the device's settings menu. Leave blank to fall back to cloud-relay.
4. Repeat for the second device.

## License

MIT.
