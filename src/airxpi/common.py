"""Shared helpers for the AirXPi services (stdlib only).

Everything the appliance needs to know about paths, configuration files and
shell commands lives here so that the network daemon, the web panel and the
HDMI user interface cannot drift apart.
"""

import json
import os
import re
import socket
import subprocess
import tempfile
import time

APP_ROOT = "/opt/airxpi"
BIN_DIR = os.path.join(APP_ROOT, "bin")
WEB_DIR = os.path.join(APP_ROOT, "web")
STATE_DIR = "/var/lib/airxpi"
CONF_DIR = "/etc/airxpi"
RUN_DIR = os.path.join(STATE_DIR, "run")
LOG_DIR = "/var/log/airxpi"

AXNET_CONF = os.path.join(CONF_DIR, "airxpi.json")
PANEL_CONF = os.path.join(CONF_DIR, "panel.json")
VPN_CONF = "/etc/vpnexit/config.json"

AIRPLAY_PORT = 8090
VPN_PORT = 8088
AXNET_PORT = 8079

PANEL_PORT = 80

# ``/app`` and ``/data`` are the fixed paths the vendored AirPlay panel uses.
AIRPLAY_VENDOR_DIR = os.path.join(APP_ROOT, "airplay2")
AIRPLAY_DATA = "/data"

DEFAULTS = {
    "device": {
        "name": "AirXPi",
        "language": "en",
    },
    "wan": {
        # auto | eth0 | usb
        "mode": "auto",
    },
    "lan": {
        "cidr": "192.168.168.1/24",
        "dhcp_start": "192.168.168.10",
        "dhcp_end": "192.168.168.200",
        "lease": "12h",
        "ethernet": True,
        "nat": True,
    },
    "wifi": {
        "enabled": True,
        "ssid": "AirXPi",
        "passphrase": "",
        "channel": 6,
        "country": "",
        "hidden": False,
        "max_clients": 16,
        "ieee80211n": True,
    },
    "airplay": {
        "name": "AirXPi",
    },
    "panel": {
        "wan_access": False,
    },
}

SSID_RE = re.compile(r"^[\x20-\x7e]{1,32}$")
PSK_RE = re.compile(r"^[\x20-\x7e]{8,63}$")
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,30})$")


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------
def ensure_dirs():
    for path in (STATE_DIR, CONF_DIR, RUN_DIR, LOG_DIR):
        os.makedirs(path, exist_ok=True)


def hostname():
    """Short host name, portable (os.uname is Linux-only, tests run anywhere)."""
    return socket.gethostname().split(".")[0]


def read_text(path, default=""):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return default


