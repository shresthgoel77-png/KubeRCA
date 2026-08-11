import os
from pydantic import BaseModel

class Settings(BaseModel):
    # Model Configuration
    BASE_MODEL: str = os.getenv("BASE_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    ADAPTER_MODEL: str = os.getenv("ADAPTER_MODEL", "Devsg17/kuberca-qwen-stage1")

    # Server Configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

settings = Settings()
