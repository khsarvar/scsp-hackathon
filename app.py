"""Streamlit UI: discover CDC datasets OR upload/pick local; clean, hypothesize, analyze.

Session state holds a Workspace (multiple named DataFrames) plus a `primary_alias`
that the clean/hypothesize/analyze tabs operate on. The user can switch alias
to inspect intermediate frames (e.g. parents of a merge)."""

import os
import pandas as pd
import streamlit as st

from tools import profile_df
from agent import auto_clean, generate_hypotheses, analyze, discover
from discovery import Workspace

DATA_DIR = "data"

st.set_page_config(page_title="Data Analyst Agent", layout="wide")
st.title("Data Analyst Agent")


def _ensure_state():
    if "workspace" not in st.session_state:
        st.session_state.workspace = Workspace()
        st.session_state.primary_alias = None
        st.session_state.discover_events = []
        st.session_state.clean_events = []
        st.session_state.analyze_events = []
        st.session_state.log = []
        st.session_state.hypotheses = []
        st.session_state.history = []
        st.session_state.pending_question = ""
        st.session_state.source_label = None


ICONS = {"thought": "💭", "tool_call": "🔧", "tool_result": "✓", "final": "🏁"}


def render_event(event: dict, container) -> None:
    """Render a single agent event into a Streamlit container."""
    icon = ICONS.get(event.get("type"), "•")
    et = event.get("type")
    if et == "thought":
        container.markdown(f"{icon} _{event['text']}_")
    elif et == "tool_call":
        rationale = event.get("rationale") or ""
        args = event.get("args", {})
        args_str = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:4])
        line = f"{icon} **{event['name']}**({args_str})"
        if rationale:
            line += f" — {rationale}"
        container.markdown(line)
    elif et == "tool_result":
        container.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{icon} {event.get('summary', '')}", unsafe_allow_html=True)
    elif et == "final":
        summary = event.get("summary", "")
        extra = ""
        if event.get("primary_alias"):
            extra = f" → primary alias `{event['primary_alias']}`"
        container.markdown(f"{icon} **done**{extra} — {summary}")


def render_event_stream(events: list, expanded: bool = False, label: str = "Agent thought process"):
    """Render a list of events inside an expander (for replay after the run)."""
    if not events:
        return
    with st.expander(f"{label} ({len(events)} events)", expanded=expanded):
        for e in events:
            render_event(e, st)


def make_streaming_callback(placeholder):
    """Return (on_event, flush) — appends events to a buffer rendered live in `placeholder`."""
    buffer: list = []

    def on_event(event: dict):
        buffer.append(event)
        with placeholder.container():
            for e in buffer:
                render_event(e, st)

    return on_event


_ensure_state()
ws: Workspace = st.session_state.workspace


# ---------- Sidebar: data source ----------

with st.sidebar:
    st.header("Data source")
    source = st.radio(
        "Source",
        ["Discover (CDC)", "Upload CSV/XLSX", "Local datasets"],
        key="src",
    )

    if source == "Discover (CDC)":
        question = st.text_area(
            "Research question",
            placeholder="e.g. How does flu vaccination coverage relate to influenza hospitalization rates by state?",
            key="discover_q",
        )
        if st.button("Discover datasets", type="primary", disabled=not question.strip()):
            st.markdown("**Agent thought process**")
            stream_box = st.empty()
            on_event = make_streaming_callback(stream_box)
            with st.spinner("Searching CDC catalog..."):
                ws_out, primary, events = discover(question, workspace=ws, on_event=on_event)
                st.session_state.workspace = ws_out
                st.session_state.primary_alias = primary
                st.session_state.discover_events = events
                st.session_state.source_label = ("discover", question[:60])
                st.session_state.log = []
                st.session_state.clean_events = []
                st.session_state.analyze_events = []
                st.session_state.hypotheses = []
                st.session_state.history = []
                st.rerun()

    elif source == "Upload CSV/XLSX":
        up = st.file_uploader("Upload", type=["csv", "xlsx"])
        if up is not None:
            label = ("upload", up.name)
            if st.session_state.source_label != label:
                df_in = pd.read_csv(up) if up.name.lower().endswith(".csv") else pd.read_excel(up)
                ws.add("main", df_in, {"source": f"upload:{up.name}"})
                st.session_state.primary_alias = "main"
                st.session_state.source_label = label
                st.session_state.log = []
                st.session_state.hypotheses = []
                st.session_state.history = []

    else:  # Local datasets
        files = []
        if os.path.isdir(DATA_DIR):
            files = sorted(f for f in os.listdir(DATA_DIR) if f.lower().endswith((".csv", ".xlsx")))
        if not files:
            st.info(f"Drop CSV/XLSX files into ./{DATA_DIR}/ to use them here.")
        else:
            choice = st.selectbox("Dataset", files)
            label = ("local", choice)
            if st.session_state.source_label != label:
                path = os.path.join(DATA_DIR, choice)
                df_in = pd.read_csv(path) if path.lower().endswith(".csv") else pd.read_excel(path)
                ws.add("main", df_in, {"source": f"local:{choice}"})
                st.session_state.primary_alias = "main"
                st.session_state.source_label = label
                st.session_state.log = []
                st.session_state.hypotheses = []
                st.session_state.history = []

    # Workspace summary + alias picker
    if ws.frames:
        st.divider()
        st.subheader("Workspace")
        aliases = list(ws.frames.keys())
        current = st.session_state.primary_alias or aliases[0]
        idx = aliases.index(current) if current in aliases else 0
        st.session_state.primary_alias = st.selectbox("Active dataset", aliases, index=idx)
        for a in aliases:
            df_a = ws.frames[a]
            st.caption(f"`{a}` — {len(df_a)} × {len(df_a.columns)} — {ws.meta.get(a, {}).get('source', '')}")
        if st.button("Clear workspace"):
            st.session_state.workspace = Workspace()
            st.session_state.primary_alias = None
            st.session_state.source_label = None
            st.session_state.discover_log = []
            st.session_state.log = []
            st.session_state.hypotheses = []
            st.session_state.history = []
            st.rerun()