def write_atomic(path, text, mode=0o644):
    """Write ``text`` to ``path`` through a temporary file in the same dir."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".axpi-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, (dict, list)) else (default if default is not None else {})
    except (OSError, ValueError):
        return {} if default is None else default


def save_json(path, data, mode=0o600):
    write_atomic(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", mode)


def merge_defaults(base, patch):
    """Recursively overlay ``patch`` on a copy of ``base`` (dicts only)."""
    out = json.loads(json.dumps(base))
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_defaults(out[key], value)
        else:
            out[key] = value
    return out


def config():
    """Return the appliance configuration merged over the defaults."""
    return merge_defaults(DEFAULTS, load_json(AXNET_CONF, {}))


def save_config(cfg):
    ensure_dirs()
    save_json(AXNET_CONF, cfg, 0o600)


# --------------------------------------------------------------------------
# shell
# --------------------------------------------------------------------------
def run(cmd, timeout=30):
    """Run a command (list or string) and return ``(rc, combined_output)``."""
    try:
        proc = subprocess.run(
            cmd,
            shell=isinstance(cmd, str),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.decode("utf-8", "replace").strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout: %s" % (cmd if isinstance(cmd, str) else " ".join(cmd))
    except FileNotFoundError:
        return 127, "not found"
    except OSError as exc:
        return 126, str(exc)


def service(action, unit, timeout=45):
    return run(["systemctl", action, unit], timeout=timeout)


def service_active(unit):
    rc, out = run(["systemctl", "is-active", unit], timeout=10)
    return out.strip() == "active"


def log(message, tag="axnet"):
    """Append a line to the journal only - no state on disk is touched."""
    line = "%s [%s] %s" % (time.strftime("%Y-%m-%dT%H:%M:%S"), tag, message)
    try:
        print(line, flush=True)
    except Exception:
        pass


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------
def valid_ssid(value):
    return bool(SSID_RE.match(value or ""))


def valid_psk(value):
    return bool(PSK_RE.match(value or ""))


def valid_channel(value):
    try:
        channel = int(value)
    except (TypeError, ValueError):
        return False
    return 1 <= channel <= 13


def valid_hostname(value):
    return bool(HOSTNAME_RE.match(value or ""))


def sanitize_text(value, limit=64):
    """Keep printable ASCII and clamp the length (hostapd value safety)."""
    cleaned = "".join(ch for ch in str(value or "") if 0x20 <= ord(ch) <= 0x7E)
    return cleaned[:limit].strip()


def valid_country(value):
    return bool(re.match(r"^[A-Za-z]{2}$", value or ""))


# --------------------------------------------------------------------------
# network helpers
# --------------------------------------------------------------------------
def interfaces():
    """Return ``{name: {ip, mac, operstate, kind}}`` for every IPv4 interface."""
    result = {}
    rc, out = run(["ip", "-o", "link", "show"], timeout=10)
    if rc == 0:
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) < 2:
                continue
            name = parts[1].strip().split("@")[0]
            state = ""
            match = re.search(r"state (\S+)", line)
            if match:
                state = match.group(1)
            mac = ""
            match = re.search(r"link/ether (\S+)", line)
            if match:
                mac = match.group(1)
            result[name] = {"ip": "", "mac": mac, "operstate": state, "kind": iface_kind(name)}
    rc, out = run(["ip", "-o", "-4", "addr", "show"], timeout=10)
    if rc == 0:
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            name = parts[1].split("@")[0]
            match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", line)
            if name in result and match:
                result[name]["ip"] = match.group(1)
    return result


def iface_kind(name):
    if name == "br0":
        return "bridge"
    if name.startswith(("wlan", "wlp")):
        return "wifi"
    if name.startswith(("usb", "enx")):
        return "usb"
    if name.startswith(("eth", "enp", "eno")):
        return "ethernet"
    return "other"


def usb_net_ifaces():
    return sorted(n for n, v in interfaces().items() if v["kind"] == "usb")


def wan_candidates():
    """Interfaces that may carry the internet uplink, best first."""
    found = interfaces()
    ethernet = [n for n in ("eth0",) if n in found]
    usb = [n for n, v in found.items() if v["kind"] == "usb"]
    return {"ethernet": ethernet, "usb": sorted(usb)}


def default_route():
    rc, out = run(["ip", "-4", "route", "show", "default"], timeout=10)
    if rc != 0 or not out:
        return {}
    line = out.splitlines()[0]
    dev = re.search(r"dev (\S+)", line)
    via = re.search(r"via (\d+\.\d+\.\d+\.\d+)", line)
    return {"dev": dev.group(1) if dev else "", "via": via.group(1) if via else ""}


def ip_of(iface):
    rc, out = run(["ip", "-4", "-o", "addr", "show", "dev", iface], timeout=10)
    match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
    return match.group(1) if match else ""


def lan_cidr():
    cfg = config()
    return cfg["lan"]["cidr"]


def lan_network():
    """``192.168.168.0/24`` derived from the configured LAN address."""
    cidr = lan_cidr()
    try:
        addr, prefix = cidr.split("/")
    except ValueError:
        return "192.168.168.0/24"
    octets = addr.split(".")
    if len(octets) != 4 or prefix != "24":
        return "192.168.168.0/24"
    return "%s.%s.%s.0/24" % (octets[0], octets[1], octets[2])
