# VPN: the feed exit and your own profiles

The appliance has **two** VPN engines and they never run at the same time:

| Engine | Port | What it owns | Configuration |
|---|---|---|---|
| `vpnexit` | 8088 | the built-in IKEv2 **feed** (one provider, many locations) | `/etc/vpnexit/config.json` |
| `axtunnel` | 8086 (loopback) | **your** profiles: manual IKEv2, WireGuard, AmneziaWG, VLESS + REALITY, OpenVPN, L2TP/IPsec, SSTP | `/etc/airxpi/tunnels.json` |

Connecting anything in one engine disconnects the other. They also use different
marks/tables (`vpnexit`: `0x1a1` / 417, `axtunnel`: `0x1a2` / 418), so a stale
rule set from one can never capture the traffic of the other.

## Adding a profile in the panel

*VPN -> My VPN profiles -> New profile*, pick the protocol, fill the fields (or
paste a config file) and **Save**. The card then offers *Connect*; the state,
the tunnel address and the verified exit address appear on the same page.

Everything is stored in `/etc/airxpi/tunnels.json` (mode `0600`). Secrets are
never sent back to the browser: editing a profile shows `(stored)` next to a
secret field, and an empty field keeps the saved value. Uploaded files live in
`/etc/airxpi/tunnels/<id>.*`, also `0600`.

## Protocol matrix

| Protocol | Client | Needs | Notes |
|---|---|---|---|
| IKEv2 (manual) | strongSwan `swanctl` | `strongswan-swanctl` running | EAP-MSCHAPv2 (user + password) or PSK; optional CA PEM; server must accept `local_addrs = %any` |
| WireGuard | `wg-quick` | `wireguard-tools`, kernel module `wireguard` | fields **or** an uploaded `wg-quick` `.conf` |
| AmneziaWG | `awg-quick` | `amneziawg` kernel module + `amneziawg-tools` (not in Debian) | WireGuard fields plus `Jc/Jmin/Jmax/S1/S2/H1..H4` |
| VLESS + REALITY | `sing-box` | `sing-box` (installed by `install.sh` when GitHub is reachable) | TUN inbound `axtun0`, `flow = xtls-rprx-vision`, uTLS fingerprint |
| OpenVPN | `openvpn` | `openvpn` | fields **or** an uploaded `.ovpn` (inline certs work) |
| L2TP/IPsec | `xl2tpd` + strongSwan transport mode | `xl2tpd`, `ppp`, strongSwan | optional PSK; `pppd` uses `nodefaultroute` |
| SSTP | `sstpc` + `pppd` | `sstp-client`, `ppp` | `pppd` peer `axpi-sstp`, no default route |

If a client binary is missing the profile is still saved, and the panel shows
which package is missing instead of failing at connect time.

## What a connect actually does

1. Tear down any other engine's tunnel and the previous axtunnel profile.
2. Start the client with the options that keep the appliance's own traffic out
   of the tunnel:
   * WireGuard/AmneziaWG: `Table = off` (injected into uploaded configs too),
   * OpenVPN: `--route-nopull --pull-filter ignore redirect-gateway`,
   * L2TP/SSTP: `nodefaultroute`,
   * sing-box: TUN with `auto_route = false`.
3. Mark LAN traffic and route it through the tunnel:

```
prerouting  iifname br0  ip daddr !exclude  meta mark set 0x1a2
ip rule     fwmark 0x1a2 -> table 418
table 418   default dev <tunnel>            (or via the uplink, for IKEv2)
postrouting oifname <tunnel> meta mark 0x1a2 masquerade
            (IKEv2: oifname <wan> meta mark 0x1a2 snat ip to <assigned VIP>)
```

4. Verify the exit: `curl https://1.1.1.1/cdn-cgi/trace` with and without the
   mark. If both report the same address, the tunnel is up but the LAN is not
   using it, and the panel says so.

`exclude` contains loopback, multicast, the LAN subnet, the tunnel endpoints and
the address the peer assigned - the IKE/ESP or handshake packets must leave
through the uplink unmarked.

## Files

| Path | Content |
|---|---|
| `/etc/airxpi/tunnels.json` | profiles + settings (mode 0600) |
| `/etc/airxpi/tunnels/<id>.wg.conf` / `.awg.conf` | generated or uploaded WireGuard configs |
| `/etc/airxpi/tunnels/<id>.ovpn` | uploaded OpenVPN config |
| `/etc/airxpi/tunnels/<id>.singbox.json` | generated sing-box config (contains the UUID) |
| `/etc/swanctl/conf.d/axtunnel*.conf` | manual IKEv2 / L2TP connections |
| `/var/lib/airxpi/tunnel-state.json` | last state (survives restarts) |
| `/var/log/airxpi/tunnel.log` | what happened, including client stderr |

## CLI

```bash
python3 -m airxpi.axtunnel state
python3 -m airxpi.axtunnel connect <profile-id>
python3 -m airxpi.axtunnel disconnect
python3 -m airxpi.axtunnel selftest
python3 -m airxpi.axtunnel capabilities
```

## Limits

* One tunnel at a time. That is a hardware limit as much as a design choice:
  the Pi 3B encrypts on the same CPU that decodes AirPlay 2.
* `axtunnel` only shares the tunnel with the LAN; it does not turn the Pi into a
  VPN *server* for remote clients.
* L2TP and SSTP are available for compatibility, not for speed - both are
  measurably slower than WireGuard on this board.
* AmneziaWG needs a kernel module Debian does not ship; build
  `amneziawg-linux-kernel-module` for the running kernel first, otherwise the
  panel reports the protocol as unavailable.
* IPv6 stays disabled on the LAN (see `docs/NETWORK.md`); none of these
  adapters carries IPv6.

## خلاصه فارسی

دو موتور VPN وجود دارد: `vpnexit` برای فهرست موقعیت‌های آماده (IKEv2) و
`axtunnel` برای پروفایل‌های شخصی. در پنل، تب VPN → «پروفایل‌های شخصی من» می‌توانید
IKEv2 دستی، WireGuard، AmneziaWG، VLESS + REALITY، OpenVPN، L2TP/IPsec و SSTP را
با فیلدها یا با آپلود فایل تنظیم کنید. هر پروفایل پس از اتصال، به‌صورت خودکار با
همه کلاینت‌های وای‌فای و اترنت به اشتراک گذاشته می‌شود. هم‌زمان فقط یکی از دو موتور
فعال می‌شود و تنظیمات محرمانه در فایل با دسترسی 0600 ذخیره می‌شود.
