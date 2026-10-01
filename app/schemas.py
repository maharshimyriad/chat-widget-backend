from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=256)
    environment: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=10000)
    profile: dict[str, str] = Field(default_factory=dict)


class SessionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=256)
    environment: str = Field(min_length=1, max_length=64)
    profile: dict[str, str] = Field(default_factory=dict)
