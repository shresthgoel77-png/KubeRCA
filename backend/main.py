import os
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from model_runner import ModelRunner

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("kuberca")

from schemas import DiagnoseRequest, DiagnosisResponse, HealthResponse

# ---------------------------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------------------------
CORS_ORIGINS: List[str] = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    ).split(",")
    if origin.strip()
]

# ---------------------------------------------------------------------------
# Application lifespan – load model once
# ---------------------------------------------------------------------------
runner: ModelRunner | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global runner
    logger.info("Starting up – loading KubeRCA model …")
    try:
        runner = ModelRunner()
        logger.info("Model loaded successfully.")
    except Exception:
        logger.exception("Failed to load model.")
        runner = None
    yield
    logger.info("Shutting down.")
    runner = None


app = FastAPI(
    title="KubeRCA API",
    description="Kubernetes Root-Cause Analysis inference API",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handler – never leak stack traces
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def _unhandled_exception_handler(_request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok" if runner is not None else "unavailable",
        model_loaded=runner is not None,
        device=runner.device if runner else "n/a",
    )


@app.post("/diagnose", response_model=DiagnosisResponse)
async def diagnose(body: DiagnoseRequest):
    if runner is None:
        raise HTTPException(status_code=503, detail="Model is not loaded.")

    request_id = uuid.uuid4().hex[:12]
    logger.info("[%s] /diagnose – %d chars of telemetry", request_id, len(body.telemetry))

    start = time.perf_counter()
    try:
        result = runner.generate(prompt=body.telemetry)
    except ValueError as e:
        logger.warning("[%s] Model output parsing failed: %s", request_id, e)
        raise HTTPException(
            status_code=502,
            detail="Model produced an unparseable response. Please retry.",
        )
    except Exception:
        logger.exception("[%s] Inference error", request_id)
        raise HTTPException(
            status_code=500,
            detail="Internal inference error.",
        )
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info("[%s] Inference completed in %.1f ms", request_id, elapsed_ms)

    return DiagnosisResponse(**result)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
