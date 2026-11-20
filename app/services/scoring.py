from typing import Dict, Tuple

def calculate_score(data: Dict) -> Tuple[float, Dict]:
    """Calculate a simple matching score.

    The score is based on the overlap between resume keywords and job description keywords.
    It returns a float between 0 and 10 (higher is better) and a details dict.
    """
    resume_kws = set(data.get("resume_keywords", []))
    jd_kws = set(data.get("job_description_keywords", []))
    if not resume_kws or not jd_kws:
        overlap = 0
    else:
        overlap = len(resume_kws.intersection(jd_kws)) / len(jd_kws)
    score = round(overlap * 10, 2)
    details = {
        "resume_keyword_count": len(resume_kws),
        "job_description_keyword_count": len(jd_kws),
        "matched_keywords": sorted(list(resume_kws.intersection(jd_kws)))
    }
    return score, details
