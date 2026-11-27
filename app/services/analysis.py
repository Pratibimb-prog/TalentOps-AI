import hashlib
import io
import re
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

# ---------------------------------------------------------------------------
# Education extraction
# ---------------------------------------------------------------------------

# Common degree patterns (order matters — longer/more specific first)
_DEGREE_PATTERNS = [
    r"(?:Doctor(?:ate)?|Ph\.?D)\.?",
    r"(?:Master(?:'?s)?|M\.?S\.?|M\.?A\.?|M\.?Tech\.?|M\.?B\.?A\.?|M\.?C\.?A\.?|M\.?E\.?)",
    r"(?:Bachelor(?:'?s)?|B\.?S\.?|B\.?A\.?|B\.?Tech\.?|B\.?E\.?|B\.?B\.?A\.?|B\.?C\.?A\.?|B\.?Sc\.?)",
    r"(?:Associate(?:'?s)?)",
    r"(?:Diploma)",
    r"(?:High\s*School|HSC|SSC|12th|10th|10\+2)",
]

_DEGREE_RE = re.compile(
    r"(?i)\b(" + "|".join(_DEGREE_PATTERNS) + r")"
    r"(?:\s+(?:of|in|–|-|—)\s+)?"
    r"([\w\s,/&]{0,80}?)?"         # optional field of study
    r"(?:\s*(?:from|at|,|–|-|—)\s*)?"
    r"([\w\s.,'&]{0,80}?)?"        # optional institution
    r"(?:\s*[\(,]?\s*(\d{4}))?",    # optional year
)

def extract_education(text: str) -> List[Dict[str, str]]:
    """Return a list of education entries found in the text."""
    entries: List[Dict[str, str]] = []
    seen: set = set()
    for m in _DEGREE_RE.finditer(text):
        degree = m.group(1).strip() if m.group(1) else ""
        field = (m.group(2) or "").strip().rstrip(" ,–-—fromatin")
        institution = (m.group(3) or "").strip().rstrip(" ,–-—")
        year = (m.group(4) or "").strip()
        key = degree.lower()
        if key and key not in seen:
            seen.add(key)
            entry: Dict[str, str] = {"degree": degree}
            if field:
                entry["field"] = field
            if institution:
                entry["institution"] = institution
            if year:
                entry["year"] = year
            entries.append(entry)
    return entries

# ---------------------------------------------------------------------------
# Location extraction
# ---------------------------------------------------------------------------

# Major Indian cities / metros + common international cities
_KNOWN_CITIES = [
    "Ahmedabad", "Bangalore", "Bengaluru", "Bhopal", "Chandigarh",
    "Chennai", "Coimbatore", "Delhi", "Faridabad", "Ghaziabad",
    "Gurgaon", "Gurugram", "Hyderabad", "Indore", "Jaipur",
    "Kanpur", "Kochi", "Kolkata", "Lucknow", "Mumbai", "Nagpur",
    "Nashik", "Navi Mumbai", "Noida", "Patna", "Pune", "Surat",
    "Thane", "Thiruvananthapuram", "Vadodara", "Visakhapatnam",
    # international
    "New York", "San Francisco", "London", "Dubai", "Singapore",
    "Toronto", "Sydney", "Berlin", "Tokyo", "Remote",
]
_CITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _KNOWN_CITIES) + r")\b",
    re.IGNORECASE,
)

# Patterns like "Location: XYZ" or "City: XYZ" or "Address: XYZ"
_LOCATION_LABEL_RE = re.compile(
    r"(?i)(?:location|city|address|based\s+(?:in|out\s+of))\s*[:–—-]\s*(.+)",
)

def extract_location(text: str) -> str:
    """Best-effort location string from resume text."""
    # Try labelled lines first
    m = _LOCATION_LABEL_RE.search(text)
    if m:
        # Take up to the first newline / pipe / bullet
        loc = re.split(r"[|\n•●]", m.group(1))[0].strip().rstrip(" ,;.")
        if loc:
            return loc
    # Fall back to known-city matching
    cities = list(dict.fromkeys(c.group(1).title() for c in _CITY_RE.finditer(text)))
    return ", ".join(cities) if cities else ""

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
            "education": extract_education(resume_text),
            "location": extract_location(resume_text),
        }
        cached_results[analysis_id] = payload
        results.append((analysis_id, payload))

    return results

def invalidate_cache(analysis_id: str) -> None:
    """Remove a cached analysis – used when documents change."""
    cached_results.pop(analysis_id, None)
