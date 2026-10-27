# HDMI user interface

`axgui.service` starts `xinit` on `tty1`, which runs
`/opt/airxpi/bin/axgui-client` → `python3 -m airxpi.gui` (PyQt5) full screen on
`DISPLAY=:0`.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ AirXPi   [AirPlay ●] [VPN ●] [Wi-Fi ●]                    21:34   [فا]   │
├───────────────────────────────────┬──────────────────────────────────────┤
│                                   │ [AirPlay] [VPN exit] [Wi-Fi]         │
│                                   │                                      │
│           cover art               │  name      [ Living Room      ]      │
│                                   │  output    [ vc4-hdmi ✓       ▾]     │
│  NOW PLAYING                      │  delay     [  -30 ms ]               │
│  Song title                       │  [Save] [Test tone] [Restart]        │
│  Artist · Album                   │  running · vc4-hdmi                  │
│  ▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░          │                                      │
│  ⏮   ▶   ⏭     Volume  – 62% +    │  hint text …                         │
├───────────────────────────────────┴──────────────────────────────────────┤
│ Panel http://192.168.168.1/  ·  Uplink usb0           kernel 6.6 · up 3h 12m │
└──────────────────────────────────────────────────────────────────────────┘
```

* **Left**: cover art (from `/api/artwork`), title/artist/album, progress,
  transport (⏮ ▶/⏸ ⏭) and volume ±4 %. The background is a blurred, darkened copy
  of the current artwork.
* **Right**: three tabs.
  * **AirPlay** - name, output PCM (all `aplay -l` entries, HDMI marked), sync
    delay, *Save*, *Test tone*, *Restart*, receiver state.
  * **VPN** - state, exit address, location list (tap to connect, tap again to
    disconnect), *Refresh*, *Verify*.
  * **Wi-Fi** - on/off, SSID, passphrase, channel, country, *Apply*, *Generate*.
* **Header**: status chips (AirPlay, VPN, Wi-Fi), clock, language toggle (EN/فا).
* **Footer**: panel URL, active uplink, kernel, uptime.

## Input

No keyboard? The UI ships an on-screen keyboard: tapping the name, SSID or
passphrase field opens it (shift, space, backspace, clear, OK). A USB mouse is
enough; a USB keyboard works too (fields are normal `QLineEdit`s).

## Data flow

The UI polls `http://127.0.0.1/api/state` every 1.5 s in a `QThread`
(`Poller`), so a slow service never freezes the picture. Artwork is fetched only
when `now_playing.art_version` changes. Commands are `POST`s executed on a
`QThreadPool` worker, so a 30 s VPN connect does not block the UI.

## Resolution and scaling

The layout is layout-manager based (no absolute geometry except the progress bar),
so 720p, 1080p and 4K all work; Qt scales the fonts by pixel density. Default HDMI
mode comes from the TV's EDID. To force one:

```
# /boot/firmware/config.txt
hdmi_force_hotplug=1
hdmi_group=1
hdmi_mode=16      # 1080p60
```

## Alternative back-ends

X11 is used because it is the most forgiving path on a 1 GB Pi 3B. To run without
X (Qt's KMS backend), change the unit:

```ini
# /etc/systemd/system/axgui.service.d/eglfs.conf
[Service]
ExecStart=
Environment=QT_QPA_PLATFORM=eglfs
Environment=QT_QPA_EGLFS_ALWAYS_SET_MODE=1
ExecStart=/opt/airxpi/bin/axgui-client
```

`QT_QPA_EGLFS_HIDECURSOR=1` hides the pointer. If the screen stays black, check
`journalctl -u axgui -b` - usually a missing `dtoverlay=vc4-kms-v3d` or the
`video` group.

## Idle behaviour

With no AirPlay session the left side shows the appliance name and
"Open Control Center on your iPhone or iPad and pick this device"; art and progress
appear as soon as a sender connects. The screen is never blanked (no DPMS) so the
TV always shows the state of the box.
