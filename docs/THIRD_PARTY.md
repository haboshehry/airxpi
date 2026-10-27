# Third-party components

## Vendored source (copied into this repository)

| Folder | Upstream | Notes |
|---|---|---|
| `vendor/airplay2/` | `airxplay2` (`app/main.py`, `app/static/index.html`) | The AirPlay 2 receiver panel: shairport-sync supervisor, metadata/artwork reader, D-Bus volume, ALSA discovery. Copied verbatim; it expects `/app` and `/data`, which the installer provides as symlinks. MIT. |
| `vendor/vpnexit/` | `vpnexit-openwrt/portable/` (`vpnexit.py`, `web/`) | IKEv2 exit switcher: feed download, swanctl connection, nftables policy routing, watchdog. Copied verbatim; only `/etc/vpnexit/config.json` differs (`lan_iface=br0`). |

They are vendored rather than installed as packages so that the image is
self-contained and a single `git clone` is enough to build. To update them, replace
the folder contents from upstream and re-run `image/install.sh`.

## Packages installed on the image

| Component | License | Why |
|---|---|---|
| Raspberry Pi OS Lite (Debian bookworm) | mixed free licences | base system, RPi kernel |
| shairport-sync 5.6 | GPL (see upstream) | AirPlay 2 audio receiver, built from source with `--with-airplay-2` |
| nqptp | GPL (see upstream) | AirPlay 2 PTP timing, built from source |
| Avahi | LGPL | mDNS/DNS-SD advertisement |
| hostapd / dnsmasq | BSD / GPL | access point, DHCP + DNS |
| strongSwan (+ swanctl) | GPLv2 | IKEv2 client used by vpnexit |
| nftables | GPLv2 | routing marks, NAT, input filter |
| PyQt5 | **GPLv3** or commercial | HDMI user interface |
| Qt 5 | LGPLv3 / GPLv3 | PyQt5 runtime |
| Xorg, xinit | MIT | display server for the kiosk UI |
| Noto, DejaVu fonts | OFL / Bitstream Vera | Persian and Latin text |

### Licence consequence of PyQt5

PyQt5 is GPLv3. Distributing a combined image that includes it means the whole
distribution must satisfy the GPLv3 (source availability, same-licence
redistribution). This repository is MIT for its own code, which is compatible with
that, but the **image** is effectively GPLv3 because of PyQt5/Qt.

If an MIT-only distribution is required, replace the UI layer with GTK 3 through
`python3-gi` (LGPL) - `axgui` only uses labels, buttons, line edits, lists and a
custom-painted background, so the port is mechanical. The web panel is unaffected
(vanilla JS, no framework).
