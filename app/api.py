from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any

from .services.analysis import get_analysis, invalidate_cache, cached_results
from .services.scoring import calculate_score
from .services.roadmap import generate_roadmap

router = APIRouter()

class AnalysisResponse(BaseModel):
    analysis_id: str = Field(..., description="Identifier for the analysis result")
    data: Dict[str, Any]

class ScoreRequest(BaseModel):
    analysis_id: str

class ScoreResponse(BaseModel):
    score: float
    details: Dict[str, Any]

class RoadmapRequest(BaseModel):
    analysis_id: str
    time_available: int = Field(..., description="Time available in hours")

class RoadmapResponse(BaseModel):
    roadmap: Dict[str, Any]

@router.post("/upload", response_model=AnalysisResponse)
async def upload_documents(resume: UploadFile = File(...), job_description: UploadFile = File(...)):
    try:
        analysis_id, data = await get_analysis(resume, job_description)
        return AnalysisResponse(analysis_id=analysis_id, data=data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/analysis/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis_endpoint(analysis_id: str):
    data = cached_results.get(analysis_id)
    if not data:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return AnalysisResponse(analysis_id=analysis_id, data=data)

@router.post("/score", response_model=ScoreResponse)
async def score_analysis(request: ScoreRequest):
    data = cached_results.get(request.analysis_id)
    if not data:
        raise HTTPException(status_code=404, detail="Analysis not found")
    score, details = calculate_score(data)
    return ScoreResponse(score=score, details=details)

@router.post("/roadmap", response_model=RoadmapResponse)
async def roadmap(request: RoadmapRequest):
    data = cached_results.get(request.analysis_id)
    if not data:
        raise HTTPException(status_code=404, detail="Analysis not found")
    roadmap = generate_roadmap(data, request.time_available)
    return RoadmapResponse(roadmap=roadmap)
