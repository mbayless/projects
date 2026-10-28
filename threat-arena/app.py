"""Threat Arena: watch bot attacks arrive on a live map and learn what each one is.

Run:  ./run      (or: streamlit run app.py)
"""
import math
from collections import Counter
from datetime import datetime, timedelta, timezone

import pydeck as pdk
import streamlit as st

from threatfeed import ATTACKS
from threatfeed.sample import SampleSource

# Where the attacks land: the lab in Azure East US (Virginia).
TARGET = {"name": "Your lab (Azure East US)", "lat": 36.67, "lon": -78.39}

st.set_page_config(page_title="Threat Arena", page_icon="🛡️", layout="wide")

# --- Sidebar ------------------------------------------------------------------

with st.sidebar:
    st.header("🛡️ Threat Arena")
    source_name = st.selectbox("Source", ["Sample data"],
                               help="More sources (honeypot, Sentinel) arrive in later steps. See README.")
    rate = st.slider("Attacks per minute", 5, 120, 30, help="Sample data only: how busy the botnets are.")
    window = st.slider("Show the last (minutes)", 5, 60, 15)
    refresh = st.select_slider("Refresh every (seconds)", [2, 5, 10, 30], value=5)
    paused = st.toggle("Pause", value=False)
    shown = st.multiselect("Attack types", list(ATTACKS), default=list(ATTACKS),
                           format_func=lambda k: f"{ATTACKS[k].emoji} {ATTACKS[k].name}")

if "source" not in st.session_state:
    st.session_state.source = SampleSource()
    st.session_state.events = st.session_state.source.history(minutes=15)
source = st.session_state.source
source.rate = rate

st.title("🛡️ Threat Arena")
if source_name == "Sample data":
    st.caption("**Sample data.** Simulated botnets with documentation-only IPs (192.0.2.x, 198.51.100.x, "
               "203.0.113.x). Step 2 in the README connects a real honeypot.")


def recent_events():
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window)
    return [e for e in st.session_state.events if e.time >= cutoff and e.attack in shown]


# --- Live part: re-runs on its own every few seconds --------------------------

@st.fragment(run_every=None if paused else refresh)
def live():
    if not paused:
        st.session_state.events += source.tick(seconds=refresh)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)
        st.session_state.events = [e for e in st.session_state.events if e.time >= cutoff]
    events = recent_events()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Bursts", len(events))
    c2.metric("Attempts", f"{sum(e.count for e in events):,}")
    c3.metric("Attacker IPs", len({e.source_ip for e in events}))
    c4.metric("Countries", len({e.country for e in events}))
    c5.metric("Got through", sum(not e.blocked for e in events),
              help="Bursts the defence didn't stop. In real data, start your investigation here.")

    left, right = st.columns([2, 1])
    with left:
        rows = [{
            "from": [e.lon, e.lat], "to": [TARGET["lon"], TARGET["lat"]],
            "color": [*ATTACKS[e.attack].color, 230 if not e.blocked else 140],
            "width": 1 + math.log10(e.count + 1) * 1.5,
            "radius": 30000 + math.log10(e.count + 1) * 40000,
            "label": f"{ATTACKS[e.attack].emoji} {ATTACKS[e.attack].name}",
            "ip": e.source_ip, "place": f"{e.city}, {e.country}", "count": e.count,
            "status": "blocked" if e.blocked else "GOT THROUGH",
        } for e in events]
        arcs = pdk.Layer("ArcLayer", rows, get_source_position="from", get_target_position="to",
                         get_source_color="color", get_target_color="color", get_width="width",
                         pickable=True, auto_highlight=True)
        dots = pdk.Layer("ScatterplotLayer", rows, get_position="from", get_fill_color="color",
                         get_radius="radius", pickable=True, opacity=0.6)
        home = pdk.Layer("ScatterplotLayer", [TARGET], get_position=["lon", "lat"],
                         get_fill_color=[255, 255, 255, 255], get_line_color=[0, 0, 0, 255],
                         stroked=True, line_width_min_pixels=2, get_radius=90000)
        st.pydeck_chart(pdk.Deck(
            layers=[arcs, dots, home],
            initial_view_state=pdk.ViewState(latitude=25, longitude=10, zoom=0.9, pitch=35),
            tooltip={"html": "<b>{label}</b><br/>{ip} · {place}<br/>{count} attempts · {status}"},
        ), height=520)

        counts = Counter(e.attack for e in events)
        st.markdown("  ".join(f"{a.emoji} **{a.name}** {counts.get(k, 0)}"
                              for k, a in ATTACKS.items() if k in shown))

    with right:
        st.markdown("**Live feed**")
        feed = [{
            "time": e.time.strftime("%H:%M:%S"),
            "attack": f"{ATTACKS[e.attack].emoji} {ATTACKS[e.attack].name}",
            "from": f"{e.source_ip} ({e.city})",
            "tries": e.count,
            "result": "✅ blocked" if e.blocked else "⚠️ through",
        } for e in reversed(events[-60:])]
        st.dataframe(feed, hide_index=True, height=560, width="stretch")


live()

# --- Understand a threat ------------------------------------------------------

st.divider()
st.subheader("Understand a threat")
events = recent_events()
counts = Counter(e.attack for e in events)
# Fixed labels and order: if they changed with the counts, Streamlit would reset the choice.
pick = st.radio("Attack type", shown or list(ATTACKS), horizontal=True, key="pick",
                format_func=lambda k: f"{ATTACKS[k].emoji} {ATTACKS[k].name}")
a = ATTACKS[pick]

c1, c2 = st.columns([3, 2])
with c1:
    st.markdown(f"### {a.emoji} {a.name}")
    st.caption(f"{counts.get(pick, 0)} bursts in the last {window} minutes")
    st.markdown(f"**Severity:** {a.severity} · **MITRE ATT&CK:** [{a.mitre_id} {a.mitre_name}]({a.mitre_url})")
    st.markdown(f"**What's happening.** {a.what}")
    st.markdown(f"**Why it's a bot.** {a.why_bot}")
    st.markdown("**What to look for in the logs**\n" + "\n".join(f"- {x}" for x in a.look_for))
    st.markdown("**How to stop it**\n" + "\n".join(f"- {x}" for x in a.defend))
    st.caption(f"In the Minecraft arena (step 4) this attack is a **{a.minecraft_mob}**.")
with c2:
    mine = [e for e in events if e.attack == pick]
    if mine:
        latest = mine[-1]
        st.markdown(f"**Latest evidence** from `{latest.source_ip}` ({latest.city}, {latest.country}), "
                    f"{latest.count} attempts")
        st.code("\n".join(latest.evidence), language=None)
        top = Counter(e.source_ip for e in mine).most_common(5)
        st.markdown("**Busiest attacker IPs**")
        st.dataframe([{"ip": ip, "bursts": n} for ip, n in top], hide_index=True, width="stretch")
    else:
        st.info("None of these in the current window.")
