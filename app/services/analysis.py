import hashlib
from typing import Tuple, Dict
from fastapi import UploadFile

# Simple in‑memory cache for analysis results
cached_results: Dict[str, Dict] = {}

def _hash_content(content: bytes) -> str:
    """Return a short deterministic hash for the given bytes."""
    return hashlib.sha256(content).hexdigest()[:12]

async def _read_file(file: UploadFile) -> bytes:
    return await file.read()

async def get_analysis(resume: UploadFile, job_description: UploadFile) -> Tuple[str, Dict]:
    """Read the two uploaded files, compute a deterministic analysis ID, and store a simple analysis payload.

    The payload includes the raw text of both documents and a list of extracted keywords (naïve split).
    """
    resume_content = await _read_file(resume)
    jd_content = await _read_file(job_description)

    # Create a deterministic ID based on both contents (order independent)
    combined = resume_content + b"||" + jd_content
    analysis_id = _hash_content(combined)

    # Very simple keyword extraction – split on whitespace and keep unique lower‑cased tokens longer than 3 chars
    def extract_keywords(text: str):
        return sorted({tok.lower() for tok in text.split() if len(tok) > 3})

    payload = {
        "resume_text": resume_content.decode(errors="ignore"),
        "job_description_text": jd_content.decode(errors="ignore"),
        "resume_keywords": extract_keywords(resume_content.decode(errors="ignore")),
        "job_description_keywords": extract_keywords(jd_content.decode(errors="ignore")),
    }

    # Invalidate any previous analysis so only the latest upload is active
    cached_results.clear()
    cached_results[analysis_id] = payload
    return analysis_id, payload

def invalidate_cache(analysis_id: str) -> None:
    """Remove a cached analysis – used when documents change."""
    cached_results.pop(analysis_id, None)
