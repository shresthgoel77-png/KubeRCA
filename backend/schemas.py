from typing import List, Literal
from pydantic import BaseModel, Field

MAX_TELEMETRY_CHARS = 10_000

class DiagnoseRequest(BaseModel):
    telemetry: str = Field(
        ...,
        description="Raw Kubernetes telemetry text to diagnose",
        min_length=1,
        max_length=MAX_TELEMETRY_CHARS,
    )

    @classmethod
    def telemetry_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("telemetry must not be empty or whitespace-only")
        return v

class DiagnosisResponse(BaseModel):
    failure: str
    root_cause: str
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    evidence: List[str]
    severity: Literal["SEV-1", "SEV-2", "SEV-3"]

class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    device: str

