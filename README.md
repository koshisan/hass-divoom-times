# Divoom Times — Home Assistant integration

Local control for newer Divoom devices: **Times Gate** and **Times Frame**.

Existing HA Divoom integrations target older Bluetooth-Classic Aurabox/Pixoo/Timebox hardware or the Pixoo 64 HTTP API. Times Gate and Times Frame ship a newer firmware that requires a per-device `DeviceToken` on every command — none of the existing projects handle it. This integration does.

## Status

- [x] LAN discovery via Divoom cloud (`Device/ReturnSameLANDevice`, no auth needed as long as HA sits on the same public IP as the devices)
- [x] Manual setup fallback with IP + `DeviceToken`
- [x] Divoom cloud sign-in path to auto-fetch `DeviceToken` per device
- [x] Light entity: on/off + brightness (Times Gate)
- [ ] Times Frame local protocol (device only exposes an unknown service on port 9000 + ADB on 5037 — needs sniffing)
- [ ] Channel select, notify/text/GIF platforms, sensors — planned

## Install

Via HACS as a custom repository (`https://github.com/koshisan/hass-divoom-times`, category "Integration"), then add via **Settings → Devices & Services → Add Integration → Divoom Times**.

## Configuration

Three entry points:

1. **Discover** — cloud LAN lookup, pick device, paste `DeviceToken`.
2. **Manual** — enter IP, port, DeviceId and DeviceToken by hand.
3. **Cloud** — Divoom account email + password; the flow fetches the DeviceToken from `/UserLogin` + `/Device/ReturnDeviceList` and stores only the resulting token, not the credentials.

## Getting a DeviceToken without an account

If you don't want to hand over Divoom credentials, capture the traffic between the Divoom app and `app.divoom-gz.com` (mitmproxy, Charles, etc.) and copy the `DeviceToken` field out of any signed request payload.

## License

MIT.
