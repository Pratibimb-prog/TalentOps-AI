from typing import Dict

def generate_roadmap(data: Dict, time_available: int) -> Dict:
    """Generate a simple roadmap based on available time.

    For demonstration, we split the matched keywords into chunks that fit into the
    provided time (hours). Each hour gets a list of up to 5 keywords.
    """
    matched = data.get("matched_keywords", [])
    # If not present, compute overlap keywords
    if not matched:
        resume_kws = set(data.get("resume_keywords", []))
        jd_kws = set(data.get("job_description_keywords", []))
        matched = sorted(list(resume_kws.intersection(jd_kws)))
    # Distribute keywords across time_available hours
    per_hour = max(1, len(matched) // max(1, time_available))
    roadmap = {}
    for hour in range(1, time_available + 1):
        start = (hour - 1) * per_hour
        end = start + per_hour
        roadmap[f"hour_{hour}"] = matched[start:end]
    return roadmap
