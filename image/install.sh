#!/bin/sh
# AirXPi installer - turns a plain Raspberry Pi OS Lite (Bookworm, 64-bit)
# into the AirPlay 2 + VPN-exit appliance described in docs/ARCHITECTURE.md.
#
#   sudo sh image/install.sh                 # normal install on a live system
#   sudo sh image/install.sh --skip-build    # reuse an existing shairport-sync
#   sudo sh image/install.sh --image         # inside a pi-gen chroot (no services)
#
# Idempotent: re-running upgrades the code and keeps /etc/airxpi/airxpi.json,
# /etc/vpnexit/config.json and the panel password.
set -eu

SRC=$(cd "$(dirname "$0")/.." && pwd)
PREFIX=/opt/airxpi
STATE=/var/lib/airxpi
CONFDIR=/etc/airxpi
MARKER="$CONFDIR/.installed"
SHAIRPORT_VERSION="${SHAIRPORT_VERSION:-5.6}"

SKIP_BUILD=0
IMAGE_MODE=0
for arg in "$@"; do
    case "$arg" in
        --skip-build) SKIP_BUILD=1 ;;
        --image) IMAGE_MODE=1 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

BASE_PKGS="python3 python3-pyqt5 alsa-utils avahi-daemon avahi-utils libnss-mdns
 dbus hostapd dnsmasq dhcpcd5 iw wireless-regdb rfkill nftables iproute2
 usbutils usbmuxd curl ca-certificates openssl sshpass openssh-client
 fonts-dejavu-core fonts-noto-core
 xserver-xorg xserver-xorg-legacy xserver-xorg-video-fbdev xserver-xorg-input-libinput
 xinit x11-xserver-utils
 strongswan strongswan-swanctl libcharon-extra-plugins libstrongswan-extra-plugins
 plymouth plymouth-themes librsvg2-bin cec-utils openssh-server"

BUILD_PKGS="git build-essential autoconf automake libtool pkg-config
 libasound2-dev libavahi-client-dev libssl-dev libsoxr-dev libplist-dev
 libpopt-dev libconfig-dev libglib2.0-dev libdbus-1-dev libplist-utils xxd libsodium-dev libgcrypt20-dev libavutil-dev libavcodec-dev libavformat-dev libswresample-dev"

say() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m    %s\033[0m\n' "$*"; }

# ``systemctl enable`` works offline in a chroot, but fall back to the symlink
# it would have created so a pi-gen image never boots without its services.
enable_unit() {
    unit=$1
    if systemctl enable "$unit" >/dev/null 2>&1; then
        return 0
    fi
    for dir in /etc/systemd/system /lib/systemd/system /usr/lib/systemd/system; do
        if [ -f "$dir/$unit" ]; then
            mkdir -p /etc/systemd/system/multi-user.target.wants
            ln -sf "$dir/$unit" "/etc/systemd/system/multi-user.target.wants/$unit"
            return 0
        fi
    done
    warn "cannot enable $unit"
}

[ "$(id -u)" = "0" ] || { echo "run as root" >&2; exit 1; }
[ -f /etc/os-release ] || { echo "not a Debian system" >&2; exit 1; }
. /etc/os-release
echo "==> AirXPi installer"
echo "    ${PRETTY_NAME:-unknown} on $(uname -m)"

export DEBIAN_FRONTEND=noninteractive

say "packages"
# shellcheck disable=SC2086
apt-get update -qq
# shellcheck disable=SC2086
apt-get install -y -qq $BASE_PKGS
if [ "$SKIP_BUILD" = "0" ]; then
    # shellcheck disable=SC2086
    apt-get install -y -qq $BUILD_PKGS
fi

# --------------------------------------------------------------------------
# AirPlay 2 stack: nqptp + shairport-sync 5.x built with --with-airplay-2
# (the Debian package is AirPlay 1 only, so it cannot be used here)
# --------------------------------------------------------------------------
airplay2_ready() {
    command -v shairport-sync >/dev/null 2>&1 || return 1
    shairport-sync -V 2>/dev/null | grep -qi 'airplay2'
}

build_nqptp() {
    say "building nqptp"
    tmp=$(mktemp -d)
    git clone --depth 1 https://github.com/mikebrady/nqptp.git "$tmp/nqptp"
    cd "$tmp/nqptp"
    autoreconf -fi >/dev/null 2>&1
    ./configure --with-systemd-startup >/dev/null
    make -j"$(nproc)" >/dev/null
    make install >/dev/null
    cd - >/dev/null
    rm -rf "$tmp"
    echo "    nqptp $(command -v nqptp) installed"
}

build_shairport() {
    say "building shairport-sync ${SHAIRPORT_VERSION} (AirPlay 2)"
    tmp=$(mktemp -d)
    git clone --depth 1 --branch "$SHAIRPORT_VERSION" \
        https://github.com/mikebrady/shairport-sync.git "$tmp/ss" 2>/dev/null \
        || git clone --depth 1 https://github.com/mikebrady/shairport-sync.git "$tmp/ss"
    cd "$tmp/ss"
    autoreconf -fi >/dev/null 2>&1
    ./configure --sysconfdir=/etc \
        --with-alsa --with-avahi --with-ssl=openssl --with-soxr \
        --with-metadata --with-dbus-interface --with-airplay-2 >/dev/null
    make -j"$(nproc)" >/dev/null
    make install >/dev/null
    cd - >/dev/null
    rm -rf "$tmp"
    echo "    $(shairport-sync -V 2>/dev/null | head -n1)"
}

if [ "$SKIP_BUILD" = "0" ]; then
    command -v nqptp >/dev/null 2>&1 || build_nqptp
    if ! airplay2_ready; then
        if command -v shairport-sync >/dev/null 2>&1; then
            warn "existing shairport-sync is not AirPlay 2 capable - rebuilding"
        fi
        build_shairport
    fi
else
    warn "skipping the source build (--skip-build)"
fi

if ! airplay2_ready; then
    warn "shairport-sync is missing or has no AirPlay 2 support; the receiver will not start"
fi

# --------------------------------------------------------------------------
# application tree
# --------------------------------------------------------------------------
say "installing files"
install -d "$PREFIX/lib" "$PREFIX/bin" "$PREFIX/web" "$PREFIX/airplay2/static" \
    "$PREFIX/vpnexit/web" "$STATE/airplay2" "$STATE/run" "$CONFDIR" /var/log/airxpi \
    /usr/local/sbin /etc/hostapd /etc/dnsmasq.d

rm -rf "$PREFIX/lib/airxpi"
cp -a "$SRC/src/airxpi" "$PREFIX/lib/airxpi"
find "$PREFIX/lib/airxpi" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

cp -a "$SRC/src/airxpi/web/." "$PREFIX/web/"
cp -a "$SRC/vendor/airplay2/main.py" "$PREFIX/airplay2/main.py"
cp -a "$SRC/vendor/airplay2/static/." "$PREFIX/airplay2/static/"
cp -a "$SRC/vendor/vpnexit/vpnexit.py" "$PREFIX/vpnexit/vpnexit.py"
cp -a "$SRC/vendor/vpnexit/web/." "$PREFIX/vpnexit/web/"

install -m 0755 "$SRC/scripts/axgui-client" "$PREFIX/bin/axgui-client"
install -m 0755 "$SRC/scripts/axp-bootstrap" "$PREFIX/bin/axp-bootstrap"
install -m 0755 "$SRC/scripts/axp-audio" /usr/local/sbin/axp-audio
install -m 0755 "$SRC/scripts/axp-passwd" /usr/local/sbin/axp-passwd
install -m 0755 "$SRC/scripts/axp-doctor" /usr/local/sbin/axp-doctor

cat > /usr/local/sbin/vpnexit <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /opt/airxpi/vpnexit/vpnexit.py "$@"
EOF
chmod 0755 /usr/local/sbin/vpnexit

# the vendored AirPlay panel hard-codes /app and /data
rm -rf /app /data
ln -sfn "$PREFIX/airplay2" /app
ln -sfn "$STATE/airplay2" /data

install -m 0644 "$SRC/systemd/axnet.service" /etc/systemd/system/axnet.service
install -m 0644 "$SRC/systemd/axnet-apply.service" /etc/systemd/system/axnet-apply.service
install -m 0644 "$SRC/systemd/axpanel.service" /etc/systemd/system/axpanel.service
install -m 0644 "$SRC/systemd/axplay.service" /etc/systemd/system/axplay.service
install -m 0644 "$SRC/systemd/axgui.service" /etc/systemd/system/axgui.service
install -m 0644 "$SRC/systemd/axcec.service" /etc/systemd/system/axcec.service
install -m 0644 "$SRC/systemd/axp-splash-quit.service" /etc/systemd/system/axp-splash-quit.service
install -m 0644 "$SRC/systemd/axp-splash-quit.timer" /etc/systemd/system/axp-splash-quit.timer
install -m 0644 "$SRC/systemd/vpnexit-web.service" /etc/systemd/system/vpnexit-web.service
install -m 0644 "$SRC/systemd/vpnexit-supervisor.service" /etc/systemd/system/vpnexit-supervisor.service
if [ ! -f /lib/systemd/system/nqptp.service ] && [ ! -f /etc/systemd/system/nqptp.service ]; then
    install -m 0644 "$SRC/systemd/nqptp.service" /etc/systemd/system/nqptp.service
fi

install -m 0644 "$SRC/config/udev-net.rules" /etc/udev/rules.d/90-airxpi-net.rules
install -m 0644 "$SRC/config/modules-load.conf" /etc/modules-load.d/airxpi-usb.conf
install -m 0644 "$SRC/config/Xwrapper.config" /etc/X11/Xwrapper.config

# --------------------------------------------------------------------------
# configuration (kept across re-installs)
# --------------------------------------------------------------------------
say "configuration"
export PYTHONPATH="$PREFIX/lib"

if [ ! -f "$CONFDIR/airxpi.json" ]; then
    /usr/bin/python3 - <<'PY'
from airxpi import common

# open network on purpose: the box is the appliance, not a router behind a
# captive portal. A passphrase can be set in the panel at any time.
cfg = common.config()
cfg["wifi"]["ssid"] = "AirXPi"
cfg["wifi"]["passphrase"] = ""
cfg["wifi"]["enabled"] = True
common.save_config(cfg)
print("    access point: AirXPi (open, 192.168.168.1)")
PY
fi

# vpnexit: LAN side is the bridge, so its policy routing matches bridged clients
if [ ! -f /etc/vpnexit/config.json ]; then
    install -d /etc/vpnexit /var/lib/vpnexit /etc/swanctl/conf.d /etc/swanctl/x509ca
    /usr/bin/python3 - <<'PY'
import json, secrets
cfg = {
    "feed_url": "https://s-gke-euw1-nssi3-4.europe-west1.firebasedatabase.app/.json?ns=global-vpn-ios",
    "token": secrets.token_hex(16),
    "share_lan": True, "block_ipv6": True, "auto_reconnect": True,
    "tunnel_mtu": 1400, "refresh_hours": 24, "watchdog_seconds": 20,
    "retry_seconds": 120, "lan_iface": "br0", "mark": "0x1a1", "table": 417,
    "rule_priority": 1000, "relay_enabled": False, "relay_list": "", "relay_pass": "",
}
with open("/etc/vpnexit/config.json", "w") as fh:
    json.dump(cfg, fh, indent=1)
PY
    chmod 600 /etc/vpnexit/config.json
else
    /usr/bin/python3 - <<'PY'
import json
path = "/etc/vpnexit/config.json"
cfg = json.load(open(path))
if cfg.get("lan_iface") != "br0":
    cfg["lan_iface"] = "br0"
    json.dump(cfg, open(path, "w"), indent=1)
PY
fi

# strongSwan: routes/NAT belong to vpnexit
install -d /etc/strongswan.d
cat > /etc/strongswan.d/vpnexit.conf <<'EOF'
charon {
    install_routes = no
    install_virtual_ip = no
    port = 500
    port_nat_t = 4500
}
EOF
# one certificate per file for the pem plugin
/usr/bin/python3 - <<'PY'
import os, re
src, dst = "/etc/ssl/certs/ca-certificates.crt", "/etc/swanctl/x509ca"
os.makedirs(dst, exist_ok=True)
try:
    data = open(src).read()
except OSError:
    raise SystemExit(0)
if len([f for f in os.listdir(dst) if f.startswith("sys-")]) < 10:
    for i, block in enumerate(re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", data, re.S)):
        open(os.path.join(dst, "sys-%03d.pem" % i), "w").write(block + "\n")
PY

cat > /etc/default/hostapd <<'EOF'
# AirXPi: hostapd is driven by axnetd, the config file is generated
DAEMON_CONF="/etc/hostapd/hostapd.conf"
EOF

cat > /etc/sysctl.d/90-airxpi.conf <<'EOF'
net.ipv4.ip_forward=1
net.ipv4.conf.all.src_valid_mark=1
net.ipv6.conf.all.disable_ipv6=1
net.ipv6.conf.default.disable_ipv6=1
net.ipv4.conf.all.rp_filter=0
net.ipv4.conf.default.rp_filter=0
net.ipv4.tcp_mtu_probing=1
EOF

# resolv.conf must be a plain file: dnsmasq forwards to the uplink resolvers
if [ -L /etc/resolv.conf ]; then
    rm -f /etc/resolv.conf
    printf 'nameserver 1.1.1.1\nnameserver 9.9.9.9\n' > /etc/resolv.conf
fi

say "hostname"
printf 'airxpi\n' > /etc/hostname
if ! grep -q '^127\.0\.1\.1[[:space:]]*airxpi' /etc/hosts 2>/dev/null; then
    printf '127.0.1.1\tairxpi\n' >> /etc/hosts
fi

# --------------------------------------------------------------------------
# HDMI audio + kiosk display
# --------------------------------------------------------------------------
say "display and audio"
BOOTCFG=/boot/firmware/config.txt
[ -f "$BOOTCFG" ] || BOOTCFG=/boot/config.txt
if [ -f "$BOOTCFG" ] && ! grep -q '^# --- AirXPi ---' "$BOOTCFG"; then
    printf '\n' >> "$BOOTCFG"
    cat "$SRC/config/config.txt.append" >> "$BOOTCFG"
    echo "    appended the AirXPi block to $BOOTCFG"
fi

# --------------------------------------------------------------------------
# boot experience: quiet kernel, logo + progress bar, CEC, ssh
# --------------------------------------------------------------------------
say "boot splash"
if command -v plymouth >/dev/null 2>&1 && command -v rsvg-convert >/dev/null 2>&1; then
    THEME=/usr/share/plymouth/themes/airxpi
    install -d "$THEME"
    sed 's/#020202/#ffffff/g' "$SRC/assets/airxlogoWhite.svg" > "$THEME/logo.svg"
    rsvg-convert -w 300 -h 300 "$THEME/logo.svg" -o "$THEME/logo.png"
    printf '%s\n' '<svg xmlns="http://www.w3.org/2000/svg" width="560" height="8">' \
        '<rect width="560" height="8" rx="4" fill="#1d2733"/></svg>' > "$THEME/bar_track.svg"
    printf '%s\n' '<svg xmlns="http://www.w3.org/2000/svg" width="560" height="8">' \
        '<rect width="WIDTH" height="8" rx="4" fill="#e9f2fb"/></svg>' > "$THEME/bar_fill.svg"
    rsvg-convert "$THEME/bar_track.svg" -o "$THEME/bar_track.png"
    step=0
    while [ "$step" -le 20 ]; do
        width=$((560 * step / 20))
        [ "$width" -lt 8 ] && width=8
        sed "s/WIDTH/$width/" "$THEME/bar_fill.svg" > "$THEME/frame.svg"
        rsvg-convert "$THEME/frame.svg" -o "$THEME/bar_fill_$step.png"
        step=$((step + 1))
    done
    rm -f "$THEME/frame.svg"
    install -m 0644 "$SRC/config/plymouth/airxpi.plymouth" "$THEME/airxpi.plymouth"
    install -m 0644 "$SRC/config/plymouth/airxpi.script" "$THEME/airxpi.script"
    install -d /etc/plymouth
    cat > /etc/plymouth/plymouthd.conf <<'PLYMOUTH'
[Daemon]
Theme=airxpi
ShowDelay=0
DeviceTimeout=8
PLYMOUTH
    # the splash stays up until the Qt window is painted: the GUI quits it, and
    # axp-splash-quit.timer is the safety net if the UI never comes up
    systemctl mask plymouth-quit.service plymouth-quit-wait.service >/dev/null 2>&1 || true
    enable_unit axp-splash-quit.timer
    echo "    plymouth theme installed"
fi

CMDLINE=/boot/firmware/cmdline.txt
[ -f "$CMDLINE" ] || CMDLINE=/boot/cmdline.txt
if [ -f "$CMDLINE" ]; then
    line=$(tr -d '\n' < "$CMDLINE")
    case " $line " in *" quiet "*) ;; *) line="quiet $line" ;; esac
    case " $line " in *" splash "*) ;; *) line="$line splash" ;; esac
    case " $line " in *" loglevel="*) ;; *) line="$line loglevel=0" ;; esac
    case " $line " in *" logo.nologo"*) ;; *) line="$line logo.nologo" ;; esac
    case " $line " in *" vt.global_cursor_default="*) ;; *) line="$line vt.global_cursor_default=0" ;; esac
    printf '%s\n' "$line" > "$CMDLINE"
    echo "    cmdline: $line"
