"""
Multi-Source Candidate Data Transformer — Streamlit UI

Thin UI layer on top of the existing candidate_transformer engine.
Run locally with:  streamlit run app.py
Deploy free on Streamlit Community Cloud by pointing it at this file.

This file does not reimplement any pipeline logic. It only:
  1. collects inputs (CSV / notes / resume PDF / GitHub URL / config),
  2. calls candidate_transformer.cli.run(...),
  3. renders the resulting profile as a readable card + raw JSON.
"""

import json
import tempfile
from pathlib import Path

import streamlit as st

from candidate_transformer.cli import run as run_pipeline

st.set_page_config(
    page_title="Candidate Data Transformer",
    page_icon="🧩",
    layout="wide",
)

DEFAULT_CONFIG_PATH = Path("configs/custom_output.json")


# ────────────────────────────── helpers ──────────────────────────────

def save_upload(uploaded_file, suffix: str) -> str | None:
    """Write an uploaded file to a temp path and return that path."""
    if uploaded_file is None:
        return None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded_file.getvalue())
    tmp.close()
    return tmp.name


def confidence_color(value: float) -> str:
    if value >= 0.8:
        return "#16a34a"   # green
    if value >= 0.6:
        return "#d97706"   # amber
    return "#dc2626"       # red


def confidence_bar(label: str, value: float, sources: list[str] | None = None):
    pct = max(0, min(100, round(value * 100)))
    color = confidence_color(value)
    src = f"  ·  {', '.join(sources)}" if sources else ""
    st.markdown(
        f"""
        <div style="margin-bottom:10px;">
          <div style="display:flex;justify-content:space-between;font-size:0.85rem;color:#444;">
            <span><b>{label}</b>{src}</span>
            <span style="color:{color};font-weight:600;">{pct}%</span>
          </div>
          <div style="background:#e5e7eb;border-radius:6px;height:8px;width:100%;">
            <div style="background:{color};width:{pct}%;height:8px;border-radius:6px;"></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_profile_card(profile: dict):
    name = profile.get("full_name") or "(name unknown)"
    headline = profile.get("headline")
    overall = profile.get("overall_confidence")
    loc = profile.get("location") or {}
    loc_str = ", ".join(v for v in [loc.get("city"), loc.get("region"), loc.get("country")] if v) or "—"

    top = st.columns([3, 1])
    with top[0]:
        st.markdown(f"## {name}")
        if headline:
            st.markdown(f"*{headline}*")
        st.markdown(f"📍 {loc_str}")
    with top[1]:
        if overall is not None:
            st.metric("Overall confidence", f"{round(overall * 100)}%")

    st.divider()

    cols = st.columns(2)
    with cols[0]:
        st.markdown("**Emails**")
        emails = profile.get("emails") or []
        st.write(", ".join(emails) if emails else "—")
    with cols[1]:
        st.markdown("**Phones**")
        phones = profile.get("phones") or []
        st.write(", ".join(phones) if phones else "—")

    links = profile.get("links") or {}
    link_bits = []
    if links.get("github"):
        link_bits.append(f"[GitHub]({links['github']})")
    if links.get("linkedin"):
        link_bits.append(f"[LinkedIn]({links['linkedin']})")
    if links.get("portfolio"):
        link_bits.append(f"[Portfolio]({links['portfolio']})")
    for other in links.get("other") or []:
        link_bits.append(other)
    if link_bits:
        st.markdown("**Links:** " + " · ".join(link_bits))

    st.markdown("")
    st.markdown("### Skills")
    skills = profile.get("skills") or []
    if not skills:
        st.caption("No skills extracted.")
    else:
        skill_cols = st.columns(2)
        for i, s in enumerate(skills):
            with skill_cols[i % 2]:
                confidence_bar(s.get("name", "?"), s.get("confidence", 0), s.get("sources"))

    exp = profile.get("experience") or []
    if exp:
        st.markdown("### Experience")
        for e in exp:
            title = e.get("title", "")
            company = e.get("company", "")
            start, end = e.get("start"), e.get("end")
            when = f"{start or '?'} → {end or 'present'}"
            st.markdown(f"**{title}**{' at ' + company if company else ''}  \n*{when}*")
            if e.get("summary"):
                st.caption(e["summary"])

    edu = profile.get("education") or []
    if edu:
        st.markdown("### Education")
        for ed in edu:
            inst = ed.get("institution", "")
            degree = ed.get("degree", "")
            field = ed.get("field", "")
            end_year = ed.get("end_year", "")
            line = " — ".join(x for x in [degree, field] if x)
            st.markdown(f"**{inst}**  \n{line} ({end_year})" if line else f"**{inst}** ({end_year})")

    prov = profile.get("provenance") or []
    if prov:
        with st.expander(f"Provenance — where each field came from ({len(prov)} entries)"):
            st.dataframe(prov, use_container_width=True, hide_index=True)

    warns = profile.get("warnings") or []
    if warns:
        with st.expander(f"⚠️ Warnings ({len(warns)})"):
            for w in warns:
                level = w.get("level", "warning")
                msg = w.get("message", "")
                (st.error if level == "error" else st.warning)(msg)


# ────────────────────────────── sidebar (inputs) ──────────────────────────────

st.sidebar.title("🧩 Inputs")
st.sidebar.caption("Provide at least one structured source (CSV) and one unstructured source (notes / resume / GitHub).")

csv_file = st.sidebar.file_uploader("Recruiter CSV", type=["csv"])
notes_file = st.sidebar.file_uploader("Recruiter notes (.txt)", type=["txt"])
resume_file = st.sidebar.file_uploader("Resume (.pdf)", type=["pdf"])
github_url = st.sidebar.text_input("GitHub profile URL", placeholder="https://github.com/username")

st.sidebar.divider()
st.sidebar.subheader("Output shape")
config_mode = st.sidebar.radio(
    "Schema",
    ["Default canonical schema", "Custom config file", "Paste custom config JSON"],
    index=0,
)

config_path = None
pasted_config_text = None

if config_mode == "Custom config file":
    config_upload = st.sidebar.file_uploader("Config JSON", type=["json"], key="config_upload")
    config_path = save_upload(config_upload, ".json")
elif config_mode == "Paste custom config JSON":
    default_text = (
        DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
        if DEFAULT_CONFIG_PATH.exists()
        else '{\n  "fields": [\n    { "path": "full_name", "type": "string", "required": true }\n  ],\n  "include_confidence": true,\n  "include_provenance": false,\n  "on_missing": "null"\n}'
    )
    pasted_config_text = st.sidebar.text_area("Config JSON", value=default_text, height=220)

run_clicked = st.sidebar.button("▶ Run pipeline", type="primary", use_container_width=True)

st.title("Multi-Source Candidate Data Transformer")
st.caption("Messy multi-source candidate inputs → one canonical, schema-valid profile with provenance and confidence.")

if "result" not in st.session_state:
    st.session_state.result = None

if run_clicked:
    if not csv_file and not notes_file and not resume_file and not github_url:
        st.error("Provide at least one source before running.")
    else:
        try:
            csv_path = save_upload(csv_file, ".csv")
            notes_path = save_upload(notes_file, ".txt")
            resume_path = save_upload(resume_file, ".pdf")

            effective_config_path = config_path
            if config_mode == "Paste custom config JSON" and pasted_config_text:
                json.loads(pasted_config_text)  # validate early, raises on bad JSON
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8")
                tmp.write(pasted_config_text)
                tmp.close()
                effective_config_path = tmp.name

            with st.spinner("Extracting, normalizing, merging, projecting…"):
                output = run_pipeline(
                    csv_path=csv_path,
                    notes_path=notes_path,
                    config_path=effective_config_path,
                    github_url=github_url or None,
                    resume_path=resume_path,
                )
            Path("outputs").mkdir(exist_ok=True)

            with open("outputs/latest_output.json", "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)

            st.session_state.result = output
            st.success("Done.")
        except json.JSONDecodeError as e:
            st.error(f"Config JSON is invalid: {e}")
        except Exception as e:
            st.error(f"Pipeline failed: {e}")

result = st.session_state.result

if result is None:
    st.info("Add your sources in the sidebar and click **Run pipeline**.")
else:
    tab_card, tab_json = st.tabs(["📇 Profile card", "🧾 Raw JSON"])

    with tab_card:
        if "candidate_id" in result and "full_name" in result:
            render_profile_card(result)
        else:
            # Custom projected schema — field set is user-defined, so show as a clean table instead.
            st.markdown("### Projected output")
            st.caption("This is a custom config projection, not the default canonical schema, so it's shown as key/value pairs.")
            for k, v in result.items():
                st.markdown(f"**{k}**")
                st.write(v)

    with tab_json:
        st.json(result)
        st.download_button(
            "Download JSON",
            data=json.dumps(result, indent=2),
            file_name="candidate_profile.json",
            mime="application/json",
        )