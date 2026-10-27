#!/usr/bin/env python3
"""axpanel - the single web control panel of the AirXPi appliance.

It fronts three local services and adds the appliance-level pieces the stock
panels do not have:

    :8090  airxplay2  AirPlay 2 receiver (shairport-sync supervisor)
    :8088  vpnexit    IKEv2 exit switcher (token protected)
    :8079  axnetd     uplink / bridge / access point

Everything the LAN sees is this process: one password, one session cookie,
one JSON API, one single-page UI.  Standard library only.
"""

import hashlib
import hmac
import json
import os
import secrets
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import common as c

PBKDF2_ROUNDS = 200_000
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"
COOKIE = "axpi"
SESSION_HOURS = 12
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
}
POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="axproxy")


# --------------------------------------------------------------------------
# credentials
# --------------------------------------------------------------------------
def _hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS)
    return "pbkdf2_sha256$%d$%s$%s" % (PBKDF2_ROUNDS, salt, digest.hex())


def _verify(password, stored):
    try:
        _, rounds, salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(calc.hex(), digest)
    except (ValueError, AttributeError):
        return False


def panel_config():
    data = c.load_json(c.PANEL_CONF, {})
    changed = False
    if not data.get("password_hash"):
        data["password_hash"] = _hash(DEFAULT_PASSWORD)
        data["default_password"] = True
        changed = True
    if not data.get("username"):
        data["username"] = DEFAULT_USER
        changed = True
    if not data.get("secret"):
        data["secret"] = secrets.token_hex(32)
        changed = True
    if not data.get("api_token"):
        data["api_token"] = secrets.token_hex(16)
        changed = True
    data.setdefault("language", c.config()["device"].get("language", "en"))
    if changed:
        c.save_json(c.PANEL_CONF, data, 0o600)
    return data


def issue_token(secret):
    expires = str(int(time.time()) + SESSION_HOURS * 3600)
    signature = hmac.new(secret.encode(), expires.encode(), hashlib.sha256).hexdigest()[:32]
    return "%s.%s" % (expires, signature)


def token_valid(secret, token):
    try:
        expires, signature = token.split(".", 1)
        if int(expires) < time.time():
            return False
        expected = hmac.new(secret.encode(), expires.encode(), hashlib.sha256).hexdigest()[:32]
        return hmac.compare_digest(signature, expected)
    except (ValueError, AttributeError):
        return False


def set_password(password):
    if len(password or "") < 8:
        return {"ok": False, "error": "password must be at least 8 characters"}
    data = panel_config()
    data["password_hash"] = _hash(password)
    data["default_password"] = False
    c.save_json(c.PANEL_CONF, data, 0o600)
    return {"ok": True}


# --------------------------------------------------------------------------
# local service calls
# --------------------------------------------------------------------------
def http_json(url, payload=None, headers=None, timeout=8):
    data = None
    request_headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode()
        request_headers["Content-Type"] = "application/json"
    request_headers.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=request_headers,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            try:
                return json.loads(body.decode("utf-8", "replace") or "{}")
            except ValueError:
                return {"ok": False, "error": "bad json from %s" % url}
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            data = json.loads(body.decode("utf-8", "replace") or "{}")
        except ValueError:
            data = {"ok": False, "error": "http %d" % exc.code}
        data.setdefault("ok", False)
        data["_status"] = exc.code
        return data
    except (urllib.error.URLError, OSError) as exc:
        return {"ok": False, "error": "unreachable: %s" % getattr(exc, "reason", exc)}


def vpn_token():
    return c.load_json(c.VPN_CONF, {}).get("token", "")


def vpn_call(endpoint, payload=None, timeout=20):
    token = vpn_token()
    if not token:
        return {"ok": False, "error": "vpnexit is not configured"}
    url = "http://127.0.0.1:%d/api/%s" % (c.VPN_PORT, endpoint)
    return http_json(url, payload, {"X-Auth-Token": token}, timeout)


def net_call(endpoint, payload=None):
    return http_json("http://127.0.0.1:%d/%s" % (c.AXNET_PORT, endpoint), payload, None, 30)


def airplay_call(endpoint, payload=None, timeout=8):
    return http_json("http://127.0.0.1:%d/api/%s" % (c.AIRPLAY_PORT, endpoint), payload, None, timeout)


# --------------------------------------------------------------------------
# system information
# --------------------------------------------------------------------------
def cpu_temp():
    raw = c.read_text("/sys/class/thermal/thermal_zone0/temp", "").strip()
    try:
        return round(int(raw) / 1000.0, 1)
    except ValueError:
        return None