fi

# sshd: enabled by default so the box can be maintained without a keyboard
ssh-keygen -A >/dev/null 2>&1 || true
enable_unit ssh.service

# --------------------------------------------------------------------------
# services
# --------------------------------------------------------------------------
say "services"
systemctl mask shairport-sync.service >/dev/null 2>&1 || true   # axplay owns it
systemctl disable --now hostapd.service >/dev/null 2>&1 || true # axnetd starts it
systemctl disable --now dnsmasq.service >/dev/null 2>&1 || true
systemctl mask systemd-resolved.service >/dev/null 2>&1 || true
systemctl disable --now NetworkManager.service >/dev/null 2>&1 || true
systemctl mask NetworkManager.service >/dev/null 2>&1 || true
# strongSwan ships different unit names across releases
enable_any() {
    for unit in "$@"; do
        for dir in /etc/systemd/system /lib/systemd/system /usr/lib/systemd/system; do
            if [ -f "$dir/$unit" ]; then
                enable_unit "$unit"
                return 0
            fi
        done
    done
    warn "no systemd unit found for: $*"
    return 0
}

enable_unit dhcpcd.service
enable_unit avahi-daemon.service
for unit in axnet.service axpanel.service axplay.service axgui.service axcec.service \
            vpnexit-web.service vpnexit-supervisor.service; do
    enable_unit "$unit"
