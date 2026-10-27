#!/usr/bin/env python3
"""AirXPi HDMI user interface.

Full-screen PyQt5 application on the HDMI output of the Pi:

    * left  - the AirPlay 2 now-playing view (cover art, title, transport, volume)
    * right - the appliance settings (AirPlay, VPN exit, Wi-Fi access point)

It talks to the same local API the web panel uses (``axpanel`` on port 80,
which is reachable without a password from 127.0.0.1), so nothing is
duplicated: the panel and the TV always show the same state.

Run with ``python3 -m airxpi.gui`` (the ``axgui`` systemd unit starts it on
tty1 through xinit).  ``--windowed`` opens a normal window for development.
"""

import json
import random
import signal
import sys
import time
import urllib.error
import urllib.request

try:
    from PyQt5.QtCore import (QObject, QRect, QRunnable, QSize, Qt, QThread, QThreadPool,
                              QTimer, pyqtSignal, pyqtSlot)
    from PyQt5.QtGui import (QColor, QFont, QFontDatabase, QImage, QLinearGradient,
                             QPainter, QPixmap)
    from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFrame,
                                 QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                                 QListWidgetItem, QPushButton, QSizePolicy, QSpinBox,
                                 QStackedWidget, QVBoxLayout, QWidget)
except ImportError:  # pragma: no cover - the message is the point
    sys.stderr.write("PyQt5 is required: apt install python3-pyqt5\n")
    raise

API = "http://127.0.0.1"
LOCAL_STATE = API + "/api/state"
ARTWORK = API + "/api/airplay/artwork"

CHANNELS = list(range(1, 14))
COUNTRIES = ["", "IR", "TJ", "AF", "AE", "DE", "GB", "US", "TR", "RU", "IN",
             "PK", "SA", "QA", "FR", "NL", "SE", "CA", "AU", "JP", "SG"]

TEXT = {
    "en": {
        "now_playing": "NOW PLAYING", "idle": "READY TO RECEIVE",
        "idle_hint": "Open Control Center on your iPhone or iPad and pick this device.",
        "airplay": "AirPlay", "vpn": "VPN exit", "wifi": "Wi-Fi",
        "volume": "Volume", "settings": "Settings",
        "name": "AirPlay name", "device": "Output", "delay": "Delay (ms)",
        "save": "Save", "test": "Test tone", "restart": "Restart",
        "connect": "Connect", "disconnect": "Disconnect", "refresh": "Refresh",
        "verify": "Verify", "locations": "Locations", "search": "Search",
        "state": "State", "exit": "Exit address", "uplink": "Uplink", "clients": "clients",
        "ssid": "Network name", "psk": "Password", "channel": "Channel",
        "country": "Country", "enabled": "Access point enabled", "apply": "Apply",
        "generate": "Generate", "panel": "Panel", "reboot": "Reboot",
        "hint_wifi": "Applying restarts the access point for a few seconds.",
        "hint_airplay": "Name, output and delay changes restart the receiver.",
        "off": "off", "on": "on", "connected": "connected", "connecting": "connecting",
        "disconnected": "disconnected", "error": "error", "no_hdmi": "no HDMI sink",
        "lang": "فا", "rebooting": "Rebooting…",
    },
    "fa": {
        "now_playing": "در حال پخش", "idle": "آماده دریافت",
        "idle_hint": "از مرکز کنترل آیفون یا آیپد این دستگاه را انتخاب کنید.",
        "airplay": "AirPlay", "vpn": "خروجی VPN", "wifi": "وای‌فای",
        "volume": "صدا", "settings": "تنظیمات",
        "name": "نام AirPlay", "device": "خروجی", "delay": "تأخیر (م‌ث)",
        "save": "ذخیره", "test": "صدای آزمایشی", "restart": "راه‌اندازی مجدد",
        "connect": "اتصال", "disconnect": "قطع", "refresh": "به‌روزرسانی",
        "verify": "بررسی", "locations": "موقعیت‌ها", "search": "جستجو",
        "state": "وضعیت", "exit": "آدرس خروجی", "uplink": "اینترنت", "clients": "کاربر",
        "ssid": "نام شبکه", "psk": "گذرواژه", "channel": "کانال",
        "country": "کشور", "enabled": "نقطه دسترسی فعال", "apply": "اعمال",
        "generate": "ساخت", "panel": "پنل", "reboot": "راه‌اندازی مجدد",
        "hint_wifi": "با اعمال، نقطه دسترسی چند ثانیه راه‌اندازی مجدد می‌شود.",
        "hint_airplay": "تغییر نام، خروجی و تأخیر باعث راه‌اندازی مجدد گیرنده می‌شود.",
        "off": "خاموش", "on": "روشن", "connected": "متصل", "connecting": "در حال اتصال",
        "disconnected": "قطع", "error": "خطا", "no_hdmi": "خروجی HDMI نیست",
        "lang": "EN", "rebooting": "در حال راه‌اندازی مجدد…",
    },
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def http_json(path, payload=None, timeout=6):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(API + path, data=data, headers=headers,
                                     method="POST" if data else "GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace") or "{}")


