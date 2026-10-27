# AirXPi

An operating-system image for the **Raspberry Pi 3B** that turns the board into an
AirPlay 2 receiver **and** a VPN exit gateway at the same time:

* **AirPlay 2 receiver** on the Linux kernel, with the cover art, track info and the
  playback settings drawn on the **HDMI output** (the same screen the TV shows).
* **VPN exit** for every client of the box: the tunnel is taken from
  `vpnexit` (IKEv2 / strongSwan) and shared to the LAN.
* **Internet uplink** from `eth0` **or** from a phone that shares its connection
  over USB (iPhone `ipheth`, Android `rndis`/`cdc_ether`).
* **LAN side**: `eth1` (USB Ethernet adapter) and the on-board Wi-Fi access point,
  both bridged into one subnet, both behind the same VPN.
* **One web panel** to see/switch the VPN location **and** change the wireless
  settings, plus the AirPlay controls.
* The **HDMI UI** shows the AirPlay view with the appliance settings right next to
  it - VPN, Wi-Fi, output device, sync delay.

```
   iPhone / Android                     ┌──────────────────── Raspberry Pi 3B ───────────────────┐
   USB tethering  ──┐                   │                                                        │
                    ├──► WAN (usb0) ───►│ axnetd ── nftables NAT ── vpnexit (IKEv2) ──► VPN exit │
   router / cable ──┘    (eth0)         │    │                                                   │
                                        │    └── br0 ──┬── eth1 (USB Ethernet)  ──► clients     │
   AirPlay sender ──► shairport-sync ──►│              └── wlan0 (hostapd AP)    ──► clients     │
        (HDMI audio out)                │                          │                             │
                                        │  axpanel :80   axplay :8090   vpnexit :8088  axnet :8079
                                        │  HDMI UI: now playing + settings (PyQt5 on :0)         │
                                        └────────────────────────────────────────────────────────┘
```

## What is inside

| Part | Source | Role |
|---|---|---|
| `axplay` | [`airxplay2`](https://github.com/haboshehry/airxplay2) (vendored) | supervises `shairport-sync`, reads AirPlay metadata/artwork, D-Bus volume |
| `vpnexit` | `vpnexit-openwrt/portable` (vendored) | downloads the daily IKEv2 feed, connects, steers LAN traffic, verifies the exit address |
| `axnetd` | this repo | uplink detection, `br0` bridge, hostapd AP, dnsmasq, nftables NAT, localhost API |
| `axpanel` | this repo | the single web panel (auth, AirPlay + VPN + Wi-Fi + system), port 80 |
| `axgui` | this repo | full-screen PyQt5 UI on HDMI: cover art, transport, volume, settings tabs |
| `image/` | this repo | pi-gen stage, `install.sh`, Docker/CI build |

`shairport-sync` **5.6 with `--with-airplay-2`** and `nqptp` are compiled during the
install - the Debian package is AirPlay 1 only and cannot join AirPlay 2 groups.

## Hardware

| Role | Port | Notes |
|---|---|---|
| Internet | `eth0` | built-in Ethernet |
| Internet (alt.) | `usb0` / `enx*` | iPhone USB tethering (`usbmuxd` + `ipheth`), Android (`rndis_host`) |
| LAN | `eth1` | USB Ethernet adapter (the Pi 3B has one NIC only) |
| LAN (Wi-Fi) | `wlan0` | on-board 2.4 GHz, hostapd AP, channels 1-13 |
| Audio + UI | HDMI | `vc4-kms-v3d`, HDMI audio PCM, 1080p UI |

Optional: USB keyboard/mouse for the on-screen settings (the UI also has a built-in
on-screen keyboard, so a mouse alone is enough).

## Install

### A. Flash the image

```bash
git clone https://github.com/haboshehry/airxpi.git
cd airxpi
sudo ./image/build-in-docker.sh      # produces dist/airxpi-*-rpi3b.img.xz
```

Write `dist/airxpi-*.img.xz` with Raspberry Pi Imager or `dd`, boot the Pi, and open
`http://10.42.0.1/` (or `http://airxpi.local/`). The panel password is on the boot
partition in `AIRXPI.txt` and in the console banner.

### B. On top of an existing Raspberry Pi OS Lite (Bookworm, 64-bit)

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/haboshehry/airxpi.git /tmp/airxpi
sudo sh /tmp/airxpi/image/install.sh
sudo reboot
```

The installer is idempotent and keeps `/etc/airxpi/airxpi.json`,
`/etc/vpnexit/config.json` and the panel password on re-runs.

## First boot

1. Plug the LAN side: USB Ethernet into `eth1`, or connect to the `AirXPi` Wi-Fi
   (password is in `/etc/airxpi/airxpi.json`, printed by the installer).
2. Plug the uplink: cable into `eth0`, or USB tethering from the phone
   (iPhone: *Personal Hotspot* + *Trust*; Android: *USB tethering*).
3. Open the panel: **Wi-Fi** tab to change SSID/password/channel/country,
   **VPN** tab to pick a location, **System** for the panel password and reboot.
4. On the TV: the AirPlay view shows the cover art; the right column has the
   AirPlay / VPN / Wi-Fi settings. Pick the device in the iPhone Control Center.

## Panel API

The panel is a thin, authenticated front-end over three local services. Scripts can
use the same endpoints with the panel's API token (`/etc/airxpi/panel.json`):

```bash
TOKEN=$(python3 -c 'import json;print(json.load(open("/etc/airxpi/panel.json"))["api_token"])')
curl -s -H "X-Auth-Token: $TOKEN" http://127.0.0.1/api/state | jq .
curl -s -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"key":"free-netherlands","index":0}' http://127.0.0.1/api/vpn/connect
curl -s -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"ssid":"Home","channel":6,"enabled":true}' http://127.0.0.1/api/net/wifi
```

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/state` | GET | AirPlay + VPN + network + system in one object |
| `/api/airplay/{config,volume,action}` | POST | receiver settings, volume, transport/test |
| `/api/airplay/artwork` | GET | current cover art |
| `/api/vpn/{locations,status,settings,connect,disconnect,refresh,selftest}` | GET/POST | exit switching |
| `/api/net/{state,wifi,wan,lan,device}` | GET/POST | wireless, uplink, LAN, device name/language |
| `/api/system` | GET | kernel, temperature, memory, disk, service states |
| `/api/system/{password,reboot}` | POST | credentials, reboot |

