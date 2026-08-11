from pydantic import BaseModel, Field

class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="The prompt to send to the model")
    max_new_tokens: int = Field(default=512, description="Maximum number of new tokens to generate")
    temperature: float = Field(default=0.7, description="Sampling temperature")
    top_p: float = Field(default=0.9, description="Nucleus sampling threshold")

class GenerateResponse(BaseModel):
    response: str