def fmt_uptime(seconds):
    seconds = int(seconds or 0)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return "%dd %dh" % (days, hours)
    if hours:
        return "%dh %dm" % (hours, minutes)
    return "%dm" % minutes


class Poller(QThread):
    """Polls the panel API and fetches artwork when it changes."""

    state_changed = pyqtSignal(dict)
    artwork_changed = pyqtSignal(bytes)

    def __init__(self):
        super().__init__()
        self._running = True
        self._art_version = None

    def run(self):
        while self._running:
            try:
                state = http_json("/api/state", timeout=6)
                if isinstance(state, dict) and state.get("ok"):
                    self.state_changed.emit(state)
                    airplay = state.get("airplay") or {}
                    version = (airplay.get("now_playing") or {}).get("art_version")
                    if version and version != self._art_version:
                        self._art_version = version
                        try:
                            with urllib.request.urlopen(ARTWORK, timeout=8) as response:
                                blob = response.read()
                            if blob:
                                self.artwork_changed.emit(blob)
                        except (urllib.error.URLError, OSError):
                            pass
            except (urllib.error.URLError, OSError, ValueError):
                self.state_changed.emit({"ok": False})
            for _ in range(15):
                if not self._running:
                    return
                self.msleep(100)

    def stop(self):
        self._running = False


class Worker(QRunnable):
    """POSTs a command without blocking the UI thread."""

    class Signals(QObject):
        done = pyqtSignal(dict)

    def __init__(self, path, payload):
        super().__init__()
        self.path = path
        self.payload = payload
        self.signals = Worker.Signals()

    @pyqtSlot()
    def run(self):
        try:
            self.signals.done.emit(http_json(self.path, self.payload, timeout=90))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self.signals.done.emit({"ok": False, "error": str(exc)})


def post(path, payload, callback=None):
    worker = Worker(path, payload)
    if callback:
        worker.signals.done.connect(callback)
    QThreadPool.globalInstance().start(worker)
    return worker


# --------------------------------------------------------------------------
# on-screen keyboard (the TV has no keyboard, only a remote or a mouse)
# --------------------------------------------------------------------------
class Keyboard(QDialog):
    def __init__(self, parent, target, password=False):
        super().__init__(parent)
        self.target = target
        self.password = password
        self.shift = False
        self.setWindowTitle("Keyboard")
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self.preview = QLabel(self._render())
        self.preview.setObjectName("kbPreview")
        layout.addWidget(self.preview)

        rows = ["1234567890", "qwertyuiop", "asdfghjkl-", "zxcvbnm._+"]
        grid = QGridLayout()
        grid.setSpacing(6)
        for r, row in enumerate(rows):
            for c, char in enumerate(row):
                button = QPushButton(char)
                button.setFixedSize(56, 52)
                button.clicked.connect(lambda _=False, ch=char: self.type_char(ch))
                grid.addWidget(button, r, c)
        layout.addLayout(grid)

        bottom = QHBoxLayout()
        for label, action in (("⇧", self.toggle_shift), ("Space", lambda: self.type_char(" ")),
                              ("⌫", self.backspace), ("Clear", self.clear), ("OK", self.accept)):
            button = QPushButton(label)
            button.setMinimumHeight(52)
            button.clicked.connect(action)
            bottom.addWidget(button)
        layout.addLayout(bottom)
        self.setStyleSheet(parent.styleSheet())

    def _render(self):
        text = self.target.text() or " "
        return "*" * len(text) if self.password else text

    def type_char(self, char):
        char = char.upper() if self.shift else char
        self.target.setText(self.target.text() + char)
        self.preview.setText(self._render())
        if self.shift:
            self.toggle_shift()

    def toggle_shift(self):
        self.shift = not self.shift

    def backspace(self):
        self.target.setText(self.target.text()[:-1])
        self.preview.setText(self._render())

    def clear(self):
        self.target.setText("")
        self.preview.setText(self._render())


