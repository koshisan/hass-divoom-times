# Divoom Times — Home Assistant integration

Cloud-relayed control for newer Divoom devices: **Times Gate** and **Times Frame**.

## Why this exists

Existing HA Divoom integrations target Bluetooth-Classic Aurabox/Pixoo/Timebox hardware or the Pixoo 64 local HTTP API. Times Gate and Times Frame ship a firmware that requires a per-device `DeviceToken` on every local `/post` request — and that token isn't handed out via any public API.

The workaround: Divoom's cloud accepts the same command names at `https://app.divoom-gz.com/<Command>` when authenticated with the account's `UserId` + login `Token`. The cloud then relays the command to the device. This integration uses that path.

## Status

- [x] Login via Divoom account (`/UserLogin`) — password is md5'd before sending, only the resulting `UserId` + `Token` are stored.
- [x] Device enumeration via `/Device/GetList` — populates a picker in the config flow.
- [x] Light entity: on/off (`Channel/OnOffScreen`) + brightness (`Channel/SetBrightness`).
- [x] Reauth flow when the stored token is refused.
- [ ] Channel select, notify/text/GIF, sensors — planned.
- [ ] Local mode with a sniffed `DeviceToken` for offline use — optional future path.

## Install

Add as HACS custom repository: `https://github.com/koshisan/hass-divoom-times`, category "Integration". Then in HA: **Settings → Devices & Services → Add Integration → Divoom Times**.

## Configuration

Enter your Divoom account email and password. The flow signs in, lists your bound devices, and lets you pick one to add. Each Divoom device becomes its own config entry — repeat the flow for the second one.

## Latency

Every command hits `app.divoom-gz.com` first. Expect a few hundred milliseconds per command. Fine for automations like "dim when the room is empty," not great for real-time visualisation.

## License

MIT.
