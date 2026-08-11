from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
import uvicorn

from config import settings
from schemas import GenerateRequest, GenerateResponse
from model_runner import ModelRunner

runner = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global runner
    print("Starting up... loading model runner (this may take a while).")
    try:
        runner = ModelRunner()
    except Exception as e:
        print(f"Failed to load model: {e}")
        runner = None
    yield
    print("Shutting down... cleaning up.")
    runner = None

app = FastAPI(
    title="KubeRCA Minimal Backend",
    description="FastAPI backend for KubeRCA model inference",
    version="1.0.0",
    lifespan=lifespan
)

@app.post("/generate", response_model=GenerateResponse)
async def generate_response(request: GenerateRequest):
    if runner is None:
        raise HTTPException(
            status_code=503, 
            detail="Model is currently unavailable. It might be loading or failed to load."
        )
        
    try:
        response_text = runner.generate(
            prompt=request.prompt,
            max_new_tokens=request.max_new_tokens,
            temperature=request.temperature,
            top_p=request.top_p
        )
        return GenerateResponse(response=response_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {
        "status": "up",
        "model_loaded": runner is not None,
        "base_model": settings.BASE_MODEL,
        "adapter_model": settings.ADAPTER_MODEL
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=False)
