# Troubleshooting

Start with `axp-doctor` - it prints the model, services, ALSA devices, interfaces,
uplink, VPN state, AirPlay state and the last warnings in one screen.

## AirPlay

| Symptom | Cause / fix |
|---|---|
| Not visible on the iPhone | `axnetd` must advertise on the interface the phone is on. Check `allow-interfaces` in `/etc/avahi/avahi-daemon.conf` (br0 + uplink), then `systemctl restart avahi-daemon axplay`. |
| Visible but silent | Wrong ALSA PCM. `axp-audio list` marks the HDMI one; `axp-audio hdmi` selects it. A display must be connected - HDMI with no sink produces no audio. |
| `output_device_error_19` | The PCM does not exist (overlay not applied). Check `aplay -l` and the AirXPi block in `/boot/firmware/config.txt`. |
| Cover art missing | Depends on the sender; Apple Music/Spotify on iOS 15+ send artwork, some apps only send volume. `/data/copl-last.txt` shows the raw metadata. |
| Audio late compared to other speakers | AirPlay tab → *Sync delay* negative (e.g. -150 ms). Applying restarts the receiver. |
| Group drops as soon as it forms | Two `shairport-sync` or two `nqptp`. `systemctl status shairport-sync` must be *masked*; `pgrep -a nqptp` must show one process. Also never restrict the receiver to 44.1 kHz. |
| `systemctl status shairport-sync` says inactive (dead) | That is expected: the unit is masked on purpose and `axplay` owns the one allowed instance. Judge the receiver by `pgrep -f shairport-sync` or the AirPlay tab, not by that unit. |
| Only AirPlay 1, AirPlay 2 groups never form | `nqptp` is not running: it must bind **UDP 319/320**, so its unit needs `CAP_NET_BIND_SERVICE`. Check `/dev/shm/nqptp` and `journalctl -u nqptp`. The AirPlay tab shows `AirPlay 1 (nqptp down)` in that case. |
| Receiver stops a second after it starts | The AirPlay tab prints the last lines of `/data/shairport.log` (`server.last_error`). Usual causes: the PCM disappeared, a build without `--with-pipe`/`--with-ffmpeg`, or an ALSA device that the TV is not offering. |
| Two entries with the same name | A stale instance from a previous install. `pkill -f shairport-sync; systemctl restart axplay`. |

## HDMI UI

| Symptom | Cause / fix |
|---|---|
| Black screen, TV says no signal | `hdmi_force_hotplug=1` in `config.txt`, reboot. Check `journalctl -u axgui -b`. |
| X starts, no window | `DISPLAY` must be `:0`; check `/root/.xsession-errors` and `journalctl -u axgui`. |
| Cursor hidden / no pointer | Remove `-nocursor` from `ExecStart` in `axgui.service` (it is there on purpose for TVs). |
| UI too small / cut off | TV overscan. Set the TV to *Just Scan/16:9*, or force `hdmi_mode` (see docs/GUI.md). |
| Settings text unreadable in Persian | `fonts-noto-core` missing: `apt install fonts-noto-core`, restart `axgui`. |

## Wi-Fi access point

| Symptom | Cause / fix |
|---|---|
| `wlan0` not found | `rfkill list` - unblock with `rfkill unblock wlan`; check `dtoverlay=disable-wifi` is not set. |
| hostapd fails to start | The Wi-Fi tab -> *Run check* runs `hostapd -t` and shows the exact parser error; `journalctl -u hostapd -b` has the driver message. Usually an invalid channel for the regulatory domain: set the country first, or pick 1-11. |
| Panel stays on "applying…" | The old code ran the whole plan inside the request. Now `net.apply` reports its `step`; if it is stuck, `journalctl -u axnet -n 50`. *Restart access point* runs the same steps with a bounded wait and returns the error. |
| Some phones cannot join, others can | *Run check* on the Wi-Fi tab: look at `hostapd -t`, `iw reg get` (channel 12/13 needs a country) and `rfkill`. PMF is pinned off and `disassoc_low_ack=0` so an idle phone is not dropped. |
| Clients connect, no internet | Uplink missing (`ip route`), or dnsmasq down (`systemctl status dnsmasq`). `axp-doctor` shows both. |
| Clients get no address | `br0` must be up with `192.168.168.1/24`: `ip -br addr show br0`. Re-apply with `python3 -m airxpi.axnetd apply`. |
| Slow throughput | It is a Pi 3B: 2.4 GHz 802.11n, roughly 30-45 Mbit/s real throughput, and the VPN adds encryption on the same CPU. |

