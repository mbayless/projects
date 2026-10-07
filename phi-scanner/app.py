"""PHI / PII Scanner — find protected health information and personal data across files and links,
with metrics and a manual-validation step. Runs entirely on your machine.

Run:  pip install -r requirements.txt && streamlit run app.py
"""
import io
import json

import pandas as pd
import streamlit as st

import detectors as D
import extractors as E

st.set_page_config(page_title="PHI / PII Scanner", page_icon="🛡️", layout="wide")

st.title("🛡️ PHI / PII Scanner")
st.caption("Find protected health information and personal data in JSON, text, Excel, Word and links — "
           "review every finding by hand, see the metrics, and export a redacted copy.")

with st.sidebar:
    st.header("Scan settings")
    st.success("Runs on this computer. Files are scanned in memory and never uploaded anywhere. "
               "The only network use is fetching a link you paste.", icon="🔒")
    min_conf = st.slider("Minimum confidence to show", 0.0, 0.99, 0.4, 0.05)
    with st.expander("Which identifiers to look for"):
        enabled = set()
        for t in D.ALL_TYPES:
            if st.checkbox(t, value=True, key=f"en_{t}"):
                enabled.add(t)
    st.caption(f"{len(enabled)} of {len(D.ALL_TYPES)} detectors on.")


def run_scan(segments, enabled):
    rows = []
    for label, text in segments:
        for f in D.scan_text(text, source=label, enabled=enabled):
            rows.append(f)
    df = pd.DataFrame(rows)
    if len(df):
        df.insert(0, "id", range(len(df)))
        df["status"] = "pending"
    return df


def merge_into_state(df):
    """Keep validation decisions when rescanning: match on (source,type,value,start)."""
    old = st.session_state.get("findings")
    if old is not None and len(old):
        prev = {(r["source"], r["type"], r["value"], r["start"]): r["status"] for _, r in old.iterrows()}
        df["status"] = [prev.get((r["source"], r["type"], r["value"], r["start"]), "pending") for _, r in df.iterrows()]
    st.session_state["findings"] = df
    st.session_state["segments"] = st.session_state.get("segments", {})


tab_scan, tab_review, tab_metrics, tab_export = st.tabs(
    ["1 · Scan", "2 · Validate", "3 · Metrics", "4 · Export"])

# ------------------------------------------------------------------ scan
with tab_scan:
    st.subheader("Add files or links")
    files = st.file_uploader("Files (JSON, TXT/CSV, Excel, Word)", type=["json", "txt", "md", "log", "csv", "tsv", "xlsx", "xlsm", "xls", "docx"],
                             accept_multiple_files=True)
    urls = st.text_area("Links to open and scan (one per line)", placeholder="https://example.com/report.html")
    paste = st.text_area("…or paste text directly", height=120)
    if st.button("Scan now", type="primary"):
        segments, seg_text, errors = [], {}, []
        for uf in files or []:
            try:
                segs = E.extract(uf.name, uf.getvalue())
                segments += segs
                for lbl, txt in segs:
                    seg_text[lbl] = txt
            except Exception as e:
                errors.append(f"{uf.name}: {type(e).__name__}: {e}")
        for url in [u.strip() for u in urls.splitlines() if u.strip()]:
            try:
                segs = E.from_url(url)
                segments += segs
                for lbl, txt in segs:
                    seg_text[lbl] = txt
            except Exception as e:
                errors.append(f"{url}: {type(e).__name__}: {e}")
        if paste.strip():
            segments.append(("pasted text", paste))
            seg_text["pasted text"] = paste
        if not segments:
            st.warning("Add at least one file, link or some pasted text.")
        else:
            df = run_scan(segments, enabled)
            st.session_state["segments"] = seg_text
            merge_into_state(df)
            st.success(f"Scanned {len(seg_text)} segment(s) from {len(files or [])} file(s), "
                       f"{len([u for u in urls.splitlines() if u.strip()])} link(s). Found {len(df)} potential item(s).")
        for e in errors:
            st.error(e)
    if st.session_state.get("findings") is not None:
        n = len(st.session_state["findings"])
        st.info(f"{n} finding(s) ready. Go to **Validate** to review them.")