## CLI

```bash
axp-doctor            # one screen: services, audio, interfaces, VPN, AirPlay, recent errors
axp-audio list        # playback PCMs, HDMI marked
axp-audio hdmi        # select the HDMI PCM and route the mixer
axp-audio test        # 2 s tone on the selected output
axp-passwd            # new random panel password (also written to the boot partition)
vpnexit status        # tunnel state as JSON
vpnexit locations
vpnexit selftest      # verifies the exit address, not just the tunnel
```

## Security model

* The web panel is password protected (PBKDF2-SHA256, 12 h signed session cookie,
  optional `X-Auth-Token` for scripts). The API is reachable only through the panel;
  `8090`, `8088` and `8079` are dropped by nftables on every non-loopback interface.
* `vpnexit`'s own panel keeps its random token and is never exposed to the LAN.
* IPv6 is disabled: the tunnel carries IPv4 only, so IPv6 on the LAN would be a leak.
* The access point is WPA2-PSK (CCMP) and refuses to start without a valid passphrase.
* `vpnexit` traffic is excluded from the appliance SNAT rule, so marked packets keep
  the address the peer assigned.

## Status and known limits

* The image build is reproducible (`image/build.sh`, GitHub Actions); the code in
  this repository has been syntax-checked and reviewed, but **a full hardware run on
  a Pi 3B is still required** - after flashing, `axp-doctor` is the first thing to run.
* Raspberry Pi 3B Wi-Fi is **2.4 GHz only** (channels 1-13, 802.11n).
* One USB tether at a time; `eth0` always wins in `auto` mode.
* VPN profiles are IKEv2 only (that is what the `vpnexit` feed provides).
* AirPlay 2 group playback needs exactly one `shairport-sync` and one `nqptp`; the
  installer masks the distribution unit and `axplay` owns the process.

## Build details

See [docs/BUILD.md](docs/BUILD.md). Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Networking: [docs/NETWORK.md](docs/NETWORK.md). Panel: [docs/PANEL.md](docs/PANEL.md).
HDMI UI: [docs/GUI.md](docs/GUI.md). Troubleshooting: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## خلاصه فارسی

این مخزن یک سیستم‌عامل کامل برای رزبری‌پای ۳B می‌سازد: گیرنده AirPlay 2 روی کرنل لینوکس
با نمایش کاور آهنگ و تنظیمات روی خروجی HDMI، به‌همراه vpnexit که تونل VPN را از
اینترنت eth0 یا اشتراک USB آیفون/اندروید می‌گیرد و آن را روی eth1 و وای‌فای (hostapd)
به اشتراک می‌گذارد. یک پنل وب واحد (پورت ۸۰) هم وضعیت/انتخاب VPN و هم تنظیمات وایرلس و
AirPlay را مدیریت می‌کند؛ روی HDMI هم کنار صفحه پخش، تنظیمات AirPlay/VPN/Wi-Fi دیده
می‌شود. برای ساخت ایمیج: `sudo ./image/build-in-docker.sh` و سپس نوشتن فایل
`dist/airxpi-*.img.xz` روی کارت حافظه.

## License

MIT (see [LICENSE](LICENSE)). Vendored components keep their own licenses -
see [docs/THIRD_PARTY.md](docs/THIRD_PARTY.md).
