import hashlib
import logging
import os
from typing import Optional

from app.config import PROJECT_ID, REDIS_URL

logger = logging.getLogger(__name__)
SESSIONS: dict[tuple[str, str], str] = {}
_redis_client = None

if not REDIS_URL:
    logger.warning("REDIS_URL is unset; session IDs will be stored in process memory")


def session_storage_key(session_key: tuple[str, str]) -> str:
    user_id, environment = session_key
    user_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return f"chat-widget:{PROJECT_ID}:session:{environment}:{user_hash}"


def get_redis_client():
    global _redis_client
    if not REDIS_URL:
        return None
    if _redis_client is None:
        from redis.asyncio import Redis

        _redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


async def load_session_id(session_key: tuple[str, str]) -> Optional[str]:
    redis_client = get_redis_client()
    if redis_client:
        return await redis_client.get(session_storage_key(session_key))
    return SESSIONS.get(session_key)


async def store_session_id(session_key: tuple[str, str], session_id: str) -> None:
    redis_client = get_redis_client()
    if redis_client:
        await redis_client.set(session_storage_key(session_key), session_id)
    else:
        SESSIONS[session_key] = session_id


async def remove_session_id(session_key: tuple[str, str]) -> None:
    redis_client = get_redis_client()
    if redis_client:
        await redis_client.delete(session_storage_key(session_key))
    else:
        SESSIONS.pop(session_key, None)
