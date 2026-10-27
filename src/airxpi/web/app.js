/* AirXPi control panel - vanilla JS, no build step. */
"use strict";

const I18N = {
  en: {
    "login.sub": "AirPlay 2 receiver & VPN exit",
    "login.username": "User name",
    "login.password": "Panel password",
    "login.submit": "Sign in",
    "login.hint": "Default login is admin / admin. Change it in System after the first sign-in.",
    "common.logout": "Log out",
    "common.save": "Save",
    "common.apply": "Apply",
    "common.refresh": "Refresh",
    "chip.airplay": "AirPlay",
    "tab.dashboard": "Dashboard",
    "tab.airplay": "AirPlay",
    "tab.vpn": "VPN",
    "tab.wifi": "Wi-Fi",
    "tab.network": "Network",
    "tab.system": "System",
    "np.idle": "Nothing playing",
    "np.playing": "Now playing",
    "np.paused": "Paused",
    "np.volume": "Volume",
    "dash.vpn": "VPN exit",
    "dash.uplink": "Uplink",
    "dash.wifi": "Access point",
    "dash.clients": "Connected clients",
    "clients.name": "Name",
    "clients.ip": "IP",
    "clients.mac": "MAC",
    "clients.link": "Link",
    "ap.title": "Receiver",
    "ap.name": "AirPlay name",
    "ap.device": "Output device",
    "ap.delay": "Sync delay (ms)",
    "ap.password": "AirPlay password (optional)",
    "ap.test": "Test tone",
    "ap.restart": "Restart receiver",
    "ap.hint": "Changing the name, device or delay restarts Shairport Sync; an active AirPlay session (and any group) stops.",
    "ap.status": "Receiver status",
    "ap.state": "Service",
    "ap.hdmi": "HDMI sink",
    "ap.detected": "Detected outputs",
    "ap.volume_mode": "Volume mode",
    "ap.meta": "Metadata",
    "vpn.exit": "VPN exit",
    "vpn.refresh": "Refresh list",
    "vpn.disconnect": "Disconnect",
    "vpn.selftest": "Verify exit",
    "vpn.locations": "Locations",
    "vpn.settings": "Tunnel settings",
    "vpn.share": "Share VPN with LAN clients",
    "vpn.block6": "Block IPv6 on the LAN",
    "vpn.reconnect": "Auto reconnect",
    "wifi.ap": "Wi-Fi access point",
    "wifi.ssid": "Network name (SSID)",
    "wifi.psk": "Password (8-63 chars)",
    "wifi.channel": "Channel (2.4 GHz)",
    "wifi.country": "Country (regulatory)",
    "wifi.max": "Max clients",
    "wifi.hidden": "Hidden network",
    "wifi.regen": "Generate password",
    "wifi.hint": "Applying restarts the access point: wireless clients drop for a few seconds.",
    "wifi.status": "Access point status",
    "wifi.state": "State",
    "wifi.clients": "Wireless clients",
    "wifi.lan": "LAN side",
    "wifi.bridge": "Bridge",
    "wifi.address": "Address",
    "wifi.ethernet": "USB Ethernet (eth1)",
    "net.uplink": "Internet uplink",
    "net.uplink_hint": "The Pi takes its internet from the cable port or from a phone that shares its connection over USB.",
    "net.auto": "Auto",
    "net.eth0": "Ethernet (eth0)",
    "net.usb": "USB tethering",
    "net.active": "Active uplink",
    "net.ip": "Uplink address",
    "net.detected": "Detected interfaces",
    "net.plan": "Addressing",
    "net.bridge": "LAN bridge",
    "net.dhcp": "DHCP range",
    "net.panel": "Panel",
    "net.plan_hint": "Clients on eth1 and the Wi-Fi AP share one subnet; the VPN exit applies to all of them when it is connected.",
    "sys.hardware": "Hardware",
    "sys.model": "Model",
    "sys.kernel": "Kernel",
    "sys.uptime": "Uptime",
    "sys.temp": "CPU temperature",
    "sys.mem": "Memory",
    "sys.disk": "Storage",
    "sys.services": "Services",
    "sys.password": "Panel password",
    "sys.new_password": "New password",
    "sys.repeat": "Repeat",
    "sys.device": "Device",
    "sys.device_name": "Name",
    "sys.reboot": "Reboot appliance",
    "sys.diag": "Download diagnostics",
    "sys.reboot_hint": "Stops AirPlay, the access point and the VPN tunnel for about 30 seconds.",
    "msg.saved": "Saved",
    "msg.applied": "Applied",
    "msg.failed": "Failed",
    "msg.confirm_reboot": "Reboot the appliance now?",
    "msg.confirm_restart": "Restart the AirPlay receiver? Any playing session stops.",
    "msg.pass_mismatch": "The two passwords do not match",
    "msg.connecting": "Connecting…",
    "msg.disconnected": "Disconnected",
    "msg.refreshing": "Updating the location list…",
    "msg.no_clients": "No clients yet",
    "msg.never": "never",
    "msg.default_pass": "Default password is still in use - change it in System.",
  },
  fa: {
    "login.sub": "گیرنده AirPlay 2 و دروازه VPN",
    "login.username": "نام کاربری",
    "login.password": "گذرواژه پنل",
    "login.submit": "ورود",
    "login.hint": "ورود پیش‌فرض admin / admin است. بعد از اولین ورود از بخش سیستم تغییرش دهید.",
    "common.logout": "خروج",
    "common.save": "ذخیره",
    "common.apply": "اعمال",
    "common.refresh": "به‌روزرسانی",
    "chip.airplay": "AirPlay",
    "tab.dashboard": "داشبورد",
    "tab.airplay": "AirPlay",
    "tab.vpn": "VPN",
    "tab.wifi": "وای‌فای",
    "tab.network": "شبکه",
    "tab.system": "سیستم",
    "np.idle": "چیزی در حال پخش نیست",
    "np.playing": "در حال پخش",
    "np.paused": "متوقف شده",
    "np.volume": "صدا",
    "dash.vpn": "خروجی VPN",
    "dash.uplink": "اتصال اینترنت",
    "dash.wifi": "نقطه دسترسی",
    "dash.clients": "کاربران متصل",
    "clients.name": "نام",
    "clients.ip": "آدرس",
    "clients.mac": "مک",
    "clients.link": "اتصال",
    "ap.title": "گیرنده",
    "ap.name": "نام AirPlay",
    "ap.device": "دستگاه خروجی",
    "ap.delay": "تأخیر هم‌زمانی (میلی‌ثانیه)",
    "ap.password": "گذرواژه AirPlay (اختیاری)",
    "ap.test": "صدای آزمایشی",
    "ap.restart": "راه‌اندازی مجدد گیرنده",
    "ap.hint": "تغییر نام، دستگاه یا تأخیر باعث راه‌اندازی مجدد Shairport Sync می‌شود؛ پخش فعال (و هر گروه) قطع می‌شود.",
    "ap.status": "وضعیت گیرنده",
    "ap.state": "سرویس",
    "ap.hdmi": "خروجی HDMI",
    "ap.detected": "خروجی‌های شناسایی‌شده",
    "ap.volume_mode": "حالت صدا",
    "ap.meta": "اطلاعات آهنگ",
    "vpn.exit": "خروجی VPN",
    "vpn.refresh": "به‌روزرسانی فهرست",
    "vpn.disconnect": "قطع اتصال",
    "vpn.selftest": "بررسی خروجی",
    "vpn.locations": "موقعیت‌ها",
    "vpn.settings": "تنظیمات تونل",
    "vpn.share": "اشتراک VPN با کاربران شبکه",
    "vpn.block6": "بستن IPv6 در شبکه محلی",
    "vpn.reconnect": "اتصال مجدد خودکار",
    "wifi.ap": "نقطه دسترسی وای‌فای",
    "wifi.ssid": "نام شبکه (SSID)",
    "wifi.psk": "گذرواژه (۸ تا ۶۳ نویسه)",
    "wifi.channel": "کانال (۲.۴ گیگاهرتز)",
    "wifi.country": "کشور (تنظیمات رگولاتوری)",
    "wifi.max": "حداکثر کاربر",
    "wifi.hidden": "شبکه پنهان",
    "wifi.regen": "ساخت گذرواژه",
    "wifi.hint": "با اعمال، نقطه دسترسی راه‌اندازی مجدد می‌شود و کاربران بی‌سیم چند ثانیه قطع می‌شوند.",
    "wifi.status": "وضعیت نقطه دسترسی",
    "wifi.state": "وضعیت",
    "wifi.clients": "کاربران بی‌سیم",
    "wifi.lan": "بخش شبکه محلی",
    "wifi.bridge": "پل",
    "wifi.address": "آدرس",
    "wifi.ethernet": "اترنت USB (eth1)",
    "net.uplink": "اتصال اینترنت",
    "net.uplink_hint": "اینترنت دستگاه از پورت کابلی یا از گوشی‌ای که اتصالش را با USB به اشتراک می‌گذارد گرفته می‌شود.",
    "net.auto": "خودکار",
    "net.eth0": "اترنت (eth0)",
    "net.usb": "اشتراک USB",
    "net.active": "اتصال فعال",
    "net.ip": "آدرس اینترنت",
    "net.detected": "رابط‌های شناسایی‌شده",
    "net.plan": "آدرس‌دهی",
    "net.bridge": "پل شبکه محلی",
    "net.dhcp": "بازه DHCP",
    "net.panel": "پنل",
    "net.plan_hint": "کاربران eth1 و وای‌فای در یک زیرشبکه هستند؛ با اتصال VPN، خروجی برای همه آن‌ها اعمال می‌شود.",
    "sys.hardware": "سخت‌افزار",
    "sys.model": "مدل",
    "sys.kernel": "کرنل",
    "sys.uptime": "زمان کارکرد",
    "sys.temp": "دمای پردازنده",
    "sys.mem": "حافظه",
    "sys.disk": "فضای ذخیره‌سازی",
    "sys.services": "سرویس‌ها",
    "sys.password": "گذرواژه پنل",
    "sys.new_password": "گذرواژه جدید",
    "sys.repeat": "تکرار",
    "sys.device": "دستگاه",
    "sys.device_name": "نام",
    "sys.reboot": "راه‌اندازی مجدد دستگاه",
    "sys.diag": "دریافت گزارش عیب‌یابی",
    "sys.reboot_hint": "AirPlay، نقطه دسترسی و تونل VPN حدود ۳۰ ثانیه متوقف می‌شوند.",
    "msg.saved": "ذخیره شد",
    "msg.applied": "اعمال شد",
    "msg.failed": "ناموفق",
    "msg.confirm_reboot": "دستگاه اکنون راه‌اندازی مجدد شود؟",
    "msg.confirm_restart": "گیرنده AirPlay راه‌اندازی مجدد شود؟ پخش فعلی قطع می‌شود.",
    "msg.pass_mismatch": "دو گذرواژه یکسان نیستند",
    "msg.connecting": "در حال اتصال…",
    "msg.disconnected": "قطع شد",
    "msg.refreshing": "به‌روزرسانی فهرست موقعیت‌ها…",
    "msg.no_clients": "هنوز کاربری متصل نیست",
    "msg.never": "هرگز",
    "msg.default_pass": "گذرواژه پیش‌فرض هنوز فعال است — از بخش سیستم تغییرش دهید.",
  },
};

