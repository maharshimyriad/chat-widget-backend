from __future__ import annotations

import vertexai
from functools import lru_cache
from typing import Any, AsyncIterator

from vertexai import agent_engines

from app.config import LOCATION, PROJECT_ID

vertexai.init(project=PROJECT_ID, location=LOCATION)


@lru_cache(maxsize=8)
def get_remote_app(resource_name: str):
    return agent_engines.get(resource_name)


async def stream_agent_query(
    remote_app: Any,
    query: str,
    scoped_user_id: str,
    session_id: str,
) -> AsyncIterator[Any]:
    async for chunk in remote_app.async_stream_query(
        message=query,
        user_id=scoped_user_id,
        session_id=session_id,
        run_config={"streaming_mode": "sse"},
    ):
        yield chunk