done
systemctl set-default multi-user.target >/dev/null 2>&1 || ln -sf /lib/systemd/system/multi-user.target /etc/systemd/system/default.target
enable_unit nqptp.service
enable_any strongswan-starter.service strongswan-swanctl.service

if [ "$IMAGE_MODE" = "0" ]; then
    systemctl daemon-reload
    systemctl restart systemd-sysctl.service >/dev/null 2>&1 || true
    systemctl start nqptp.service >/dev/null 2>&1 || true
    systemctl start strongswan-starter.service >/dev/null 2>&1 || true
    systemctl restart axnet.service >/dev/null 2>&1 || true
    sleep 3
    systemctl restart axplay.service >/dev/null 2>&1 || true
    systemctl restart vpnexit-web.service vpnexit-supervisor.service >/dev/null 2>&1 || true
    systemctl restart axpanel.service >/dev/null 2>&1 || true
    systemctl restart axgui.service >/dev/null 2>&1 || true
    /usr/local/sbin/vpnexit refresh >/dev/null 2>&1 || warn "VPN feed not reachable yet - retry from the panel"
fi

# --------------------------------------------------------------------------
# credentials
# --------------------------------------------------------------------------
say "panel credentials"
PASSWORD=""
if [ -f "$MARKER" ] && [ -f "$CONFDIR/panel.json" ]; then
    echo "    keeping the existing panel credentials"
