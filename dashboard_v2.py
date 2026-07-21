"""
Dashboard Smart Building — Design LO Industry
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

BROKER_HOST   = "localhost"
BROKER_PORT   = 1883
MAX_ANOMALIES = 60
ZONES         = ["floor1", "floor2", "floor3", "server_room"]

ZONE_LABELS  = {"floor1": "Étage 1", "floor2": "Étage 2", "floor3": "Étage 3", "server_room": "Salle serveur"}
ZONE_COLORS  = {"floor1": "#10b981", "floor2": "#3b82f6", "floor3": "#ef4444", "server_room": "#8b5cf6"}

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
    "cpu_load_pct": ("⚙", "Charge CPU",   "%"),
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

#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 1.5rem 2rem 1rem !important; max-width: 100% !important; }

/* ── TOP BAR ── */
.topbar {
    display: flex; align-items: center; justify-content: space-between;
    background: #fff; border-radius: 14px; padding: 14px 22px;
    margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.04);
}
.topbar-left  { display: flex; align-items: center; gap: 14px; }
.topbar-title { font-size: 1.55rem; font-weight: 800; color: #1e293b; }
.topbar-sub   { font-size: 0.72rem; color: #64748b; margin-top: 1px; }
.topbar-right { display: flex; align-items: center; gap: 12px; }
.topbar-time  { font-size: 0.78rem; color: #64748b; }
.pill-conn { display:inline-flex;align-items:center;gap:5px;padding:5px 12px;
             border-radius:999px;font-size:0.73rem;font-weight:600; }
.pill-ok   { background:#dcfce7;color:#16a34a; }
.pill-err  { background:#fee2e2;color:#dc2626; }
.dot { width:7px;height:7px;border-radius:50%; }
.dot-ok  { background:#16a34a; }
.dot-err { background:#dc2626; }

/* ── SECTION TITLE ── */
.section-title {
    font-size: 0.72rem; font-weight: 700; color: #94a3b8;
    text-transform: uppercase; letter-spacing: .1em;
    margin: 18px 0 10px; padding-bottom: 2px;
}

/* ── KPI CARDS ── */
.kpi-card {
    border-radius: 14px; padding: 20px 22px; color: #fff;
    position: relative; overflow: hidden; min-height: 110px;
}
.kpi-card .kpi-icon {
    font-size: 1.8rem; opacity: .8; margin-bottom: 4px; display: block;
}
.kpi-card .kpi-val {
    font-size: 2.2rem; font-weight: 800; line-height: 1; color: inherit;
}
.kpi-card .kpi-label {
    font-size: 0.8rem; font-weight: 500; opacity: .8; margin-top: 4px; color: inherit;
}
.kpi-red    { background: linear-gradient(135deg, #f87171, #fca5a5); color:#7f1d1d !important; }
.kpi-orange { background: linear-gradient(135deg, #fb923c, #fdba74); color:#7c2d12 !important; }
.kpi-blue   { background: linear-gradient(135deg, #60a5fa, #93c5fd); color:#1e3a8a !important; }
.kpi-purple { background: linear-gradient(135deg, #a78bfa, #c4b5fd); color:#3b0764 !important; }
.kpi-green  { background: linear-gradient(135deg, #34d399, #6ee7b7); color:#064e3b !important; }
.kpi-teal   { background: linear-gradient(135deg, #14b8a6, #5eead4); color:#134e4a !important; }

/* ── SENSOR CARDS ── */
.sensor-wrap {
    background: #fff; border-radius: 14px; padding: 16px 18px;
    box-shadow: 0 1px 3px rgba(0,0,0,.04); height: 100%;
}
.sensor-head {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 4px;
}
.sensor-name { font-size: 0.9rem; font-weight: 700; color: #1e293b; }
.sensor-ts   { font-size: 0.65rem; color: #94a3b8; margin-bottom: 10px; }
.s-badge { font-size:0.68rem;font-weight:700;padding:3px 9px;border-radius:6px;
           text-transform:uppercase;letter-spacing:.05em; }
.s-run  { background:#dcfce7;color:#16a34a; }
.s-pau  { background:#fef9c3;color:#ca8a04; }
.s-sto  { background:#fee2e2;color:#dc2626; }
.s-unk  { background:#f1f5f9;color:#94a3b8; }
.metric-row {
    display:flex;justify-content:space-between;align-items:center;
    padding:5px 0;border-bottom:1px solid #f8fafc;font-size:0.8rem;
}
.metric-row:last-child { border-bottom:none; }
.m-label { color:#64748b; }
.m-val   { font-weight:600;color:#334155;font-family:monospace; }
.m-val.danger { color:#f43f5e; }
.ano-badge {
    margin-top:8px;padding:5px 10px;border-radius:6px;
    background:#fff5f5;border:1px solid #fde8e8;
    font-size:0.72rem;font-weight:700;color:#dc2626;text-transform:uppercase;
}

/* ── FEED ── */
.feed-box {
    max-height:380px;overflow-y:auto;padding-right:3px;
}
.feed-item {
    display:flex;gap:10px;padding:9px 12px;background:#fff;
    border-radius:10px;margin-bottom:6px;
    box-shadow:0 1px 2px rgba(0,0,0,.04);border-left:3px solid;
}
.f-fire   { border-color:#fca5a5; }
.f-high   { border-color:#fed7aa; }
.f-medium { border-color:#bfdbfe; }
.feed-zone { font-size:0.78rem;font-weight:600;color:#334155; }
.feed-type { font-size:0.7rem;color:#64748b;margin-top:1px; }
.feed-time { font-size:0.65rem;color:#94a3b8;white-space:nowrap;font-family:monospace; }

/* ── DECISIONS ── */
.dec-box { max-height:480px;overflow-y:auto;padding-right:3px;margin-top:0; }
.dec-item {
    background:#fff;border-radius:10px;padding:13px 15px;
    margin-bottom:7px;box-shadow:0 1px 2px rgba(0,0,0,.04);border-left:3px solid;
}
.dec-critical { border-color:#fca5a5; }
.dec-high     { border-color:#fed7aa; }
.dec-medium   { border-color:#bfdbfe; }
.dec-low      { border-color:#a7f3d0; }
.dec-risque   { font-size:0.68rem;font-weight:800;text-transform:uppercase;letter-spacing:.07em; }
.dec-r-critical { color:#ef4444; }
.dec-r-high     { color:#f97316; }
.dec-r-medium   { color:#3b82f6; }
.dec-r-low      { color:#10b981; }
.dec-zone       { font-size:0.8rem;font-weight:600;color:#334155;margin:3px 0; }
.dec-diag       { font-size:0.74rem;color:#475569;line-height:1.55;margin-bottom:5px; }
.dec-action     { font-size:0.7rem;color:#64748b;font-style:italic;margin-bottom:5px;line-height:1.45; }
.dec-actions    { font-size:0.68rem;font-weight:700; }
.urg-tag        { background:#fee2e2;color:#dc2626;font-size:0.58rem;padding:1px 5px;
                  border-radius:4px;font-weight:800;margin-left:5px;vertical-align:middle; }
.no-data        { color:#94a3b8;font-size:0.8rem;font-style:italic;padding:10px 0; }

/* ── BUTTONS ── */
.stButton > button {
    border-radius:8px !important;font-size:0.78rem !important;font-weight:600 !important;
    border:1px solid #e8edf2 !important;background:#fafbfc !important;
    color:#475569 !important;padding:4px 10px !important;transition:all .15s !important;
}
.stButton > button:hover {
    background:#f1f5f9 !important;border-color:#dde3ea !important;color:#334155 !important;
}

/* ── SIDEBAR ── */
section[data-testid="stSidebar"] {
    background: #0f172a !important;
    border-right: none !important;
}
section[data-testid="stSidebar"] * { color: #94a3b8 !important; }
section[data-testid="stSidebar"] h3 { color: #e2e8f0 !important; font-size:0.85rem !important; }
section[data-testid="stSidebar"] .stMarkdown p { font-size:0.78rem !important; }
.sidebar-section { font-size:0.62rem;font-weight:700;text-transform:uppercase;
                   letter-spacing:.1em;color:#475569;margin:16px 0 8px; }
.stSlider > div > div > div { background:#3b82f6 !important; }
</style>
"""

