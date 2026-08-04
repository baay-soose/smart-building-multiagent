"""
Dashboard Smart Building — avec création de zones dynamiques
Lancement : streamlit run dashboard.py
"""
import json
import time
import threading
from datetime import datetime, timezone
from collections import deque
import streamlit as st
import plotly.graph_objects as go
import paho.mqtt.client as mqtt
import uuid
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from simulators.generic_sensor import GenericSensor, SENSOR_TYPES
except ImportError:
    GenericSensor = None
    SENSOR_TYPES = {}

BROKER_HOST   = "localhost"
BROKER_PORT   = 1883
MAX_ANOMALIES = 60
ZONES         = ["floor1", "floor2", "floor3", "server_room"]

ZONE_LABELS  = {"floor1": "Étage 1", "floor2": "Étage 2", "floor3": "Étage 3", "server_room": "Salle serveur"}
ZONE_COLORS  = {"floor1": "#10b981", "floor2": "#3b82f6", "floor3": "#ef4444", "server_room": "#8b5cf6"}
DYN_COLORS   = ["#f59e0b", "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#14b8a6"]

ANOMALY_ICONS = {
    "fire": "🔴", "overheating": "🟠", "overheat": "🟠",
    "cpu_spike": "🟠", "power_surge": "🟠",
    "poor_air": "🟡", "no_light": "🟡",
    "high_humidity": "🟡", "motion_stuck": "🟡",
}

METRIC_LABELS = {
    "temperature":  ("🌡", "Température",  "°C"),
    "humidity":     ("💧", "Humidité",     "%"),
    "co2_ppm":      ("🌫", "CO₂",          " ppm"),
    "cpu_load_pct": ("⚙",  "Charge CPU",  "%"),
    "power_w":      ("⚡", "Puissance",    " W"),
    "luminosity":   ("💡", "Luminosité",   " lux"),
    "motion":       ("🚶", "Mouvement",    ""),
    "smoke":        ("🔥", "Fumée",        ""),
}

THRESHOLDS = {
    "temperature": 28, "co2_ppm": 1000,
    "cpu_load_pct": 90, "power_w": 2000, "humidity": 65,
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
    background: #f8fafc !important;
    color: #334155 !important;
}
#MainMenu, footer { visibility: hidden; }
header { background: transparent !important; }
header [data-testid="stToolbar"] { display: none; }
.block-container { padding: 1.5rem 2rem 1rem !important; max-width: 100% !important; }

