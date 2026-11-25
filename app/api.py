from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, List

from .services.analysis import get_analysis, invalidate_cache, cached_results
from .services.scoring import calculate_score
from .services.roadmap import generate_roadmap

router = APIRouter()

class CandidateAnalysis(BaseModel):
    analysis_id: str = Field(..., description="Identifier for this candidate's analysis")
    candidate: str = Field("", description="Original resume filename")
    data: Dict[str, Any]

class AnalysisResponse(BaseModel):
    """Returned by /upload — one entry per uploaded resume."""
    analyses: List[CandidateAnalysis]

class SingleAnalysisResponse(BaseModel):
    analysis_id: str = Field(..., description="Identifier for the analysis result")
    data: Dict[str, Any]

class ScoreRequest(BaseModel):
    analysis_id: str

class ScoreResponse(BaseModel):
    score: float
    details: Dict[str, Any]

class ScoreAllRequest(BaseModel):
    analysis_ids: List[str]

class CandidateScore(BaseModel):
    analysis_id: str
    candidate: str = ""
    score: float
    details: Dict[str, Any]

class ScoreAllResponse(BaseModel):
    scores: List[CandidateScore]

class RoadmapRequest(BaseModel):
    analysis_id: str
    time_available: int = Field(..., description="Time available in hours")

class RoadmapResponse(BaseModel):
    roadmap: Dict[str, Any]

@router.post("/upload", response_model=AnalysisResponse)
async def upload_documents(resume: List[UploadFile] = File(...), job_description: UploadFile = File(...)):
    try:
        results = await get_analysis(resume, job_description)
        analyses = [
            CandidateAnalysis(
                analysis_id=aid,
                candidate=data.get("candidate", ""),
                data=data,
            )
            for aid, data in results
        ]
        return AnalysisResponse(analyses=analyses)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/analysis/{analysis_id}", response_model=SingleAnalysisResponse)
async def get_analysis_endpoint(analysis_id: str):
    data = cached_results.get(analysis_id)
    if not data:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return SingleAnalysisResponse(analysis_id=analysis_id, data=data)

@router.post("/score", response_model=ScoreResponse)
async def score_analysis(request: ScoreRequest):
    data = cached_results.get(request.analysis_id)
    if not data:
        raise HTTPException(status_code=404, detail="Analysis not found")
    score, details = calculate_score(data)
    return ScoreResponse(score=score, details=details)

@router.post("/score-all", response_model=ScoreAllResponse)
async def score_all(request: ScoreAllRequest):
    """Score every candidate in a single call."""
    scores = []
    for aid in request.analysis_ids:
        data = cached_results.get(aid)
        if not data:
            raise HTTPException(status_code=404, detail=f"Analysis {aid} not found")
        score, details = calculate_score(data)
        scores.append(CandidateScore(
            analysis_id=aid,
            candidate=data.get("candidate", ""),
            score=score,
            details=details,
        ))
    return ScoreAllResponse(scores=scores)

@router.post("/roadmap", response_model=RoadmapResponse)
async def roadmap(request: RoadmapRequest):
    data = cached_results.get(request.analysis_id)
    if not data:
        raise HTTPException(status_code=404, detail="Analysis not found")
    roadmap = generate_roadmap(data, request.time_available)
    return RoadmapResponse(roadmap=roadmap)
