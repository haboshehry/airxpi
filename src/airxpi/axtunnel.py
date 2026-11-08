#!/usr/bin/env python3
"""axtunnel - the "personal VPN" side of the AirXPi appliance.

vpnexit owns the built-in IKEv2 *feed*.  This service owns everything the user
brings themselves:

    ikev2      manual server / user / password / PSK / CA (strongSwan swanctl)
    wireguard  fields or an uploaded wg-quick .conf
    amneziawg  WireGuard with the Amnezia obfuscation fields (awg-quick)
    vless      VLESS + REALITY through sing-box (TUN inbound)
    openvpn    fields or an uploaded .ovpn
    l2tp       L2TP/IPsec with PSK (xl2tpd + strongSwan transport mode)
    sstp       SSTP through sstp-client + pppd

All of them end in the same data path as vpnexit: LAN traffic (iifname br0) is
marked, a dedicated routing table sends the marked packets through the tunnel
and nftables masquerades only that traffic.  The appliance itself keeps its own
uplink, so the panel, the feed and the AirPlay control channel stay reachable.

The mark/table pair is deliberately different from vpnexit (0x1a1 / 417): the
two managers are mutually exclusive, and both writing the same mark would send
the LAN into a half-configured tunnel.

Standard library only, like the rest of the appliance.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = "/etc/airxpi"
CONF = os.path.join(BASE, "tunnels.json")
PROFILE_DIR = os.path.join(BASE, "tunnels")
STATE_DIR = "/var/lib/airxpi"
STATE = os.path.join(STATE_DIR, "tunnel-state.json")
RUN_DIR = os.path.join(STATE_DIR, "run")
LOG = "/var/log/airxpi/tunnel.log"
PORT = 8086

PROTOCOLS = ("ikev2", "wireguard", "amneziawg", "vless", "openvpn", "l2tp", "sstp")
LABELS = {
    "ikev2": "IKEv2 (manual)",
    "wireguard": "WireGuard",
    "amneziawg": "AmneziaWG",
    "vless": "VLESS + REALITY",
    "openvpn": "OpenVPN",
    "l2tp": "L2TP / IPsec",
    "sstp": "SSTP",
}

DEFAULTS = {
    "share_lan": True,
    "block_ipv6": True,
    "auto_reconnect": True,
    "mark": "0x1a2",
    "table": 418,
    "rule_priority": 1001,
    "lan_iface": "br0",
    "mtu": 1400,
}

SECRET_FIELDS = {
    "ikev2": ("password", "psk", "ca"),
    "wireguard": ("private_key", "preshared_key"),
    "amneziawg": ("private_key", "preshared_key"),
    "vless": ("uuid",),
    "openvpn": ("password", "tls_auth"),
    "l2tp": ("password", "psk"),
    "sstp": ("password",),
}

# fields that are safe (and useful) to show back to the panel
SHOWN_FIELDS = (
    "name", "protocol", "server", "port", "username", "endpoint", "address",
    "local_id", "remote_id", "sni", "public_key", "short_id", "fingerprint",
    "flow", "network", "security", "proto", "device", "allowed_ips",
    "interface", "mtu", "verify", "comment",
)

LOCK = threading.Lock()
ROUTING_LOCK = threading.Lock()


# --------------------------------------------------------------------- utils
def ensure_dirs():
    for path in (BASE, PROFILE_DIR, STATE_DIR, RUN_DIR, os.path.dirname(LOG)):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass


def log(message):
    line = "%s [axtunnel] %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), message)
    try:
        with open(LOG, "a", encoding="utf-8") as handle:
            handle.write(line)
        if os.path.getsize(LOG) > 256 * 1024:
            with open(LOG, "rb") as handle:
                tail = handle.read()[-128 * 1024:]
            with open(LOG, "wb") as handle:
                handle.write(tail)
    except OSError:
        pass
    try:
        print(line.rstrip(), flush=True)
    except Exception:  # noqa: BLE001
        pass


def run(cmd, timeout=30, stdin_text=None, env=None):
    """Run a command list, always bounded by ``timeout``."""
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            input=stdin_text.encode() if stdin_text is not None else None,
            env=env,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.decode("utf-8", "replace").strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout: %s" % " ".join(cmd)
    except FileNotFoundError:
        return 127, "not found: %s" % cmd[0]
    except OSError as exc:
        return 126, str(exc)


def read_text(path, default=""):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return default


def write_text(path, text, mode=0o600):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else default
    except (OSError, ValueError):
        return default


def save_json(path, data, mode=0o600):
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", mode)


def cfg(key=None):
    data = dict(DEFAULTS)
    data.update(load_json(CONF, {}))
    return data if key is None else data.get(key, DEFAULTS.get(key))


def cfg_set(**patch):
    data = cfg()
    data.update(patch)
    save_json(CONF, data)
    return data


def state_read():
    st = load_json(STATE, {"state": "idle"})
    st.setdefault("state", "idle")
    return st


def state_patch(**patch):
    st = state_read()
    st.update(patch)
    save_json(STATE, st)
    return st


def iface_cidr(dev):
    rc, out = run(["ip", "-4", "-o", "addr", "show", "dev", dev], timeout=10)
    match = re.search(r"inet\s+([0-9.]+/\d+)", out)
    return match.group(1) if match else ""


def iface_addr(dev):
    cidr = iface_cidr(dev)
    return cidr.split("/")[0] if cidr else ""


def default_route():
    rc, out = run(["ip", "-4", "route", "show", "default"], timeout=10)
    line = out.splitlines()[0] if out.splitlines() else ""
    gateway = re.search(r"via\s+([0-9.]+)", line)
    device = re.search(r"dev\s+(\S+)", line)
    return (gateway.group(1) if gateway else ""), (device.group(1) if device else "")


def links():
    rc, out = run(["ip", "-o", "link", "show"], timeout=10)
    names = set()
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) > 1:
            names.add(parts[1].strip().split("@")[0])
    return names


def link_exists(dev):
    return bool(dev) and run(["ip", "link", "show", "dev", dev], timeout=8)[0] == 0


def new_ppp_iface(before):
    for name in sorted(links()):
        if name.startswith("ppp") and name not in before:
            return name
    for name in sorted(links()):
        if name.startswith("ppp"):
            return name
    return ""


# ------------------------------------------------------------------ profiles
def profile_key(profile):
    raw = "%s-%s" % (profile.get("protocol", "p"), profile.get("name", "profile"))
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")[:40] or "profile"
    return slug


def new_id(profile):
    return "%s-%04x" % (profile_key(profile), int(time.time() * 1000) % 0xFFFF)


def profiles():
    data = load_json(CONF, {})
    items = data.get("profiles")
    return items if isinstance(items, list) else []


def find_profile(profile_id):
    for item in profiles():
        if item.get("id") == profile_id:
            return item
    return None


def save_profiles(items):
    data = cfg()
    data["profiles"] = items
    save_json(CONF, data)


def public_profile(profile, reveal=False):
    proto = profile.get("protocol", "")
    out = {"id": profile.get("id", ""), "protocol": proto,
           "label": LABELS.get(proto, proto), "updated_at": profile.get("updated_at", 0),
           "conf_set": bool(profile.get("conf")), "ready": bool(profile.get("ready"))}
    for key in SHOWN_FIELDS:
        if profile.get(key) not in (None, ""):
            out[key] = profile[key]
    for key in SECRET_FIELDS.get(proto, ()):
        value = profile.get(key) or ""
        if reveal:
            out[key] = value
        else:
            out[key + "_set"] = bool(value)
    return out


def public_profiles():
    return [public_profile(item) for item in profiles()]


# -------------------------------------------------------------- capabilities
def which(name):
    return shutil.which(name) or ""


def module_present(name):
    return os.path.isdir("/sys/module/%s" % name)


def capabilities():
    charon = run(["systemctl", "is-active", "strongswan-swanctl"], timeout=6)[1].strip()
    if charon != "active":
        charon = run(["systemctl", "is-active", "strongswan-starter"], timeout=6)[1].strip()
    caps = {
        "ikev2": {
            "ok": bool(which("swanctl")) and charon == "active",
            "missing": [name for name in ("swanctl",) if not which(name)],
            "note": "strongSwan is not running" if charon != "active" else "",
        },
        "wireguard": {
            "ok": bool(which("wg-quick")) and bool(which("wg")),
            "missing": [name for name in ("wg-quick", "wg") if not which(name)],
            "note": "" if module_present("wireguard") else "kernel module wireguard is not loaded",
        },
        "amneziawg": {
            "ok": bool(which("awg-quick")) and bool(which("awg")),
            "missing": [name for name in ("awg-quick", "awg")
                        if not which(name)] + ([] if module_present("amneziawg") or which("amneziawg-go")
                                               else ["amneziawg-go"]),
            "note": "" if module_present("amneziawg") else (
                "userspace amneziawg-go (slower than the kernel module)"
                if which("amneziawg-go") else "amneziawg is not installed"),
        },
        "vless": {
            "ok": bool(which("xray")),
            "missing": [] if which("xray") else ["xray"],
            "note": "" if which("xray") else (
                "xray-core is required for REALITY pqv; sing-box cannot verify mldsa65"),
        },
        "openvpn": {
            "ok": bool(which("openvpn")),
            "missing": [] if which("openvpn") else ["openvpn"],
            "note": "",
        },
        "l2tp": {
            "ok": bool(which("xl2tpd")) and bool(which("swanctl")) and charon == "active",
            "missing": [name for name in ("xl2tpd", "swanctl") if not which(name)],
            "note": "IPsec (strongSwan) is required for L2TP",
        },
        "sstp": {
            "ok": bool(which("sstpc")) and bool(which("pppd")),
            "missing": [name for name in ("sstpc", "pppd") if not which(name)],
            "note": "",
        },
    }
    for proto, item in caps.items():
        item["label"] = LABELS.get(proto, proto)
    return caps


# --------------------------------------------------------- config rendering
def _esc(value):
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def render_wireguard(profile):
    address = (profile.get("address") or "").strip() or "10.66.66.2/32"
    lines = [
        "# generated by axtunnel - LAN sharing is done with policy routing,",
        "# so the host keeps its own uplink (Table = off).",
        "[Interface]",
        "PrivateKey = %s" % (profile.get("private_key") or "").strip(),
        "Address = %s" % address,
        "Table = off",
    ]
    if profile.get("mtu"):
        lines.append("MTU = %s" % int(profile["mtu"]))
    if profile.get("amnezia"):
        for key in ("jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4"):
            if profile.get(key) not in (None, ""):
                lines.append("%s = %s" % (key.upper(), profile[key]))
    lines += [
        "",
        "[Peer]",
        "PublicKey = %s" % (profile.get("peer_public_key") or "").strip(),
        "AllowedIPs = %s" % ((profile.get("allowed_ips") or "0.0.0.0/0,::/0").strip()),
        "Endpoint = %s" % (profile.get("endpoint") or "").strip(),
    ]
    if profile.get("preshared_key"):
        lines.append("PresharedKey = %s" % profile["preshared_key"].strip())
    if profile.get("keepalive"):
        lines.append("PersistentKeepalive = %s" % int(profile["keepalive"]))
    return "\n".join(lines) + "\n"


def normalise_uploaded_conf(text, kind):
    """Keep an uploaded wg/awg/ovpn config from hijacking the appliance.

    A stock ``wg-quick`` file installs a default route and rewrites resolv.conf;
    both would break the panel and the AirPlay control channel.  ``Table = off``
    leaves routing to axtunnel, and DNS stays with the local dnsmasq.
    """
    if kind in ("wireguard", "amneziawg"):
        lines = []
        in_interface = False
        for raw in text.splitlines():
            line = raw.rstrip()
            stripped = line.strip()
            if stripped.startswith("["):
                in_interface = stripped.lower() == "[interface]"
                lines.append(line)
                continue
            key = stripped.split("=")[0].strip().lower() if "=" in stripped else ""
            if in_interface and key in ("dns", "saveconfig"):
                continue
            if in_interface and key == "table":
                continue
            lines.append(line)
        out = []
        inserted = False
        for line in lines:
            out.append(line)
            if line.strip().lower() == "[interface]" and not inserted:
                out.append("Table = off")
                inserted = True
        return "\n".join(out).strip() + "\n"
    # OpenVPN: keep the file as uploaded; the command line adds route-nopull.
    return text.strip() + "\n"


def write_profile_file(profile, suffix, text):
    path = os.path.join(PROFILE_DIR, "%s.%s" % (profile["id"], suffix))
    write_text(path, text, 0o600)
    return path


# ------------------------------------------------------------------ adapters
class TunnelError(Exception):
    pass


def parse_endpoint(profile):
    host = (profile.get("server") or profile.get("endpoint") or "").strip()
    host = re.sub(r"^[a-z0-9+]+://", "", host, flags=re.I)
    host = host.split("/")[0]
    if host.count(":") == 1:
        host = host.split(":")[0]
    return host


def resolve4(host):
    if not host:
        return []
    rc, out = run(["getent", "ahostsv4", host], timeout=10)
    result = []
    for line in out.splitlines():
        ip = line.split()[0] if line.split() else ""
        if ip.count(".") == 3 and ip not in result:
            result.append(ip)
    return result[:4]


def kernel_ipsec():
    """Load the kernel modules L2TP/IPsec needs, silently when unavailable."""
    for module in ("af_key", "xfrm_user"):
        run(["modprobe", module], timeout=10)


AMNEZIA_KEYS = ("jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4")


def looks_like_amnezia(profile):
    """True when the profile really carries AmneziaWG obfuscation.

    The keys arrive either as individual fields or inside an uploaded .conf.
    Checking only the fields made a pasted Amnezia config fall through to
    wg-quick, which then died with "Line unrecognized: `Jc=4'".
    """
    pattern = r"(?mi)^\s*(jc|jmin|jmax|s1|s2|h1|h2|h3|h4)\s*="
    if re.search(pattern, str(profile.get("conf") or "")):
        return True
    return any(str(profile.get(key) or "").strip() for key in AMNEZIA_KEYS)


def up_wireguard(profile, amnezia=False):
    text = profile.get("conf")
    if text:
        text = normalise_uploaded_conf(text, "amneziawg" if amnezia else "wireguard")
    else:
        missing = [key for key in ("private_key", "peer_public_key", "endpoint")
                   if not (profile.get(key) or "").strip()]
        if missing:
            raise TunnelError("missing fields: %s" % ", ".join(missing))
        text = render_wireguard(dict(profile, amnezia=amnezia))
    # wg-quick derives the interface name from the file name, so the file has to
    # be .../axpi0.conf: a profile-id file name would create a >15 character
    # interface (or reject the dotted name) and the tunnel would never come up.
    if amnezia and not which("awg-quick"):
        # Debian ships no AmneziaWG package.  A config without obfuscation keys
        # is plain WireGuard and works on wg-quick; a real Amnezia profile gets
        # an actionable message instead of a wg-quick parse error.
        if looks_like_amnezia(profile):
            raise TunnelError(
                "this profile uses AmneziaWG obfuscation (Jc/Jmin/S1/H1..H4) but "
                "awg-quick is not installed; install amneziawg-tools + "
                "amneziawg-go, or remove those keys to run plain WireGuard")
        amnezia = False
    if amnezia:
        binary = "awg-quick"
        path = "/etc/amnezia/amneziawg/axpi0.conf"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_text(path, text, 0o600)
    else:
        binary = "wg-quick"
        path = "/etc/wireguard/axpi0.conf"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_text(path, text, 0o600)
    if not which(binary):
        raise TunnelError("%s is not installed" % binary)
    run([binary, "down", "axpi0"], timeout=25)
    run(["ip", "link", "del", "axpi0"], timeout=10)
    env = None
    if amnezia and not module_present("amneziawg"):
        # userspace implementation: no kernel module on Raspberry Pi OS
        env = dict(os.environ)
        env["WG_QUICK_USERSPACE_IMPLEMENTATION"] = "amneziawg-go"
    rc, out = run([binary, "up", "axpi0"], timeout=45, env=env)
    if rc != 0:
        raise TunnelError("%s up failed: %s" % (binary, out[-300:]))
    if not link_exists("axpi0"):
        raise TunnelError("%s did not create axpi0" % binary)
    return {"device": "axpi0", "mode": "masquerade", "local_ip": iface_addr("axpi0"),
            "endpoints": resolve4(parse_endpoint(profile)), "driver": binary}


def down_wireguard(profile, amnezia=False):
    binary = "awg-quick" if amnezia else "wg-quick"
    if which(binary):
        run([binary, "down", "axpi0"], timeout=25)
    run(["ip", "link", "del", "axpi0"], timeout=10)


VLESS_TCP_PORT = 12345
VLESS_HTTP_PORT = 18081
VLESS_LOCAL = "127.0.0.1"


def vless_parse(uri):
    """Parse a ``vless://`` URL the way the OpenWrt panel does.

    The URL carries everything REALITY needs - ``sni``, ``sid``, ``fp``,
    ``spx`` and, for the post-quantum variant, ``pqv``.  Dropping those (the
    old code kept only host/port/uuid/pbk) is what made a pasted profile fail
    the TLS handshake.
    """
    uri = (uri or "").strip()
    if not uri.startswith("vless://"):
        return {"error": "not a vless:// URL"}
    rest = uri[8:].split("#", 1)[0]
    main, _, query = rest.partition("?")
    uuid, sep, hostport = main.partition("@")
    if not sep or not uuid or not hostport:
        return {"error": "the URL has no uuid@host"}
    host, port = hostport, 443
    if hostport.startswith("["):
        close = hostport.find("]")
        if close > 0:
            host = hostport[1:close]
            tail = hostport[close + 1:]
            if tail.startswith(":"):
                port = int(tail[1:] or 443)
    else:
        h, sep, p = hostport.rpartition(":")
        if sep and p.isdigit():
            host, port = h, int(p)
    params = {}
    for pair in query.split("&"):
        if not pair:
            continue
        key, sep, value = pair.partition("=")
        params[key.lower()] = urllib.parse.unquote(value)
    return {
        "uuid": uuid, "server": host, "port": port,
        "flow": params.get("flow", ""),
        "security": (params.get("security") or "none").lower(),
        "sni": params.get("sni") or params.get("host") or host,
        "fingerprint": params.get("fp") or "chrome",
        "public_key": params.get("pbk", ""),
        "short_id": params.get("sid", ""),
        "spx": params.get("spx", "/"),
        "pqv": params.get("pqv", ""),
        "network": (params.get("type") or "tcp").lower(),
        "path": params.get("path", "/"),
        "host_header": params.get("host", ""),
        "service": params.get("servicename", ""),
        "alpn": params.get("alpn", ""),
        "raw": uri,
    }


def vless_fields(profile):
    """Fields stored on the profile, with a pasted URL filling the blanks."""
    parsed = vless_parse(profile.get("conf") or "")
    out = {}
    for key in ("server", "uuid", "public_key", "short_id", "sni", "fingerprint",
                "flow", "security", "network", "path", "host_header", "service",
                "spx", "pqv"):
        value = str(profile.get(key) or "").strip()
        if not value and not parsed.get("error"):
            value = str(parsed.get(key) or "").strip()
        out[key] = value
    out["port"] = int(str(profile.get("port") or parsed.get("port") or 443).strip() or 443)
    out["server"] = out["server"] or str(parsed.get("server") or "").strip()
    out["uuid"] = out["uuid"] or str(parsed.get("uuid") or "").strip()
    return out


def xray_config(v):
    """Xray config: a redirect inbound for LAN traffic, an http inbound for tests.

    Xray (not sing-box) is the client because REALITY here uses the ML-DSA-65
    post-quantum key (``pqv``); sing-box has no ``mldsa65Verify`` and answers
    with "tls: handshake failure".
    """
    reality = {
        "serverName": v.get("sni") or v.get("server"),
        "fingerprint": v.get("fingerprint") or "chrome",
        "publicKey": v.get("public_key"),
        "shortId": v.get("short_id", ""),
    }
    if v.get("spx"):
        reality["spiderX"] = v["spx"]
    if v.get("pqv"):
        reality["mldsa65Verify"] = v["pqv"]
    user = {"id": v["uuid"], "encryption": "none"}
    if v.get("flow"):
        user["flow"] = v["flow"]
    stream = {"network": "tcp"}
    if v.get("security") == "reality":
        stream.update({"security": "reality", "realitySettings": reality})
    elif v.get("security") == "tls":
        tls = {"serverName": v.get("sni") or v.get("server")}
        if v.get("alpn"):
            tls["alpn"] = [a for a in v["alpn"].split(",") if a]
        stream.update({"security": "tls", "tlsSettings": tls})
    else:
        stream["security"] = "none"
    if v.get("network") == "ws":
        ws = {"path": v.get("path") or "/"}
        if v.get("host_header"):
            ws["headers"] = {"Host": v["host_header"]}
        stream.update({"network": "ws", "wsSettings": ws})
    elif v.get("network") == "grpc":
        stream.update({"network": "grpc", "grpcSettings": {"serviceName": v.get("service", "")}})
    outbound = {
        "tag": "proxy",
        "protocol": "vless",
        "settings": {"vnext": [{"address": v["server"], "port": int(v["port"]), "users": [user]}]},
        "streamSettings": stream,
    }
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                # REDIRECT rewrites the destination to this host's address, so
                # the socket must not be loopback-only (that needs
                # route_localnet on br0, which would expose every 127.0.0.1
                # service to the LAN).  Direct connections to the port are
                # dropped by the ruleset; only DNAT'd ones are allowed.
                "tag": "tproxy-in", "listen": "0.0.0.0", "port": VLESS_TCP_PORT,
                "protocol": "dokodemo-door",
                "settings": {"network": "tcp,udp", "followRedirect": True},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"], "routeOnly": True},
            },
            {"tag": "http-in", "listen": VLESS_LOCAL, "port": VLESS_HTTP_PORT, "protocol": "http"},
        ],
        "outbounds": [outbound, {"tag": "direct", "protocol": "freedom"}],
    }


def vless_probe_ip(seconds=8):
    """Exit address as seen through the local http inbound (works before routing)."""
    rc, out = run(["curl", "-fsS", "--max-time", str(seconds), "-x",
                   "http://%s:%d" % (VLESS_LOCAL, VLESS_HTTP_PORT), PROBE], timeout=seconds + 6)
    match = re.search(r"ip=([0-9.]+)", out)
    return match.group(1) if match else ""


def up_vless_singbox(profile, v):
    """Plain VLESS/TLS: Xray 26 refuses vless without TLS to a public address,
    sing-box accepts it, so this path keeps working instead of failing the
    profile outright."""
    if not which("sing-box"):
        raise TunnelError("sing-box is not installed (needed for a plain VLESS inbound)")
    outbound = {
        "type": "vless", "tag": "proxy", "server": v["server"], "server_port": int(v["port"]),
        "uuid": v["uuid"], "packet_encoding": "xudp",
    }
    if v.get("flow"):
        outbound["flow"] = v["flow"]
    if v.get("security") in ("tls", "reality"):
        tls = {"enabled": True, "server_name": v.get("sni") or v["server"],
               "utls": {"enabled": True, "fingerprint": v.get("fingerprint") or "chrome"}}
        if v.get("security") == "reality":
            tls["reality"] = {"enabled": True, "public_key": v.get("public_key", ""),
                              "short_id": v.get("short_id", "")}
        outbound["tls"] = tls
    config = {
        "log": {"level": "warn", "timestamp": True},
        "inbounds": [{
            "type": "tun", "tag": "tun-in", "interface_name": "axtun0",
            "address": ["172.19.0.1/30"], "mtu": int(profile.get("mtu") or cfg("mtu") or 1400),
            "auto_route": False, "strict_route": False, "stack": "system",
        }],
        "outbounds": [outbound, {"type": "direct", "tag": "direct"}],
        "route": {"rules": [], "final": "proxy", "auto_detect_interface": False},
    }
    path = write_profile_file(profile, "singbox.json", json.dumps(config, indent=2) + "\n")
    run(["pkill", "-f", "sing-box run -c %s" % path], timeout=10)
    rc, out = run(["sing-box", "check", "-c", path], timeout=25)
    if rc != 0:
        raise TunnelError("sing-box rejected the config: %s" % out[-300:])
    log_path = os.path.join(PROFILE_DIR, "%s.singbox.log" % profile["id"])
    with open(log_path, "ab", buffering=0) as handle:
        subprocess.Popen(["sing-box", "run", "-c", path], stdout=handle,
                         stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(25):
        time.sleep(0.4)
        if link_exists("axtun0"):
            break
    if not link_exists("axtun0"):
        tail = read_text(log_path)[-300:].strip()
        raise TunnelError("sing-box did not create axtun0%s" % (": " + tail if tail else ""))
    return {"device": "axtun0", "mode": "masquerade", "local_ip": iface_addr("axtun0"),
            "endpoints": resolve4(v["server"]), "driver": "sing-box"}


def up_vless(profile):
    v = vless_fields(profile)
    if not v.get("server") or not v.get("uuid"):
        raise TunnelError("the profile has no server or uuid")
    if v.get("security") != "reality":
        return up_vless_singbox(profile, v)
    if v.get("security") == "reality" and not v.get("public_key"):
        raise TunnelError("the URL has no pbk, so REALITY cannot be verified")
    if v.get("security") == "reality" and not v.get("short_id"):
        raise TunnelError("the URL has no sid (short id)")
    binary = "xray" if which("xray") else ""
    if not binary:
        raise TunnelError("xray-core is not installed (it is the only client that "
                          "can verify REALITY pqv/mldsa65)")
    config = xray_config(v)
    path = write_profile_file(profile, "xray.json", json.dumps(config, indent=2) + "\n")
    down_vless(profile)
    rc, out = run([binary, "run", "-test", "-c", path], timeout=30)
    if rc != 0:
        tail = "\n".join(line for line in out.splitlines() if "Info" not in line)[-300:]
        raise TunnelError("xray rejected the configuration: %s" % tail.strip())
    log_path = os.path.join(PROFILE_DIR, "%s.xray.log" % profile["id"])
    try:
        with open(log_path, "ab", buffering=0) as handle:
            subprocess.Popen([binary, "run", "-c", path], stdout=handle,
                             stderr=subprocess.STDOUT, start_new_session=True)
    except OSError as exc:
        raise TunnelError("cannot start xray: %s" % exc)
    exit_ip = ""
    for _ in range(10):
        time.sleep(1.0)
        exit_ip = vless_probe_ip(6)
        if exit_ip:
            break
    if not exit_ip:
        tail = read_text(log_path)[-400:].strip()
        down_vless(profile)
        raise TunnelError("the VLESS handshake failed%s" % (": " + tail if tail else ""))
    return {"device": "", "mode": "redirect", "local_ip": "", "proxy_port": VLESS_TCP_PORT,
            "probe_port": VLESS_HTTP_PORT, "endpoints": resolve4(v["server"]),
            "driver": "xray", "exit_ip": exit_ip, "server_ip": ""}


def down_vless(profile):
    pid = os.path.join(PROFILE_DIR, "%s.xray.json" % (profile or {}).get("id", ""))
    run(["pkill", "-f", "xray run -c %s" % pid], timeout=10)
    run(["pkill", "-f", "sing-box run -c %s" % os.path.join(
        PROFILE_DIR, "%s.singbox.json" % (profile or {}).get("id", ""))], timeout=10)
    run(["ip", "link", "del", "axtun0"], timeout=10)


def up_openvpn(profile):
    text = profile.get("conf") or ""
    if not text:
        missing = [key for key in ("endpoint",) if not (profile.get(key) or "").strip()]
        if missing:
            raise TunnelError("missing fields: endpoint (or upload an .ovpn file)")
        server = profile["endpoint"].strip()
        lines = [
            "client",
            "dev axtun1",
            "dev-type tun",
            "proto %s" % (profile.get("proto") or "udp"),
            "remote %s %s" % (server, int(profile.get("port") or 1194)),
            "resolv-retry infinite",
            "nobind",
            "persist-key",
            "persist-tun",
            "remote-cert-tls server",
            "cipher AES-256-GCM",
            "auth SHA256",
            "verb 3",
        ]
        if profile.get("ca"):
            continue_from = write_profile_file(profile, "ca.crt", profile["ca"].strip() + "\n")
            lines.append("ca %s" % continue_from)
        text = "\n".join(lines) + "\n"
    path = write_profile_file(profile, "ovpn", text)
    if not which("openvpn"):
        raise TunnelError("openvpn is not installed")
    auth_file = ""
    if profile.get("username") or profile.get("password"):
        auth_file = write_profile_file(
            profile, "auth", "%s\n%s\n" % (profile.get("username") or "", profile.get("password") or ""))
    pid_file = os.path.join(RUN_DIR, "openvpn.pid")
    run(["pkill", "-f", "openvpn --config %s" % path], timeout=10)
    run(["ip", "link", "del", "axtun1"], timeout=10)
    cmd = ["openvpn", "--config", path, "--daemon", "axpi-openvpn",
           "--writepid", pid_file, "--dev", "axtun1", "--dev-type", "tun",
           "--route-nopull", "--pull-filter", "ignore", "redirect-gateway",
           # SoftEther pushes these; OpenVPN 2.6 rejects a pushed dhcp-option
           # (it is a server-side option there) and aborts option import.
           "--pull-filter", "ignore", "dhcp-option",
           "--pull-filter", "ignore", "block-outside-dns",
           "--pull-filter", "ignore", "register-dns",
           "--ping", "10", "--ping-restart", "60", "--auth-nocache", "--verb", "3"]
    if auth_file:
        cmd += ["--auth-user-pass", auth_file]
    rc, out = run(cmd, timeout=40)
    if rc != 0:
        raise TunnelError("openvpn failed to start: %s" % out[-300:])
    for _ in range(30):
        if link_exists("axtun1") and iface_addr("axtun1"):
            break
        time.sleep(0.5)
    if not link_exists("axtun1"):
        raise TunnelError("openvpn did not create axtun1 - check /var/log/airxpi/tunnel.log")
    return {"device": "axtun1", "mode": "masquerade", "local_ip": iface_addr("axtun1"),
            "endpoints": resolve4(parse_endpoint(profile)), "driver": "openvpn"}


def down_openvpn(profile):
    path = os.path.join(PROFILE_DIR, "%s.ovpn" % profile.get("id", ""))
    run(["pkill", "-f", "openvpn --config %s" % path], timeout=10)
    run(["ip", "link", "del", "axtun1"], timeout=10)


def up_ikev2(profile):
    for key in ("server", "username", "password"):
        if not (profile.get(key) or "").strip():
            raise TunnelError("missing fields: %s" % key)
    server = profile["server"].strip()
    local_id = (profile.get("local_id") or profile.get("username")).strip()
    remote_id = (profile.get("remote_id") or server).strip()
    proposals = (profile.get("proposals") or
                 "aes256-sha256-modp2048,aes128-sha256-modp2048,aes256-sha1-modp1024").strip()
    esp = (profile.get("esp_proposals") or
           "aes256-sha256,aes128-sha256,aes256-sha1,aes128-sha1").strip()
    use_psk = bool((profile.get("psk") or "").strip())
    if use_psk:
        local_auth, remote_auth = "psk", "psk"
        remote_id = (profile.get("remote_id") or "").strip() or "%any"
    else:
        local_auth, remote_auth = "eap-mschapv2", "pubkey"
    conn = f"""# generated by axtunnel - manual IKEv2 profile