if not ws.frames or not st.session_state.primary_alias:
    st.info("Pick a data source to begin: discover via CDC, upload a file, or pick a local dataset.")
    render_event_stream(st.session_state.discover_events, expanded=True, label="Discovery — agent thought process")
    st.stop()


alias = st.session_state.primary_alias
df = ws.get(alias)


# ---------- Layout ----------

left, right = st.columns([1, 1])

with left:
    st.subheader(f"`{alias}` — {len(df)} rows × {len(df.columns)} cols")
    st.caption(ws.meta.get(alias, {}).get("source", ""))
    st.dataframe(df.head(50), use_container_width=True)

    with st.expander("Profile", expanded=False):
        st.json(profile_df(df))

    render_event_stream(st.session_state.discover_events, expanded=False, label="Discovery — agent thought process")

with right:
    tab_clean, tab_hypo, tab_analyze = st.tabs(["1. Clean", "2. Hypotheses", "3. Analyze"])

    with tab_clean:
        st.write(f"Auto-clean runs the agent on `{alias}` until it decides the data is analysis-ready.")
        if st.button("Auto-clean", type="primary"):
            stream_box = st.empty()
            on_event = make_streaming_callback(stream_box)
            with st.spinner("Cleaning agent thinking..."):
                events = auto_clean(ws, alias, on_event=on_event)
                st.session_state.clean_events = events
                st.rerun()
        render_event_stream(st.session_state.clean_events, expanded=True, label="Cleaning — agent thought process")

    with tab_hypo:
        if st.button("Generate hypotheses"):
            with st.spinner("Generating..."):
                st.session_state.hypotheses = generate_hypotheses(ws, alias)
        for i, h in enumerate(st.session_state.hypotheses):
            with st.container(border=True):
                st.markdown(f"**{h.get('question', '(no question)')}**")
                st.caption(
                    f"Test: `{h.get('test_type', '?')}` · Vars: {h.get('variables', [])}"
                )
                if h.get("rationale"):
                    st.write(h["rationale"])
                if st.button("Run this", key=f"run_h_{i}"):
                    st.session_state.pending_question = h.get("question", "")
                    st.rerun()

    with tab_analyze:
        q = st.text_input(
            "Ask a question",
            value=st.session_state.get("pending_question", ""),
            placeholder="e.g. Does outcome differ between treatment and control?",
            key="q_input",
        )
        if st.button("Analyze", type="primary") and q.strip():
            stream_box = st.empty()
            on_event = make_streaming_callback(stream_box)
            with st.spinner("Analyzing..."):
                answer, events = analyze(q, ws, alias, on_event=on_event)
                st.session_state.analyze_events = events
                st.session_state.history.append({"q": q, "alias": alias, "a": answer, "events": events})
                st.session_state.pending_question = ""
                st.rerun()
        for entry in reversed(st.session_state.history):
            with st.container(border=True):
                st.markdown(f"**Q ({entry.get('alias','?')}):** {entry['q']}")
                st.write(entry["a"])
                if entry.get("events"):
                    render_event_stream(entry["events"], expanded=False, label="Thought process")