# ------------------------------------------------------------------ validate
with tab_review:
    st.subheader("Review each finding")
    df = st.session_state.get("findings")
    if df is None or not len(df):
        st.info("Nothing scanned yet. Add files or links on the Scan tab.")
    else:
        view = df[df["confidence"] >= min_conf].copy()
        c = st.columns(4)
        c[0].metric("Shown", len(view))
        c[1].metric("Confirmed", int((df["status"] == "confirmed").sum()))
        c[2].metric("False positive", int((df["status"] == "false positive").sum()))
        c[3].metric("Pending", int((df["status"] == "pending").sum()))
        st.caption("Set each row's status, then click Save decisions. Confirmed items are the ones redacted on export.")
        edited = st.data_editor(
            view[["id", "source", "type", "category", "value", "confidence", "context", "status"]],
            width="stretch", hide_index=True, disabled=["id", "source", "type", "category", "value", "confidence", "context"],
            column_config={"status": st.column_config.SelectboxColumn("status", options=["pending", "confirmed", "false positive"], required=True),
                           "confidence": st.column_config.ProgressColumn("confidence", min_value=0.0, max_value=1.0)},
            key="editor")
        colA, colB, colC = st.columns(3)
        if colA.button("Save decisions", type="primary"):
            m = dict(zip(edited["id"], edited["status"]))
            df["status"] = df["id"].map(lambda i: m.get(i, df.loc[df["id"] == i, "status"].iloc[0]))
            st.session_state["findings"] = df
            st.success("Saved.")
            st.rerun()
        if colB.button("Confirm all shown"):
            ids = set(view["id"])
            df.loc[df["id"].isin(ids), "status"] = "confirmed"
            st.session_state["findings"] = df; st.rerun()
        if colC.button("Reset to pending"):
            df["status"] = "pending"; st.session_state["findings"] = df; st.rerun()

# ------------------------------------------------------------------ metrics
with tab_metrics:
    st.subheader("Metrics")
    df = st.session_state.get("findings")
    if df is None or not len(df):
        st.info("Nothing scanned yet.")
    else:
        confirmed = df[df["status"] == "confirmed"]
        reviewed = df[df["status"] != "pending"]
        c = st.columns(4)
        c[0].metric("Total findings", len(df))
        c[1].metric("Confirmed PHI/PII", len(confirmed))
        c[2].metric("Reviewed", f"{len(reviewed)}/{len(df)}")
        c[3].metric("Sources with findings", df["source"].nunique())
        pct = round(100 * len(reviewed) / len(df)) if len(df) else 0
        st.progress(pct / 100, f"Manual validation: {pct}% reviewed")
        st.markdown("**By category**")
        st.dataframe(df.groupby("category").agg(findings=("id", "count"),
                     confirmed=("status", lambda s: (s == "confirmed").sum())).reset_index(),
                     width="stretch", hide_index=True)
        st.markdown("**By type**")
        bytype = df.groupby("type").agg(findings=("id", "count"),
                   confirmed=("status", lambda s: (s == "confirmed").sum()),
                   avg_confidence=("confidence", "mean")).reset_index().sort_values("findings", ascending=False)
        bytype["avg_confidence"] = bytype["avg_confidence"].round(2)
        st.dataframe(bytype, width="stretch", hide_index=True)
        st.markdown("**By source (file, field or link)**")
        st.dataframe(df.groupby("source").agg(findings=("id", "count"),
                     confirmed=("status", lambda s: (s == "confirmed").sum())).reset_index().sort_values("findings", ascending=False),
                     width="stretch", hide_index=True)
        with st.expander("HIPAA 18 Safe Harbor coverage — findings per identifier"):
            counts = df["type"].value_counts().to_dict()
            rows = []
            for ident, dets in D.HIPAA_18:
                n = sum(counts.get(t, 0) for t in dets)
                rows.append({"HIPAA identifier": ident,
                             "Detector(s)": ", ".join(dets) if dets else "manual review (not text-detectable)",
                             "Findings": n})
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            st.caption("Identifiers 16 and 17 (biometrics, photos) can't be found in text — review those sources by hand.")

# ------------------------------------------------------------------ export
with tab_export:
    st.subheader("Export")
    df = st.session_state.get("findings")
    if df is None or not len(df):
        st.info("Nothing scanned yet.")
    else:
        confirmed = df[df["status"] == "confirmed"]
        st.write(f"{len(confirmed)} confirmed finding(s) will be redacted. Items left pending or marked false positive are not redacted.")
        mode = st.radio("Redaction style", ["Label — [US phone number]", "Mask — ****", "Remove"], index=0)
        mode_key = {"Label — [US phone number]": "type", "Mask — ****": "mask", "Remove": "remove"}[mode]
        st.markdown("**Finding report** — every finding and your decision:")
        only_conf = st.checkbox("Export only confirmed findings", value=False)
        out_df = (confirmed if only_conf else df).drop(columns=["id"])
        st.download_button("Download finding (CSV)", out_df.to_csv(index=False),
                           "finding.csv", "text/csv")
        st.download_button("Download finding (JSON)", out_df.to_json(orient="records", indent=1),
                           "finding.json", "application/json")
        st.markdown("**Redacted text** — each source with confirmed items removed:")
        seg_text = st.session_state.get("segments", {})
        parts = []
        for src, txt in seg_text.items():
            items = [r for _, r in confirmed.iterrows() if r["source"] == src]
            red = D.redact(txt, items, mode_key) if items else txt
            parts.append(f"===== {src} =====\n{red}")
        redacted = "\n\n".join(parts)
        st.download_button("Download redacted text", redacted, "redacted.txt", "text/plain")
        with st.expander("Preview redacted output"):
            st.text(redacted[:8000] + ("\n… (truncated)" if len(redacted) > 8000 else ""))