connections {{
  axtunnel {{
    version = 2
    local_addrs = %any
    remote_addrs = {server}
    proposals = {proposals}
    local {{
      auth = {local_auth}
      id = {local_id}
      {"eap_id = " + profile['username'].strip() if not use_psk else ""}
    }}
    remote {{
      auth = {remote_auth}
      id = {remote_id}
    }}
    vips = 0.0.0.0
    dpd_delay = 30s
    dpd_timeout = 120s
    children {{
      axtunnel {{
        local_ts = 0.0.0.0/0
        remote_ts = 0.0.0.0/0
        esp_proposals = {esp}
        start_action = none
        dpd_action = restart
        close_action = none
      }}
    }}
  }}
}}
"""
    write_text("/etc/swanctl/conf.d/axtunnel.conf", conn, 0o600)
    if use_psk:
        secret = _esc(profile["psk"])
        secrets = ('secrets {\n  ike-axtunnel {\n    id = %s\n    secret = "%s"\n  }\n}\n'
                   % (remote_id, secret))
    else:
        secret = _esc(profile["password"])
        secrets = ('secrets {\n  eap-axtunnel {\n    id = %s\n    secret = "%s"\n  }\n}\n'
                   % (local_id, secret))
    write_text("/etc/swanctl/conf.d/axtunnel-secrets.conf", secrets, 0o600)
    ca = (profile.get("ca") or "").strip()
    ca_path = "/etc/swanctl/x509ca/axtunnel-ca.pem"
    if ca:
        write_text(ca_path, ca + "\n", 0o644)
    elif os.path.exists(ca_path):
        os.unlink(ca_path)
    if not which("swanctl"):
        raise TunnelError("strongSwan (swanctl) is not installed")
    run(["swanctl", "--load-creds"], timeout=40)
    rc, out = run(["swanctl", "--load-conns"], timeout=40)
    if rc != 0:
        raise TunnelError("strongSwan rejected the profile: %s" % out[-300:])
    run(["swanctl", "--terminate", "--ike", "axtunnel"], timeout=25)
    rc, out = run(["swanctl", "--initiate", "--child", "axtunnel", "--timeout", "20"], timeout=50)
    active = {}
    for _ in range(15):
        active = ikev2_state()
        if active.get("child") and active.get("vip"):
            break
        time.sleep(1)
    if not active.get("child") or not active.get("vip"):
        raise TunnelError("IKEv2 handshake failed: %s" % (out[-260:] or "no answer from the server"))
    gateway, wan = default_route()
    return {"device": wan, "mode": "snat", "local_ip": active["vip"],
            "endpoints": resolve4(server), "driver": "swanctl",
            "remote": active.get("remote", "")}


def down_ikev2(profile=None):
    run(["swanctl", "--terminate", "--ike", "axtunnel"], timeout=25)
    for path in ("/etc/swanctl/conf.d/axtunnel.conf", "/etc/swanctl/conf.d/axtunnel-secrets.conf"):
        try:
            os.unlink(path)
        except OSError:
            pass


def ikev2_state():
    rc, out = run(["swanctl", "--list-sas"], timeout=20)
    state = {"ike": False, "child": False, "vip": "", "remote": ""}
    current = False
    for line in out.splitlines():
        if re.match(r"^axtunnel.*: #\d+, ESTABLISHED", line):
            current = True
            state["ike"] = True
            continue
        if re.match(r"^\S.*: #\d+,", line):
            current = False
        if not current:
            continue
        if "INSTALLED" in line and "reqid" in line:
            state["child"] = True
        match = re.search(r"local\s+'[^']*'\s+@\s+[0-9.]+\[\d+\](?:\s+\[([0-9.]+)\])?", line)
        if match and match.group(1) and not state["vip"]:
            state["vip"] = match.group(1)
        match = re.search(r"remote\s+'[^']*'\s+@\s+([0-9.]+)\[", line)
        if match and not state["remote"]:
            state["remote"] = match.group(1)
    return state


def up_l2tp(profile):
    for key in ("server", "username", "password"):
        if not (profile.get(key) or "").strip():
            raise TunnelError("missing fields: %s" % key)
    server = profile["server"].strip()
    psk = (profile.get("psk") or "").strip()
    kernel_ipsec()
    write_text("/etc/ppp/options.axpi-l2tp", "\n".join([
        "ipcp-accept-local",
        "ipcp-accept-remote",
        "refuse-eap",
        "require-mschap-v2",
        "noccp",
        "noauth",
        "idle 0",
        "mtu %d" % int(profile.get("mtu") or cfg("mtu") or 1400),
        "mru %d" % int(profile.get("mtu") or cfg("mtu") or 1400),
        "nodefaultroute",
        "usepeerdns",
        "name %s" % profile["username"].strip(),
        "password %s" % profile["password"],
        "",
    ]), 0o600)
    write_text("/etc/xl2tpd/xl2tpd.conf", "\n".join([
        "[global]",
        "port = 1701",
        "access control = no",
        "",
        "[lac axpi]",
        "lns = %s" % server,
        "name = %s" % profile["username"].strip(),
        "ppp debug = no",
        "pppoptfile = /etc/ppp/options.axpi-l2tp",
        "length bit = yes",
        "redial = yes",
        "redial timeout = 10",
        "max redials = 3",
        "",
    ]), 0o600)
    if psk:
        write_text("/etc/swanctl/conf.d/axtunnel-l2tp.conf",
                   "connections {\n  axtunnel-l2tp {\n    version = 1\n"
                   "    local_addrs = %%any\n    remote_addrs = %s\n"
                   "    proposals = aes256-sha1-modp1024,aes128-sha1-modp1024,3des-sha1-modp1024\n"
                   "    local { auth = psk }\n    remote { auth = psk; id = %s }\n"
                   "    children {\n      axtunnel-l2tp {\n        mode = transport\n"
                   "        local_ts = dynamic\n        remote_ts = dynamic\n"
                   "        esp_proposals = aes256-sha1,aes128-sha1,3des-sha1\n"
                   "        start_action = trap\n        dpd_action = clear\n      }\n    }\n  }\n}\n"
                   % (server, server), 0o600)
        write_text("/etc/swanctl/conf.d/axtunnel-l2tp-secrets.conf",
                   'secrets {\n  ike-axtunnel-l2tp {\n    id = %s\n    secret = "%s"\n  }\n}\n'
                   % (server, _esc(psk)), 0o600)
        run(["swanctl", "--load-creds"], timeout=40)
        run(["swanctl", "--load-conns"], timeout=40)
        run(["swanctl", "--initiate", "--ike", "axtunnel-l2tp", "--timeout", "20"], timeout=40)
    before = links()
    run(["systemctl", "restart", "xl2tpd"], timeout=45)
    time.sleep(1.0)
    rc, out = run(["xl2tpd-control", "connect", "axpi"], timeout=20)
    if rc != 0:
        # older builds only expose the control FIFO
        try:
            with open("/var/run/xl2tpd/l2tp-control", "w") as fifo:
                fifo.write("c axpi\n")
            rc = 0
        except OSError as exc:
            raise TunnelError("cannot talk to xl2tpd: %s" % exc)
    device = ""
    for _ in range(30):
        device = new_ppp_iface(before)
        if device and iface_addr(device):
            break
        time.sleep(1)
    if not device:
        raise TunnelError("L2TP did not bring up a ppp interface")
    return {"device": device, "mode": "masquerade", "local_ip": iface_addr(device),
            "endpoints": resolve4(server), "driver": "xl2tpd"}


def down_l2tp(profile=None):
    run(["xl2tpd-control", "disconnect", "axpi"], timeout=15)
    run(["systemctl", "stop", "xl2tpd"], timeout=25)
    run(["swanctl", "--terminate", "--ike", "axtunnel-l2tp"], timeout=20)
    for path in ("/etc/swanctl/conf.d/axtunnel-l2tp.conf",
                 "/etc/swanctl/conf.d/axtunnel-l2tp-secrets.conf"):
        try:
            os.unlink(path)
        except OSError:
            pass


def up_sstp(profile):
    for key in ("server", "username", "password"):
        if not (profile.get(key) or "").strip():
            raise TunnelError("missing fields: %s" % key)
    if not which("sstpc"):
        raise TunnelError("sstp-client is not installed")
    server = profile["server"].strip()
    port = int(profile.get("port") or 443)
    # --nolaunchpppd is mandatory here: without it sstpc starts its *own* pppd
    # on the pty and the outer pppd only sees "Modem hangup" (ppp0 never comes
    # up even though the SSTP session itself is established).
    pty = "sstpc --nolaunchpppd --log-level 1 --cert-warn --user %s --password %s %s:%d" % (
        shlex_quote(profile["username"].strip()), shlex_quote(profile["password"]), server, port)
    write_text("/etc/ppp/peers/axpi-sstp", "\n".join([
        "pty \"%s\"" % pty,
        "noauth",
        # sstpc's --user/--password only cover the HTTP layer; the PPP peer
        # inside the tunnel authenticates with MS-CHAPv2 and needs the same
        # credentials here, otherwise pppd dies with "I couldn't find any
        # suitable secret (password) for it to use".
        "user %s" % shlex_quote(profile["username"].strip()),
        "password %s" % shlex_quote(profile["password"]),
        "refuse-eap",
        "require-mschap-v2",
        "nodefaultroute",
        "usepeerdns",
        "mtu %d" % int(profile.get("mtu") or cfg("mtu") or 1400),
        "mru %d" % int(profile.get("mtu") or cfg("mtu") or 1400),
        "persist",
        "maxfail 2",
        "",
    ]), 0o600)
    write_ppp_secrets(profile["username"].strip(), profile["password"])
    before = links()
    rc, out = run(["pppd", "call", "axpi-sstp"], timeout=40)
    if rc != 0:
        raise TunnelError("sstp failed to start: %s" % out[-300:])
    device = ""
    for _ in range(30):
        device = new_ppp_iface(before)
        if device and iface_addr(device):
            break
        time.sleep(1)
    if not device:
        raise TunnelError("SSTP did not bring up a ppp interface")
    return {"device": device, "mode": "masquerade", "local_ip": iface_addr(device),
            "endpoints": resolve4(server), "driver": "sstpc"}


def down_sstp(profile=None):
    run(["pkill", "-f", "pppd call axpi-sstp"], timeout=10)
    run(["pkill", "-f", "sstpc .*--user"], timeout=10)


def write_ppp_secrets(username, password):
    """Give pppd a secret for *any* peer name.

    SoftEther's SSTP endpoint asks for MS-CHAPv2 before it tells us its name, so
    ``user``/``password`` in the peers file alone leaves pppd with "I couldn't
    find any suitable secret (password) for it to use".  A ``*`` server entry in
    chap-secrets/pap-secrets is the documented fix.
    """
    entry = '"%s" * "%s" *' % (username.replace('"', ''), password.replace('"', ''))
    begin, end = "# airxpi begin", "# airxpi end"
    for path in ("/etc/ppp/chap-secrets", "/etc/ppp/pap-secrets"):
        body = read_text(path)
        keep, inside = [], False
        for line in body.splitlines():
            if line.strip() == begin:
                inside = True
                continue
            if line.strip() == end:
                inside = False
                continue
            if not inside:
                keep.append(line)
        while keep and not keep[-1].strip():
            keep.pop()
        keep += [begin, entry, end, ""]
        write_text(path, "\n".join(keep), 0o600)


def shlex_quote(value):
    return "'" + str(value or "").replace("'", "'\\''") + "'"


ADAPTERS = {
    "ikev2": {"up": up_ikev2, "down": down_ikev2, "alive": lambda p: ikev2_state()["child"]},
    "wireguard": {"up": lambda p: up_wireguard(p, False),
                  "down": lambda p: down_wireguard(p, False),
                  "alive": lambda p: link_exists("axpi0")},
    "amneziawg": {"up": lambda p: up_wireguard(p, True),
                  "down": lambda p: down_wireguard(p, True),
                  "alive": lambda p: link_exists("axpi0")},
    "vless": {"up": up_vless, "down": down_vless,
              "alive": lambda p: bool(run(["pgrep", "-f", "xray run -c %s" % os.path.join(
                  PROFILE_DIR, "%s.xray.json" % (p or {}).get("id", ""))], timeout=10)[1].strip())
              or link_exists("axtun0")},
    "openvpn": {"up": up_openvpn, "down": down_openvpn, "alive": lambda p: link_exists("axtun1")},
    "l2tp": {"up": up_l2tp, "down": down_l2tp, "alive": lambda p: bool(iface_addr("ppp0"))},
    "sstp": {"up": up_sstp, "down": down_sstp, "alive": lambda p: bool(iface_addr("ppp0"))},
}


# ------------------------------------------------------------------- routing
def lan_iface():
    name = cfg("lan_iface") or "br0"
    return name if link_exists(name) else "br0"


def redirect_ruleset(tunnel):
    """LAN traffic handed to the xray redirect socket (no tunnel device).

    ``redirect`` is used instead of TPROXY on this kernel: the TPROXY verdict
    never delivered the frames to a socket bound on 127.0.0.1, while a plain
    NAT redirect to the dokodemo-door port does - verified with a veth client
    on br0.  QUIC is rejected so browsers fall back to TCP instead of leaking
    outside the tunnel.
    """
    lan = lan_iface()
    lan_cidr = iface_cidr(lan) or "192.168.168.0/24"
    wan = default_route()[1]
    exclude = ["127.0.0.0/8", "224.0.0.0/4", "255.255.255.255/32", lan_cidr]
    for address in tunnel.get("endpoints") or []:
        entry = address + "/32"
        if entry not in exclude:
            exclude.append(entry)
    port = int(tunnel.get("proxy_port") or VLESS_TCP_PORT)
    rules = [
        "table inet axtunnel {",
        "\tset exclude4 {",
        "\t\ttype ipv4_addr",
        "\t\tflags interval",
        "\t\tauto-merge",
        "\t\telements = { %s }" % ", ".join(exclude),
        "\t}",
        "\tchain forward {",
        "\t\ttype filter hook forward priority filter; policy accept;",
        '\t\tiifname "%s" accept' % lan,
        "\t}",
        # the proxy port is open on the LAN address only so REDIRECT can reach
        # it; anything that is not a DNAT'd connection is refused, which keeps
        # an open proxy off the wire.
        "\tchain inbound {",
        "\t\ttype filter hook input priority filter; policy accept;",
        '\t\tiifname "%s" tcp dport %d ct status dnat accept' % (lan, port),
        '\t\tiifname "%s" tcp dport %d drop' % (lan, port),
        "\t}",
    ]
    if cfg("block_ipv6") and wan:
        rules += [
            "\tchain fwd6 {",
            "\t\ttype filter hook forward priority filter; policy accept;",
            '\t\tiifname "%s" oifname "%s" meta nfproto ipv6 drop' % (lan, wan),
            "\t}",
        ]
    rules += [
        "}",
        "table ip axtunnel_redirect {",
        "\tset exclude4 {",
        "\t\ttype ipv4_addr",
        "\t\tflags interval",
        "\t\tauto-merge",
        "\t\telements = { %s }" % ", ".join(exclude),
        "\t}",
        "\tchain pre {",
        "\t\ttype nat hook prerouting priority dstnat; policy accept;",
        '\t\tiifname != "%s" return' % lan,
        "\t\tip daddr @exclude4 return",
        "\t\tmeta l4proto tcp counter redirect to :%d" % port,
        "\t\tudp dport 443 reject",
        "\t}",
        "}",
        "",
    ]
    return "\n".join(rules) + "\n"


def ruleset(tunnel):
    if tunnel.get("mode") == "redirect":
        return redirect_ruleset(tunnel)
    mark = cfg("mark")
    table = int(cfg("table"))
    mtu = int(cfg("mtu") or 1400)
    mss = max(1200, mtu - 80)
    lan = lan_iface()
    lan_cidr = iface_cidr(lan) or "192.168.168.0/24"
    wan = default_route()[1]
    exclude = ["127.0.0.0/8", "224.0.0.0/4", "255.255.255.255/32", lan_cidr]
    for address in tunnel.get("endpoints") or []:
        entry = address + "/32"
        if entry not in exclude:
            exclude.append(entry)
    if tunnel.get("local_ip"):
        exclude.append(tunnel["local_ip"] + "/32")
    rules = [
        "table inet axtunnel {",
        "\tset exclude4 {",
        "\t\ttype ipv4_addr",
        "\t\tflags interval",
        "\t\tauto-merge",
        "\t\telements = { %s }" % ", ".join(exclude),
        "\t}",
        "\tchain markin {",
        "\t\ttype filter hook prerouting priority mangle; policy accept;",
        '\t\tiifname != "%s" return' % lan,
        "\t\tip daddr @exclude4 return",
        "\t\tmeta mark set %s counter" % mark,
        "\t}",
        "\tchain mss {",
        "\t\ttype filter hook postrouting priority mangle; policy accept;",
        "\t\tmeta mark %s tcp flags syn tcp option maxseg size set %d" % (mark, mss),
        "\t}",
    ]
    if cfg("block_ipv6") and wan:
        rules += [
            "\tchain fwd6 {",
            "\t\ttype filter hook forward priority filter; policy accept;",
            '\t\tiifname "%s" oifname "%s" meta nfproto ipv6 drop' % (lan, wan),
            "\t}",
        ]
    rules += [
        "}",
        "table ip axtunnel_nat {",
        "\tchain post {",
        "\t\ttype nat hook postrouting priority srcnat; policy accept;",
    ]
    if tunnel.get("mode") == "snat" and tunnel.get("local_ip"):
        rules.append('\t\toifname "%s" meta mark %s counter snat ip to %s'
                     % (tunnel.get("device") or wan, mark, tunnel["local_ip"]))
    else:
        rules.append('\t\toifname "%s" meta mark %s counter masquerade'
                     % (tunnel.get("device") or "", mark))
    rules += ["\t}", "}", ""]
    return "\n".join(rules) + "\n"


def routing_apply(tunnel):
    with ROUTING_LOCK:
        redirect = tunnel.get("mode") == "redirect"
        device = tunnel.get("device") or ""
        if not redirect and (not device or not link_exists(device)):
            return {"ok": False, "error": "tunnel interface %s is missing" % (device or "-")}
        table = int(cfg("table"))
        mark = cfg("mark")
        text = ruleset(tunnel)
        path = os.path.join(RUN_DIR, "axtunnel.nft")
        write_text(path, text, 0o600)
        rc, out = run(["nft", "-c", "-f", path], timeout=20)
        if rc != 0:
            log("routing: ruleset rejected: %s" % out[-200:])
            return {"ok": False, "error": "nftables rejected the ruleset"}
        batch = ""
        if run(["nft", "list", "table", "inet", "axtunnel"], timeout=10)[0] == 0:
            batch += "delete table inet axtunnel\n"
        if run(["nft", "list", "table", "ip", "axtunnel_nat"], timeout=10)[0] == 0:
            batch += "delete table ip axtunnel_nat\n"
        if run(["nft", "list", "table", "ip", "axtunnel_redirect"], timeout=10)[0] == 0:
            batch += "delete table ip axtunnel_redirect\n"
        bpath = os.path.join(RUN_DIR, "axtunnel-apply.nft")
        write_text(bpath, batch + text, 0o600)
        rc, out = run(["nft", "-f", bpath], timeout=20)
        if rc != 0:
            log("routing: apply failed: %s" % out[-200:])
            return {"ok": False, "error": "cannot apply the nftables rules"}
        if redirect:
            # no route, no mark: the redirect socket dials the server itself
            priority = int(cfg("rule_priority"))
            for _ in range(4):
                run(["ip", "rule", "del", "fwmark", mark, "lookup", str(table),
                     "priority", str(priority)], timeout=10)
            run(["ip", "route", "flush", "table", str(table)], timeout=10)
            log("routing: redirect on 127.0.0.1:%d" % int(tunnel.get("proxy_port") or VLESS_TCP_PORT))
            return {"ok": True, "device": "", "redirect": True}
        if tunnel.get("mode") == "snat":
            gateway, wan = default_route()
            route = (["ip", "route", "replace", "default", "via", gateway, "dev", wan, "table", str(table)]
                     if gateway else ["ip", "route", "replace", "default", "dev", wan, "table", str(table)])
        else:
            route = ["ip", "route", "replace", "default", "dev", device, "table", str(table)]
        rc, out = run(route, timeout=15)
        if rc != 0:
            return {"ok": False, "error": "cannot add the tunnel route"}
        priority = int(cfg("rule_priority"))
        for _ in range(4):
            run(["ip", "rule", "del", "fwmark", mark, "lookup", str(table), "priority", str(priority)], timeout=10)
        rc, out = run(["ip", "rule", "add", "fwmark", mark, "lookup", str(table),
                       "priority", str(priority)], timeout=15)
        if rc != 0:
            return {"ok": False, "error": "cannot add the ip rule"}
        log("routing: active via %s (%s)" % (device, tunnel.get("local_ip") or "-"))
        return {"ok": True, "device": device}


def routing_clear():
    with ROUTING_LOCK:
        table = int(cfg("table"))
        mark = cfg("mark")
        priority = int(cfg("rule_priority"))
        run(["nft", "delete", "table", "inet", "axtunnel"], timeout=15)
        run(["nft", "delete", "table", "ip", "axtunnel_nat"], timeout=15)
        run(["nft", "delete", "table", "ip", "axtunnel_redirect"], timeout=15)
        run(["nft", "delete", "table", "inet", "axtunnel_probe"], timeout=15)
        for _ in range(4):
            run(["ip", "rule", "del", "fwmark", mark, "lookup", str(table),
                 "priority", str(priority)], timeout=10)
        run(["ip", "route", "flush", "table", str(table)], timeout=10)


def routing_active():
    st = state_read()
    if st.get("mode") == "redirect":
        return run(["nft", "list", "table", "ip", "axtunnel_redirect"], timeout=10)[0] == 0
    table = int(cfg("table"))
    if run(["nft", "list", "table", "inet", "axtunnel"], timeout=10)[0] != 0:
        return False
    rc, out = run(["ip", "rule", "show"], timeout=10)
    if "fwmark %s lookup %d" % (cfg("mark"), table) not in out:
        return False
    return run(["ip", "route", "show", "table", str(table)], timeout=10)[0] == 0


# ------------------------------------------------------------------ selftest
PROBE = "https://1.1.1.1/cdn-cgi/trace"


def probe_ip(marked):
    if marked:
        run(["nft", "delete", "table", "inet", "axtunnel_probe"], timeout=10)
        run(["nft", "add", "table", "inet", "axtunnel_probe"], timeout=10)
        run(["nft", "add", "chain", "inet", "axtunnel_probe", "out",
             "{ type route hook output priority mangle; policy accept; }"], timeout=10)
        run(["nft", "add", "rule", "inet", "axtunnel_probe", "out",
             "ip daddr 1.1.1.1", "meta", "mark", "set", cfg("mark")], timeout=10)
    rc, out = run(["curl", "-fsS", "--max-time", "12", PROBE], timeout=20)
    if marked:
        run(["nft", "delete", "table", "inet", "axtunnel_probe"], timeout=10)
    match = re.search(r"ip=([0-9.]+)", out)
    return match.group(1) if match else ""


def selftest(force=False):
    st = state_read()
    # connect() verifies *before* it publishes state="connected"; without this
    # flag every successful connection was recorded with the bogus error
    # "tunnel is down", which is what the panel then showed for manual setups.
    if not force and st.get("state") != "connected":
        return {"ok": False, "detail": "tunnel is down"}
    direct = probe_ip(False)
    if st.get("mode") == "redirect":
        # the redirect socket is the only path into xray from this box: asking
        # through its http inbound proves the handshake without touching the
        # LAN routing (which is only installed for forwarded traffic)
        marked = vless_probe_ip(10)
    else:
        marked = probe_ip(True)
    if not marked:
        return {"ok": False, "detail": "no answer through the tunnel", "direct": direct}
    if direct and direct == marked:
        return {"ok": False, "detail": "traffic still uses the uplink", "direct": direct}
    return {"ok": True, "ip": marked, "direct": direct, "detail": "exit verified"}


# ------------------------------------------------------------------- connect
def connect(profile_id, verify=True):
    profile = find_profile(profile_id)
    if not profile:
        return {"ok": False, "error": "unknown profile"}
    proto = profile.get("protocol")
    adapter = ADAPTERS.get(proto)
    if not adapter:
        return {"ok": False, "error": "unsupported protocol %s" % proto}
    with LOCK:
        state_patch(state="connecting", profile=profile_id, protocol=proto,
                    name=profile.get("name", ""), error="", checked_at=int(time.time()))
        # vpnexit and axtunnel must never steer the LAN at the same time: they
        # use different marks but the same idea, and a leftover VPN exit would
        # send the marked packets of one manager into the other's tunnel.
        if os.path.exists("/usr/local/sbin/vpnexit"):
            run(["/usr/local/sbin/vpnexit", "disconnect"], timeout=25)
        routing_clear()
        try:
            adapter["down"](profile)
        except Exception:  # noqa: BLE001
            pass
        try:
            tunnel = adapter["up"](profile)
        except TunnelError as exc:
            log("connect: %s failed: %s" % (proto, exc))
            state_patch(state="error", error=str(exc), checked_at=int(time.time()))
            routing_clear()
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            log("connect: %s crashed: %r" % (proto, exc))
            state_patch(state="error", error=repr(exc), checked_at=int(time.time()))
            routing_clear()
            return {"ok": False, "error": repr(exc)}
        state_patch(device=tunnel.get("device", ""), local_ip=tunnel.get("local_ip", ""),
                    mode=tunnel.get("mode", ""), driver=tunnel.get("driver", ""),
                    server=parse_endpoint(profile), since=int(time.time()))
        routing = {"active": False}
        if cfg("share_lan"):
            result = routing_apply(tunnel)
            routing["active"] = bool(result.get("ok"))
            if not result.get("ok"):
                log("connect: routing failed: %s" % result.get("error"))
        if verify:
            # WireGuard needs a handshake and the userspace/tun drivers need a
            # moment before the first packet is carried; a single probe right
            # after ``up`` reported "no answer through the tunnel" for tunnels
            # that were in fact working (and blank in the panel).
            test = {"ok": False, "detail": "no answer through the tunnel"}
            for _ in range(6):
                test = selftest(True)
                if test.get("ok") or test.get("detail") == "traffic still uses the uplink":
                    break
                time.sleep(2.0)
        else:
            test = {"ok": False, "detail": "not tested"}
        state_patch(state="connected", exit_ip=test.get("ip", "") or tunnel.get("exit_ip", ""),
                    error="" if test.get("ok") else test.get("detail", ""),
                    routing=routing["active"], checked_at=int(time.time()), attempts=0)
        log("connect: %s up on %s, exit %s" % (proto, tunnel.get("device"), test.get("ip") or "-"))
        return {"ok": True, "device": tunnel.get("device"), "exit_ip": test.get("ip", ""),
                "detail": test.get("detail", "")}


def disconnect(reason=""):
    st = state_read()
    profile = find_profile(st.get("profile", "")) if st.get("profile") else None
    proto = st.get("protocol") or (profile or {}).get("protocol") or ""
    if proto in ADAPTERS:
        try:
            ADAPTERS[proto]["down"](profile)
        except Exception as exc:  # noqa: BLE001
            log("disconnect: %s teardown: %r" % (proto, exc))
    else:
        for name, adapter in ADAPTERS.items():
            try:
                adapter["down"]({})
            except Exception:  # noqa: BLE001
                pass
    routing_clear()
    if reason:
        log("disconnect: %s" % reason)
    state_patch(state="idle", error="", exit_ip="", device="", local_ip="",
                checked_at=int(time.time()), routing=False)
    return {"ok": True}


def status():
    st = state_read()
    profile = find_profile(st.get("profile", "")) if st.get("profile") else None
    out = {
        "state": st.get("state", "idle"),
        "profile": st.get("profile", ""),
        "name": (profile or {}).get("name", st.get("name", "")),
        "protocol": st.get("protocol", ""),
        "label": LABELS.get(st.get("protocol", ""), ""),
        "device": st.get("device", ""),
        "local_ip": st.get("local_ip", ""),
        "exit_ip": st.get("exit_ip", ""),
        "error": st.get("error", ""),
        "since": int(st.get("since", 0) or 0),
        "routing": {"active": routing_active(), "share_lan": bool(cfg("share_lan"))},
        "capabilities": capabilities(),
    }
    if out["state"] == "connected" and not out["routing"]["active"] and out["routing"]["share_lan"]:
        out["warning"] = "routing rules are missing"
    return out


# ------------------------------------------------------------------- profile
def upsert_profile(payload):
    protocol = str(payload.get("protocol") or "").strip().lower()
    if protocol not in PROTOCOLS:
        return {"ok": False, "error": "unsupported protocol"}, None
    profile_id = str(payload.get("id") or "").strip()
    items = profiles()
    current = find_profile(profile_id) if profile_id else None
    if profile_id and not current:
        return {"ok": False, "error": "unknown profile"}, None
    base = dict(current or {})
    name = str(payload.get("name") or base.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "name is required"}, None
    if len(name) > 48:
        return {"ok": False, "error": "name is too long"}, None
    base.update({"name": name, "protocol": protocol, "updated_at": int(time.time())})
    for key, value in payload.items():
        if key in ("id", "protocol", "updated_at", "ready", "conf_set"):
            continue
        if isinstance(value, str):
            value = value.strip()
        if key in SECRET_FIELDS.get(protocol, ()) and value in ("", None):
            continue  # an empty secret keeps the stored one
        base[key] = value
    conf = str(payload.get("conf") or "").strip()
    if conf:
        if len(conf) > 256 * 1024:
            return {"ok": False, "error": "config file is too large"}, None
        base["conf"] = normalise_uploaded_conf(conf, protocol) if protocol in (
            "wireguard", "amneziawg") else conf + "\n"
    if protocol in ("wireguard", "amneziawg") and not base.get("conf"):
        missing = [key for key in ("private_key", "peer_public_key", "endpoint")
                   if not str(base.get(key) or "").strip()]
        if missing:
            return {"ok": False, "error": "missing fields: %s" % ", ".join(missing)}, None
    if protocol == "vless":
        # a pasted vless:// URL is the normal way to add this profile; keep the
        # URL but fold every parameter it carries into the stored fields so the
        # panel shows them and the client gets sni/sid/fp/pqv.
        parsed = vless_parse(base.get("conf") or "")
        if not parsed.get("error"):
            for key in ("server", "uuid", "public_key", "short_id", "sni", "fingerprint",
                        "flow", "security", "network", "path", "host_header", "service",
                        "spx", "pqv"):
                if not str(base.get(key) or "").strip() and parsed.get(key):
                    base[key] = parsed[key]
            if not str(base.get("port") or "").strip() and parsed.get("port"):
                base["port"] = parsed["port"]
        needed = ["server", "uuid"]
        # a plain VLESS inbound (security none/tls) has no REALITY key at all
        if str(base.get("security") or "reality").lower() == "reality":
            needed.append("public_key")
        missing = [key for key in needed if not str(base.get(key) or "").strip()]
        if missing:
            return {"ok": False, "error": "missing fields: %s" % ", ".join(missing)}, None
    if protocol == "ikev2":
        missing = [] if str(base.get("server") or "").strip() else ["server"]
        if not str(base.get("psk") or "").strip():
            # EAP-MSCHAPv2 logins need a user name and a password; a pure
            # PSK profile only needs the pre-shared key.
            missing += [key for key in ("username", "password")
                        if not str(base.get(key) or "").strip()]
        if missing:
            return {"ok": False, "error": "missing fields: %s" % ", ".join(missing)}, None
    if protocol in ("l2tp", "sstp"):
        missing = [key for key in ("server", "username", "password")
                   if not str(base.get(key) or "").strip()]
        if missing:
            return {"ok": False, "error": "missing fields: %s" % ", ".join(missing)}, None
    if protocol == "openvpn" and not base.get("conf") and not base.get("endpoint"):
        return {"ok": False, "error": "upload an .ovpn file or give an endpoint"}, None
    if not base.get("id"):
        base["id"] = new_id(base)
    base["ready"] = True
    items = [item for item in items if item.get("id") != base["id"]]
    items.append(base)
    items.sort(key=lambda item: (item.get("protocol", ""), item.get("name", "")))
    save_profiles(items)
    log("profile saved: %s (%s)" % (base["name"], protocol))
    return {"ok": True, "profile": public_profile(base)}, base


def delete_profile(profile_id):
    items = profiles()
    target = find_profile(profile_id)
    if not target:
        return {"ok": False, "error": "unknown profile"}
    st = state_read()
    if st.get("profile") == profile_id:
        disconnect("profile removed")
    for suffix in ("wg.conf", "awg.conf", "ovpn", "singbox.json", "auth", "ca.crt"):
        path = os.path.join(PROFILE_DIR, "%s.%s" % (profile_id, suffix))
        if os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass
    save_profiles([item for item in items if item.get("id") != profile_id])
    return {"ok": True}


def settings():
    data = cfg()
    data.pop("profiles", None)
    data["capabilities"] = capabilities()
    data["version"] = "1.0.0"
    return data


# ---------------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    server_version = "axtunnel/1.0"

    def log_message(self, *args):
        return

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _body(self):
        try:
            size = int(self.headers.get("Content-Length") or 0)
            if not size:
                return {}
            return json.loads(self.rfile.read(size).decode("utf-8", "replace") or "{}")
        except (ValueError, OSError):
            return {}

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/state":
            return self._json({"ok": True, "status": status(), "profiles": public_profiles(),
                               "settings": settings()})
        if path == "/profiles":
            return self._json({"ok": True, "items": public_profiles(),
                               "capabilities": capabilities()})
        if path == "/profile":
            profile_id = self.path.split("id=")[-1].split("&")[0] if "id=" in self.path else ""
            item = find_profile(profile_id)
            if not item:
                return self._json({"ok": False, "error": "unknown profile"}, 404)
            return self._json({"ok": True, "profile": public_profile(item, reveal=True)})
        if path == "/capabilities":
            return self._json({"ok": True, "capabilities": capabilities()})
        if path == "/log":
            return self._json({"ok": True, "text": read_text(LOG)[-8000:]})
        if path == "/health":
            return self._json({"ok": True, "service": "axtunnel"})
        return self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._body()
        if path == "/profile":
            result, _ = upsert_profile(body)
            return self._json(result, 200 if result.get("ok") else 400)
        if path == "/profile/delete":
            result = delete_profile(str(body.get("id") or ""))
            return self._json(result, 200 if result.get("ok") else 400)
        if path == "/connect":
            profile_id = str(body.get("id") or "")
            if not find_profile(profile_id):
                return self._json({"ok": False, "error": "unknown profile"}, 400)
            if state_read().get("state") == "connecting":
                return self._json({"ok": False, "error": "busy: a connection attempt is running"}, 409)
            state_patch(state="connecting", profile=profile_id, error="", checked_at=int(time.time()))
            threading.Thread(target=lambda: connect(profile_id, True), daemon=True).start()
            return self._json({"ok": True, "async": True, "state": "connecting"})
        if path == "/disconnect":
            return self._json(disconnect("user request"))
        if path == "/selftest":
            result = selftest(True)
            if result.get("ok"):
                state_patch(exit_ip=result.get("ip", ""), checked_at=int(time.time()))
            return self._json({"ok": result.get("ok", False), "result": result})
        if path == "/settings":
            patch = {}
            for key in ("share_lan", "block_ipv6", "auto_reconnect"):
                if key in body:
                    patch[key] = bool(body[key])
            if "mtu" in body:
                try:
                    patch["mtu"] = max(1200, min(1420, int(body["mtu"])))
                except (TypeError, ValueError):
                    pass
            cfg_set(**patch)
            st = state_read()
            if st.get("state") == "connected" and st.get("device"):
                if cfg("share_lan"):
                    routing_apply({"device": st.get("device"), "local_ip": st.get("local_ip"),
                                   "mode": st.get("mode"), "endpoints": []})
                else:
                    routing_clear()
            return self._json({"ok": True, "settings": settings()})
        return self._json({"ok": False, "error": "not found"}, 404)


# ------------------------------------------------------------------ watchdog
def supervise_once():
    st = state_read()
    if st.get("state") == "error":
        if not cfg("auto_reconnect"):
            return
        if time.time() - int(st.get("checked_at", 0) or 0) < 120:
            return
        if st.get("profile"):
            log("watchdog: retrying %s" % st.get("profile"))
            connect(st["profile"], verify=False)
        return
    if st.get("state") != "connected":
        return
    profile = find_profile(st.get("profile", ""))
    adapter = ADAPTERS.get((profile or {}).get("protocol", ""))
    if not profile or not adapter:
        return
    try:
        alive = adapter["alive"](profile)
    except Exception:  # noqa: BLE001
        alive = False
    if alive:
        if cfg("share_lan") and not routing_active() and st.get("device"):
            routing_apply({"device": st.get("device"), "local_ip": st.get("local_ip"),
                           "mode": st.get("mode"), "endpoints": []})
            log("watchdog: routing rules restored")
        return
    attempts = int(st.get("attempts", 0) or 0) + 1
    log("watchdog: tunnel lost (attempt %d)" % attempts)
    routing_clear()
    if not cfg("auto_reconnect") or attempts > 5:
        state_patch(state="error", error="tunnel lost", attempts=attempts,
                    checked_at=int(time.time()))
        return
    state_patch(attempts=attempts, checked_at=int(time.time()))
    connect(st["profile"], verify=False)


def supervise():
    ensure_dirs()
    if state_read().get("state") == "connecting":
        state_patch(state="idle")
    log("supervisor started")
    while True:
        try:
            supervise_once()
        except Exception as exc:  # noqa: BLE001
            log("watchdog error: %r" % (exc,))
        time.sleep(20)


def serve(host="127.0.0.1", port=PORT):
    ensure_dirs()
    threading.Thread(target=supervise, daemon=True).start()
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    log("api listening on %s:%d" % (host, port))
    server.serve_forever()


def main(argv):
    ensure_dirs()
    cmd = argv[1] if len(argv) > 1 else "state"
    if cmd == "serve":
        serve(port=int(argv[2]) if len(argv) > 2 else PORT)
    elif cmd == "supervise":
        supervise()
    elif cmd == "state":
        print(json.dumps({"status": status(), "profiles": public_profiles()}, indent=2))
    elif cmd == "connect":
        print(json.dumps(connect(argv[2], True)))
    elif cmd == "disconnect":
        print(json.dumps(disconnect("cli")))
    elif cmd == "selftest":
        print(json.dumps(selftest()))
    elif cmd == "capabilities":
        print(json.dumps(capabilities(), indent=2))
    else:
        print("usage: axtunnel {serve|supervise|state|connect ID|disconnect|selftest|capabilities}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