def system_info():
    total = used = 0
    for line in c.read_text("/proc/meminfo").splitlines():
        if line.startswith("MemTotal:"):
            total = int(line.split()[1])
        elif line.startswith("MemAvailable:"):
            used = total - int(line.split()[1])
    disk_total, disk_used = 0, 0
    try:
        usage = shutil.disk_usage("/")
        disk_total, disk_used = usage.total, usage.used
    except OSError:
        pass
    model = ""
    for line in c.read_text("/proc/device-tree/model", "").split("\x00"):
        if line.strip():
            model = line.strip()
            break
    uname = os.uname() if hasattr(os, "uname") else None
    return {
        "hostname": c.hostname(),
        "model": model or "Raspberry Pi",
        "kernel": uname.release if uname else "unknown",
        "uptime": int(float((c.read_text("/proc/uptime", "0").split() or ["0"])[0] or 0)),
        "temp_c": cpu_temp(),
        "mem_total_kb": total,
        "mem_used_kb": used,
        "disk_total": disk_total,
        "disk_used": disk_used,
        "lang": panel_config().get("language", "en"),
        "version": "1.0.0",
    }


def services_health():
    units = ["axnet", "axpanel", "axplay", "axgui", "vpnexit-web",
             "vpnexit-supervisor", "hostapd", "dnsmasq", "avahi-daemon", "shairport-sync"]
    result = {}
    for unit in units:
        rc, out = c.run(["systemctl", "is-active", unit], timeout=5)
        state = (out.strip().splitlines() or ["unknown"])[0].strip()
        if not state or "systemd" in state or "Failed to connect" in state:
            state = "unknown"
        result[unit] = state
    return result


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "AirXPi/1.0"
    protocol_version = "HTTP/1.1"

    # -- plumbing ---------------------------------------------------------
    def log_message(self, *args):
        return

    def _send(self, code, body, ctype="application/json", headers=None, cache="no-store"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
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

    def _local(self):
        return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def _token(self):
        header = self.headers.get("X-Auth-Token") or ""
        if header:
            return header
        raw = self.headers.get("Cookie") or ""
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:  # noqa: BLE001
            return ""
        morsel = cookie.get(COOKIE)
        return morsel.value if morsel else ""

    def _authed(self, config):
        if self._local():
            return True
        token = self._token()
        if not token:
            return False
        if token_valid(config["secret"], token):
            return True
        return hmac.compare_digest(token, config.get("api_token", ""))

    # -- routes -----------------------------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        config = panel_config()

        if path in ("/", "/index.html"):
            return self._serve_static("index.html")
        if path.startswith("/static/"):
            return self._serve_static(path[len("/static/"):])
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if path == "/api/session":
            return self._send(200, {
                "ok": True,
                "authenticated": self._authed(config),
                "username": config.get("username", DEFAULT_USER),
                "default_password": bool(config.get("default_password")),
                "language": config.get("language", "en"),
                "local": self._local(),
                "version": "1.0.0",
            })
        if not path.startswith("/api/"):
            return self._send(404, {"error": "not found"})
        if not self._authed(config):
            return self._send(401, {"ok": False, "error": "unauthorized"})

        query = urllib.parse.parse_qs(parsed.query)
        if path == "/api/state":
            return self._send(200, build_state())
        if path == "/api/airplay/artwork":
            return self._proxy_artwork()
        if path == "/api/vpn/locations":
            refresh = "1" if query.get("refresh") == ["1"] else None
            endpoint = "locations?refresh=1" if refresh else "locations"
            return self._send(200, vpn_call(endpoint, None, 60))
        if path == "/api/vpn/status":
            return self._send(200, vpn_call("status"))
        if path == "/api/vpn/settings":
            return self._send(200, vpn_call("settings"))
        if path == "/api/vpn/log":
            return self._send(200, vpn_call("log?lines=120"))
        if path == "/api/net/state":
            return self._send(200, net_call("state"))
        if path == "/api/system":
            return self._send(200, {"ok": True, "system": system_info(), "services": services_health()})
        return self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        config = panel_config()
        body = self._body()

        if path == "/api/login":
            user = str(body.get("username") or DEFAULT_USER).strip().encode()
            expected = str(config.get("username", DEFAULT_USER)).encode()
            if hmac.compare_digest(user, expected) and _verify(
                    str(body.get("password") or ""), config["password_hash"]):
                token = issue_token(config["secret"])
                header = "%s=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d" % (
                    COOKIE, token, SESSION_HOURS * 3600)
                return self._send(200, {"ok": True}, headers={"Set-Cookie": header})
            time.sleep(0.6)  # damp brute force
            return self._send(403, {"ok": False, "error": "wrong password"})

        if path == "/api/logout":
            return self._send(200, {"ok": True},
                              headers={"Set-Cookie": "%s=; Path=/; Max-Age=0" % COOKIE})

        if not path.startswith("/api/"):
            return self._send(404, {"ok": False, "error": "not found"})
        if not self._authed(config):
            return self._send(401, {"ok": False, "error": "unauthorized"})

        if path == "/api/airplay/config":
            return self._engine(airplay_call("config", body, 45))
        if path == "/api/airplay/volume":
            return self._engine(airplay_call("volume", body, 15))
        if path == "/api/airplay/action":
            return self._engine(airplay_call("action", body, 90))
        if path == "/api/vpn/connect":
            return self._engine(vpn_call("connect", body, 60))
        if path == "/api/vpn/disconnect":
            return self._engine(vpn_call("disconnect", body, 60))
        if path == "/api/vpn/refresh":
            return self._engine(vpn_call("refresh", {}, 90))
        if path == "/api/vpn/selftest":
            return self._engine(vpn_call("selftest", {}, 60))
        if path == "/api/net/wifi":
            return self._engine(net_call("wifi", body))
        if path == "/api/net/wan":
            return self._engine(net_call("wan", body))
        if path == "/api/net/lan":
            return self._engine(net_call("lan", body))
        if path == "/api/net/device":
            result = net_call("device", body)
            if body.get("language") in ("en", "fa"):
                config["language"] = body["language"]
                c.save_json(c.PANEL_CONF, config, 0o600)
            return self._engine(result)
        if path == "/api/system/password":
            return self._send(200, set_password(str(body.get("password") or "")))
        if path == "/api/system/reboot":
            threading.Thread(
                target=lambda: (time.sleep(1.0), c.run(["systemctl", "reboot"], timeout=10)),
                daemon=True).start()
            return self._send(200, {"ok": True, "rebooting": True})
        return self._send(404, {"ok": False, "error": "not found"})

    # -- helpers ----------------------------------------------------------
    def _serve_static(self, name):
        safe = os.path.normpath(name).lstrip("/\\")
        if safe.startswith("..") or os.path.isabs(safe):
            return self._send(404, {"error": "not found"})
        path = os.path.join(c.WEB_DIR, safe)
        if not os.path.isfile(path):
            return self._send(404, {"error": "not found"})
        ctype = STATIC_TYPES.get(os.path.splitext(path)[1], "application/octet-stream")
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            return self._send(500, {"error": "read failed"})
        cache = "no-store" if path.endswith(".html") else "public, max-age=300"
        return self._send(200, data, ctype, cache=cache)

    def _engine(self, result):
        """Pass an engine answer through, but not with a 200 when it is gone."""
        code = 200
        if isinstance(result, dict) and result.get("ok") is False:
            error = str(result.get("error") or "")
            code = 502 if (error.startswith("unreachable") or "timed out" in error) else 400
        return self._send(code, result)

    def _proxy_artwork(self):
        url = "http://127.0.0.1:%d/api/artwork" % c.AIRPLAY_PORT
        try:
            with urllib.request.urlopen(url, timeout=8) as response:
                data = response.read()
                ctype = response.headers.get("Content-Type", "image/jpeg")
        except urllib.error.HTTPError:
            return self._send(404, b"", "image/png")
        except (urllib.error.URLError, OSError):
            return self._send(404, b"", "image/png")
        return self._send(200, data, ctype, cache="no-store")

    def do_HEAD(self):
        self.do_GET()


# --------------------------------------------------------------------------
# aggregated state
# --------------------------------------------------------------------------
def build_state():
    airplay_f = POOL.submit(airplay_call, "state")
    vpn_f = POOL.submit(vpn_call, "status")
    net_f = POOL.submit(net_call, "state")
    airplay = airplay_f.result()
    vpn = vpn_f.result()
    net = net_f.result()

    # the receiver reports every playback PCM with connected=None; mark them and
    # flag the HDMI ones so both front-ends can show where the sound goes
    for device in airplay.get("devices") or []:
        label = ("%s %s" % (device.get("card_name", ""), device.get("pcm_name", ""))).lower()
        device["hdmi"] = "hdmi" in label or "vc4" in label
        if device.get("connected") is None:
            device["connected"] = True
    vpn_status = (vpn or {}).get("status", {}) if isinstance(vpn, dict) else {}
    return {
        "ok": True,
        "airplay": airplay if airplay.get("config") else {"ok": False, "error": airplay.get("error", "unavailable")},
        "vpn": {
            "ok": bool(vpn.get("ok")) if isinstance(vpn, dict) else False,
            "state": vpn_status.get("state", "unknown"),
            "exit_ip": vpn_status.get("exit_ip", ""),
            "key": vpn_status.get("key") or (vpn_status.get("location") or {}).get("key", ""),
            "error": vpn_status.get("error", "") or ("" if vpn.get("ok") else vpn.get("error", "")),
            "routing": vpn_status.get("routing", {}),
            "uptime": vpn_status.get("uptime", 0),
            "server": (vpn_status.get("server") or {}).get("host", ""),
            "location": vpn_status.get("location", {}),
        },
        "net": (net or {}).get("state", {}),
        "system": system_info(),
    }


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def main():
    c.ensure_dirs()
    panel_config()
    port = int(os.environ.get("AXPANEL_PORT", c.PANEL_PORT))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    srv.daemon_threads = True
    c.log("panel listening on :%d" % port, "axpanel")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
