import streamlit as st
import httpx
import json

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="TalentOps-AI", layout="wide")

st.title("TalentOps-AI")

resume_files = st.file_uploader(
    "Upload Resume(s) (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"], accept_multiple_files=True
)
job_file = st.file_uploader("Upload Job Description (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"])

if st.button("Analyze"):
    if not resume_files or not job_file:
        st.error("At least one resume and a job description must be uploaded.")
    else:
        job_type = job_file.type or "application/octet-stream"
        files = []
        for rf in resume_files:
            rt = rf.type or "application/octet-stream"
            files.append(("resume", (rf.name, rf.read(), rt)))
        files.append(("job_description", (job_file.name, job_file.read(), job_type)))
        try:
            resp = httpx.post(f"{API_URL}/upload", files=files, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            analyses = data["analyses"]
            st.session_state.analyses = analyses
            st.success(f"Analysed {len(analyses)} candidate(s)")
            for a in analyses:
                with st.expander(f"📄 {a['candidate'] or a['analysis_id']}"):
                    st.json(a["data"])
        except httpx.HTTPError as e:
            st.error(f"Upload failed: {e}")

if "analyses" in st.session_state:
    analyses = st.session_state.analyses

    if st.button("Score All Candidates"):
        try:
            ids = [a["analysis_id"] for a in analyses]
            resp = httpx.post(f"{API_URL}/score-all", json={"analysis_ids": ids}, timeout=30.0)
            resp.raise_for_status()
            scores = resp.json()["scores"]
            # Sort by score descending
            scores.sort(key=lambda s: s["score"], reverse=True)
            st.subheader("🏆 Candidate Rankings")
            for rank, s in enumerate(scores, 1):
                label = s.get("candidate") or s["analysis_id"]
                st.markdown(f"**{rank}. {label}** — Score: **{s['score']}** / 10")
                with st.expander("Details"):
                    st.json(s["details"])
            st.session_state.scores = scores
        except httpx.HTTPError as e:
            st.error(f"Score request failed: {e}")

    # --- Per-candidate roadmap ---
    candidate_options = {
        (a.get("candidate") or a["analysis_id"]): a["analysis_id"] for a in analyses
    }
    selected_candidate = st.selectbox("Select candidate for roadmap", list(candidate_options.keys()))
    time_days = st.number_input("Time Available (days)", min_value=1, max_value=30, value=1)
    if st.button("Generate Roadmap"):
        try:
            time_hours = int(time_days) * 24
            analysis_id = candidate_options[selected_candidate]
            resp = httpx.post(
                f"{API_URL}/roadmap",
                json={"analysis_id": analysis_id, "time_available": time_hours},
            )
            resp.raise_for_status()
            roadmap = resp.json().get("roadmap")
            # Generate a friendly summary via Ollama
            ollama_resp = httpx.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3",
                    "prompt": f"Summarize the following CV‑Guru roadmap in plain English. Provide a short paragraph per day. Roadmap data: {json.dumps(roadmap)}",
                },
                timeout=60,
            )
            ollama_resp.raise_for_status()
            summary = ollama_resp.json().get("response", "(no summary returned)")
            st.write(summary)
        except httpx.HTTPError as e:
            st.error(f"Roadmap request failed: {e}")
