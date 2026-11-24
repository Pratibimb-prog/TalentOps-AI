import streamlit as st
import httpx
import json

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="TalentOps-AI", layout="wide")

st.title("TalentOps-AI")

resume_file = st.file_uploader("Upload Resume (txt)", type=["txt"])
job_file = st.file_uploader("Upload Job Description (txt)", type=["txt"])

if st.button("Analyze"):
    if not resume_file or not job_file:
        st.error("Both files must be uploaded.")
    else:
        files = {
            "resume": (resume_file.name, resume_file.read(), "text/plain"),
            "job_description": (job_file.name, job_file.read(), "text/plain"),
        }
        try:
            resp = httpx.post(f"{API_URL}/upload", files=files, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            analysis_id = data["analysis_id"]
            st.session_state.analysis_id = analysis_id
            st.success("Analysis completed")
            st.json(data["data"])
        except httpx.HTTPError as e:
            st.error(f"Upload failed: {e}")

if "analysis_id" in st.session_state:
    if st.button("Score"):
        try:
            resp = httpx.post(f"{API_URL}/score", json={"analysis_id": st.session_state.analysis_id})
            resp.raise_for_status()
            st.json(resp.json())
        except httpx.HTTPError as e:
            st.error(f"Score request failed: {e}")
    # Time input in days (converted to hours for the backend)
    time_days = st.number_input("Time Available (days)", min_value=1, max_value=30, value=1)
    if st.button("Generate Roadmap"):
        try:
            # Convert days to total hours for API
            time_hours = int(time_days) * 24
            resp = httpx.post(
                f"{API_URL}/roadmap",
                json={"analysis_id": st.session_state.analysis_id, "time_available": time_hours},
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