# Logo SVG smart building


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
    }

@st.cache_resource
def get_mqtt_client():
    state = get_shared_state()

    def on_connect(client, userdata, flags, rc, props):
        if str(rc) in ("0", "Success"):
            client.subscribe("building/#", qos=1)
            client.subscribe("status/#",   qos=1)
            client.subscribe("decisions/#",qos=1)
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
                if loc in ZONES:
                    with state["lock"]:
                        state["sensor_data"][loc]  = values
                        state["last_update"][loc]  = datetime.now()
                    if "anomaly" in values:
                        now = datetime.now()
                        with state["lock"]:
                            state["anomalies"].appendleft({
                                "time":     now.strftime("%H:%M:%S"),
                                "location": loc,
                                "type":     values["anomaly"],
                                "values":   {k: v for k, v in values.items() if k != "anomaly"},
                            })
                            state["anomaly_counts"][loc].append((now, values["anomaly"]))
                            if len(state["anomaly_counts"][loc]) > 100:
                                state["anomaly_counts"][loc].pop(0)
            elif topic.startswith("status/"):
                loc    = payload.get("location")
                status = payload.get("status", "unknown")
                if loc in ZONES:
                    with state["lock"]:
                        state["sensor_status"][loc] = status
            elif topic.startswith("decisions/"):
                with state["lock"]:
                    state["decisions"].appendleft({
                        "time":       datetime.now().strftime("%H:%M:%S"),
                        "location":   payload.get("location", "?"),
                        "diagnostic": payload.get("diagnostic", ""),
                        "risque":     payload.get("risque", "medium"),
                        "urgence":    payload.get("urgence", False),
                        "action":     payload.get("action_recommandee", ""),
                        "actions":    payload.get("actions_declenchees", []),
                    })
        except Exception:
            pass

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="dashboard-v2")
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
        client.loop_start()
    except Exception:
        pass
    return client

