# Networking

## Interface plan

| Interface | Role | Address | Managed by |
|---|---|---|---|
| `eth0` | uplink (cable) | DHCP | dhcpcd |
| `usb0`, `enx*` | uplink (phone tethering) | DHCP (172.20.10.x / 192.168.42.x) | dhcpcd |
| `eth1` | LAN, wired clients | bridge member | axnetd |
| `wlan0` | LAN, Wi-Fi AP | bridge member (hostapd `bridge=br0`) | axnetd + hostapd |
| `br0` | LAN | `10.42.0.1/24` | axnetd |

`/etc/dhcpcd.conf` contains an axnetd-owned block:

```
denyinterfaces br0 eth1 wlan0
allowinterfaces eth0 usb0 enx* usb* ...
```

so dhcpcd can never put a lease on the LAN side.

## Uplink selection

`wan.mode` in `/etc/airxpi/airxpi.json`:

* `auto` (default) - `eth0` if its carrier is up, otherwise the first USB tether.
* `eth0` - cable only.
* `usb` - USB tethering only (useful when both are plugged in).

USB tethering needs `usbmuxd` (iPhone pairing - accept *Trust This Computer*) and
one of `ipheth`, `rndis_host`, `cdc_ether`; all four are listed in
`/etc/modules-load.d/airxpi-usb.conf`. A udev rule restarts `axnet-apply.service`
when `usb*`, `enx*` or `eth1` appears, so plugging the phone in re-runs the plan.

## Access point

`/etc/hostapd/hostapd.conf` is generated from the JSON config:

| Key | Value |
|---|---|
| `interface` / `bridge` | `wlan0` / `br0` |
| `hw_mode` / `channel` | `g` / 1-13 (2.4 GHz only on a Pi 3B) |
| `ieee80211n` | 1 |
| `wpa` / `wpa_key_mgmt` / `rsn_pairwise` | 2 / WPA-PSK / CCMP |
| `country_code` | optional, also applied with `iw reg set` |
| `max_num_sta` | 1-64 |
| `ignore_broadcast_ssid` | hidden network |

The AP refuses to start without a passphrase of at least 8 characters. Applying a
change restarts hostapd (clients reconnect in a few seconds).

## DHCP / DNS

`/etc/dnsmasq.d/airxpi.conf`:

```
interface=br0
bind-dynamic
dhcp-range=10.42.0.10,10.42.0.200,255.255.255.0,12h
dhcp-option=option:router,10.42.0.1
dhcp-option=option:dns-server,10.42.0.1
except-interface=eth0
except-interface=usb0
```

`systemd-resolved` is masked so port 53 belongs to dnsmasq; `/etc/resolv.conf` is a
plain file that dhcpcd rewrites with the uplink resolvers, and dnsmasq forwards to it.

## Firewall and NAT

`axnetd` owns two nftables tables (the file it applies is
`/var/lib/airxpi/run/airxpi.nft`):

```
table inet airxpi {
    chain input {
        type filter hook input priority filter; policy accept;
        iifname != "lo" tcp dport { 8079, 8088, 8090 } drop
    }
    chain forward {
        type filter hook forward priority filter; policy accept;
        ct state established,related accept
        iifname "br0" accept
    }
}
table ip airxpi_nat {
    chain postrouting {
        type nat hook postrouting priority srcnat; policy accept;
        oifname != "br0" ip saddr 10.42.0.0/24 meta mark != 0x1a1 masquerade
    }
}
```

The `meta mark != 0x1a1` guard is what keeps the two NAT owners apart: marked
packets belong to `vpnexit`, which SNATs them to the address the peer assigned.

## VPN

`vpnexit` runs with `lan_iface = br0`, `mark = 0x1a1`, `table = 417`, and its own
nginx-free design:

```
prerouting (mangle):  iifname br0  →  meta mark set 0x1a1
ip rule:              fwmark 0x1a1 →  table 417
table 417:            default via <uplink gateway> dev <uplink>   (so ESP leaves the uplink)
postrouting:          oifname <uplink> meta mark 0x1a1 → snat to <assigned VIP>
```

Because packets from bridged clients enter the local IP stack with `iifname br0`,
one rule covers `eth1` **and** `wlan0`. `charon` runs with `install_routes = no`
and `install_virtual_ip = no` (`/etc/strongswan.d/vpnexit.conf`).

What stays outside the tunnel: the box's own traffic that is not LAN-forwarded, the
IKE/ESP packets themselves, and the destinations in `vpnexit`'s exclude set
(private LAN, the peer address, multicast).

## IPv6

`net.ipv6.conf.all.disable_ipv6=1` in `/etc/sysctl.d/90-airxpi.conf`. The feed is
IPv4-only IKEv2, so an IPv6-capable LAN would silently bypass the exit.

## MTU

The tunnel uses 1400 bytes and `vpnexit` clamps MSS to `mtu - 80` for marked TCP
SYNs. For the untunnelled path `net.ipv4.tcp_mtu_probing=1` covers PPPoE-style
uplinks. USB tethering (especially iPhone) sometimes needs `tunnel_mtu` lowered to
1360 from the vpnexit settings API if large downloads stall.