## Uplink / tethering

| Symptom | Cause / fix |
|---|---|
| iPhone tether not detected | Unlock the phone and accept *Trust*; `systemctl status usbmuxd`; `lsusb` must show the Apple device; `ip -br addr` must show `usb0`. |
| Android tether not detected | Enable *USB tethering*, check `dmesg | tail` for `rndis_host`/`cdc_ether`, then `systemctl restart axnet`. |
| `eth0` up but no route | `dhcpcd -4 -n eth0` to debug the lease; the axnetd block in `/etc/dhcpcd.conf` must not deny `eth0`. |
| Wrong uplink picked | Panel → Network → choose *Ethernet* or *USB tethering* explicitly instead of *Auto*. |

## VPN

| Symptom | Cause / fix |
|---|---|
| Location list empty | The feed needs internet: `vpnexit refresh`. If the uplink blocks it, configure `relay_enabled`/`relay_list`. |
| `handshake failed` | Port 500/4500 blocked by the uplink. Try another location/server index; a mobile carrier that blocks IKEv2 cannot be used. |
| Connected but clients still use the uplink | `vpnexit status` → `routing.active` must be `true` and `lan_iface` must be `br0`. `verify` (selftest) compares the direct and the marked exit address. |
| Tunnel up, LAN clients lose DNS | The DNS mark rule needs the tunnel; check `nft list table inet vpnexit` and that `charon` is running. |
| Everything bypasses the VPN | IPv6 must be off (`sysctl net.ipv6.conf.all.disable_ipv6` = 1) and the client must not use its own DNS-over-HTTPS. |
| Large downloads stall | Lower `tunnel_mtu` to 1360 in the panel's VPN settings. |
| A personal profile fails to connect | *VPN -> My VPN profiles* shows the engine error. `python3 -m airxpi.axtunnel capabilities` lists the missing binary per protocol (e.g. `sing-box`, `awg-quick`, `sstpc`). The full client output is in `/var/log/airxpi/tunnel.log`. |
| WireGuard connects but LAN clients still use the uplink | `tunnel-state.json` -> `routing`; check `ip rule` for `fwmark 0x1a2 lookup 418` and `nft list table inet axtunnel`. A vpnexit tunnel must not be connected at the same time. |

## Panel

| Symptom | Cause / fix |
|---|---|
| Password lost | Console: `axp-passwd`. The new password is also written to `/boot/firmware/AIRXPI.txt`. |
| Login works, everything is "unavailable" | `axpanel` cannot reach an engine: `systemctl status axplay vpnexit-web axnet`. |
| Panel unreachable from LAN | The client must be on `br0` (AP or `eth1`); `:80` is the only open port. |
| Panel reachable from the uplink and you do not want that | Set `panel.wan_access` to `false` in `/etc/airxpi/airxpi.json` and `systemctl restart axnet`. |

## Collecting a report

```bash
axp-doctor > /tmp/airxpi.txt 2>&1
journalctl -b -u axnet -u axplay -u axpanel -u axgui -u hostapd -u dnsmasq >> /tmp/airxpi.txt
tar czf /tmp/airxpi-logs.tgz /tmp/airxpi.txt /var/log/airxpi /var/lib/airxpi/airplay2/*.log
```

Attach `/tmp/airxpi-logs.tgz` to the GitHub issue.
