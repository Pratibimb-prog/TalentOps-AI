import io
import json

import pytest
import httpx
from docx import Document
from pypdf import PdfWriter

from app.main import app as fastapi_app
from app.services.analysis import cached_results

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file(content: str, filename: str = "file.txt"):
    return (filename, content.encode(), "text/plain")

def _make_docx_file(text: str, filename: str = "doc.docx"):
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return (filename, buf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

def _upload_files(resume_tuples, jd_tuple):
    """Build multipart file list. resume_tuples can be a single tuple or a list."""
    if not isinstance(resume_tuples, list):
        resume_tuples = [resume_tuples]
    files = [("resume", r) for r in resume_tuples]
    files.append(("job_description", jd_tuple))
    return files

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_cache():
    cached_results.clear()
    yield
    cached_results.clear()

@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

# ---------------------------------------------------------------------------
# Tests — single resume (backward-compat behaviour)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_resume_upload(client: httpx.AsyncClient):
    resume = _make_file("John Doe experience in python data science")
    jd = _make_file("Looking for python data science expertise")
    resp = await client.post("/upload", files=_upload_files(resume, jd))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["analyses"]) == 1
    assert body["analyses"][0]["analysis_id"]

@pytest.mark.asyncio
async def test_same_documents_produce_same_analysis_id(client: httpx.AsyncClient):
    resume = _make_file("John Doe experience in python data science")
    jd = _make_file("Looking for python data science expertise")
    files = _upload_files(resume, jd)
    resp1 = await client.post("/upload", files=files)
    resp2 = await client.post("/upload", files=files)
    id1 = resp1.json()["analyses"][0]["analysis_id"]
    id2 = resp2.json()["analyses"][0]["analysis_id"]
    assert id1 == id2

@pytest.mark.asyncio
async def test_score_single_candidate(client: httpx.AsyncClient):
    resume = _make_file("skillA skillB skillC")
    jd = _make_file("skillB skillC skillD")
    upload = await client.post("/upload", files=_upload_files(resume, jd))
    aid = upload.json()["analyses"][0]["analysis_id"]
    score_resp = await client.post("/score", json={"analysis_id": aid})
    assert score_resp.status_code == 200
    # Overlap: skillB, skillC => 2/3 jd keywords => score ~ 6.67
    assert score_resp.json()["score"] == pytest.approx(6.67, rel=1e-2)

@pytest.mark.asyncio
async def test_changing_document_invalidates_cache(client: httpx.AsyncClient):
    r1 = _make_file("A B C")
    jd = _make_file("X Y Z")
    id1 = (await client.post("/upload", files=_upload_files(r1, jd))).json()["analyses"][0]["analysis_id"]
    r2 = _make_file("A B D")
    id2 = (await client.post("/upload", files=_upload_files(r2, jd))).json()["analyses"][0]["analysis_id"]
    assert id1 != id2
    assert (await client.get(f"/analysis/{id1}")).status_code == 404

@pytest.mark.asyncio
async def test_roadmap_time_type(client: httpx.AsyncClient):
    resume = _make_file("python java")
    jd = _make_file("python")
    upload = await client.post("/upload", files=_upload_files(resume, jd))
    aid = upload.json()["analyses"][0]["analysis_id"]
    roadmap_resp = await client.post("/roadmap", json={"analysis_id": aid, "time_available": 3})
    assert roadmap_resp.status_code == 200
    data = roadmap_resp.json()
    assert len(data["roadmap"]) == 3
    for key in data["roadmap"]:
        assert key.startswith("hour_")

@pytest.mark.asyncio
async def test_invalid_json_returns_clear_error(client: httpx.AsyncClient):
    resp = await client.post("/score", json={})
    assert resp.status_code == 422
    resp2 = await client.post("/score", data="not a json")
    assert resp2.status_code == 422

@pytest.mark.asyncio
async def test_docx_upload(client: httpx.AsyncClient):
    resume = _make_docx_file("experienced python fast developer", filename="resume.docx")
    jd = _make_file("seeking python developer", filename="jd.txt")
    resp = await client.post("/upload", files=_upload_files(resume, jd))
    assert resp.status_code == 200
    data = resp.json()["analyses"][0]["data"]
    assert "python" in data["resume_keywords"]
    assert "developer" in data["resume_keywords"]

# ---------------------------------------------------------------------------
# Tests — multiple resumes (per-candidate scoring)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_resumes_return_separate_analyses(client: httpx.AsyncClient):
    r1 = _make_file("python django flask", filename="alice.txt")
    r2 = _make_file("javascript react nextjs", filename="bob.txt")
    jd = _make_file("looking for python react developer", filename="jd.txt")
    resp = await client.post("/upload", files=_upload_files([r1, r2], jd))
    assert resp.status_code == 200
    analyses = resp.json()["analyses"]
    assert len(analyses) == 2
    # Each candidate has their own analysis_id
    assert analyses[0]["analysis_id"] != analyses[1]["analysis_id"]
    # Candidate names come from filenames
    assert analyses[0]["candidate"] == "alice.txt"
    assert analyses[1]["candidate"] == "bob.txt"
    # Keywords are NOT merged — each candidate has only their own
    assert "python" in analyses[0]["data"]["resume_keywords"]
    assert "python" not in analyses[1]["data"]["resume_keywords"]
    assert "react" in analyses[1]["data"]["resume_keywords"]

@pytest.mark.asyncio
async def test_score_all_candidates(client: httpx.AsyncClient):
    r1 = _make_file("python django")       # matches 1 of 3 jd kw
    r2 = _make_file("python react angular") # matches 3 of 3 jd kw
    jd = _make_file("python react angular")
    upload = await client.post("/upload", files=_upload_files([r1, r2], jd))
    analyses = upload.json()["analyses"]
    ids = [a["analysis_id"] for a in analyses]
    score_resp = await client.post("/score-all", json={"analysis_ids": ids})
    assert score_resp.status_code == 200
    scores = score_resp.json()["scores"]
    assert len(scores) == 2
    # Second candidate should score higher (perfect match)
    assert scores[1]["score"] > scores[0]["score"]
    assert scores[1]["score"] == pytest.approx(10.0, rel=1e-2)

@pytest.mark.asyncio
async def test_individual_score_after_multi_upload(client: httpx.AsyncClient):
    """Each candidate can be scored individually via /score."""
    r1 = _make_file("skillA skillB skillC")
    r2 = _make_file("skillX skillY skillZ")
    jd = _make_file("skillB skillC skillD")
    upload = await client.post("/upload", files=_upload_files([r1, r2], jd))
    analyses = upload.json()["analyses"]
    # Score candidate 1 — overlap: skillB, skillC => 2/3 => 6.67
    s1 = await client.post("/score", json={"analysis_id": analyses[0]["analysis_id"]})
    assert s1.json()["score"] == pytest.approx(6.67, rel=1e-2)
    # Score candidate 2 — overlap: none => 0
    s2 = await client.post("/score", json={"analysis_id": analyses[1]["analysis_id"]})
    assert s2.json()["score"] == pytest.approx(0.0)