else
    PASSWORD="${AIRXPI_PASSWORD:-admin}"
    /usr/bin/python3 - "$PASSWORD" <<'PY'
import json
import sys
from airxpi import axpanel

result = axpanel.set_password(sys.argv[1])
print("    stored panel credentials:", json.dumps(result))
sys.exit(0 if result.get("ok") else 1)
PY
    mkdir -p /boot/firmware 2>/dev/null || true
    {
        echo "AirXPi appliance"
        echo
        echo "panel   : http://192.168.168.1/   (or http://airxpi.local/)"
        echo "user    : admin"
        echo "password: $PASSWORD"
        echo
        echo "Change the password in the panel (System) after the first login."
        echo
        echo "Access point: AirXPi / see the panel (Wi-Fi tab)"
        echo "CLI: axp-doctor, axp-passwd, axp-audio"
    } > /boot/firmware/AIRXPI.txt 2>/dev/null || true
fi

/usr/bin/python3 - <<'PY'
import json, os, time
info = {
    "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "source": "/opt/airxpi",
    "shairport": os.popen("shairport-sync -V 2>/dev/null | head -n1").read().strip(),
    "kernel": os.uname().release,
}
os.makedirs("/etc/airxpi", exist_ok=True)
json.dump(info, open("/etc/airxpi/build-info.json", "w"), indent=1)
open("/etc/airxpi/.installed", "w").write(time.strftime("%Y-%m-%dT%H:%M:%S\n"))
PY

cat <<EOF

  AirXPi is installed.

  Panel     : http://192.168.168.1/  (also http://airxpi.local/)
  Login     : admin / ${PASSWORD:-unchanged - use axp-passwd to reset}
  Wi-Fi AP  : AirXPi (see /etc/airxpi/airxpi.json)
  HDMI UI   : starts on tty1 (axgui.service)

  Reboot once so the HDMI audio overlay and the bridge come up cleanly.
  Diagnostics: axp-doctor

EOF
