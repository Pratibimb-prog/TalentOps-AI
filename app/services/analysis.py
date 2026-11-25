import hashlib
import io
from pathlib import Path
from typing import List, Tuple, Dict
from fastapi import UploadFile
from pypdf import PdfReader
from docx import Document

# Simple in‑memory cache for analysis results
cached_results: Dict[str, Dict] = {}

def _hash_content(content: bytes) -> str:
    """Return a short deterministic hash for the given bytes."""
    return hashlib.sha256(content).hexdigest()[:12]

async def _read_file(file: UploadFile) -> bytes:
    return await file.read()

def extract_text_from_bytes(content: bytes, filename: str = "") -> str:
    """Extract plain text from txt, pdf, or docx bytes."""
    ext = Path(filename).suffix.lower() if filename else ""

    if ext == ".pdf" or content.startswith(b"%PDF"):
        try:
            reader = PdfReader(io.BytesIO(content))
            pages_text = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages_text)
        except Exception:
            return content.decode(errors="ignore")

    if ext in [".docx", ".doc"]:
        try:
            doc = Document(io.BytesIO(content))
            return "\n".join([p.text for p in doc.paragraphs if p.text])
        except Exception:
            return content.decode(errors="ignore")

    # Default to text decoding (txt, etc.)
    return content.decode(errors="ignore")

async def get_analysis(resumes: List[UploadFile], job_description: UploadFile) -> List[Tuple[str, Dict]]:
    """Analyse each resume independently against a single job description.

    Returns a list of (analysis_id, payload) tuples — one per resume.
    Each analysis is cached separately so it can be scored / roadmapped on its own.
    """
    jd_content = await _read_file(job_description)
    jd_text = extract_text_from_bytes(jd_content, getattr(job_description, "filename", "") or "")

    def extract_keywords(text: str):
        return sorted({tok.lower() for tok in text.split() if len(tok) > 3})

    jd_keywords = extract_keywords(jd_text)

    # Invalidate previous analyses so only the latest batch is active
    cached_results.clear()

    results: List[Tuple[str, Dict]] = []
    for resume in resumes:
        resume_content = await _read_file(resume)
        resume_filename = getattr(resume, "filename", "") or ""
        resume_text = extract_text_from_bytes(resume_content, resume_filename)

        combined = resume_content + b"||" + jd_content
        analysis_id = _hash_content(combined)

        payload = {
            "candidate": resume_filename,
            "resume_text": resume_text,
            "job_description_text": jd_text,
            "resume_keywords": extract_keywords(resume_text),
            "job_description_keywords": jd_keywords,
        }
        cached_results[analysis_id] = payload
        results.append((analysis_id, payload))

    return results

def invalidate_cache(analysis_id: str) -> None:
    """Remove a cached analysis – used when documents change."""
    cached_results.pop(analysis_id, None)
