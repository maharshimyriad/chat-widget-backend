from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=256)
    environment_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=10000)
    session_id: str | None = Field(default=None, min_length=1, max_length=256)
