# Architecture

## Boot chain

```
firmware (start4/start.elf) → Linux kernel (Debian bookworm arm64, RPi kernel)
  → systemd multi-user.target
      ├─ dhcpcd            WAN lease on eth0 / usb0 (never on br0/eth1/wlan0)
      ├─ axnet             apply network plan, then serve the localhost API :8079
      ├─ nqptp             AirPlay 2 PTP timing daemon (one instance, shared memory)
      ├─ avahi-daemon      mDNS/DNS-SD advertisement (br0 + uplink)
      ├─ axplay            vendored airxplay2: supervises shairport-sync, :8090
      ├─ vpnexit-supervisor  tunnel watchdog + daily profile refresh
      ├─ vpnexit-web        vpnexit JSON API :8088 (token)
      ├─ axpanel           the single web panel :80 (auth + proxy + Wi-Fi)
      └─ axgui             xinit :0 → PyQt5 full-screen UI on tty1/HDMI
```

`shairport-sync` is **not** a systemd unit of its own: `axplay` starts and supervises
it (that is how the upstream panel is built, and it guarantees a single instance -
two `shairport-sync` or two `nqptp` processes break AirPlay 2 groups). The
distribution unit is masked by the installer.

## Components

| Process | Port | Listener | Auth | Responsibility |
|---|---|---|---|---|
| `axpanel` | 80 | LAN + uplink | password / token | the only user-facing HTTP surface |
| `axplay` (airxplay2) | 8090 | loopback | none | shairport-sync supervision, metadata, D-Bus volume |
| `vpnexit-web` | 8088 | all | `X-Auth-Token` | IKEv2 connect/disconnect, feed, selftest |
| `axnetd` | 8079 | loopback | none | uplink, bridge, AP, NAT, clients |

`axpanel` is the only port reachable from the LAN. nftables drops `8079`, `8088`
and `8090` on every interface except `lo`, so a compromised LAN client cannot talk
to the engine APIs directly - only through the authenticated panel.

## Audio / metadata path

```
iPhone ──RTSP/RTP──► shairport-sync ──ALSA──► plughw:CARD=vc4hdmi,DEV=0 ──► HDMI (TV)
                           │
                           ├─ metadata pipe ──► axplay ──► /data/artwork.bin
                           └─ D-Bus ─────────► axplay (volume, transport)
```

* `axplay` writes `/etc/shairport-sync.conf` and pins the **output** side to
  48 kHz/S16/stereo so a group join never renegotiates HDMI while the display holds
  the PCM, without restricting the input (44.1 kHz is resampled internally).
* Cover art and track info are served to both front-ends:
  `GET :8090/api/artwork` (bytes) and `now_playing` in `:8090/api/state`.
* The HDMI UI polls `axpanel:/api/state` every 1.5 s; it never talks to
  `shairport-sync` directly.

## Network data path

```
client (br0) ──► nftables prerouting ──┬─ mark 0x1a1 (vpnexit) ──► ip rule table 417 ──► ESP to peer
                                       └─ unmarked ──────────────► default route (uplink)
                     postrouting: vpnexit SNATs marked packets to the peer's address;
                                  axnetd masquerades the rest to the uplink address
```

Details and the exact ruleset: [NETWORK.md](NETWORK.md).

## Files

| Path | Owner | Purpose |
|---|---|---|
| `/etc/airxpi/airxpi.json` | axnetd | appliance configuration (WAN mode, LAN, Wi-Fi, device) |
| `/etc/airxpi/panel.json` | axpanel | password hash, session secret, API token, language |
| `/etc/vpnexit/config.json` | vpnexit | feed URL, token, `lan_iface=br0`, routing knobs |
| `/etc/hostapd/hostapd.conf` | axnetd | generated AP config (mode 0600, holds the PSK) |
| `/etc/dnsmasq.d/airxpi.conf` | axnetd | DHCP/DNS for `br0` |
| `/etc/avahi/avahi-daemon.conf` | axnetd | advertisement scope (br0 + uplink) |
| `/var/lib/airxpi/airplay2/` | axplay | shairport config, log, artwork, metadata trace |
| `/opt/airxpi/lib/airxpi/` | installer | `axnetd`, `axpanel`, `gui` |
| `/opt/airxpi/airplay2/`, `/app` | installer | vendored airxplay2 (`/app` is a symlink) |
| `/opt/airxpi/vpnexit/` | installer | vendored vpnexit engine |
| `/var/lib/misc/dnsmasq.leases` | dnsmasq | client names shown in the panel |
| `/boot/firmware/AIRXPI.txt` | installer | first-boot panel password |

## Design decisions

* **One panel, three engines.** The user asked for VPN + wireless in one place;
  proxying keeps each engine's tested logic untouched and gives one password.
* **`br0` instead of two subnets.** Wireless and wire clients share `10.42.0.0/24`,
  so `vpnexit`'s single `lan_iface` mark covers both. `br0` is created by `axnetd`
  with multicast snooping **off** - mDNS (AirPlay discovery) must be flooded.
* **Mark-based VPN routing.** The tunnel does not replace the default route; only
  LAN-originated, marked packets take table 417. The box keeps its own uplink for
  updates and the AirPlay control channel.
* **No IPv6.** The feed is IKEv2/IPv4; leaving IPv6 on the LAN would leak around it.
* **Standard library Python.** Only the GUI needs a dependency (PyQt5), which keeps
  the appliance resilient to broken package upgrades.
