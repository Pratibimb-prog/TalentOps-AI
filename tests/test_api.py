import asyncio
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.main import app as fastapi_app

# Helper to create in‑memory text files
def _make_file(content: str, filename: str = "file.txt"):
    return (filename, content.encode(), "text/plain")

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
async def client():
    async with AsyncClient(app=fastapi_app, base_url="http://testserver") as ac:
        yield ac

@pytest.mark.anyio
async def test_same_documents_produce_same_analysis_id(client: AsyncClient):
    resume = _make_file("John Doe experience in python data science")
    jd = _make_file("Looking for python data science expertise")
    files = {"resume": resume, "job_description": jd}
    resp1 = await client.post("/upload", files=files)
    assert resp1.status_code == 200
    data1 = resp1.json()
    resp2 = await client.post("/upload", files=files)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data1["analysis_id"] == data2["analysis_id"]

@pytest.mark.anyio
async def test_score_is_computed_from_data(client: AsyncClient):
    resume = _make_file("skillA skillB skillC")
    jd = _make_file("skillB skillC skillD")
    files = {"resume": resume, "job_description": jd}
    upload = await client.post("/upload", files=files)
    analysis_id = upload.json()["analysis_id"]
    score_resp = await client.post("/score", json={"analysis_id": analysis_id})
    assert score_resp.status_code == 200
    payload = score_resp.json()
    # Overlap: skillB, skillC => 2 / 3 jd keywords = 0.666..., score ~ 6.67
    assert payload["score"] == pytest.approx(6.67, rel=1e-2)

@pytest.mark.anyio
async def test_changing_document_invalidates_cache(client: AsyncClient):
    # First upload
    r1 = _make_file("A B C")
    jd1 = _make_file("X Y Z")
    upload1 = await client.post("/upload", files={"resume": r1, "job_description": jd1})
    id1 = upload1.json()["analysis_id"]
    # Change resume only
    r2 = _make_file("A B D")
    upload2 = await client.post("/upload", files={"resume": r2, "job_description": jd1})
    id2 = upload2.json()["analysis_id"]
    assert id1 != id2
    # Ensure old id is no longer reachable
    resp_old = await client.get(f"/analysis/{id1}")
    assert resp_old.status_code == 404

@pytest.mark.anyio
async def test_roadmap_time_type(client: AsyncClient):
    resume = _make_file("python java")
    jd = _make_file("python")
    upload = await client.post("/upload", files={"resume": resume, "job_description": jd})
    analysis_id = upload.json()["analysis_id"]
    roadmap_resp = await client.post("/roadmap", json={"analysis_id": analysis_id, "time_available": 3})
    assert roadmap_resp.status_code == 200
    data = roadmap_resp.json()
    # Should contain exactly three hour keys
    assert len(data["roadmap"]) == 3
    for hour_key in data["roadmap"]:
        assert hour_key.startswith("hour_")

@pytest.mark.anyio
async def test_invalid_json_returns_clear_error(client: AsyncClient):
    # Missing required field "analysis_id"
    resp = await client.post("/score", json={})
    assert resp.status_code == 422  # FastAPI validation error – clear JSON error
    # Send malformed JSON (handled by client library as exception)
    # Instead, call endpoint with wrong content type
    resp2 = await client.post("/score", data="not a json")
    assert resp2.status_code == 422
