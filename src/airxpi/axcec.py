#!/usr/bin/env python3
"""axcec - bridge the TV remote (HDMI-CEC) into the HDMI user interface.

The Pi 3B exposes CEC as ``/dev/cec0`` through the vc4 HDMI block; ``cec-client``
(libcec) turns the TV's user-control messages into readable lines such as::

    DEBUG:   [ 1234]   key pressed: 'up' (1)

This daemon parses those lines and forwards one short word per key press to
``/run/airxpi/remote.sock`` (a unix datagram socket the GUI binds), so the remote
works exactly like the arrow keys on a keyboard.
"""

import os
import re
import socket
import subprocess
import sys
import time

from airxpi import common as c

REMOTE_SOCK = "/run/airxpi/remote.sock"

# libcec names -> the vocabulary the GUI understands
KEYS = {
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "select": "select",
    "enter": "select",
    "back": "back",
    "exit": "back",
    "root menu": "back",
    "home": "back",
    "play": "play_pause",
    "pause": "play_pause",
    "stop": "stop",
    "forward": "next",
    "backward": "previous",
    "volume up": "volume_up",
    "volume down": "volume_down",
    "mute": "mute",
}

KEY_RE = re.compile(r"key (pressed|released):\s*'?([a-z0-9 ]+)'?\s*\((\d+)\)", re.I)


def publish(key):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.sendto(key.encode("ascii", "ignore"), REMOTE_SOCK)
    except OSError:
        # nobody is listening: the UI is restarting, drop the key press
        pass
    finally:
        sock.close()


def cec_available():
    if not os.path.exists("/dev/cec0"):
        return False, "/dev/cec0 is missing (CEC needs vc4-kms-v3d and a TV on HDMI)"
    for candidate in ("/usr/bin/cec-client", "/usr/local/bin/cec-client"):
        if os.path.exists(candidate):
            return True, candidate
    return False, "cec-client is not installed"


def main():
    c.ensure_dirs()
    os.makedirs(os.path.dirname(REMOTE_SOCK), exist_ok=True)

    available, detail = cec_available()
    if not available:
        c.log("disabled: %s" % detail, tag="axcec")
        return 0

    seen = set()
    while True:
        c.log("starting %s" % detail, tag="axcec")
        try:
            process = subprocess.Popen(
                [detail, "-m", "-o", "AirXPi"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, bufsize=1, universal_newlines=True)
        except OSError as exc:
            c.log("spawn failed: %r" % (exc,), tag="axcec")
            time.sleep(5)
            continue

        for line in process.stdout:
            match = KEY_RE.search(line)
            if not match:
                continue
            action, name, code = match.group(1).lower(), match.group(2).strip().lower(), match.group(3)
            token = (action, code)
            if action == "released":
                seen.discard(code)
                continue
            # some TVs repeat "pressed" for a held key - keep one per code
            if token in seen:
                continue
            seen.add(code)
            key = KEYS.get(name)
            if key:
                publish(key)
                c.log("key %s -> %s" % (name, key), tag="axcec")

        rc = process.wait()
        c.log("cec-client exited (%s), restarting" % rc, tag="axcec")
        time.sleep(3)


if __name__ == "__main__":
    sys.exit(main())