.topbar {
    display:flex; align-items:center; justify-content:space-between;
    background:#fff; border-radius:14px; padding:14px 22px;
    margin-bottom:20px; box-shadow:0 1px 3px rgba(0,0,0,.04);
}
.topbar-left  { display:flex; align-items:center; gap:14px; }
.topbar-title { font-size:1.6rem; font-weight:630; color:#1e293b; }
.topbar-sub   { font-size:0.7rem; color:#94a3b8; margin-top:2px; }
.topbar-right { display:flex; align-items:center; gap:12px; }
.topbar-time  { font-size:0.77rem; color:#94a3b8; }
.pill { display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border-radius:999px;font-size:0.72rem;font-weight:600; }
.pill-ok  { background:#dcfce7;color:#16a34a; }
.pill-err { background:#fee2e2;color:#dc2626; }
.dot { width:7px;height:7px;border-radius:50%; }
.dot-ok  { background:#16a34a; }
.dot-err { background:#dc2626; }

.section-title {
    font-size:0.68rem; font-weight:700; color:#94a3b8;
    text-transform:uppercase; letter-spacing:.12em; margin:18px 0 10px;
}

.kpi-card { border-radius:14px; padding:20px 22px; min-height:108px; }
.kpi-val   { font-size:2.1rem; font-weight:800; line-height:1; }
.kpi-label { font-size:0.78rem; font-weight:500; opacity:.75; margin-top:5px; }
.kpi-teal   { background:linear-gradient(135deg,#14b8a6,#5eead4); color:#134e4a !important; }
.kpi-orange { background:linear-gradient(135deg,#fb923c,#fdba74); color:#7c2d12 !important; }
.kpi-red    { background:linear-gradient(135deg,#f87171,#fca5a5); color:#7f1d1d !important; }
.kpi-purple { background:linear-gradient(135deg,#a78bfa,#c4b5fd); color:#3b0764 !important; }
.kpi-green  { background:linear-gradient(135deg,#34d399,#6ee7b7); color:#064e3b !important; }

.s-badge { font-size:0.66rem;font-weight:700;padding:3px 8px;border-radius:6px;text-transform:uppercase;letter-spacing:.05em; }
.s-run  { background:#dcfce7;color:#16a34a; }
.s-pau  { background:#fef9c3;color:#ca8a04; }
.s-sto  { background:#fee2e2;color:#dc2626; }
.s-unk  { background:#f1f5f9;color:#94a3b8; }
.sensor-ts { font-size:0.64rem;color:#94a3b8;margin-bottom:8px; }
.metric-row { display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid #f8fafc;font-size:0.79rem; }
.metric-row:last-child { border-bottom:none; }
.m-label { color:#94a3b8; }
.m-val   { font-weight:600;color:#334155;font-family:monospace; }
.m-val.danger { color:#ef4444; }
.ano-badge { margin-top:7px;padding:4px 10px;border-radius:6px;background:#fff5f5;border:1px solid #fde8e8;font-size:0.7rem;font-weight:700;color:#ef4444;text-transform:uppercase; }

.card-item {
    background:#fff; border-radius:10px; padding:13px 15px;
    margin-bottom:7px; box-shadow:0 1px 2px rgba(0,0,0,.04); border-left:3px solid;
}
.ci-fire     { border-color:#fca5a5; }
.ci-high     { border-color:#fed7aa; }
.ci-medium   { border-color:#bfdbfe; }
.ci-critical { border-color:#fca5a5; }
.ci-low      { border-color:#a7f3d0; }

.ci-badge {
    font-size:0.65rem; font-weight:800; padding:2px 7px;
    border-radius:5px; letter-spacing:.07em; text-transform:uppercase;
    display:inline-block;
}
.ci-b-critical { background:#fee2e2;color:#ef4444; }
.ci-b-high     { background:#ffedd5;color:#f97316; }
.ci-b-medium   { background:#dbeafe;color:#3b82f6; }
.ci-b-low      { background:#dcfce7;color:#16a34a; }
.ci-b-urgent   { background:#7f1d1d;color:#fca5a5;margin-left:5px; }

.ci-zone   { font-size:0.8rem;font-weight:700;color:#1e293b;margin:4px 0 3px; }
.ci-desc   { font-size:0.73rem;color:#64748b;line-height:1.55;margin-bottom:3px; }
.ci-action { font-size:0.7rem;color:#64748b;font-style:italic;line-height:1.45; }
.ci-type   { font-size:0.7rem;color:#64748b;margin-top:2px; }
.ci-time   { font-size:0.64rem;color:#94a3b8;font-family:monospace;white-space:nowrap; }

.scroll-box { max-height:420px;overflow-y:auto;padding-right:2px; }
.no-data { color:#cbd5e1;font-size:0.78rem;font-style:italic;padding:10px 0; }

/* ── CAROUSEL ── */
.sensor-carousel {
    display: flex; gap: 14px;
    overflow-x: auto; overflow-y: hidden;
    padding: 4px 4px 14px 4px;
    scroll-behavior: smooth;
    scroll-snap-type: x mandatory;
}
.sensor-carousel::-webkit-scrollbar { height: 8px; }
.sensor-carousel::-webkit-scrollbar-track { background: #f1f5f9; border-radius: 4px; }
.sensor-carousel::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
.sensor-carousel::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
.sensor-slide {
    flex: 0 0 calc(25% - 11px);
    min-width: 260px;
    scroll-snap-align: start;
    background: #fff;
    border-radius: 12px;
    padding: 14px 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,.05);
    border: 1px solid #f1f5f9;
}
.slide-head {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 8px;
}
.slide-title { font-size: 0.9rem; font-weight: 700; color: #1e293b; }
.slide-badge { font-size:0.66rem;font-weight:700;padding:3px 8px;border-radius:6px;text-transform:uppercase;letter-spacing:.05em; }
.slide-ts    { font-size: 0.63rem; color: #94a3b8; margin-bottom: 10px; }
.slide-metric { display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #f8fafc;font-size:0.79rem; }
.slide-metric:last-child { border-bottom:none; }
.carousel-nav {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 8px;
}
.carousel-hint {
    font-size: 0.68rem; color: #94a3b8;
    display: flex; align-items: center; gap: 6px;
}

.stButton > button {
    border-radius:7px !important;font-size:0.72rem !important;font-weight:600 !important;
    border:1px solid #e8edf2 !important;background:#fafbfc !important;
    color:#64748b !important;transition:all .15s !important;
    padding:3px 4px !important;min-width:0 !important;width:100% !important;
}
.stButton > button:hover { background:#f1f5f9 !important;color:#334155 !important; }

section[data-testid="stSidebar"] { background:#0f172a !important; }
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] span { color:#94a3b8 !important; }
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] .stMultiSelect div { color:#e2e8f0 !important; }
.sb-sep { height:1px;background:#1e293b;margin:12px 0; }
</style>
"""

# ─── SHARED STATE ────────────────────────────────────────────────────────────
@st.cache_resource
def get_shared_state():
    return {
        "sensor_data":    {z: {} for z in ZONES},
        "sensor_status":  {z: "unknown" for z in ZONES},
        "last_update":    {z: None for z in ZONES},
        "anomalies":      deque(maxlen=MAX_ANOMALIES),
        "anomaly_counts": {z: [] for z in ZONES},
        "decisions":      deque(maxlen=30),
        "connected":      [False],
        "lock":           threading.Lock(),
        "dynamic_zones":  {},   # zone_id -> {"label", "types", "sensor_obj"}
    }

# ─── MQTT ────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_mqtt_client():
    state = get_shared_state()

    def all_known_zones():
        return list(ZONES) + list(state["dynamic_zones"].keys())

    def on_connect(client, userdata, flags, rc, props):
        if str(rc) in ("0", "Success"):
            client.subscribe("building/#",  qos=1)
            client.subscribe("status/#",    qos=1)
            client.subscribe("decisions/#", qos=1)
        state["connected"][0] = True

    def on_disconnect(client, userdata, flags, rc, props):
        state["connected"][0] = False

    def on_message(client, userdata, msg):
        try:
            topic   = msg.topic
            payload = json.loads(msg.payload.decode())

            if topic.startswith("building/"):
                loc    = payload.get("location")
                values = payload.get("values", {})
                if loc in all_known_zones():
                    with state["lock"]:
                        state["sensor_data"][loc] = values
                        state["last_update"][loc] = datetime.now()
                    if "anomaly" in values:
                        now = datetime.now()
                        with state["lock"]:
                            state["anomalies"].appendleft({
                                "time":     now.strftime("%H:%M:%S"),
                                "location": loc,
                                "type":     values["anomaly"],
                                "values":   {k: v for k, v in values.items() if k != "anomaly"},
                            })
                            state["anomaly_counts"].setdefault(loc, []).append((now, values["anomaly"]))
                            if len(state["anomaly_counts"][loc]) > 100:
                                state["anomaly_counts"][loc].pop(0)

            elif topic.startswith("status/"):
                loc    = payload.get("location")
                status = payload.get("status", "unknown")
                if loc in all_known_zones():
                    with state["lock"]:
                        state["sensor_status"][loc] = status

            elif topic.startswith("decisions/"):
                with state["lock"]:
                    state["decisions"].appendleft({
                        "time":     datetime.now().strftime("%H:%M:%S"),
                        "location": payload.get("location", "?"),
                        "diagnostic": payload.get("diagnostic", ""),
                        "risque":   payload.get("risque", "medium"),
                        "urgence":  payload.get("urgence", False),
                        "action":   payload.get("action_recommandee", ""),
                    })
        except Exception:
            pass

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"dashboard-{uuid.uuid4().hex[:8]}")
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
        client.loop_start()
    except Exception:
        pass
    return client

def send_control(zone, cmd):
    c = get_mqtt_client()
    if c:
        c.publish(f"control/{zone}", json.dumps({
            "command": cmd, "timestamp": datetime.now(timezone.utc).isoformat()
        }), qos=1)

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def sbadge(status):
    return {"running":("● Actif","s-run"), "paused":("⏸ Pausé","s-pau"),
            "stopped":("■ Arrêté","s-sto")}.get(status, ("○ Inconnu","s-unk"))

def is_danger(k, v):
    th = THRESHOLDS.get(k)
    if th and isinstance(v, (int, float)): return v > th
    return k == "smoke" and v == 1

def fmt_val(k, v):
    if k == "motion": return "Détecté" if v else "Aucun"
    if k == "smoke":  return "⚠ DÉTECTÉE" if v else "Aucune"
    _, _, u = METRIC_LABELS.get(k, ("","","")); return f"{v}{u}"

def anom_classes(atype):
    if atype == "fire":
        return "ci-fire", "ci-b-critical", "CRITICAL"
    if atype in ("overheating","overheat","cpu_spike","power_surge"):
        return "ci-high", "ci-b-high", "HIGH"
    return "ci-medium", "ci-b-medium", "MEDIUM"

def normalize_risque(risque):
    r = risque.lower()
    if "critical" in r or "critique" in r: return "critical"
    if "high" in r or "élevé" in r or "eleve" in r: return "high"
    if "low" in r or "faible" in r: return "low"
    return "medium"

def dec_classes(risque):
    r = normalize_risque(risque)
    if r == "critical": return "ci-critical", "ci-b-critical"
    if r == "high":     return "ci-high",     "ci-b-high"
    if r == "low":      return "ci-low",       "ci-b-low"
    return "ci-medium", "ci-b-medium"

def zone_display_name(zid, state):
    if zid in ZONE_LABELS:
        return ZONE_LABELS[zid]
    dz = state["dynamic_zones"].get(zid)
    return dz["label"] if dz else zid

def render_sensor_card(zone, label, state, icon="", key_prefix=""):
    """Affiche une carte capteur avec boutons start/stop."""
    with state["lock"]:
        data   = dict(state["sensor_data"].get(zone, {}))
        status = state["sensor_status"].get(zone, "unknown")
        lu     = state["last_update"].get(zone)
    delta    = f"{(datetime.now()-lu).seconds}s" if lu else "—"
    anom_val = data.pop("anomaly", None) if data else None
    lbl, bcls = sbadge(status)

    with st.container(border=True):
        th, tb1, tb2 = st.columns([4, 1, 1])
        with th:
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:2px">'
                f'<span style="font-size:.9rem;font-weight:700;color:#1e293b">{icon}{label}</span>'
                f'<span class="s-badge {bcls}">{lbl}</span></div>'
                f'<div class="sensor-ts">Mis à jour il y a {delta}</div>',
                unsafe_allow_html=True
            )
        with tb1:
            if st.button("▶", key=f"{key_prefix}s_{zone}", help="Démarrer"):
                send_control(zone, "start")
        with tb2:
            if st.button("⏸", key=f"{key_prefix}p_{zone}", help="Arrêter"):
                send_control(zone, "stop")

        if data:
            rows = ""
            for k, v in data.items():
                if k not in METRIC_LABELS: continue
                micon, mlbl, _ = METRIC_LABELS[k]
                vcls = "m-val danger" if is_danger(k, v) else "m-val"
                rows += (f'<div class="metric-row">'
                         f'<span class="m-label">{micon} {mlbl}</span>'
                         f'<span class="{vcls}">{fmt_val(k,v)}</span></div>')
            if anom_val:
                rows += f'<div class="ano-badge">⚠ {anom_val}</div>'
            st.markdown(rows, unsafe_allow_html=True)
        else:
            st.caption("En attente de données...")

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(page_title="Smart Building", page_icon="",
                       layout="wide", initial_sidebar_state="expanded")
    get_mqtt_client()
    state = get_shared_state()
    st.markdown(CSS, unsafe_allow_html=True)

    # Utiliser l'état réel du client MQTT au lieu du flag
    mqtt_client = get_mqtt_client()
    connected   = mqtt_client.is_connected() if mqtt_client else False

    with state["lock"]:
        anomalies_all = list(state["anomalies"])
        dyn_zones     = dict(state["dynamic_zones"])
        all_zone_ids  = list(ZONES) + list(dyn_zones.keys())
        counts_snap   = {z: list(state["anomaly_counts"].get(z, [])) for z in all_zone_ids}
        active_zones  = sum(1 for z in all_zone_ids if state["sensor_status"].get(z) == "running")
        decisions     = list(state["decisions"])
        zones_with_anomaly = set(a["location"] for a in anomalies_all)
        norm_zones    = sum(1 for z in all_zone_ids
                            if z not in zones_with_anomaly
                            and state["sensor_status"].get(z) == "running")

    total_zones = len(all_zone_ids)
    fire_count  = sum(1 for a in anomalies_all if a["type"] == "fire")
    high_count  = sum(1 for a in anomalies_all if a["type"] in ("overheating","overheat","cpu_spike","power_surge"))
    total_anom  = sum(len(counts_snap[z]) for z in all_zone_ids)

    # ── TOP BAR ──
    pill_cls = "pill-ok"  if connected else "pill-err"
    dot_cls  = "dot-ok"   if connected else "dot-err"
    pill_txt = "MQTT Connecté" if connected else "MQTT Déconnecté"

    st.markdown(f"""
    <div class="topbar">
      <div class="topbar-left">
        <div>
          <div class="topbar-title">Smart Building - Supervision IoT</div>
          <div class="topbar-sub">Plateforme multi-agents IA · Temps réel</div>
        </div>
      </div>
      <div class="topbar-right">
        <span class="topbar-time">{datetime.now().strftime("%d %b %Y — %H:%M:%S")}</span>
        <span class="pill {pill_cls}"><span class="dot {dot_cls}"></span>{pill_txt}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── KPI ──
    st.markdown('<div class="section-title">Notifications en temps réel</div>', unsafe_allow_html=True)
    for col, val, label, cls in zip(
        st.columns(5),
        [f"{active_zones}/{total_zones}", str(total_anom), str(fire_count), str(high_count), str(norm_zones)],
        ["Zones actives", "Anomalies totales", "Alertes incendie", "Surchauffes", "Zones normales"],
        ["kpi-teal", "kpi-orange", "kpi-red", "kpi-purple", "kpi-green"]
    ):
        with col:
            st.markdown(f"""<div class="kpi-card {cls}">
              <div class="kpi-val">{val}</div>
              <div class="kpi-label">{label}</div>
            </div>""", unsafe_allow_html=True)

    # ── ZONES CAPTEURS — CAROUSEL HORIZONTAL ──
    st.markdown('<div class="section-title">Données capteurs en temps réel</div>', unsafe_allow_html=True)

    # Liste unifiée
    all_zones_display = []
    for z in ZONES:
        all_zones_display.append({"id": z, "label": ZONE_LABELS[z], "icon": "", "is_dynamic": False})
    for zid, zinfo in dyn_zones.items():
        all_zones_display.append({"id": zid, "label": zinfo["label"], "icon": "", "is_dynamic": True})

    total = len(all_zones_display)
    if total > 4:
        st.markdown(
            f'<div class="carousel-hint">← Faire défiler pour voir toutes les zones ({total} au total) →</div>',
            unsafe_allow_html=True
        )

    # Carrousel HTML pur (visuel uniquement)
    slides_html = ""
    for z_info in all_zones_display:
        zid   = z_info["id"]
        label = z_info["label"]
        icon  = z_info["icon"]
        with state["lock"]:
            data   = dict(state["sensor_data"].get(zid, {}))
            status = state["sensor_status"].get(zid, "unknown")
            lu     = state["last_update"].get(zid)
        delta    = f"{(datetime.now()-lu).seconds}s" if lu else "—"
        anom_val = data.pop("anomaly", None) if data else None
        lbl, bcls = sbadge(status)

        metrics = ""
        if data:
            for k, v in data.items():
                if k not in METRIC_LABELS: continue
                micon, mlbl, _ = METRIC_LABELS[k]
                color = "#ef4444" if is_danger(k, v) else "#334155"
                metrics += (
                    f'<div class="slide-metric">'
                    f'<span style="color:#94a3b8">{micon} {mlbl}</span>'
                    f'<span style="font-weight:600;color:{color};font-family:monospace">{fmt_val(k,v)}</span>'
                    f'</div>'
                )
            if anom_val:
                metrics += f'<div class="ano-badge">⚠ {anom_val}</div>'
        else:
            metrics = '<div style="color:#94a3b8;font-size:0.78rem;font-style:italic;padding:8px 0">En attente...</div>'

        slides_html += (
            f'<div class="sensor-slide">'
            f'<div class="slide-head">'
            f'<span class="slide-title">{icon}{label}</span>'
            f'<span class="slide-badge {bcls}">{lbl}</span>'
            f'</div>'
            f'<div class="slide-ts">Mis à jour il y a {delta}</div>'
            f'{metrics}'
            f'</div>'
        )

    st.markdown(f'<div class="sensor-carousel">{slides_html}</div>', unsafe_allow_html=True)

    # ── CONTRÔLES DES CAPTEURS (expander repliable) ──
    with st.expander("Contrôle des capteurs"):
        for row_start in range(0, total, 3):
            row = all_zones_display[row_start:row_start+3]
            row_cols = st.columns(3)
            for i, z_info in enumerate(row):
                with row_cols[i]:
                    zid   = z_info["id"]
                    label = z_info["label"]
                    icon  = z_info["icon"]
                    is_dynamic = z_info["is_dynamic"]
                    with state["lock"]:
                        status = state["sensor_status"].get(zid, "unknown")
                    lbl, bcls = sbadge(status)

                    with st.container(border=True):
                        if is_dynamic:
                            cl, cb1, cb2, cb3 = st.columns([4, 1, 1, 1])
                        else:
                            cl, cb1, cb2 = st.columns([4, 1, 1])

                        with cl:
                            st.markdown(
                                f'<div style="display:flex;align-items:center;gap:8px;padding-top:2px">'
                                f'<span style="font-size:.88rem;font-weight:700;color:#1e293b">{icon}{label}</span>'
                                f'<span class="s-badge {bcls}">{lbl}</span>'
                                f'</div>',
                                unsafe_allow_html=True
                            )
                        with cb1:
                            if st.button("▶", key=f"ctrl_s_{zid}", help="Démarrer"):
                                send_control(zid, "start")
                        with cb2:
                            if st.button("⏸", key=f"ctrl_p_{zid}", help="Arrêter"):
                                send_control(zid, "stop")
                        if is_dynamic:
                            with cb3:
                                if st.button("🗑", key=f"del_{zid}", help="Supprimer"):
                                    with state["lock"]:
                                        info = state["dynamic_zones"].pop(zid, None)
                                        state["sensor_status"].pop(zid, None)
                                        state["sensor_data"].pop(zid, None)
                                        state["last_update"].pop(zid, None)
                                        state["anomaly_counts"].pop(zid, None)
                                    if info and info.get("sensor_obj"):
                                        try:
                                            info["sensor_obj"].stop()
                                        except Exception:
                                            pass
                                    # Pas de st.rerun() — laisser le refresh automatique gérer

    # ── AJOUTER UNE ZONE (page principale) ──
    with st.expander("Ajouter une nouvelle zone"):
        if GenericSensor is None:
            st.warning("generic_sensor.py introuvable dans simulators/ — place le fichier puis relance.")
        else:
            with st.form("new_zone_form_main", clear_on_submit=True):
                fc1, fc2 = st.columns(2)
                with fc1:
                    zone_label  = st.text_input("Nom de la zone", placeholder="ex: Cafétéria")
                with fc2:
                    zone_id_raw = st.text_input("Identifiant (sans espaces)", placeholder="ex: cafeteria")
                selected_types = st.multiselect(
                    "Types de capteurs",
                    list(SENSOR_TYPES.keys()),
                    default=["temperature", "humidity"],
                )
                submitted = st.form_submit_button("Créer la zone")

            if submitted:
                if not (zone_label and zone_id_raw and selected_types):
                    st.error("Remplis tous les champs.")
                else:
                    zone_id = zone_id_raw.strip().lower().replace(" ", "_")
                    with state["lock"]:
                        exists = zone_id in state["dynamic_zones"] or zone_id in ZONES
                    if exists:
                        st.error(f"Zone '{zone_id}' existe déjà.")
                    else:
                        sensor = GenericSensor(
                            zone_id=zone_id,
                            zone_label=zone_label,
                            sensor_types=selected_types,
                        )
                        sensor.start(anomaly_probability=0.05)
                        with state["lock"]:
                            state["dynamic_zones"][zone_id] = {
                                "label": zone_label,
                                "types": selected_types,
                                "sensor_obj": sensor,
                            }
                            state["sensor_status"][zone_id]  = "running"
                            state["sensor_data"][zone_id]    = {}
                            state["last_update"][zone_id]    = None
                            state["anomaly_counts"][zone_id] = []
                        st.success(f"Zone '{zone_label}' créée ! Elle apparaîtra dans quelques secondes.")



    # ── BOTTOM ──
    st.markdown('<div class="section-title" style="margin-top:22px">Chiffres clés & Activité</div>', unsafe_allow_html=True)
    ca, cd, cg = st.columns([2, 2, 3])

    # Flux anomalies
    with ca:
        st.markdown("<div class='section-title' style='margin-top:0'>Flux d'anomalies</div>", unsafe_allow_html=True)
        if anomalies_all:
            html = ""
            for a in anomalies_all[:25]:
                card_cls, badge_cls, sev_lbl = anom_classes(a["type"])
                vals = " · ".join(f"{k}={v}" for k, v in list(a["values"].items())[:3])
                zname = ZONE_LABELS.get(a["location"]) or dyn_zones.get(a["location"], {}).get("label", a["location"])
                html += (
                    f'<div class="card-item {card_cls}">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">'
                    f'<span class="ci-badge {badge_cls}">{sev_lbl}</span>'
                    f'<span class="ci-time">{a["time"]}</span></div>'
                    f'<div class="ci-zone">{zname}</div>'
                    f'<div class="ci-type">{a["type"]} &nbsp;·&nbsp; {vals}</div>'
                    f'</div>'
                )
            st.markdown(f'<div class="scroll-box">{html}</div>', unsafe_allow_html=True)
        else:
            st.markdown("<div class='no-data'>Aucune anomalie pour l'instant.</div>", unsafe_allow_html=True)

    # Décisions IA
    with cd:
        st.markdown("<div class='section-title' style='margin-top:0'>Décisions de l'IA</div>", unsafe_allow_html=True)
        if decisions:
            html = ""
            for d in decisions[:15]:
                r = normalize_risque(d.get("risque", "medium"))
                card_cls, badge_cls = dec_classes(r)
                urg = '<span class="ci-badge ci-b-urgent">URGENT</span>' if d.get("urgence") else ""
                zname = ZONE_LABELS.get(d["location"]) or dyn_zones.get(d["location"], {}).get("label", d["location"])
                html += (
                    f'<div class="card-item {card_cls}">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">'
                    f'<div><span class="ci-badge {badge_cls}">{r.upper()}</span>{urg}</div>'
                    f'<span class="ci-time">{d["time"]}</span></div>'
                    f'<div class="ci-zone">{zname}</div>'
                    f'<div class="ci-desc">{d.get("diagnostic","")}</div>'
                    f'<div class="ci-action">{d.get("action","")}</div>'
                    f'</div>'
                )
            st.markdown(f'<div class="scroll-box">{html}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="no-data">En attente de décisions...</div>', unsafe_allow_html=True)

    # Graphiques
    with cg:
        st.markdown("<div class='section-title' style='margin-top:0'>Évolution des anomalies</div>", unsafe_allow_html=True)

        # Couleurs — statiques + dynamiques
        def zcolor(z, idx):
            if z in ZONE_COLORS: return ZONE_COLORS[z]
            return DYN_COLORS[idx % len(DYN_COLORS)]

        labels = []
        totals = []
        colors = []
        for i, z in enumerate(all_zone_ids):
            zname = ZONE_LABELS.get(z) or dyn_zones.get(z, {}).get("label", z)
            labels.append(zname)
            totals.append(len(counts_snap[z]))
            colors.append(zcolor(z, i))

        fig_bar = go.Figure(go.Bar(
            x=labels, y=totals,
            marker_color=colors, marker_line_width=0,
            text=totals, textposition="outside",
            textfont=dict(color="#94a3b8", size=11),
        ))
        fig_bar.update_layout(
            height=185, margin=dict(l=0,r=0,t=8,b=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8", family="Inter", size=11),
            showlegend=False, bargap=0.35,
            yaxis=dict(gridcolor="#f3f5f7", zeroline=False, tickfont=dict(size=10, color="#94a3b8")),
            xaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=11, color="#94a3b8")),
        )
        st.plotly_chart(fig_bar, width="stretch", config={"displayModeBar": False})

        fig_line = go.Figure()
        has_data = False
        for i, z in enumerate(all_zone_ids):
            if counts_snap[z]:
                has_data = True
                times = [t for t, _ in counts_snap[z]]
                c = zcolor(z, i)
                r = int(c[1:3], 16); g = int(c[3:5], 16); b = int(c[5:7], 16)
                zname = ZONE_LABELS.get(z) or dyn_zones.get(z, {}).get("label", z)
                fig_line.add_trace(go.Scatter(
                    x=times, y=list(range(1, len(times)+1)),
                    mode="lines", name=zname,
                    line=dict(color=c, width=2.5),
                    fill="tozeroy", fillcolor=f"rgba({r},{g},{b},0.07)"
                ))
        fig_line.update_layout(
            height=185, margin=dict(l=0,r=0,t=8,b=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8", family="Inter", size=11),
            legend=dict(orientation="h", y=-0.3, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
            yaxis=dict(gridcolor="#f3f5f7", zeroline=False, tickfont=dict(size=10, color="#94a3b8")),
            xaxis=dict(gridcolor="#f3f5f7", tickfont=dict(size=10, color="#94a3b8")),
            hovermode="x unified",
        )
        if has_data:
            st.plotly_chart(fig_line, width="stretch", config={"displayModeBar": False})
        else:
            st.markdown('<div class="no-data">En attente de données...</div>', unsafe_allow_html=True)

    # ── SIDEBAR ──
    with st.sidebar:
        st.markdown('<div style="text-align:center;font-size:0.9rem;font-weight:700;color:#e2e8f0;padding:16px 0 4px">Smart Building</div>', unsafe_allow_html=True)
        st.markdown('<div style="text-align:center;font-size:0.67rem;color:#475569;margin-bottom:16px">Supervision IoT</div>', unsafe_allow_html=True)
        st.markdown('<div class="sb-sep"></div>', unsafe_allow_html=True)

        # ── Contrôle des capteurs ──
        st.markdown('<div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#475569;margin:12px 0 10px">Contrôle des capteurs</div>', unsafe_allow_html=True)

        for zone in ZONES:
            with state["lock"]:
                status = state["sensor_status"].get(zone, "unknown")
            lbl, _ = sbadge(status)
            st.markdown(
                f'<div style="font-size:0.82rem;font-weight:600;color:#cbd5e1;margin-bottom:3px">{ZONE_LABELS[zone]}</div>'
                f'<div style="font-size:0.67rem;color:#475569;margin-bottom:5px">{lbl}</div>',
                unsafe_allow_html=True
            )
            b1, b2 = st.columns(2)
            with b1:
                if st.button("▶ Start", key=f"sb_s_{zone}"):
                    send_control(zone, "start")
            with b2:
                if st.button("⏸ Stop", key=f"sb_p_{zone}"):
                    send_control(zone, "stop")
            st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

        # ── Ajouter une zone ──
        st.markdown('<div class="sb-sep"></div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#475569;margin:12px 0 8px">Ajouter une zone</div>', unsafe_allow_html=True)

        if GenericSensor is None:
            st.warning("generic_sensor.py introuvable dans simulators/")
        else:
            with st.form("new_zone_form", clear_on_submit=True):
                zone_label  = st.text_input("Nom de la zone", placeholder="ex: Cafétéria")
                zone_id_raw = st.text_input("Identifiant (sans espaces)", placeholder="ex: cafeteria")
                selected_types = st.multiselect(
                    "Types de capteurs",
                    list(SENSOR_TYPES.keys()),
                    default=["temperature", "humidity"],
                )
                submitted = st.form_submit_button("➕ Créer la zone")

            if submitted:
                if not (zone_label and zone_id_raw and selected_types):
                    st.error("Remplis tous les champs.")
                else:
                    zone_id = zone_id_raw.strip().lower().replace(" ", "_")
                    with state["lock"]:
                        exists = zone_id in state["dynamic_zones"] or zone_id in ZONES
                    if exists:
                        st.error(f"Zone '{zone_id}' existe déjà.")
                    else:
                        sensor = GenericSensor(
                            zone_id=zone_id,
                            zone_label=zone_label,
                            sensor_types=selected_types,
                        )
                        sensor.start(anomaly_probability=0.05)
                        with state["lock"]:
                            state["dynamic_zones"][zone_id] = {
                                "label": zone_label,
                                "types": selected_types,
                                "sensor_obj": sensor,
                            }
                            state["sensor_status"][zone_id]  = "running"
                            state["sensor_data"][zone_id]    = {}
                            state["last_update"][zone_id]    = None
                            state["anomaly_counts"][zone_id] = []
                        st.success(f"Zone '{zone_label}' créée !")



        # ── Paramètres ──
        st.markdown('<div class="sb-sep"></div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#475569;margin:10px 0 6px">Paramètres</div>', unsafe_allow_html=True)
        refresh = st.slider("Rafraîchissement", 1, 10, 3, label_visibility="collapsed")
        st.markdown(f'<div style="font-size:0.67rem;color:#475569;text-align:center">Auto-refresh toutes les {refresh}s</div>', unsafe_allow_html=True)

    time.sleep(refresh)
    st.rerun()

if __name__ == "__main__":
    main()