const CHANNELS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13];
const COUNTRIES = ["", "IR", "TJ", "AF", "AE", "DE", "GB", "US", "TR", "RU", "IN", "PK", "SA", "QA", "FR", "NL", "SE", "CA", "AU", "JP", "SG"];

const state = {
  lang: "en",
  st: null,
  locations: [],
  locationsAt: 0,
  artVersion: -1,
  pollTimer: null,
  volumeTouched: 0,
  tab: "dashboard",
  vpnSettings: null,
};

const $ = (id) => document.getElementById(id);
const t = (key) => (I18N[state.lang] && I18N[state.lang][key]) || I18N.en[key] || key;

function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

function toast(message, bad) {
  const el = $("toast");
  el.textContent = message;
  el.className = "toast show" + (bad ? " bad" : "");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { el.className = "toast"; }, 2600);
}

function uptimeText(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}

function bytesText(bytes) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = Number(bytes || 0);
  let i = 0;
  while (value >= 1024 && i < units.length - 1) { value /= 1024; i += 1; }
  return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

/* ------------------------------------------------------------------ api */
async function api(path, body) {
  const options = { method: body === undefined ? "GET" : "POST", credentials: "same-origin", headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  if (response.status === 401) {
    showLogin();
    throw new Error("unauthorized");
  }
  try {
    return await response.json();
  } catch (err) {
    return { ok: false, error: `HTTP ${response.status}` };
  }
}

/* -------------------------------------------------------------- language */
function applyLanguage() {
  document.documentElement.lang = state.lang;
  document.documentElement.dir = state.lang === "fa" ? "rtl" : "ltr";
  document.body.dir = state.lang === "fa" ? "rtl" : "ltr";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  $("lang-toggle").textContent = state.lang === "fa" ? "EN" : "فا";
  if (state.st) render(state.st);
}

async function setLanguage(lang) {
  state.lang = lang;
  applyLanguage();
  try { await api("/api/net/device", { language: lang }); } catch (err) { /* offline is fine */ }
}

/* ----------------------------------------------------------------- auth */
function showLogin() {
  $("login").classList.remove("hidden");
  $("topbar").classList.add("hidden");
  $("tabs").classList.add("hidden");
  $("main").classList.add("hidden");
  clearInterval(state.pollTimer);
  state.pollTimer = null;
  setTimeout(() => $("login-password").focus(), 60);
}

function showApp() {
  $("login").classList.add("hidden");
  $("topbar").classList.remove("hidden");
  $("tabs").classList.remove("hidden");
  $("main").classList.remove("hidden");
  startPolling();
}

async function boot() {
  try {
    const session = await api("/api/session");
    state.lang = session.language === "fa" ? "fa" : "en";
    applyLanguage();
    if (!session.authenticated) { showLogin(); return; }
    showApp();
    refresh(true);
    if (session.default_password) setTimeout(() => toast(t("msg.default_pass"), true), 800);
  } catch (err) {
    showLogin();
  }
}

/* ----------------------------------------------------------------- tabs */
function setTab(name) {
  state.tab = name;
  document.querySelectorAll(".tab").forEach((el) => el.classList.toggle("active", el.dataset.tab === name));
  document.querySelectorAll(".panel-view").forEach((el) => el.classList.toggle("active", el.dataset.view === name));
  if (name === "vpn") loadLocations(false);
  if (name === "system") loadSystem();
}

/* ---------------------------------------------------------------- polling */
function startPolling() {
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(() => {
    if (document.hidden) return;
    refresh(false);
  }, 2500);
}

async function refresh(full) {
  try {
    const st = await api("/api/state");
    if (!st || st.ok === false) return;
    state.st = st;
    render(st);
    if (full) { loadWifiForm(st); loadVpnSettings(); }
  } catch (err) { /* keep the previous view */ }
}

function chip(id, on, text, warn) {
  const el = $(id);
  el.classList.toggle("on", !!on && !warn);
  el.classList.toggle("warn", !!warn);
  el.classList.toggle("off", !on && !warn);
  if (text) {
    const span = el.querySelector("span:last-child");
    if (span) span.textContent = text;
  }
}

function render(st) {
  const airplay = st.airplay || {};
  const vpn = st.vpn || {};
  const net = st.net || {};
  const wan = net.wan || {};
  const wifi = net.wifi || {};
  const np = airplay.now_playing || {};
  const cfg = airplay.config || {};
  const system = st.system || {};

  $("device-name").textContent = (cfg.name || system.hostname || "AirXPi");
  $("device-name-input").value = system.hostname || cfg.name || "AirXPi";

  const playing = np.state === "playing";
  chip("chip-airplay", airplay.server && airplay.server.running, t("chip.airplay"));
  chip("chip-vpn", vpn.state === "connected", vpn.state === "connected" ? "VPN" : (vpn.state || "VPN"), vpn.state === "connecting");
  chip("chip-wifi", wifi.running, t("tab.wifi"));
  chip("chip-wan", wan.up, wan.iface || "WAN");

  /* now playing */
  $("np-state").textContent = playing ? t("np.playing") : (np.state === "paused" ? t("np.paused") : t("np.idle"));
  $("np-title").textContent = np.title || "—";
  $("np-sub").textContent = [np.artist, np.album].filter(Boolean).join(" · ") || "—";
  $("np-progress").style.width = `${Math.round((np.progress || 0) * 100)}%`;
  $("playpause").textContent = playing ? "⏸" : "▶";

  if (np.art_version !== undefined && np.art_version !== state.artVersion) {
    state.artVersion = np.art_version;
    const img = $("art");
    img.src = `/api/airplay/artwork?v=${np.art_version}`;
    img.onerror = () => { img.removeAttribute("src"); };
  }

  const reported = (airplay.volume && airplay.volume.reported) || 0;
  if (Date.now() - state.volumeTouched > 1500) {
    $("volume").value = reported;
    $("volume-value").textContent = `${reported}%`;
  }

  /* dashboard cards */
  $("dash-vpn").textContent = vpn.state === "connected" ? (vpn.exit_ip || "connected") : (vpn.state || "off");
  $("dash-vpn-sub").textContent = vpn.state === "connected"
    ? `${vpn.key || ""} · ${vpn.server || ""}`
    : (vpn.error || "traffic uses the uplink directly");
  $("dash-wan").textContent = wan.iface || "—";
  $("dash-wan-sub").textContent = wan.ip ? `${wan.kind || ""} · ${wan.ip}` : "no uplink";
  $("dash-wifi").textContent = wifi.running ? wifi.ssid : "off";
  $("dash-wifi-sub").textContent = wifi.running
    ? `ch ${wifi.channel} · ${wifi.clients || 0} clients`
    : (wifi.enabled ? "starting…" : "disabled");

  renderClients(net.clients || []);

  /* airplay view */
  if (airplay.config) {
    $("ap-name").value = cfg.name || "";
    $("ap-delay").value = cfg.latency_offset_ms || 0;
    $("ap-password").value = cfg.password || "";
    $("ap-state").textContent = airplay.server && airplay.server.running ? `running (pid ${airplay.server.pid || "-"})` : "stopped";
    $("ap-hdmi").textContent = airplay.hdmi_sink ? (airplay.displays || []).join(", ") : "no HDMI sink";
    $("ap-devices").textContent = (airplay.devices || [])
      .map((d) => (d.hdmi ? `${d.label} (HDMI)` : d.label)).join(", ") || "—";
    $("ap-volmode").textContent = (airplay.server && airplay.server.volume_mode) || "—";
    $("ap-meta").textContent = airplay.metadata_state || "—";
    const select = $("ap-device");
    const current = cfg.device || "";
    const options = (airplay.devices || []).map((d) =>
      `<option value="${esc(d.value)}"${d.value === current ? " selected" : ""}>${esc(d.label)}${d.hdmi ? " — HDMI" : ""}</option>`);
    if (select.dataset.signature !== options.join("")) {
      select.innerHTML = options.join("") || `<option value="${esc(current)}">${esc(current || "auto")}</option>`;
      select.dataset.signature = options.join("");
    }
  }

  /* vpn view */
  $("vpn-state").textContent = vpn.state || "unknown";
  $("vpn-state").className = "pill " + (vpn.state === "connected" ? "ok" : (vpn.state === "connecting" ? "busy" : ""));
  $("vpn-exit").textContent = vpn.exit_ip || "no exit address";
  $("vpn-server").textContent = vpn.server || vpn.key || "—";
  $("vpn-line").textContent = vpn.state === "connected"
    ? `${vpn.key || ""} — ${vpn.exit_ip || ""}`
    : "LAN clients use the uplink until a location is selected";
  const vpnError = $("vpn-error");
  if (vpn.error) { vpnError.textContent = vpn.error; vpnError.classList.remove("hidden"); }
  else vpnError.classList.add("hidden");
  updateLocationSelection(vpn);

  /* wifi view */
  $("wifi-state").textContent = wifi.running ? "active" : (wifi.enabled ? "starting" : "disabled");
  $("wifi-live-ssid").textContent = wifi.ssid || "—";
  $("wifi-live-channel").textContent = wifi.channel ? `ch ${wifi.channel}` : "—";
  $("wifi-live-clients").textContent = String(wifi.clients || 0);
  const lan = net.lan || {};
  $("lan-iface").textContent = lan.iface || "br0";
  $("lan-ip").textContent = lan.ip || "—";
  $("lan-eth").textContent = lan.ethernet ? "connected" : "not detected";
  $("wifi-enabled").checked = !!wifi.enabled;

  /* network view */
  $("net-wan").textContent = wan.iface ? `${wan.iface} (${wan.kind})` : "none";
  $("net-wan-ip").textContent = wan.ip || "—";
  const cands = wan.candidates || {};
  $("net-candidates").textContent = [...(cands.ethernet || []), ...(cands.usb || [])].join(", ") || "—";
  $("net-bridge").textContent = `${lan.iface || "br0"} · ${lan.ip || ""}`;
  $("net-dhcp").textContent = `${(st.net && st.net.config && st.net.config.lan.dhcp_start) || "10.42.0.10"} – ${(st.net && st.net.config && st.net.config.lan.dhcp_end) || "10.42.0.200"}`;
  $("net-panel").textContent = `http://${lan.ip || "192.168.168.1"}/`;
  document.querySelectorAll("input[name=wan]").forEach((input) => {
    input.checked = (wan.mode || "auto") === input.value;
  });

  /* system view */
  $("sys-model").textContent = system.model || "—";
  $("sys-kernel").textContent = system.kernel || "—";
  $("sys-uptime").textContent = uptimeText(system.uptime);
  $("sys-temp").textContent = system.temp_c != null ? `${system.temp_c} °C` : "—";
  $("sys-mem").textContent = system.mem_total_kb
    ? `${bytesText((system.mem_total_kb - system.mem_used_kb) * 1024)} free of ${bytesText(system.mem_total_kb * 1024)}`
    : "—";
  $("sys-disk").textContent = system.disk_total
    ? `${bytesText(system.disk_used)} of ${bytesText(system.disk_total)}`
    : "—";
}

function renderClients(clients) {
  const body = $("clients-table").querySelector("tbody");
  if (!clients.length) {
    body.innerHTML = `<tr><td colspan="4" class="muted">${t("msg.no_clients")}</td></tr>`;
    return;
  }
  body.innerHTML = clients.map((cl) => `<tr>
      <td>${esc(cl.name || "—")}</td>
      <td class="mono">${esc(cl.ip)}</td>
      <td class="mono">${esc(cl.mac)}</td>
      <td>${cl.wifi ? `Wi-Fi ${cl.signal_dbm != null ? cl.signal_dbm + " dBm" : ""}` : "eth1"}</td>
    </tr>`).join("");
}

/* ------------------------------------------------------------------ vpn */
async function loadLocations(force) {
  try {
    const data = await api(`/api/vpn/locations${force ? "?refresh=1" : ""}`);
    if (!data.ok) { toast(data.error || t("msg.failed"), true); return; }
    state.locations = data.items || [];
    state.locationsAt = data.fetched_at || 0;
    renderLocations();
    updateLocationSelection(state.st ? state.st.vpn : {});
  } catch (err) { toast(t("msg.failed"), true); }
}

function renderLocations() {
  const filter = ($("vpn-search").value || "").toLowerCase();
  const activeKey = state.st && state.st.vpn ? state.st.vpn.key : "";
  const items = state.locations.filter((it) =>
    !filter || `${it.title} ${it.key} ${it.country}`.toLowerCase().includes(filter));
  $("vpn-list").innerHTML = items.map((it) => `
    <button class="loc${it.key === activeKey ? " active" : ""}" data-key="${esc(it.key)}">
      <span class="flag">${esc(it.flag || "🌐")}</span>
      <span class="meta">
        <span class="name">${esc(it.title || it.key)}</span>
        <span class="sub">${(it.servers || []).length} server(s)${it.premium ? ' · <span class="premium">premium</span>' : ""}</span>
      </span>
    </button>`).join("") || `<p class="muted small">${t("msg.refreshing")}</p>`;
  $("vpn-list").querySelectorAll(".loc").forEach((el) => {
    el.addEventListener("click", () => connectVpn(el.dataset.key));
  });
}

function updateLocationSelection(vpn) {
  const activeKey = vpn && vpn.key;
  $("vpn-list").querySelectorAll(".loc").forEach((el) => {
    el.classList.toggle("active", el.dataset.key === activeKey);
  });
}

async function connectVpn(key) {
  if (!key) return;
  const current = state.st && state.st.vpn;
  if (current && current.state === "connected" && current.key === key) {
    await disconnectVpn();
    return;
  }
  toast(t("msg.connecting"));
  const res = await api("/api/vpn/connect", { key, index: 0 });
  if (!res.ok) toast(res.error || t("msg.failed"), true);
  refresh(false);
}

async function disconnectVpn() {
  const res = await api("/api/vpn/disconnect", {});
  toast(res.ok ? t("msg.disconnected") : (res.error || t("msg.failed")), !res.ok);
  refresh(false);
}

async function loadVpnSettings() {
  try {
    const data = await api("/api/vpn/settings");
    if (!data.ok) return;
    state.vpnSettings = data.settings || {};
    $("vpn-share").checked = !!state.vpnSettings.share_lan;
    $("vpn-block6").checked = !!state.vpnSettings.block_ipv6;
    $("vpn-reconnect").checked = !!state.vpnSettings.auto_reconnect;
  } catch (err) { /* ignore */ }
}

/* ------------------------------------------------------------------ wifi */
function fillSelects() {
  $("wifi-channel").innerHTML = CHANNELS.map((ch) =>
    `<option value="${ch}">${ch}</option>`).join("");
  $("wifi-country").innerHTML = COUNTRIES.map((code) =>
    `<option value="${code}">${code || "—"}</option>`).join("");
}

function loadWifiForm(st) {
  const wifi = (st.net && st.net.wifi) || {};
  const cfg = st.net && st.net.config ? st.net.config.wifi : {};
  $("wifi-ssid").value = cfg.ssid || wifi.ssid || "";
  $("wifi-channel").value = String(cfg.channel || wifi.channel || 6);
  $("wifi-country").value = cfg.country || wifi.country || "";
  $("wifi-max").value = String(cfg.max_clients || 16);
  $("wifi-hidden").checked = !!cfg.hidden;
  $("wifi-enabled").checked = !!cfg.enabled;
  $("wifi-psk").placeholder = cfg.passphrase ? "••••••••" : "no password set";
}

/* ---------------------------------------------------------------- system */
async function loadSystem() {
  try {
    const data = await api("/api/system");
    if (!data.ok) return;
    const list = data.services || {};
    const labels = {
      "axnet": "Network", "axpanel": "Panel", "axplay": "AirPlay panel", "axgui": "HDMI UI",
      "vpnexit-web": "VPN panel", "vpnexit-supervisor": "VPN watchdog", "hostapd": "Access point",
      "dnsmasq": "DHCP/DNS", "avahi-daemon": "mDNS", "shairport-sync": "Shairport Sync",
    };
    $("sys-services").innerHTML = Object.keys(labels).map((unit) => {
      const value = list[unit] || "unknown";
      const ok = value === "active";
      const idle = value === "inactive" || value === "failed";
      return `<li><span>${labels[unit]}</span><span class="pill ${ok ? "ok" : (idle ? "bad" : "busy")}">${esc(value)}</span></li>`;
    }).join("");
  } catch (err) { /* ignore */ }
}

/* --------------------------------------------------------------- handlers */
function bind() {
  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const password = $("login-password").value;
    const username = ($("login-username").value || "admin").trim();
    const res = await api("/api/login", { username, password });
    if (res.ok) {
      $("login-password").value = "";
      $("login-error").classList.add("hidden");
      showApp();
      refresh(true);
    } else {
      $("login-error").textContent = res.error || "login failed";
      $("login-error").classList.remove("hidden");
    }
  });

  $("logout").addEventListener("click", async () => {
    await api("/api/logout", {});
    showLogin();
  });

  $("lang-toggle").addEventListener("click", () => setLanguage(state.lang === "fa" ? "en" : "fa"));

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => setTab(tab.dataset.tab));
  });

  $("volume").addEventListener("input", (event) => {
    state.volumeTouched = Date.now();
    const value = Number(event.target.value);
    $("volume-value").textContent = `${value}%`;
    clearTimeout(bind._vol);
    bind._vol = setTimeout(() => api("/api/airplay/volume", { volume: value }), 220);
  });

  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api("/api/airplay/action", { action: button.dataset.action });
      refresh(false);
    });
  });

  $("airplay-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = {
      name: $("ap-name").value,
      device: $("ap-device").value,
      latency_offset_ms: Number($("ap-delay").value || 0),
      password: $("ap-password").value,
      force: true,
    };
    const res = await api("/api/airplay/config", body);
    toast(res.ok ? t("msg.saved") : (res.error || t("msg.failed")), !res.ok);
    refresh(false);
  });

  $("ap-test").addEventListener("click", async () => {
    const res = await api("/api/airplay/action", { action: "test-device", device: $("ap-device").value });
    toast(res.ok ? (res.result || "tone sent") : (res.error || t("msg.failed")), !res.ok);
  });

  $("ap-restart").addEventListener("click", async () => {
    if (!confirm(t("msg.confirm_restart"))) return;
    await api("/api/airplay/action", { action: "restart" });
    toast(t("msg.applied"));
    refresh(false);
  });

  $("vpn-refresh").addEventListener("click", () => loadLocations(true));
  $("vpn-disconnect").addEventListener("click", disconnectVpn);
  $("vpn-search").addEventListener("input", renderLocations);
  $("vpn-selftest").addEventListener("click", async () => {
    const res = await api("/api/vpn/selftest", {});
    const detail = (res.result && (res.result.detail || res.result.ip)) || res.error || "";
    toast(`${res.ok ? "OK" : t("msg.failed")} — ${detail}`, !res.ok);
  });
  $("vpn-settings-save").addEventListener("click", async () => {
    const res = await api("/api/vpn/settings", {
      share_lan: $("vpn-share").checked,
      block_ipv6: $("vpn-block6").checked,
      auto_reconnect: $("vpn-reconnect").checked,
    });
    toast(res.ok ? t("msg.saved") : (res.error || t("msg.failed")), !res.ok);
  });

  $("wifi-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = {
      ssid: $("wifi-ssid").value,
      channel: Number($("wifi-channel").value),
      country: $("wifi-country").value,
      max_clients: Number($("wifi-max").value || 16),
      hidden: $("wifi-hidden").checked,
      enabled: $("wifi-enabled").checked,
    };
    const psk = $("wifi-psk").value;
    if (psk) body.passphrase = psk;
    const res = await api("/api/net/wifi", body);
    $("wifi-ok").classList.toggle("hidden", !res.ok);
    $("wifi-error").classList.toggle("hidden", res.ok);
    if (res.ok) { $("wifi-ok").textContent = t("msg.applied"); $("wifi-psk").value = ""; }
    else $("wifi-error").textContent = res.error || t("msg.failed");
    refresh(true);
  });

  $("wifi-regen").addEventListener("click", () => {
    const alphabet = "abcdefghjkmnpqrstuvwxyz23456789";
    let out = "";
    for (let i = 0; i < 12; i += 1) out += alphabet[Math.floor(Math.random() * alphabet.length)];
    $("wifi-psk").value = out;
  });

  $("wan-save").addEventListener("click", async () => {
    const picked = document.querySelector("input[name=wan]:checked");
    const res = await api("/api/net/wan", { mode: picked ? picked.value : "auto" });
    toast(res.ok ? t("msg.applied") : (res.error || t("msg.failed")), !res.ok);
    refresh(false);
  });

  $("refresh-clients").addEventListener("click", () => refresh(false));

  $("password-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const first = $("password-new").value;
    const second = $("password-repeat").value;
    const ok = $("password-ok");
    const bad = $("password-error");
    if (first !== second) {
      bad.textContent = t("msg.pass_mismatch");
      bad.classList.remove("hidden");
      ok.classList.add("hidden");
      return;
    }
    const res = await api("/api/system/password", { password: first });
    ok.classList.toggle("hidden", !res.ok);
    bad.classList.toggle("hidden", res.ok);
    ok.textContent = t("msg.saved");
    if (!res.ok) bad.textContent = res.error || t("msg.failed");
    $("password-new").value = "";
    $("password-repeat").value = "";
  });

  $("device-save").addEventListener("click", async () => {
    const res = await api("/api/net/device", { name: $("device-name-input").value });
    toast(res.ok ? t("msg.saved") : (res.error || t("msg.failed")), !res.ok);
    refresh(true);
  });

  $("diag").addEventListener("click", async () => {
    const res = await api("/api/diag", {});
    const blob = new Blob([res.text || JSON.stringify(res, null, 2)], { type: "text/plain" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "airxpi-diagnostics.txt";
    link.click();
  });

  $("reboot").addEventListener("click", async () => {
    if (!confirm(t("msg.confirm_reboot"))) return;
    await api("/api/system/reboot", {});
    toast("rebooting…");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  fillSelects();
  bind();
  boot();
});
