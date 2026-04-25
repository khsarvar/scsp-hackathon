"""Streamlit UI: upload or pick a dataset, auto-clean, get hypotheses, run analyses."""

import os
import json
import pandas as pd
import streamlit as st

from tools import profile_df
from agent import auto_clean, generate_hypotheses, analyze

DATA_DIR = "data"

st.set_page_config(page_title="Data Analyst Agent", layout="wide")
st.title("Data Analyst Agent")

# ---------- Sidebar: data source ----------

with st.sidebar:
    st.header("Data source")
    source = st.radio("Source", ["Upload CSV/XLSX", "Local datasets"], key="src")

    df_in = None
    label = None
    if source == "Upload CSV/XLSX":
        up = st.file_uploader("Upload", type=["csv", "xlsx"])
        if up is not None:
            df_in = pd.read_csv(up) if up.name.lower().endswith(".csv") else pd.read_excel(up)
            label = ("upload", up.name)
    else:
        files = []
        if os.path.isdir(DATA_DIR):
            files = sorted(f for f in os.listdir(DATA_DIR) if f.lower().endswith((".csv", ".xlsx")))
        if not files:
            st.info(f"Drop CSV/XLSX files into ./{DATA_DIR}/ to use them here.")
        else:
            choice = st.selectbox("Dataset", files)
            path = os.path.join(DATA_DIR, choice)
            df_in = pd.read_csv(path) if path.lower().endswith(".csv") else pd.read_excel(path)
            label = ("local", choice)

if df_in is None:
    st.info("Pick or upload a dataset to begin.")
    st.stop()

# ---------- Reset session state when source changes ----------

if st.session_state.get("source_label") != label:
    st.session_state.source_label = label
    st.session_state.df = df_in.copy()
    st.session_state.original = df_in.copy()
    st.session_state.log = []
    st.session_state.hypotheses = []
    st.session_state.history = []
    st.session_state.pending_question = ""

with st.sidebar:
    if st.button("Reset to original"):
        st.session_state.df = st.session_state.original.copy()
        st.session_state.log = []
        st.rerun()

# ---------- Layout ----------

left, right = st.columns([1, 1])

with left:
    st.subheader(f"Data ({len(st.session_state.df)} rows × {len(st.session_state.df.columns)} cols)")
    st.dataframe(st.session_state.df.head(50), use_container_width=True)

    with st.expander("Profile", expanded=False):
        st.json(profile_df(st.session_state.df))

with right:
    tab_clean, tab_hypo, tab_analyze = st.tabs(["1. Clean", "2. Hypotheses", "3. Analyze"])

    # ---- Clean ----
    with tab_clean:
        st.write("Auto-clean runs the agent until it decides the data is analysis-ready.")
        if st.button("Auto-clean", type="primary"):
            with st.spinner("Cleaning agent thinking..."):
                cleaned, log = auto_clean(st.session_state.df)
                st.session_state.df = cleaned
                st.session_state.log.extend(log)
                st.rerun()
        if st.session_state.log:
            st.markdown("**Cleaning log**")
            for entry in st.session_state.log:
                st.json(entry)

    # ---- Hypotheses ----
    with tab_hypo:
        if st.button("Generate hypotheses"):
            with st.spinner("Generating..."):
                st.session_state.hypotheses = generate_hypotheses(st.session_state.df)
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

    # ---- Analyze ----
    with tab_analyze:
        q = st.text_input(
            "Ask a question",
            value=st.session_state.get("pending_question", ""),
            placeholder="e.g. Does outcome differ between treatment and control?",
            key="q_input",
        )
        if st.button("Analyze", type="primary") and q.strip():
            with st.spinner("Analyzing..."):
                answer = analyze(q, st.session_state.df)
                st.session_state.history.append({"q": q, "a": answer})
                st.session_state.pending_question = ""
                st.rerun()
        for entry in reversed(st.session_state.history):
            with st.container(border=True):
                st.markdown(f"**Q:** {entry['q']}")
                st.write(entry["a"])
