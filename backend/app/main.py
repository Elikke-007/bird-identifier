from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schemas import IdentifyRequest, IdentifyResponse
from .service import BirdRecognitionService, CLASSIFICATION_MODEL_ID, DETECTION_MODEL_ID

app = FastAPI(title="Bird Recognition API", version="0.1.0")
service = BirdRecognitionService()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "detection_model": DETECTION_MODEL_ID,
        "classification_model": CLASSIFICATION_MODEL_ID,
    }


@app.post("/identify", response_model=IdentifyResponse)
def identify(request: IdentifyRequest) -> IdentifyResponse:
    try:
        return service.identify(request)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(error)) from error