# --------------------------------------------------------------------------
# widgets
# --------------------------------------------------------------------------
class Backdrop(QWidget):
    """Dark gradient with a blurred, dimmed copy of the current cover art."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None
        self._cache = None
        self._cache_size = QSize()

    def set_art(self, pixmap):
        self._source = pixmap
        self._cache = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        rect = self.rect()
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor("#0b1118"))
        gradient.setColorAt(1.0, QColor("#101d24"))
        painter.fillRect(rect, gradient)
        if self._source and not self._source.isNull():
            if self._cache is None or self._cache_size != rect.size():
                small = self._source.scaled(24, 24, Qt.KeepAspectRatioByExpanding,
                                            Qt.SmoothTransformation)
                self._cache = small.scaled(rect.size(), Qt.KeepAspectRatioByExpanding,
                                           Qt.SmoothTransformation)
                self._cache_size = rect.size()
            painter.setOpacity(0.32)
            painter.drawPixmap(rect, self._cache)
            painter.setOpacity(1.0)
            painter.fillRect(rect, QColor(6, 10, 14, 150))
        painter.end()


def card(widget, object_name="Card"):
    widget.setObjectName(object_name)
    return widget


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(10)


class AirXPiWindow(QWidget):
    def __init__(self, app, windowed=False):
        super().__init__()
        self.app = app
        self.windowed = windowed
        self.state = {}
        self.lang = "en"
        self.art = None
        self.locations = []
        self._kb_target = None

        self.setWindowTitle("AirXPi")
        self.setObjectName("Root")
        self.backdrop = Backdrop(self)
        self.backdrop.lower()

        self._build()
        self._style()
        self._bind_language()

        self.poller = Poller()
        self.poller.state_changed.connect(self.on_state)
        self.poller.artwork_changed.connect(self.on_artwork)
        self.poller.start()

        clock = QTimer(self)
        clock.timeout.connect(self.update_clock)
        clock.start(1000)
        self.update_clock()

        if not windowed:
            self.showFullScreen()
        else:
            self.resize(1280, 720)
            self.show()

    # -- layout ---------------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 20, 26, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        self.brand = QLabel("AirXPi")
        self.brand.setObjectName("Brand")
        header.addWidget(self.brand)
        self.chip_airplay = QLabel()
        self.chip_vpn = QLabel()
        self.chip_wifi = QLabel()
        for chip in (self.chip_airplay, self.chip_vpn, self.chip_wifi):
            chip.setObjectName("Chip")
            header.addWidget(chip)
        header.addStretch(1)
        self.clock = QLabel()
        self.clock.setObjectName("Clock")
        header.addWidget(self.clock)
        self.lang_button = QPushButton()
        self.lang_button.setObjectName("Ghost")
        self.lang_button.setFixedWidth(70)
        self.lang_button.clicked.connect(self.toggle_language)
        header.addWidget(self.lang_button)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(20)

        # ---- now playing
        left = QVBoxLayout()
        left.setSpacing(12)
        self.art_label = QLabel()
        self.art_label.setObjectName("Art")
        self.art_label.setMinimumSize(320, 320)
        self.art_label.setAlignment(Qt.AlignCenter)
        self.art_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left.addWidget(self.art_label, 1)

        self.np_kicker = QLabel()
        self.np_kicker.setObjectName("Kicker")
        self.np_title = QLabel("—")
        self.np_title.setObjectName("Title")
        self.np_title.setWordWrap(True)
        self.np_sub = QLabel("—")
        self.np_sub.setObjectName("Sub")
        self.np_sub.setWordWrap(True)
        left.addWidget(self.np_kicker)
        left.addWidget(self.np_title)
        left.addWidget(self.np_sub)

        bar = QFrame()
        bar.setObjectName("Bar")
        bar.setFixedHeight(6)
        self.progress = QFrame(bar)
        self.progress.setObjectName("BarFill")
        self.progress.setGeometry(0, 0, 0, 6)
        left.addWidget(bar)
        self.bar = bar

        transport = QHBoxLayout()
        self.btn_prev = QPushButton("⏮")
        self.btn_play = QPushButton("▶")
        self.btn_next = QPushButton("⏭")
        for button in (self.btn_prev, self.btn_play, self.btn_next):
            button.setObjectName("Transport")
            button.setFixedSize(64, 64)
            transport.addWidget(button)
        transport.addSpacing(24)
        self.vol_label = QLabel()
        self.vol_label.setObjectName("Muted")
        transport.addWidget(self.vol_label)
        self.btn_vol_down = QPushButton("–")
        self.btn_vol_down.setObjectName("Transport")
        self.btn_vol_down.setFixedSize(52, 52)
        self.btn_vol_up = QPushButton("+")
        self.btn_vol_up.setObjectName("Transport")
        self.btn_vol_up.setFixedSize(52, 52)
        self.vol_value = QLabel("—")
        self.vol_value.setObjectName("Mono")
        transport.addWidget(self.btn_vol_down)
        transport.addWidget(self.vol_value)
        transport.addWidget(self.btn_vol_up)
        transport.addStretch(1)
        left.addLayout(transport)

        self.btn_prev.clicked.connect(lambda: self.action("previous"))
        self.btn_play.clicked.connect(lambda: self.action("playpause"))
        self.btn_next.clicked.connect(lambda: self.action("next"))
        self.btn_vol_down.clicked.connect(lambda: self.change_volume(-4))
        self.btn_vol_up.clicked.connect(lambda: self.change_volume(4))

        body.addLayout(left, 3)

        # ---- settings
        right = QVBoxLayout()
        right.setSpacing(10)
        self.tab_row = QHBoxLayout()
        self.tabs = {}
        for key in ("airplay", "vpn", "wifi"):
            button = QPushButton()
            button.setCheckable(True)
            button.setObjectName("Tab")
            button.clicked.connect(lambda _=False, k=key: self.set_tab(k))
            self.tab_row.addWidget(button)
            self.tabs[key] = button
        self.tab_row.addStretch(1)
        right.addLayout(self.tab_row)

        self.stack = QStackedWidget()
        self.stack.setObjectName("Stack")
        self.pages = {"airplay": self._page_airplay(),
                      "vpn": self._page_vpn(),
                      "wifi": self._page_wifi()}
        for key in ("airplay", "vpn", "wifi"):
            self.stack.addWidget(self.pages[key])
        right.addWidget(self.stack, 1)
        body.addLayout(right, 2)

        root.addLayout(body, 1)

        footer = QHBoxLayout()
        self.footer_left = QLabel()
        self.footer_left.setObjectName("Muted")
        self.footer_right = QLabel()
        self.footer_right.setObjectName("Muted")
        footer.addWidget(self.footer_left)
        footer.addStretch(1)
        footer.addWidget(self.footer_right)
        root.addLayout(footer)

    def _page_airplay(self):
        page = SettingsPage()
        self.lbl_name = QLabel()
        self.lbl_name.setObjectName("FieldLabel")
        self.inp_name = QLineEdit()
        self.inp_name.setReadOnly(True)
        self.inp_name.mousePressEvent = self._edit_name  # type: ignore[assignment]
        page.layout.addWidget(self.lbl_name)
        page.layout.addWidget(self.inp_name)

        self.lbl_device = QLabel()
        self.lbl_device.setObjectName("FieldLabel")
        self.cmb_device = QComboBox()
        page.layout.addWidget(self.lbl_device)
        page.layout.addWidget(self.cmb_device)

        delay_row = QHBoxLayout()
        self.lbl_delay = QLabel()
        self.lbl_delay.setObjectName("FieldLabel")
        self.spin_delay = QSpinBox()
        self.spin_delay.setRange(-1000, 1000)
        self.spin_delay.setSingleStep(10)
        self.spin_delay.setSuffix(" ms")
        delay_row.addWidget(self.spin_delay, 1)
        page.layout.addWidget(self.lbl_delay)
        page.layout.addLayout(delay_row)

        buttons = QHBoxLayout()
        self.btn_save_ap = QPushButton()
        self.btn_save_ap.setObjectName("Primary")
        self.btn_test_ap = QPushButton()
        self.btn_restart_ap = QPushButton()
        buttons.addWidget(self.btn_save_ap)
        buttons.addWidget(self.btn_test_ap)
        buttons.addWidget(self.btn_restart_ap)
        page.layout.addLayout(buttons)
        self.btn_save_ap.clicked.connect(self.save_airplay)
        self.btn_test_ap.clicked.connect(
            lambda: post("/api/airplay/action",
                         {"action": "test-device", "device": self.cmb_device.currentData()},
                         self.on_result))
        self.btn_restart_ap.clicked.connect(
            lambda: post("/api/airplay/action", {"action": "restart"}, self.on_result))

        self.ap_status = QLabel()
        self.ap_status.setObjectName("Muted")
        self.ap_status.setWordWrap(True)
        page.layout.addWidget(self.ap_status)
        self.lbl_hint_ap = QLabel()
        self.lbl_hint_ap.setObjectName("Hint")
        self.lbl_hint_ap.setWordWrap(True)
        page.layout.addWidget(self.lbl_hint_ap)
        page.layout.addStretch(1)
        return page

    def _page_vpn(self):
        page = SettingsPage()
        self.vpn_status = QLabel()
        self.vpn_status.setObjectName("Big")
        self.vpn_status.setWordWrap(True)
        page.layout.addWidget(self.vpn_status)
        self.vpn_detail = QLabel()
        self.vpn_detail.setObjectName("Muted")
        self.vpn_detail.setWordWrap(True)
        page.layout.addWidget(self.vpn_detail)

        buttons = QHBoxLayout()
        self.btn_vpn_disconnect = QPushButton()
        self.btn_vpn_refresh = QPushButton()
        self.btn_vpn_verify = QPushButton()
        for button in (self.btn_vpn_disconnect, self.btn_vpn_refresh, self.btn_vpn_verify):
            buttons.addWidget(button)
        page.layout.addLayout(buttons)
        self.btn_vpn_disconnect.clicked.connect(
            lambda: post("/api/vpn/disconnect", {}, self.on_result))
        self.btn_vpn_refresh.clicked.connect(lambda: self.load_locations(refresh=True))
        self.btn_vpn_verify.clicked.connect(
            lambda: post("/api/vpn/selftest", {}, self.on_result))

        self.vpn_list = QListWidget()
        self.vpn_list.setObjectName("List")
        self.vpn_list.itemClicked.connect(self.on_location_clicked)
        page.layout.addWidget(self.vpn_list, 1)
        self.lbl_vpn_hint = QLabel()
        self.lbl_vpn_hint.setObjectName("Hint")
        self.lbl_vpn_hint.setWordWrap(True)
        page.layout.addWidget(self.lbl_vpn_hint)
        return page

    def _page_wifi(self):
        page = SettingsPage()
        self.chk_wifi = QCheckBox()
        page.layout.addWidget(self.chk_wifi)

        self.lbl_ssid = QLabel()
        self.lbl_ssid.setObjectName("FieldLabel")
        self.inp_ssid = QLineEdit()
        self.inp_ssid.setReadOnly(True)
        self.inp_ssid.mousePressEvent = self._edit_ssid  # type: ignore[assignment]
        page.layout.addWidget(self.lbl_ssid)
        page.layout.addWidget(self.inp_ssid)

        self.lbl_psk = QLabel()
        self.lbl_psk.setObjectName("FieldLabel")
        self.inp_psk = QLineEdit()
        self.inp_psk.setEchoMode(QLineEdit.Password)
        self.inp_psk.setReadOnly(True)
        self.inp_psk.mousePressEvent = self._edit_psk  # type: ignore[assignment]
        page.layout.addWidget(self.lbl_psk)
        page.layout.addWidget(self.inp_psk)

        row = QHBoxLayout()
        self.lbl_channel = QLabel()
        self.lbl_channel.setObjectName("FieldLabel")
        self.cmb_channel = QComboBox()
        for channel in CHANNELS:
            self.cmb_channel.addItem("ch %d" % channel, channel)
        self.lbl_country = QLabel()
        self.lbl_country.setObjectName("FieldLabel")
        self.cmb_country = QComboBox()
        for code in COUNTRIES:
            self.cmb_country.addItem(code or "—", code)
        row.addWidget(self.cmb_channel)
        row.addWidget(self.cmb_country)
        page.layout.addWidget(self.lbl_channel)
        page.layout.addWidget(self.lbl_country)
        page.layout.addLayout(row)

        buttons = QHBoxLayout()
        self.btn_wifi_apply = QPushButton()
        self.btn_wifi_apply.setObjectName("Primary")
        self.btn_wifi_generate = QPushButton()
        buttons.addWidget(self.btn_wifi_apply, 1)
        buttons.addWidget(self.btn_wifi_generate)
        page.layout.addLayout(buttons)
        self.btn_wifi_apply.clicked.connect(self.save_wifi)
        self.btn_wifi_generate.clicked.connect(self.generate_psk)

        self.wifi_status = QLabel()
        self.wifi_status.setObjectName("Muted")
        self.wifi_status.setWordWrap(True)
        page.layout.addWidget(self.wifi_status)
        self.lbl_hint_wifi = QLabel()
        self.lbl_hint_wifi.setObjectName("Hint")
        self.lbl_hint_wifi.setWordWrap(True)
        page.layout.addWidget(self.lbl_hint_wifi)
        page.layout.addStretch(1)
        return page

    # -- style ----------------------------------------------------------
    def _style(self):
        self.setStyleSheet("""
            #Root { color: #e8eef6; }
            QLabel#Brand { font-size: 26px; font-weight: 800; letter-spacing: 1px; color: #ffffff; }
            QLabel#Clock { font-size: 22px; color: #b9c7d6; font-weight: 300; }
            QLabel#Chip {
                border: 1px solid #2a3a4a; border-radius: 14px; padding: 4px 12px;
                color: #a7b6c6; font-size: 14px; background: rgba(18, 27, 36, 0.7);
            }
            QLabel#Chip[on="true"] { color: #b9ffe0; border-color: #2f7d5f; background: rgba(16, 45, 34, 0.8); }
            QLabel#Chip[warn="true"] { color: #ffe6a7; border-color: #7a6733; }
            QLabel#Art {
                border-radius: 18px; background: rgba(12, 19, 26, 0.85);
                border: 1px solid rgba(60, 80, 100, 0.45);
            }
            QLabel#Kicker { color: #6ee7b7; font-size: 13px; letter-spacing: 3px; font-weight: 600; }
            QLabel#Title { font-size: 34px; font-weight: 700; color: #ffffff; }
            QLabel#Sub { font-size: 18px; color: #9fb2c4; }
            QLabel#Muted { color: #93a4b6; font-size: 15px; }
            QLabel#Hint { color: #6f8496; font-size: 13px; }
            QLabel#Big { font-size: 22px; font-weight: 600; }
            QLabel#Mono { font-size: 17px; color: #d6e3f0; }
            QLabel#FieldLabel { color: #8fa2b5; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; }
            QFrame#Bar { background: rgba(70, 90, 110, 0.45); border-radius: 3px; }
            QFrame#BarFill { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #34d399, stop:1 #60a5fa); border-radius: 3px; }
            QPushButton {
                background: rgba(24, 35, 47, 0.92); border: 1px solid #2a3a4a;
                border-radius: 12px; padding: 10px 16px; font-size: 15px; color: #dbe6f2;
            }
            QPushButton:hover { background: #1f2d3b; }
            QPushButton:pressed { background: #16222c; }
            QPushButton#Primary {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2fbd8b, stop:1 #38bdf8);
                color: #05131b; border: none; font-weight: 700;
            }
            QPushButton#Transport { font-size: 22px; border-radius: 32px; }
            QPushButton#Tab {
                background: transparent; border: 1px solid transparent; color: #93a4b6;
                padding: 8px 16px; border-radius: 12px;
            }
            QPushButton#Tab:checked { background: rgba(24, 35, 47, 0.95); border-color: #2a3a4a; color: #ffffff; }
            QPushButton#Ghost { background: transparent; border: 1px solid #2a3a4a; }
            QStackedWidget#Stack {
                background: rgba(14, 21, 29, 0.82); border: 1px solid #24333f;
                border-radius: 18px; padding: 12px;
            }
            QLineEdit, QComboBox, QSpinBox {
                background: #0d151d; border: 1px solid #2a3a4a; border-radius: 10px;
                padding: 10px 12px; font-size: 16px; color: #e8eef6; min-height: 26px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #34d399; }
            QComboBox QAbstractItemView { background: #0f1a24; color: #e8eef6; selection-background-color: #1c3b33; }
            QListWidget#List {
                background: rgba(9, 15, 21, 0.75); border: 1px solid #24333f;
                border-radius: 12px; font-size: 15px; padding: 4px;
            }
            QListWidget#List::item { padding: 9px 10px; border-radius: 8px; }
            QListWidget#List::item:selected { background: #14392e; color: #ffffff; }
            QCheckBox { font-size: 16px; color: #dbe6f2; spacing: 10px; }
            QCheckBox::indicator { width: 24px; height: 24px; border-radius: 7px;
                border: 1px solid #2f4254; background: #0d151d; }
            QCheckBox::indicator:checked { background: #2fbd8b; border-color: #2fbd8b; }
            QDialog { background: #0e1720; }
            QLabel#kbPreview { background: #0a1219; border: 1px solid #2a3a4a;
                border-radius: 10px; padding: 10px; font-size: 20px; }
            QScrollBar:vertical { background: transparent; width: 8px; }
            QScrollBar::handle:vertical { background: #2f4254; border-radius: 4px; }
        """)

    def _bind_language(self):
        self.tabs["airplay"].setText(self.t("airplay"))
        self.tabs["vpn"].setText(self.t("vpn"))
        self.tabs["wifi"].setText(self.t("wifi"))
        self.lang_button.setText(self.t("lang"))
        self.lbl_name.setText(self.t("name"))
        self.lbl_device.setText(self.t("device"))
        self.lbl_delay.setText(self.t("delay"))
        self.btn_save_ap.setText(self.t("save"))
        self.btn_test_ap.setText(self.t("test"))
        self.btn_restart_ap.setText(self.t("restart"))
        self.lbl_hint_ap.setText(self.t("hint_airplay"))
        self.btn_vpn_disconnect.setText(self.t("disconnect"))
        self.btn_vpn_refresh.setText(self.t("refresh"))
        self.btn_vpn_verify.setText(self.t("verify"))
        self.lbl_vpn_hint.setText(self.t("locations"))
        self.chk_wifi.setText(self.t("enabled"))
        self.lbl_ssid.setText(self.t("ssid"))
        self.lbl_psk.setText(self.t("psk"))
        self.lbl_channel.setText(self.t("channel"))
        self.lbl_country.setText(self.t("country"))
        self.btn_wifi_apply.setText(self.t("apply"))
        self.btn_wifi_generate.setText(self.t("generate"))
        self.lbl_hint_wifi.setText(self.t("hint_wifi"))
        self.vol_label.setText(self.t("volume"))
        self.np_kicker.setText(self.t("now_playing"))
        self.set_tab(getattr(self, "_tab", "airplay"))

    def t(self, key):
        return TEXT.get(self.lang, TEXT["en"]).get(key) or TEXT["en"].get(key, key)

    # -- geometry -------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.backdrop.setGeometry(self.rect())
        if self.art:
            self.apply_art_pixmap()
        self.position_progress()

    def position_progress(self):
        ratio = getattr(self, "_progress", 0.0)
        self.progress.setGeometry(0, 0, int(self.bar.width() * ratio), self.bar.height())

    # -- state ----------------------------------------------------------
    def on_state(self, state):
        self.state = state or {}
        airplay = self.state.get("airplay") or {}
        vpn = self.state.get("vpn") or {}
        net = self.state.get("net") or {}
        wifi = net.get("wifi") or {}
        system = self.state.get("system") or {}
        cfg = airplay.get("config") or {}
        np = airplay.get("now_playing") or {}

        if system.get("lang") and system["lang"] != self.lang:
            self.lang = system["lang"]
            self.apply_direction()
            self._bind_language()

        # chips
        running = bool((airplay.get("server") or {}).get("running"))
        self.set_chip(self.chip_airplay, "AirPlay", running)
        self.set_chip(self.chip_vpn, "VPN " + (vpn.get("state") or "off"),
                      vpn.get("state") == "connected",
                      vpn.get("state") in ("connecting", "error"))
        self.set_chip(self.chip_wifi, "Wi-Fi " + (wifi.get("ssid") or self.t("off")),
                      bool(wifi.get("running")))

        # now playing
        if np.get("title"):
            self.np_kicker.setText(self.t("now_playing"))
            self.np_title.setText(np.get("title") or "—")
            self.np_sub.setText(" · ".join([x for x in (np.get("artist"), np.get("album")) if x]) or "—")
        else:
            self.np_kicker.setText(self.t("idle"))
            self.np_title.setText(cfg.get("name") or "AirXPi")
            self.np_sub.setText(self.t("idle_hint"))
        self.btn_play.setText("⏸" if np.get("state") == "playing" else "▶")
        self._progress = float(np.get("progress") or 0.0)
        self.position_progress()

        volume = (airplay.get("volume") or {}).get("reported")
        if volume is not None:
            self.vol_value.setText("%d%%" % int(volume))

        # airplay page
        if cfg:
            if not self.inp_name.hasFocus() and not self.inp_name.text():
                self.inp_name.setText(cfg.get("name") or "")
            if not self.cmb_device.count():
                for device in airplay.get("devices") or []:
                    label = device.get("label") or device.get("value")
                    if device.get("hdmi"):
                        label = "%s (HDMI)" % label
                    self.cmb_device.addItem(label, device.get("value"))
            current = cfg.get("device")
            index = self.cmb_device.findData(current) if current else -1
            if index >= 0 and self.cmb_device.currentIndex() != index:
                self.cmb_device.setCurrentIndex(index)
            if not self.spin_delay.hasFocus():
                self.spin_delay.setValue(int(cfg.get("latency_offset_ms") or 0))
            server = airplay.get("server") or {}
            state_text = "%s · %s" % (
                "running" if server.get("running") else "stopped",
                airplay.get("displays") and ", ".join(airplay["displays"]) or self.t("no_hdmi"))
            self.ap_status.setText(state_text)

        # vpn page
        state_label = vpn.get("state") or "off"
        line = "%s: %s" % (self.t("state"), state_label)
        self.vpn_status.setText(line)
        detail = []
        if vpn.get("exit_ip"):
            detail.append("%s %s" % (self.t("exit"), vpn["exit_ip"]))
        if vpn.get("key"):
            detail.append(vpn["key"])
        if vpn.get("error"):
            detail.append(vpn["error"])
        self.vpn_detail.setText(" · ".join(detail) or self.t("disconnected"))
        if not self.locations and time.time() - getattr(self, "_locations_at", 0) > 30:
            self._locations_at = time.time()
            self.load_locations()

        # wifi page
        wcfg = (net.get("config") or {}).get("wifi") or {}
        self.chk_wifi.setChecked(bool(wcfg.get("enabled", wifi.get("enabled"))))
        if not self.inp_ssid.hasFocus():
            self.inp_ssid.setText(wcfg.get("ssid") or wifi.get("ssid") or "")
        if not self.inp_psk.hasFocus():
            self.inp_psk.setText(wcfg.get("passphrase") or "")
        channel = int(wcfg.get("channel") or wifi.get("channel") or 6)
        index = self.cmb_channel.findData(channel)
        if index >= 0:
            self.cmb_channel.setCurrentIndex(index)
        country_index = self.cmb_country.findData((wcfg.get("country") or "").upper())
        if country_index >= 0:
            self.cmb_country.setCurrentIndex(country_index)
        self.wifi_status.setText("SSID %s · ch %s · %s %s" % (
            wifi.get("ssid") or "—", wifi.get("channel") or "—",
            wifi.get("clients") or 0, self.t("clients")))

        # footer
        lan = (net.get("lan") or {})
        wan = (net.get("wan") or {})
        self.footer_left.setText("%s %s  ·  %s %s" % (
            self.t("panel"), "http://%s/" % (lan.get("ip") or "10.42.0.1"),
            self.t("uplink"), wan.get("iface") or "—"))
        self.footer_right.setText("kernel %s · up %s" % (
            system.get("kernel", "—"), fmt_uptime(system.get("uptime"))))

        if np.get("art_version") in (None, 0) and not self.art:
            self.show_placeholder()

    def show_placeholder(self):
        self.np_art_pixmap = None
        self.art_label.setPixmap(QPixmap())
        self.art_label.setText("AirXPi")

    def on_artwork(self, blob):
        image = QImage()
        if not image.loadFromData(blob):
            return
        self.art = QPixmap.fromImage(image)
        self.art_label.setText("")
        self.apply_art_pixmap()
        self.backdrop.set_art(self.art)

    def apply_art_pixmap(self):
        if not self.art:
            return
        size = self.art_label.size() - QSize(8, 8)
        if size.width() <= 0 or size.height() <= 0:
            return
        self.art_label.setPixmap(self.art.scaled(size, Qt.KeepAspectRatioByExpanding,
                                                 Qt.SmoothTransformation))

    def set_chip(self, label, text, on, warn=False):
        label.setText(text)
        label.setProperty("on", "true" if on and not warn else "false")
        label.setProperty("warn", "true" if warn else "false")
        label.style().unpolish(label)
        label.style().polish(label)

    def update_clock(self):
        self.clock.setText(time.strftime("%H:%M"))

    # -- language -------------------------------------------------------
    def apply_direction(self):
        self.app.setLayoutDirection(Qt.RightToLeft if self.lang == "fa" else Qt.LeftToRight)

    def toggle_language(self):
        self.lang = "en" if self.lang == "fa" else "fa"
        post("/api/net/device", {"language": self.lang}, self.on_result)
        self.apply_direction()
        self._bind_language()

    # -- interactions ---------------------------------------------------
    def set_tab(self, key):
        self._tab = key
        order = ["airplay", "vpn", "wifi"]
        self.stack.setCurrentIndex(order.index(key))
        for name, button in self.tabs.items():
            button.setChecked(name == key)

    def action(self, name):
        post("/api/airplay/action", {"action": name}, self.on_result)

    def change_volume(self, delta):
        try:
            current = int((self.state.get("airplay") or {}).get("volume", {}).get("reported") or 0)
        except (TypeError, ValueError):
            current = 0
        value = max(0, min(100, current + delta))
        post("/api/airplay/volume", {"volume": value}, self.on_result)
        self.vol_value.setText("%d%%" % value)

    def save_airplay(self):
        payload = {
            "name": self.inp_name.text().strip() or "AirXPi",
            "device": self.cmb_device.currentData(),
            "latency_offset_ms": self.spin_delay.value(),
            "force": True,
        }
        post("/api/airplay/config", payload, self.on_result)

    def save_wifi(self):
        payload = {
            "ssid": self.inp_ssid.text().strip(),
            "channel": self.cmb_channel.currentData(),
            "country": self.cmb_country.currentData() or "",
            "enabled": self.chk_wifi.isChecked(),
        }
        psk = self.inp_psk.text()
        if psk and psk != "********":
            payload["passphrase"] = psk
        post("/api/net/wifi", payload, self.on_result)

    def generate_psk(self):
        alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
        self.inp_psk.setText("".join(random.choice(alphabet) for _ in range(12)))

    def load_locations(self, refresh=False):
        """Read the cached list; ``refresh`` asks vpnexit for a new feed."""
        if getattr(self, "_locations_busy", False):
            return
        if refresh:
            self._locations_busy = True
            post("/api/vpn/refresh", {}, self.on_locations)
            return
        try:
            data = http_json("/api/vpn/locations", timeout=10)
        except (urllib.error.URLError, OSError, ValueError):
            return
        self.fill_locations(data.get("items") or [])

    def fill_locations(self, items):
        self.locations = items
        self.vpn_list.clear()
        active = ((self.state.get("vpn") or {}).get("key") or "")
        for item in items:
            text = "%s  %s" % (item.get("flag") or "🌐", item.get("title") or item.get("key"))
            entry = QListWidgetItem(text)
            entry.setData(Qt.UserRole, item.get("key"))
            self.vpn_list.addItem(entry)
            if item.get("key") == active:
                self.vpn_list.setCurrentItem(entry)

    def on_locations(self, result):
        self._locations_busy = False
        if isinstance(result, dict) and result.get("ok") is False:
            self.vpn_detail.setText(result.get("error") or "feed unavailable")
        self.load_locations(refresh=False)

    def on_location_clicked(self, entry):
        key = entry.data(Qt.UserRole)
        current = (self.state.get("vpn") or {})
        if current.get("state") == "connected" and current.get("key") == key:
            post("/api/vpn/disconnect", {}, self.on_result)
        else:
            post("/api/vpn/connect", {"key": key, "index": 0}, self.on_result)

    def on_result(self, result):
        if isinstance(result, dict) and result.get("ok") is False:
            self.vpn_detail.setText(result.get("error") or "failed")

    # -- on-screen editing ----------------------------------------------
    def _edit(self, target, password=False):
        Keyboard(self, target, password=password).exec_()

    def _edit_name(self, event):
        self._edit(self.inp_name)

    def _edit_ssid(self, event):
        self._edit(self.inp_ssid)

    def _edit_psk(self, event):
        self._edit(self.inp_psk, password=True)

    def closeEvent(self, event):
        self.poller.stop()
        self.poller.wait(1500)
        super().closeEvent(event)


def main():
    windowed = "--windowed" in sys.argv
    app = QApplication(sys.argv)
    app.setApplicationName("AirXPi")
    app.setApplicationDisplayName("AirXPi")

    families = set(QFontDatabase().families())
    for family in ("Vazirmatn", "Noto Sans Arabic", "Noto Naskh Arabic", "DejaVu Sans"):
        if family in families:
            app.setFont(QFont(family, 12))
            break

    window = AirXPiWindow(app, windowed=windowed)
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
