# Web panel

`http://192.168.168.1/` (or `http://airxpi.local/`) - one page, no build step, English
and Persian (the toggle is in the header; Persian switches the layout to RTL).

## Authentication

* Login: user `admin`, default password `admin` (also in
  `/boot/firmware/AIRXPI.txt`). PBKDF2-SHA256, 200 000 rounds, stored in
  `/etc/airxpi/panel.json`. Change it in *System -> Panel password* or with
  `axp-passwd`; the panel warns while the default is still active.
* The panel is reachable from the LAN side only (`panel.wan_access = false` by
  default): `eth1` and the Wi-Fi AP. Set it to `true` if you also want it over the
  uplink network.
* Session: HMAC-signed cookie `axpi`, 12 hours, `HttpOnly`, `SameSite=Lax`.
* Scripts: `X-Auth-Token: <api_token>` from `/etc/airxpi/panel.json` (constant-time
  compare). Loopback requests are trusted so the HDMI UI needs no credentials.
* A failed login sleeps 0.6 s to slow down brute force. The panel is LAN-only by default; `panel.wan_access = true` in
  `/etc/airxpi/airxpi.json` lets `axnetd` serve it on the uplink interface as well.

## Screens

| Tab | What it does |
|---|---|
| **Dashboard** | cover art, title/artist/album, transport, volume, VPN/AP/uplink cards, client table |
| **AirPlay** | name, output PCM (HDMI marked ✓), sync delay, optional password, test tone, restart, service state and log |
| **VPN** | current state and exit address, searchable location list, connect/disconnect, *Verify exit*, tunnel settings (share LAN / block IPv6 / auto reconnect) |
| **Wi-Fi** | SSID, passphrase, channel 1-13, regulatory country, max clients, hidden SSID, on/off - plus live AP state and LAN addressing |
| **Network** | uplink mode (auto / eth0 / USB tethering), active uplink, detected interfaces, addressing |
| **System** | model, kernel, uptime, temperature, memory, storage, service states, panel password, device name, reboot |

## How it maps to the engines

```
browser ──password──► axpanel :80 ──┬── :8090  airxplay2   (AirPlay)
                                    ├── :8088  vpnexit     (X-Auth-Token, injected server side)
                                    └── :8079  axnetd      (wireless, uplink, clients)
```

The panel never re-implements engine logic: it validates what it can (SSID length,
WPA passphrase rules, channel range, `/24` addresses), then calls the owning service
and returns its error text to the UI. That is why one panel can drive three
independent daemons without drifting.

## Adding a field

1. `src/airxpi/common.py` → `DEFAULTS` (config shape and defaults).
2. `src/airxpi/axnetd.py` → validate in `set_*`, use it in `write_hostapd` /
   `write_dnsmasq` / `apply`.
3. `src/airxpi/axpanel.py` → nothing, if you reuse `/api/net/wifi`;
   add a route only for a new engine.
4. `src/airxpi/web/index.html` + `app.js` → input, `data-i18n` key in both
   languages, include it in the POST body.
5. `src/airxpi/gui/app.py` → mirror it in `TEXT` and the matching page if it belongs
   on the TV.

## i18n

Every visible string is a `data-i18n` key resolved by `I18N[lang]` in `app.js`;
`set_language` also persists the choice (`/api/net/device`) so the HDMI UI follows.
Persian text needs `fonts-noto-core` (installed) and the UI switches `dir="rtl"`.

## Security notes

* Only `:80` is reachable from the LAN; `8079`, `8088` and `8090` are dropped by
  nftables on non-loopback interfaces.
* The panel runs as root because it configures hostapd/dnsmasq through `axnetd` and
  reads the vpnexit token. It never executes a shell with user input: all engine
  calls are JSON over loopback, and `axnetd` writes config files from validated
  values.
* The vpnexit token is read server-side and never sent to the browser.
