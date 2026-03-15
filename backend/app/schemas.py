from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BirdSex = Literal["雄", "雌", "未知"]


class IdentifyRequest(BaseModel):
    image_path: str = Field(..., alias="imagePath")
    top_k: int = Field(5, alias="topK", ge=1, le=10)

    model_config = {"populate_by_name": True}


class DetectionBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float


class IdentifyResponse(BaseModel):
    species: str
    species_original: str = Field(..., alias="speciesOriginal")
    sex: BirdSex
    confidence: float
    species_confidence: float = Field(..., alias="speciesConfidence")
    sex_confidence: float = Field(..., alias="sexConfidence")
    reason: str
    sex_reason: str = Field(..., alias="sexReason")
    top_species: list[str] = Field(..., alias="topSpecies")
    top_species_original: list[str] = Field(..., alias="topSpeciesOriginal")
    detection_count: int = Field(..., alias="detectionCount")
    detection_box: DetectionBox | None = Field(None, alias="detectionBox")

    model_config = {"populate_by_name": True}