def send_control(location, command):
    c = get_mqtt_client()
    if c:
        c.publish(f"control/{location}", json.dumps({
            "command": command,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), qos=1)

def sbadge(status):
    m = {"running":("● Actif","s-run"), "paused":("⏸ Pausé","s-pau"), "stopped":("■ Arrêté","s-sto")}
    return m.get(status, ("○ Inconnu","s-unk"))

def is_danger(k, v):
    th = THRESHOLDS.get(k)
    if th and isinstance(v, (int,float)): return v > th
    if k == "smoke": return v == 1
    return False

def risque_info(r):
    r = r.lower()
    if r == "critical": return "c-critical","b-critical"
    if r == "high":     return "c-high","b-high"
    if r == "low":      return "c-medium","b-low"
    return "c-medium","b-medium"

def fmt_val(k, v):
    if k == "motion": return "Détecté" if v else "Aucun"
    if k == "smoke":  return "⚠ DÉTECTÉE" if v else "Aucune"
    _, _, unit = METRIC_LABELS.get(k, ("","","")); return f"{v}{unit}"

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(page_title="Smart Building", page_icon="",
                       layout="wide", initial_sidebar_state="expanded")
    get_mqtt_client()
    state = get_shared_state()
    st.markdown(CSS, unsafe_allow_html=True)

    # ── TOP BAR ──
    with state["lock"]:
        connected     = state["connected"][0]
        anomalies_all = list(state["anomalies"])
        counts_snap   = {z: list(state["anomaly_counts"][z]) for z in ZONES}
        active_zones  = sum(1 for z in ZONES if state["sensor_status"][z] == "running")

    fire_count  = sum(1 for a in anomalies_all if a["type"] == "fire")
    high_count  = sum(1 for a in anomalies_all if a["type"] in ("overheating","overheat","cpu_spike","power_surge"))
    total_anom  = sum(len(counts_snap[z]) for z in ZONES)
    pill_cls    = "pill-ok" if connected else "pill-err"
    dot_cls     = "dot-ok"  if connected else "dot-err"
    pill_txt    = "MQTT Connecté" if connected else "MQTT Déconnecté"

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
        <span class="pill-conn {pill_cls}"><span class="dot {dot_cls}"></span>{pill_txt}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── KPI CARDS ──
    st.markdown('<div class="section-title">Notifications en temps réel</div>', unsafe_allow_html=True)
    k1,k2,k3,k4,k5 = st.columns(5)
    kpis = [
        (k1, "", str(active_zones)+"/4", "Capteurs actives",    "kpi-teal"),
        (k2, "",  str(total_anom),        "Anomalies totales","kpi-orange"),
        (k3, "",  str(fire_count),         "Alertes incendie","kpi-red"),
        (k4, "",  str(high_count),         "Surchauffes",     "kpi-purple"),
        (k5, "",  str(4-fire_count-high_count if 4-fire_count-high_count > 0 else 0),
              "Zones normales", "kpi-green"),
    ]
    for col, icon, val, label, cls in kpis:
        with col:
            st.markdown(f"""
            <div class="kpi-card {cls}">
              <span class="kpi-icon">{icon}</span>
              <div class="kpi-val">{val}</div>
              <div class="kpi-label">{label}</div>
            </div>""", unsafe_allow_html=True)

    # ── SENSOR CARDS ──
    st.markdown('<div class="section-title">Données capteurs en temps réel</div>', unsafe_allow_html=True)
    cols = st.columns(4)
    for i, zone in enumerate(ZONES):
        with cols[i]:
            with state["lock"]:
                data   = dict(state["sensor_data"][zone])
                status = state["sensor_status"][zone]
                lu     = state["last_update"][zone]
            delta      = f"{(datetime.now()-lu).seconds}s" if lu else "-"
            anomaly_v  = data.pop("anomaly", None) if data else None
            label, bcls = sbadge(status)

            with st.container(border=True):
                th, tb1, tb2 = st.columns([5, 1, 1])
                with th:
                    st.markdown(
                        f'<div class="sensor-head">'
                        f'<span class="sensor-name">{ZONE_LABELS[zone]}</span>'
                        f'<span class="s-badge {bcls}">{label}</span></div>'
                        f'<div class="sensor-ts">Mis à jour il y a {delta}</div>',
                        unsafe_allow_html=True
                    )
                with tb1:
                    if st.button("▶", key=f"s_{zone}", help="Démarrer"):
                        send_control(zone, "start")
                with tb2:
                    if st.button("⏸", key=f"p_{zone}", help="Arrêter"):
                        send_control(zone, "stop")

                if data:
                    rows = ""
                    for k, v in data.items():
                        if k not in METRIC_LABELS: continue
                        icon, lbl, _ = METRIC_LABELS[k]
                        danger = is_danger(k, v)
                        vcls = "m-val danger" if danger else "m-val"
                        rows += (f'<div class="metric-row">'
                                 f'<span class="m-label">{icon} {lbl}</span>'
                                 f'<span class="{vcls}">{fmt_val(k,v)}</span></div>')
                    if anomaly_v:
                        rows += f'<div class="ano-badge">⚠ {anomaly_v}</div>'
                    st.markdown(rows, unsafe_allow_html=True)
                else:
                    st.caption("En attente de données...")

    # ── BOTTOM ──
    st.markdown('<div class="section-title">Chiffres clés & Activité</div>', unsafe_allow_html=True)
    ca, cd, cg = st.columns([2, 2, 3])
    # equal top alignment

    # Flux anomalies
    with ca:
        st.markdown("<div class='section-title' style='margin-top:0'>Flux d'anomalies</div>", unsafe_allow_html=True)
        if anomalies_all:
            feed = ""
            for a in anomalies_all[:25]:
                icon = ANOMALY_ICONS.get(a["type"], "🔵")
                sev  = "f-fire" if a["type"]=="fire" else ("f-high" if a["type"] in ("overheating","overheat","cpu_spike","power_surge") else "f-medium")
                vals = " · ".join(f"{k}={v}" for k,v in list(a["values"].items())[:2])
                feed += (f'<div class="feed-item {sev}">'
                         f'<span style="font-size:.95rem;margin-top:1px">{icon}</span>'
                         f'<div style="flex:1;min-width:0">'
                         f'<div style="display:flex;justify-content:space-between">'
                         f'<span class="feed-zone">{ZONE_LABELS.get(a["location"],a["location"])}</span>'
                         f'<span class="feed-time">{a["time"]}</span></div>'
                         f'<div class="feed-type">{a["type"]} · {vals}</div>'
                         f'</div></div>')
            st.markdown(f'<div class="feed-box">{feed}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="no-data">Aucune anomalie pour l\'instant.</div>', unsafe_allow_html=True)

    # Décisions IA
    with cd:
        st.markdown("<div class='section-title' style='margin-top:0'>Décisions de l'IA</div>", unsafe_allow_html=True)
        with state["lock"]:
            decisions = list(state["decisions"])
        RCOLS = {
            "critical": ("#ef4444","dec-critical","dec-r-critical"),
            "high":     ("#f97316","dec-high",    "dec-r-high"),
            "medium":   ("#3b82f6","dec-medium",  "dec-r-medium"),
            "low":      ("#10b981","dec-low",      "dec-r-low"),
        }
        if decisions:
            dec = ""
            for d in decisions[:15]:
                r = d.get("risque", "medium").lower()
                card_cls, badge_cls = risque_info(r)
                urg = '<span class="badge-sev b-urgent">URGENT</span>' if d.get("urgence") else ""
                dec += (
                    f'<div class="card-item {card_cls}">'
                    f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:2px">'
                    f'<div><span class="badge-sev {badge_cls}">{r.upper()}</span>{urg}</div>'
                    f'<span class="c-time">{d["time"]}</span></div>'
                    f'<div class="c-zone">{ZONE_LABELS.get(d["location"],d["location"])}</div>'
                    f'<div class="c-desc">{d.get("diagnostic","")}</div>'
                    f'<div class="c-action">{d.get("action","")}</div>'
                    f'</div>'
                )
            st.markdown(f'<div class="dec-box">{dec}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="no-data">En attente de décisions...</div>', unsafe_allow_html=True)

    # Graphiques
    with cg:
        st.markdown("<div class='section-title' style='margin-top:0'>Évolution des anomalies</div>", unsafe_allow_html=True)
        totals = [len(counts_snap[z]) for z in ZONES]
        fig_bar = go.Figure(go.Bar(
            x=[ZONE_LABELS[z] for z in ZONES], y=totals,
            marker_color=[ZONE_COLORS[z] for z in ZONES],
            marker_line_width=0,
            text=totals, textposition="outside",
            textfont=dict(color="#64748b", size=11),
        ))
        fig_bar.update_layout(
            height=185, margin=dict(l=0,r=0,t=8,b=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#64748b", family="Inter", size=11),
            showlegend=False, bargap=0.35,
            yaxis=dict(gridcolor="#f3f5f7", zeroline=False, tickfont=dict(size=10, color="#94a3b8")),
            xaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=11, color="#94a3b8")),
        )
        st.plotly_chart(fig_bar, width="stretch", config={"displayModeBar": False})

        fig_line = go.Figure()
        has_data = False
        for zone in ZONES:
            if counts_snap[zone]:
                has_data = True
                times = [t for t,_ in counts_snap[zone]]
                r = int(ZONE_COLORS[zone][1:3],16)
                g = int(ZONE_COLORS[zone][3:5],16)
                b = int(ZONE_COLORS[zone][5:7],16)
                fig_line.add_trace(go.Scatter(
                    x=times, y=list(range(1, len(times)+1)),
                    mode="lines", name=ZONE_LABELS[zone],
                    line=dict(color=ZONE_COLORS[zone], width=2.5),
                    fill="tozeroy", fillcolor=f"rgba({r},{g},{b},0.08)"
                ))
        fig_line.update_layout(
            height=185, margin=dict(l=0,r=0,t=8,b=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#64748b", family="Inter", size=11),
            legend=dict(orientation="h", y=-0.28, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
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
        st.markdown('<div style="text-align:center;font-size:0.85rem;font-weight:700;color:#e2e8f0;margin-bottom:4px">Smart Building</div>', unsafe_allow_html=True)
        st.markdown('<div style="text-align:center;font-size:0.68rem;color:#475569;margin-bottom:20px">Supervision IoT</div>', unsafe_allow_html=True)
        st.markdown('<div class="sidebar-section">Contrôle des capteurs</div>', unsafe_allow_html=True)

        for zone in ZONES:
            with state["lock"]:
                status = state["sensor_status"][zone]
            label, _ = sbadge(status)
            st.markdown(f'<div style="font-size:0.68rem;color:#64748b;margin-bottom:6px">{label}</div>', unsafe_allow_html=True)
            b1, b2 = st.columns(2)
            with b1:
                if st.button("▶ Start", key=f"sb_s_{zone}", width="stretch"):
                    send_control(zone, "start")
            with b2:
                if st.button("⏸ Stop", key=f"sb_p_{zone}", width="stretch"):
                    send_control(zone, "stop")
            st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)

        st.markdown('<hr style="border-color:#1e293b;margin:8px 0"><div class="sidebar-section">Paramètres</div>', unsafe_allow_html=True)
        refresh = st.slider("Rafraîchissement", 1, 10, 3, label_visibility="collapsed")
        st.markdown(f'<div style="font-size:0.68rem;color:#475569;text-align:center">Auto-refresh toutes les {refresh}s</div>', unsafe_allow_html=True)

    time.sleep(refresh)
    st.rerun()

if __name__ == "__main__":
    main()
